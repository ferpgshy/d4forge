"""Quanto o ciclo espera antes de reclicar.

Sintoma relatado: "às vezes ele trava por um tempo e volta, é um tempo
considerável". A causa era `_act` gastar `state_timeout` (8 s) entre cada
tentativa de clique. Mas 8 s é o prazo para desistir da SESSÃO; entre duas
tentativas ele não compra nada — se o clique não chegou, esperar mais não faz
ele chegar.

Medido em 111 rodadas reais do usuário: o jogo reage em ~80 ms, p95 155 ms,
máximo 173 ms. Uma travada de 8 s depois disso é puro desperdício.
"""

import time

import pytest

from d4forge.affixes import AffixCatalog
from d4forge.automation.safety import Guard, Limits
from d4forge.engine import EnchantEngine
from d4forge.geometry import Point, Rect
from d4forge.profile import DEFAULT_PROFILE
from d4forge.profiling import Profiler
from d4forge.rules import Comparison, RuleSet, TargetRule
from d4forge.vision.ocr import OcrEngine
from d4forge.vision.states import ScreenState


# ------------------------------------------------------ janela sugerida

def test_sem_medicao_usa_o_padrao_conservador():
    assert Profiler().suggested_retry_after(default=1.2) == pytest.approx(1.2)


def test_janela_sai_da_reacao_medida_da_maquina():
    """Não é constante escrita no código: vem do que o jogo fez nesta máquina."""
    p = Profiler()
    for _ in range(20):
        p.record("reação: replace → result", 80.0)
    p.record("reação: replace → result", 173.0)   # o pior caso real medido

    # 4x o pior caso = 0,69 s, elevado ao piso de 0,8 s
    assert p.suggested_retry_after() == pytest.approx(0.8)


def test_maquina_lenta_ganha_janela_maior():
    p = Profiler()
    for _ in range(20):
        p.record("reação: replace → result", 600.0)

    assert p.suggested_retry_after() == pytest.approx(2.4)


def test_janela_nunca_passa_de_um_teto():
    """Mesmo com uma amostra absurda (o jogo travou uma vez), a janela não pode
    virar de novo uma espera de dezenas de segundos."""
    p = Profiler()
    for _ in range(10):
        p.record("reação: replace → result", 80.0)
    p.record("reação: replace → result", 30_000.0)

    assert p.suggested_retry_after(default=1.2) == pytest.approx(3.6)


# ------------------------------------------------------------ no engine

class TelaTravada:
    """Nunca muda de estado: simula todo clique se perdendo."""

    def __init__(self, shots):
        self.img = shots["enchant_locked"]

    def grab(self, _region):
        return self.img

    def close(self):
        pass


@pytest.fixture
def motor_travado(monkeypatch, shots, tmp_path):
    """Engine onde o clique nunca surte efeito, com o relógio acelerado."""
    img = shots["enchant_locked"]
    client = Rect(0, 0, img.shape[1], img.shape[0])

    class Janela:
        def __init__(self):
            self.client = client
            self.is_foreground = True

        def focus(self, timeout=1.5):
            return True

    monkeypatch.setattr("d4forge.engine.find_game_window", lambda: Janela())
    monkeypatch.setattr("d4forge.engine.click_rect", lambda *a, **k: Point(0, 0))

    engine = EnchantEngine(
        ruleset=RuleSet([TargetRule("Coisa Inexistente", Comparison.ANY)]),
        catalog=AffixCatalog.seeded(),
        ocr=OcrEngine(data_dir=tmp_path / "ocr"),
        guard=Guard(limits=Limits(max_attempts=5, max_minutes=None),
                    require_foreground=False, abort_on_mouse_move=False),
        profile=DEFAULT_PROFILE,
        capture=TelaTravada(shots),
        dry_run=False,
        start_delay=0,
        focus_game_on_start=False,
        # Com o relógio virtual, o poll define quantas voltas o laço dá para
        # cobrir a espera. 0,1 s dá 80 voltas nos 8 s em vez de 8000 — mesma
        # medida de espera, teste que roda em um segundo.
        poll_interval=0.1,
        state_timeout=8.0,
    )
    # Relógio virtual: o teste mede a espera PEDIDA, sem gastá-la de verdade.
    relogio = {"t": 0.0}
    monkeypatch.setattr("d4forge.engine.time.monotonic", lambda: relogio["t"])
    monkeypatch.setattr(engine, "_sleep", lambda s: relogio.__setitem__("t", relogio["t"] + s))
    return engine, relogio


def test_clique_perdido_nao_gasta_o_prazo_de_desistencia_a_cada_tentativa(motor_travado):
    """A regressão em si. Com 3 tentativas a 8 s cada, um clique perdido
    congelava o ciclo por 24 s; agora as duas primeiras usam a janela curta e só
    a última tem direito ao prazo cheio."""
    engine, relogio = motor_travado
    for _ in range(20):
        engine.profiler.record("reação: enchant_locked → replace", 100.0)

    from d4forge.automation.safety import StopReason

    with pytest.raises(StopReason) as exc:
        engine._act(Rect(10, 10, 20, 20), "Enchant", ScreenState.ENCHANT_LOCKED)

    assert exc.value.key == "stop.click_lost"
    # 0,8 + 0,8 + 8,0 = 9,6 s, contra 24 s antes.
    assert relogio["t"] == pytest.approx(9.6, abs=0.3)


def test_clique_perdido_aparece_no_relatorio(motor_travado):
    """Antes o profiler só registrava a reação quando a tela MUDAVA, então o
    tempo gasto esperando em vão era invisível — foi por isso que a travada não
    apareceu em nenhuma métrica."""
    engine, _ = motor_travado
    from d4forge.automation.safety import StopReason

    with pytest.raises(StopReason):
        engine._act(Rect(10, 10, 20, 20), "Enchant", ScreenState.ENCHANT_LOCKED)

    perdidos = [n for n in engine.profiler.timings if n.startswith("clique perdido")]
    assert perdidos == ["clique perdido: Enchant"]
    assert engine.profiler.timings[perdidos[0]].count == 3


def test_primeira_tentativa_que_pega_nao_espera_nada(motor_travado, monkeypatch):
    """A janela curta não pode atrapalhar o caminho normal: quando o clique
    pega, `_act` sai na primeira tentativa sem consumir espera nenhuma."""
    engine, relogio = motor_travado
    monkeypatch.setattr(
        engine, "_wait_until_leaves", lambda *a, **k: ("frame", "prof", ScreenState.REPLACE)
    )

    engine._act(Rect(10, 10, 20, 20), "Enchant", ScreenState.ENCHANT_LOCKED)

    assert relogio["t"] == pytest.approx(0.0)
    assert "clique perdido: Enchant" not in engine.profiler.timings
