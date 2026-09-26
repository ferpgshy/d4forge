"""Um device de captura para o processo inteiro.

O dxcam só aceita UM device por saída de vídeo: pedir um segundo devolve o
MESMO objeto. Com o AutoSkill no ar a sessão toda e cada aba abrindo a sua
captura, o app ficava com cinco fachadas sobre um device só — e daí vinham
três defeitos que pareciam independentes: fechar numa aba matava a captura da
outra, dois `grab` concorrentes se atropelavam, e quem perdia quadro reagia
devagar ou decidia sobre uma tela velha.
"""

import threading

import pytest

from d4forge.capture import ScreenCapture, capturas_abertas
from d4forge.geometry import Rect


class _BackendFalso:
    """Conta grabs e fechamentos, sem tocar em vídeo."""

    name = "falso"

    def __init__(self):
        self.grabs = 0
        self.fechado = False
        self.simultaneos = 0
        self.pico = 0
        self._trava = threading.Lock()

    def grab(self, region):
        with self._trava:
            self.simultaneos += 1
            self.pico = max(self.pico, self.simultaneos)
        try:
            if self.fechado:
                raise RuntimeError("device ja liberado")
            self.grabs += 1
            return region
        finally:
            with self._trava:
                self.simultaneos -= 1

    def close(self):
        self.fechado = True


@pytest.fixture
def backend(monkeypatch):
    from d4forge import capture

    falso = _BackendFalso()
    monkeypatch.setattr(capture, "_REGISTRO", {})
    monkeypatch.setattr(capture, "_abrir_backend", lambda *_a: falso)
    return falso


ROI = Rect(10, 10, 40, 20)


def test_fechar_numa_aba_nao_mata_a_captura_da_outra(backend):
    """Era assim que usar Enchant, Tempering ou Masterworking deixava o
    AutoSkill mudo: o `close()` daquela aba liberava o device compartilhado."""
    a = ScreenCapture()
    b = ScreenCapture()
    assert capturas_abertas() == 2

    a.close()
    assert not backend.fechado, "soltou o device com alguém ainda usando"
    assert b.grab(ROI) is not None, "a outra aba perdeu a captura"

    b.close()
    assert backend.fechado, "o último a sair tem de soltar o device"
    assert capturas_abertas() == 0


def test_o_device_e_um_so_para_o_processo(backend):
    a, b, c = ScreenCapture(), ScreenCapture(), ScreenCapture()
    try:
        assert capturas_abertas() == 3
        for cap in (a, b, c):
            cap.grab(ROI)
        assert backend.grabs == 3
    finally:
        for cap in (a, b, c):
            cap.close()


def test_dois_grabs_nao_entram_juntos_no_device(backend):
    """Medido com dxcam de verdade: 27 de 120 chamadas concorrentes voltavam
    None, com o D3D acusando chamada inválida."""
    cap = ScreenCapture()
    try:
        def martela():
            for _ in range(80):
                cap.grab(ROI)

        fios = [threading.Thread(target=martela) for _ in range(3)]
        for f in fios:
            f.start()
        for f in fios:
            f.join()

        assert backend.grabs == 240
        assert backend.pico == 1, f"{backend.pico} grabs ao mesmo tempo"
    finally:
        cap.close()


def test_fechar_duas_vezes_nao_derruba_a_contagem(backend):
    a = ScreenCapture()
    b = ScreenCapture()
    a.close()
    a.close()                      # idempotente
    assert capturas_abertas() == 1
    assert b.grab(ROI) is not None
    b.close()


def test_grab_depois_de_fechar_devolve_none_em_vez_de_estourar(backend):
    cap = ScreenCapture()
    cap.close()
    assert cap.grab(ROI) is None
