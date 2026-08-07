"""Ciclo do engine, com a tela sendo trocada por um roteiro falso.

O caso que motivou estes testes veio do jogo real: o clique em Enchant levou
direto para a tela Replace Affix, sem passar pelo diálogo de confirmação. A
versão anterior do engine exigia a sequência completa e travava ali.
"""

import pytest

from d4forge.affixes import AffixCatalog
from d4forge.automation.safety import Guard, Limits
from d4forge.engine import EnchantEngine
from d4forge.geometry import Point, Rect
from d4forge.profile import DEFAULT_PROFILE
from d4forge.rules import Comparison, RuleSet, TargetRule
from d4forge.vision.ocr import OcrEngine


class FakeWindow:
    def __init__(self, client: Rect) -> None:
        self.client = client
        self.is_foreground = True

    def focus(self) -> None:
        pass


class ScriptedScreen:
    """Devolve prints de referência conforme um roteiro, avançando a cada clique."""

    def __init__(self, shots, sequence):
        self.shots = shots
        self.sequence = list(sequence)
        self.step = 0
        self.clicks: list[str] = []

    @property
    def current(self):
        return self.shots[self.sequence[min(self.step, len(self.sequence) - 1)]]

    def grab(self, _region):
        return self.current

    def close(self):
        pass

    def advance(self, _rect, _profile=None):
        """Substitui click_rect: em vez de clicar, avança o roteiro."""
        self.step = (self.step + 1) % len(self.sequence)
        return Point(0, 0)


@pytest.fixture
def scripted(monkeypatch, shots, tmp_path):
    """Monta um engine cujo mundo externo é totalmente falso."""

    def build(sequence, rules, max_attempts=2):
        img = shots["enchant_locked"]
        client = Rect(0, 0, img.shape[1], img.shape[0])
        screen = ScriptedScreen(shots, sequence)

        monkeypatch.setattr("d4forge.engine.find_game_window", lambda: FakeWindow(client))
        monkeypatch.setattr("d4forge.engine.click_rect", screen.advance)

        engine = EnchantEngine(
            ruleset=rules,
            catalog=AffixCatalog.seeded(),
            ocr=OcrEngine(data_dir=tmp_path / "ocr"),
            guard=Guard(
                limits=Limits(max_attempts=max_attempts, max_minutes=None),
                require_foreground=False,
                abort_on_mouse_move=False,
            ),
            profile=DEFAULT_PROFILE,
            capture=screen,
            dry_run=False,
            start_delay=0,
            focus_game_on_start=False,
            poll_interval=0.001,
            state_timeout=1.0,
        )
        return engine, screen

    return build


def test_pula_dialogo_de_confirmacao(scripted):
    """Regressão: Enchant -> Replace Affix direto, sem passar pelo Accept.

    Antes o engine parava com "esperando o diálogo de confirmação por 8s".
    """
    rules = RuleSet([TargetRule("Coisa Inexistente", Comparison.ANY)])
    engine, screen = scripted(
        ["enchant_locked", "replace", "result"], rules, max_attempts=2
    )

    outcome = engine.run()

    assert "confirmação" not in outcome.reason
    assert outcome.count == 2, outcome.reason
    assert "tentativas" in outcome.reason  # parou no limite, nao por erro


def test_usa_o_dialogo_quando_ele_aparece(scripted):
    """Com o Accept presente, o ciclo tambem funciona."""
    rules = RuleSet([TargetRule("Coisa Inexistente", Comparison.ANY)])
    engine, _ = scripted(
        ["enchant_locked", "confirm", "replace", "result"], rules, max_attempts=2
    )

    outcome = engine.run()
    assert outcome.count == 2, outcome.reason


def test_sem_regra_batendo_mantem_no_change(scripted):
    rules = RuleSet([TargetRule("Coisa Inexistente", Comparison.ANY)])
    engine, _ = scripted(["enchant_locked", "replace", "result"], rules, max_attempts=1)

    outcome = engine.run()
    assert not outcome.found
    assert all(not a.decision.accepted for a in outcome.attempts)


def test_aborta_se_o_orbe_nao_confirma(scripted):
    """Trava de segurança: o print mostra No Change marcado, então marcar a
    opção 1 nunca é confirmado pela tela e o engine tem que desistir."""
    rules = RuleSet([TargetRule("Resource Generation", Comparison.GE, 10)])
    engine, _ = scripted(["enchant_locked", "replace", "result"], rules, max_attempts=5)

    outcome = engine.run()
    assert not outcome.found
    assert "confirmar a opção" in outcome.reason


def test_item_que_ja_cumpre_a_meta_nao_gasta_material(scripted):
    """O item da tela travada tem "+3,000 Shadow Resistance". Se o alvo já está
    satisfeito, encantar de novo só queimaria ouro — e, com azar, a meta."""
    rules = RuleSet([TargetRule("Shadow Resistance", Comparison.GE, 2000)])
    engine, screen = scripted(["enchant_locked", "replace", "result"], rules, max_attempts=5)

    outcome = engine.run()

    assert outcome.found
    assert outcome.count == 0          # nenhuma tentativa
    assert screen.step == 0            # nenhum clique
    assert "já tem" in outcome.reason


def test_limpa_recortes_de_ocr_da_sessao_anterior(scripted, monkeypatch, tmp_path):
    """Os `ocr_*.png` valem só para a sessão corrente; iniciar uma nova sessão
    os apaga. Os `debug_*.png` são evidência de erro e ficam."""
    captures = tmp_path / "captures"
    captures.mkdir()
    (captures / "ocr_opcao1_120000.png").write_bytes(b"x")
    (captures / "ocr_opcao2_120001.png").write_bytes(b"x")
    (captures / "debug_sem_selecao_120002.png").write_bytes(b"x")
    monkeypatch.setattr("d4forge.config.CAPTURES_DIR", captures)

    rules = RuleSet([TargetRule("Coisa Inexistente", Comparison.ANY)])
    engine, _ = scripted(["enchant_locked", "replace", "result"], rules, max_attempts=1)
    engine.run()

    remaining = sorted(p.name for p in captures.iterdir())
    assert remaining == ["debug_sem_selecao_120002.png"]


def test_tela_desconhecida_para_com_mensagem_clara(scripted, shots):
    """Se o jogo estiver noutra tela, o engine para em vez de clicar no escuro."""
    rules = RuleSet([TargetRule("Dexterity", Comparison.ANY)])
    engine, screen = scripted(["enchant_locked"], rules)
    # Frame preto: nao bate com nenhuma assinatura.
    screen.grab = lambda _r: shots["enchant_locked"] * 0

    outcome = engine.run()
    assert not outcome.found
    assert "não reconheço a tela" in outcome.reason
