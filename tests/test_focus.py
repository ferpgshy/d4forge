"""Foco automático do jogo ao iniciar.

Apertar Iniciar (ou F9) deixa o app em primeiro plano, não o Diablo IV — e sem
o jogo na frente o guard aborta na hora. A espera fixa existia para dar tempo de
voltar na mão; com o foco automático confirmado, ela vira atraso à toa.
"""

import pytest

from d4forge.affixes import AffixCatalog
from d4forge.automation.safety import Guard, Limits
from d4forge.engine import EnchantEngine, EventKind
from d4forge.geometry import Rect
from d4forge.profile import DEFAULT_PROFILE
from d4forge.rules import Comparison, RuleSet, TargetRule
from d4forge.vision.ocr import OcrEngine


class JanelaFalsa:
    """Janela que registra como foi chamada e obedece (ou não) o foco."""

    def __init__(self, em_foco=False, foco_funciona=True):
        self.client = Rect(0, 0, 1920, 1080)
        self._em_foco = em_foco
        self._foco_funciona = foco_funciona
        self.pedidos_de_foco = 0

    @property
    def is_foreground(self):
        return self._em_foco

    def focus(self, timeout=1.5):
        self.pedidos_de_foco += 1
        if self._foco_funciona:
            self._em_foco = True
        return self._em_foco


@pytest.fixture
def motor(monkeypatch, tmp_path):
    def build(janela, focar=True, start_delay=4.0):
        monkeypatch.setattr("d4forge.engine.find_game_window", lambda: janela)
        return EnchantEngine(
            ruleset=RuleSet([TargetRule("Dexterity", Comparison.ANY)]),
            catalog=AffixCatalog.seeded(),
            ocr=OcrEngine(data_dir=tmp_path / "ocr"),
            guard=Guard(limits=Limits(max_attempts=1, max_minutes=None),
                        require_foreground=False, abort_on_mouse_move=False),
            profile=DEFAULT_PROFILE,
            capture=object(),
            dry_run=True,          # não move o mouse
            start_delay=start_delay,
            focus_game_on_start=focar,
        )
    return build


def _dormidas(engine, monkeypatch):
    """Troca o sono real por um registro, para medir a espera sem esperar."""
    registro = []
    monkeypatch.setattr(engine, "_sleep", lambda s: registro.append(s))
    return registro


def test_foco_confirmado_dispensa_a_espera(motor, monkeypatch):
    """O ganho que o usuário pediu: apertar Iniciar e o ciclo começar, em vez de
    olhar 4 segundos de contagem regressiva."""
    janela = JanelaFalsa(em_foco=False, foco_funciona=True)
    engine = motor(janela, start_delay=4.0)
    dormidas = _dormidas(engine, monkeypatch)

    engine._countdown()

    assert janela.pedidos_de_foco == 1
    assert sum(dormidas) == pytest.approx(EnchantEngine.FOCUS_SETTLE_S)


def test_foco_recusado_cumpre_a_espera_inteira(motor, monkeypatch):
    """Quando o Windows recusa o foco é justamente quando você precisa do tempo
    para dar Alt+Tab. Aí a contagem tem que valer."""
    janela = JanelaFalsa(em_foco=False, foco_funciona=False)
    engine = motor(janela, start_delay=4.0)
    dormidas = _dormidas(engine, monkeypatch)

    engine._countdown()

    assert sum(dormidas) == pytest.approx(4.0)


def test_jogo_ja_em_foco_nao_pede_foco(motor, monkeypatch):
    """Caso do F9 com o jogo na frente: não há nada a fazer nem a esperar."""
    janela = JanelaFalsa(em_foco=True)
    engine = motor(janela)
    dormidas = _dormidas(engine, monkeypatch)

    engine._countdown()

    assert janela.pedidos_de_foco == 0
    assert sum(dormidas) == pytest.approx(EnchantEngine.FOCUS_SETTLE_S)


def test_desligar_o_foco_automatico_mantem_a_espera(motor, monkeypatch):
    janela = JanelaFalsa(em_foco=False)
    engine = motor(janela, focar=False, start_delay=3.0)
    dormidas = _dormidas(engine, monkeypatch)

    engine._countdown()

    assert janela.pedidos_de_foco == 0
    assert sum(dormidas) == pytest.approx(3.0)


def test_falha_ao_focar_e_avisada(motor, monkeypatch):
    """`focus()` devolve se conseguiu; antes o engine anunciava sucesso sempre,
    porque só olhava se a chamada levantou exceção."""
    eventos = []
    janela = JanelaFalsa(em_foco=False, foco_funciona=False)
    engine = motor(janela)
    engine._listener = lambda e: eventos.append(e)
    _dormidas(engine, monkeypatch)

    engine._countdown()

    chaves = [e.key for e in eventos if e.kind is EventKind.INFO]
    assert "eng.focus_failed" in chaves
    assert "eng.focusing" not in chaves


def test_focus_nao_desmaximiza_a_janela_do_jogo():
    """SW_RESTORE numa janela MAXIMIZADA a desmaximiza — o app mudaria o
    tamanho da tela do jogo só por tentar focar. Só vale para minimizada."""
    import d4forge.window as w

    chamadas = []

    class FakeUser32:
        def IsIconic(self, hwnd):          # noqa: N802 - espelha a API do Win32
            return 0                        # não está minimizada
        def ShowWindow(self, hwnd, cmd):    # noqa: N802
            chamadas.append(("ShowWindow", cmd))
            return 1
        def SetForegroundWindow(self, hwnd):  # noqa: N802
            chamadas.append(("SetForegroundWindow", hwnd))
            return 1
        def BringWindowToTop(self, hwnd):   # noqa: N802
            return 1
        def GetForegroundWindow(self):      # noqa: N802
            return 0
        def GetWindowThreadProcessId(self, hwnd, pid):  # noqa: N802
            return 0
        def AttachThreadInput(self, a, b, c):  # noqa: N802
            return 0

    original = w.user32
    w.user32 = FakeUser32()
    try:
        janela = w.GameWindow(hwnd=1, title="Diablo IV",
                              client=Rect(0, 0, 1920, 1080),
                              window=Rect(0, 0, 1920, 1080))
        janela.focus(timeout=0.05)
    finally:
        w.user32 = original

    assert not any(c[0] == "ShowWindow" for c in chamadas), chamadas
    assert ("SetForegroundWindow", 1) in chamadas
