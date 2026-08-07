"""Painel de progresso: dados estruturados no lugar do texto corrido.

O registro antigo era uma parede de texto que (a) escondia o que interessa e
(b) ficava congelado no idioma em que foi escrito. Estes testes fixam as duas
correções: a tabela mostra o essencial, e trocar de idioma reescreve o que já
está na tela.
"""

import pytest

from d4forge import i18n
from d4forge.affixes import ParsedAffix, Unit
from d4forge.engine import Attempt, EngineEvent, EventKind, Outcome
from d4forge.rules import Action, Comparison, Decision, TargetRule


@pytest.fixture
def painel(qt_app):
    from d4forge.gui.progress import ProgressPanel

    p = ProgressPanel()
    p.reset()
    return p


def _tentativa(index: int, acao: Action, meta: bool = False) -> Attempt:
    regra = TargetRule("Dexterity", Comparison.GE, 100)
    return Attempt(
        index=index,
        options=[
            ParsedAffix("+151 Dexterity", "Dexterity", 151.0, Unit.FLAT),
            ParsedAffix("+4 Energy", "Energy", 4.0, Unit.FLAT),
        ],
        decision=Decision(acao, regra, key="decision.match", goal_reached=meta),
    )


def _evento(tentativa: Attempt) -> EngineEvent:
    return EngineEvent(
        EventKind.ATTEMPT, "eng.attempt",
        {"index": tentativa.index, "options": "", "reason": "",
         "attempt": tentativa},
    )


def test_tentativa_vira_linha_da_tabela(painel):
    painel.push(_evento(_tentativa(1, Action.NO_CHANGE)))

    assert painel.tabela.rowCount() == 1
    assert painel.tabela.item(0, 0).text() == "1"
    assert painel.tabela.item(0, 1).text() == "+151 Dexterity"
    assert painel.tabela.item(0, 2).text() == "+4 Energy"
    assert painel.tabela.item(0, 3).text() == i18n.t("progress.kept")


def test_tentativa_nova_entra_no_topo(painel):
    """Sem isto o usuário teria que rolar até o fim a cada rodada — e uma sessão
    passa das 200 tentativas."""
    for i in (1, 2, 3):
        painel.push(_evento(_tentativa(i, Action.NO_CHANGE)))

    assert [painel.tabela.item(l, 0).text() for l in range(3)] == ["3", "2", "1"]


def test_resultado_distingue_manter_trocar_e_meta(painel):
    painel.push(_evento(_tentativa(1, Action.NO_CHANGE)))
    painel.push(_evento(_tentativa(2, Action.TAKE_OPTION_2)))
    painel.push(_evento(_tentativa(3, Action.TAKE_OPTION_1, meta=True)))

    # A tabela está invertida: linha 0 é a tentativa 3.
    assert painel.tabela.item(0, 3).text() == i18n.t("progress.goal")
    assert painel.tabela.item(1, 3).text() == i18n.t("progress.took_n", index=2)
    assert painel.tabela.item(2, 3).text() == i18n.t("progress.kept")


def test_metricas_acompanham_as_tentativas(painel):
    assert painel._metricas["current"].valor.text() == i18n.t("progress.none")

    painel.push(EngineEvent(EventKind.READ, "eng.current", {"affix": "+151 Dexterity"}))
    painel.push(_evento(_tentativa(1, Action.NO_CHANGE)))
    painel.push(_evento(_tentativa(2, Action.NO_CHANGE)))

    assert painel._metricas["attempts"].valor.text() == "2"
    assert painel._metricas["current"].valor.text() == "+151 Dexterity"


def test_ritmo_sai_do_tempo_real_da_sessao(painel):
    painel.push(_evento(_tentativa(1, Action.NO_CHANGE)))
    painel.finish(Outcome(False, "stop.max_attempts", {}, [], 0, 3.0))

    # 3 s / 1 tentativa
    assert painel._metricas["rate"].valor.text() == i18n.t("progress.rate_unit", seconds=3.0)


def test_troca_de_idioma_reescreve_o_que_ja_esta_na_tela(painel):
    """O bug relatado: o registro continuava em português depois de trocar para
    inglês, porque guardávamos a frase pronta em vez do evento."""
    painel.push(_evento(_tentativa(1, Action.NO_CHANGE)))
    assert painel.tabela.item(0, 3).text() == "manteve"
    assert "Tentativas" in painel._metricas["attempts"].rotulo.text()

    i18n.set_language("en")
    painel.retranslate()

    assert painel.tabela.item(0, 3).text() == "kept"
    assert painel._metricas["attempts"].rotulo.text() == "Attempts"
    assert painel.tabela.horizontalHeaderItem(3).text() == "Result"


def test_detalhes_tecnicos_ficam_recolhidos(painel):
    """O diagnóstico continua acessível — é o que resolveu quase todo bug deste
    projeto — mas não na cara de quem só quer ver o item ficar pronto."""
    painel.push(EngineEvent(EventKind.CLICK, "eng.click",
                            {"label": "Enchant", "x": 10, "y": 20}))

    # isVisibleTo: o painel não está numa janela mostrada durante o teste.
    assert not painel.detalhes.isVisibleTo(painel)
    assert "Enchant" in painel.detalhes.toPlainText()

    painel.btn_detalhes.setChecked(True)
    assert painel.detalhes.isVisibleTo(painel)


def test_detalhes_tambem_trocam_de_idioma(painel):
    painel.push(EngineEvent(EventKind.INFO, "eng.rules", {"count": 1}))
    assert painel.detalhes.toPlainText().strip().endswith("ativa(s)")

    i18n.set_language("en")
    painel.retranslate()
    assert "active" in painel.detalhes.toPlainText()


def test_reset_limpa_a_sessao_anterior(painel):
    painel.push(_evento(_tentativa(1, Action.NO_CHANGE)))
    painel.reset()

    assert painel.tabela.rowCount() == 0
    assert painel.detalhes.toPlainText() == ""
    assert painel._metricas["attempts"].valor.text() == "0"
