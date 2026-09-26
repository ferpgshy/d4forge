"""Captura de tela.

Dois backends:
  * dxcam  - Desktop Duplication (DXGI). Rapido, ~1-2 ms por regiao pequena.
  * mss    - GDI. Mais lento (~5-10 ms) mas funciona em qualquer lugar.

Detalhe importante do dxcam: por padrao `grab()` devolve None quando NAO houve
frame novo desde a ultima chamada. Com um consumidor so' isso e' apenas "nada
mudou"; com dois vira roubo - o primeiro a pedir consome o quadro e o segundo
recebe None. Medido: com o AutoSkill lendo o HUD, o encantamento acertava ZERO
de dez leituras. Por isso pedimos `new_frame_only=False`, que entrega sempre o
quadro mais recente - e de quebra os dois passam a enxergar o MESMO instante.

E o detalhe que custou caro: **o dxcam so' aceita UM device por saida de
video**. Pedir um segundo nao cria outro - ele devolve o MESMO objeto. Com o
AutoSkill rodando a sessao inteira e as outras abas abrindo a sua propria
captura, o app ficava com cinco fachadas apontando para um unico device, e dai
vinham tres defeitos que pareciam independentes:

* fechar a captura de uma aba chamava `release()` no device COMPARTILHADO e a
  captura das outras morria - medido: `grab` depois disso devolve None com
  "DXCamera has been released and cannot be reused";
* dois `grab` concorrentes atropelavam-se - medido: 27 de 120 chamadas
  voltaram None, com o D3D acusando chamada invalida;
* e quem perdia quadro reagia devagar ou decidia sobre uma tela velha.

Por isso o device agora e' UM so' no processo, com contagem de uso e trava:
fechar de um lado nao derruba o outro, e duas threads nao entram no D3D ao
mesmo tempo.
"""

from __future__ import annotations

import logging
import threading
from typing import Protocol

import numpy as np

from .geometry import Rect

log = logging.getLogger(__name__)


class CaptureBackend(Protocol):
    name: str

    def grab(self, region: Rect) -> np.ndarray | None:
        """Retorna a regiao como array BGR (H, W, 3) uint8."""
        ...

    def close(self) -> None: ...


class DXCamBackend:
    """Desktop Duplication. Um device por output; region grab e' feito na GPU."""

    name = "dxcam"

    def __init__(self, output_idx: int = 0) -> None:
        import dxcam

        self._camera = dxcam.create(output_idx=output_idx, output_color="BGR")
        if self._camera is None:
            raise RuntimeError(f"dxcam nao conseguiu abrir o output {output_idx}")
        # Versao antiga do dxcam pode nao aceitar `new_frame_only`; a
        # descoberta e' feita uma vez, na primeira leitura.
        self._aceita_mais_recente = True

    def grab(self, region: Rect) -> np.ndarray | None:
        box = region.as_ltrb()
        if self._aceita_mais_recente:
            try:
                return self._camera.grab(region=box, new_frame_only=False)
            except TypeError:
                self._aceita_mais_recente = False

        # Caminho antigo: sem "mais recente", None quer dizer "nada mudou", e
        # so' resta pedir de novo.
        frame = self._camera.grab(region=box)
        if frame is None:
            frame = self._camera.grab(region=box)
        return frame

    def close(self) -> None:
        try:
            self._camera.release()
        except Exception:
            pass


class MSSBackend:
    """Fallback GDI. `mss` nao e' thread-safe, entao criamos um por thread."""

    name = "mss"

    def __init__(self) -> None:
        import mss

        self._mss = mss
        self._local = threading.local()

    def _sct(self):
        sct = getattr(self._local, "sct", None)
        if sct is None:
            sct = self._mss.mss()
            self._local.sct = sct
        return sct

    def grab(self, region: Rect) -> np.ndarray | None:
        shot = self._sct().grab(
            {"left": region.x, "top": region.y, "width": region.w, "height": region.h}
        )
        # mss entrega BGRA; descartamos o alpha.
        return np.asarray(shot, dtype=np.uint8)[:, :, :3]

    def close(self) -> None:
        sct = getattr(self._local, "sct", None)
        if sct is not None:
            sct.close()
            self._local.sct = None


class _Compartilhado:
    """O device de verdade, com contagem de uso e trava.

    E' o que deixa varias fachadas conviverem: quem fecha decrementa, e so' o
    ultimo a sair e' que solta o device.
    """

    def __init__(self, backend) -> None:
        self.backend = backend
        self.usuarios = 0
        self.trava = threading.Lock()


_REGISTRO: dict = {}
_REGISTRO_TRAVA = threading.Lock()


def _abrir_backend(prefer: str, output_idx: int):
    if prefer == "dxcam":
        try:
            backend = DXCamBackend(output_idx)
            log.info("captura via dxcam (output %d)", output_idx)
            return backend
        except Exception as exc:
            log.warning("dxcam indisponivel (%s); usando mss", exc)
    return MSSBackend()


def _obter(prefer: str, output_idx: int) -> "_Compartilhado":
    chave = (prefer, output_idx)
    with _REGISTRO_TRAVA:
        alvo = _REGISTRO.get(chave)
        if alvo is None:
            alvo = _Compartilhado(_abrir_backend(prefer, output_idx))
            _REGISTRO[chave] = alvo
        alvo.usuarios += 1
        return alvo


def _devolver(chave, alvo: "_Compartilhado") -> None:
    with _REGISTRO_TRAVA:
        alvo.usuarios -= 1
        if alvo.usuarios > 0:
            return
        _REGISTRO.pop(chave, None)
    alvo.backend.close()


def capturas_abertas() -> int:
    """Quantos usuarios o device compartilhado tem agora. Para testes."""
    with _REGISTRO_TRAVA:
        return sum(a.usuarios for a in _REGISTRO.values())


class ScreenCapture:
    """Fachada sobre o device compartilhado do processo.

    Continua sendo criada e fechada por quem precisa, como antes. A diferenca
    e' que varias delas agora dividem o mesmo device sem se atrapalhar.
    """

    def __init__(self, prefer: str = "dxcam", output_idx: int = 0) -> None:
        self._chave = (prefer, output_idx)
        self._alvo = _obter(prefer, output_idx)

    @property
    def backend_name(self) -> str:
        return self._alvo.backend.name if self._alvo else "fechada"

    def grab(self, region: Rect) -> np.ndarray | None:
        if region.w <= 0 or region.h <= 0:
            return None
        alvo = self._alvo
        if alvo is None:
            log.error("grab numa captura ja fechada")
            return None
        try:
            # A trava nao e' zelo: dois `grab` concorrentes no mesmo device
            # atropelam-se. Medido, 27 de 120 chamadas voltavam None com o D3D
            # acusando chamada invalida.
            with alvo.trava:
                return alvo.backend.grab(region)
        except Exception as exc:
            log.error("falha na captura de %s: %s", region, exc)
            return None

    def grab_or_raise(self, region: Rect) -> np.ndarray:
        frame = self.grab(region)
        if frame is None:
            raise RuntimeError(f"nao foi possivel capturar a regiao {region}")
        return frame

    def close(self) -> None:
        """Devolve o device. So' o ultimo usuario e' que o solta de verdade.

        Era aqui que uma aba matava a outra: `close()` chamava `release()` no
        device compartilhado, e a captura de quem continuava rodando morria.
        """
        alvo, self._alvo = self._alvo, None
        if alvo is not None:
            _devolver(self._chave, alvo)

    def __enter__(self) -> "ScreenCapture":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
