"""Idiomas e a versão final da interface."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from d4forge import i18n  # noqa: E402


@pytest.fixture(autouse=True)
def idioma_padrao():
    yield
    i18n.set_language(i18n.DEFAULT)


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def test_so_dois_idiomas():
    assert set(i18n.LANGUAGES) == {"pt-BR", "en"}


def test_traduz():
    i18n.set_language("pt-BR")
    assert i18n.t("panel.start") == "Iniciar"
    i18n.set_language("en")
    assert i18n.t("panel.start") == "Start"


def test_idioma_desconhecido_cai_no_padrao():
    assert i18n.set_language("fr") == i18n.DEFAULT


def test_chave_ausente_devolve_a_propria_chave():
    assert i18n.t("nao.existe") == "nao.existe"


def test_ingles_cobre_todas_as_chaves():
    """Faltar chave em inglês deixa texto em português no meio da tela."""
    faltando = set(i18n.STRINGS["pt-BR"]) - set(i18n.STRINGS["en"])
    assert not faltando, sorted(faltando)


def test_formatacao_com_argumentos():
    i18n.set_language("pt-BR")
    assert "7" in i18n.t("catalog.count", count=7)


def test_argumento_faltando_nao_quebra():
    """Preferimos texto sem preencher a uma exceção no meio do desenho."""
    assert i18n.t("catalog.count") == i18n.STRINGS["pt-BR"]["catalog.count"]


# ------------------------------------------------------ versão final da GUI

def test_versao_final_da_interface(qt_app, config_isolada):
    from d4forge.gui.app import AppState, MainWindow

    janela = MainWindow(AppState.load())
    try:
        # uma aba por fluxo (Enchant, Tempering, Masterworking) mais o
        # Catálogo, que é dos três
        assert janela.tabs.count() == 4
        # o alvo virou cartão dentro do Enchant, não uma aba à parte
        assert janela.cmb_affix is not None
        # modo simulação saiu da interface
        assert not hasattr(janela, "chk_dry")
        # velocidade do mouse foi para o painel
        assert janela.cmb_speed is not None
        # catálogo já vem cheio, sem precisar importar
        assert len(janela.app.catalog) > 800
        assert not hasattr(janela, "_import_catalog")
    finally:
        janela.close()


def test_alvo_do_enchant_salva_sozinho(qt_app, config_isolada):
    """O botão "Salvar alvo" saiu: quem fechasse o app sem apertá-lo perdia o
    alvo, e nada na tela avisava disso. Agora editar já vale.
    """
    from PySide6.QtWidgets import QPushButton

    from d4forge.gui.app import AppState, MainWindow

    janela = MainWindow(AppState.load())
    try:
        rotulos = [b.text() for b in janela.findChildren(QPushButton)]
        assert not any("Salvar alvo" in r or "Save target" in r for r in rotulos), rotulos

        janela.cmb_affix.setCurrentText("Dodge Chance")
        janela.spin_value.setValue(7.5)

        # A regra vale na hora, sem esperar o temporizador do disco.
        assert janela.app.ruleset.rules[0].affix_name == "Dodge Chance"
        assert janela.app.ruleset.rules[0].threshold == pytest.approx(7.5)
        # E o resumo é o retorno visual de que o alvo foi entendido.
        assert "Dodge Chance" in janela.lbl_target_summary.text()
    finally:
        janela.close()


def test_gravacao_do_alvo_espera_parar_de_digitar(qt_app, config_isolada):
    """Cada letra escreveria rules.json, e cada nome pela metade viraria uma
    regra salva no caminho. O disco espera; a tela não."""
    from d4forge import config
    from d4forge.gui.app import AppState, MainWindow

    janela = MainWindow(AppState.load())
    try:
        janela.cmb_affix.setCurrentText("Dodge Chance")
        assert janela._target_timer.isActive()
        assert janela._target_timer.isSingleShot()

        # Disparando o que o temporizador dispararia:
        janela._save_target()
        assert config.RULES_PATH.exists()
        assert "Dodge Chance" in config.RULES_PATH.read_text(encoding="utf-8")
    finally:
        janela.close()


def test_refazer_a_aba_preserva_o_alvo(qt_app, config_isolada):
    """Trocar de idioma refaz o cartão do alvo, e encher os campos novos dispara
    os mesmos sinais que uma edição de verdade. A regra tem de sair inteira."""
    from d4forge.gui.app import AppState, MainWindow

    janela = MainWindow(AppState.load())
    try:
        janela.cmb_affix.setCurrentText("Dodge Chance")
        janela.spin_value.setValue(7.5)

        janela._set_language("en")

        assert janela.app.ruleset.rules, "o alvo sumiu ao refazer a aba"
        assert janela.app.ruleset.rules[0].affix_name == "Dodge Chance"
        assert janela.cmb_affix.currentText() == "Dodge Chance"
    finally:
        janela.close()


def test_repor_o_alvo_nao_conta_como_edicao(qt_app, config_isolada):
    """A trava de `_reload_target`, testada direto.

    Hoje ela não muda o resultado do teste acima, porque o afixo é o primeiro
    campo reposto e todo sinal já sai com o nome certo. O que ela compra é que
    essa ordem deixe de importar: com a trava ligada, mexer nos campos não
    escreve regra nenhuma — inverter duas linhas na reposição deixa de poder
    salvar um alvo sem afixo.
    """
    from d4forge.gui.app import AppState, MainWindow

    janela = MainWindow(AppState.load())
    try:
        janela.cmb_affix.setCurrentText("Dodge Chance")
        antes = list(janela.app.ruleset.rules)

        # Uma reposição na ordem ruim: mexe nos outros campos com o afixo ainda
        # vazio. Sem a trava, o primeiro sinal salvaria uma regra sem afixo —
        # que é como o código representa "não há alvo".
        janela._carregando_alvo = True
        janela.cmb_affix.setCurrentText("")
        janela.spin_value.setValue(99)
        janela.chk_climb.setChecked(False)
        assert janela.app.ruleset.rules == antes, "a reposição gravou por conta"

        # Terminada a reposição, o campo volta ao valor reposto e a edição de
        # verdade volta a valer.
        janela.cmb_affix.setCurrentText("Dodge Chance")
        janela._carregando_alvo = False
        janela.spin_value.setValue(42)
        assert janela.app.ruleset.rules[0].affix_name == "Dodge Chance"
        assert janela.app.ruleset.rules[0].threshold == pytest.approx(42)
    finally:
        janela.close()


def test_apagar_o_afixo_desfaz_o_alvo(qt_app, config_isolada):
    """Limpar o campo tem de limpar a regra — senão o alvo antigo continuaria
    valendo com a tela dizendo o contrário."""
    from d4forge.gui.app import AppState, MainWindow

    janela = MainWindow(AppState.load())
    try:
        janela.cmb_affix.setCurrentText("Dodge Chance")
        assert janela.app.ruleset.rules

        janela.cmb_affix.setCurrentText("")
        assert janela.app.ruleset.rules == []
        assert janela.lbl_target_summary.text() == "Nenhum alvo definido"
    finally:
        janela.close()


def test_troca_de_idioma_redesenha_a_janela(qt_app, config_isolada):
    from d4forge.gui.app import AppState, MainWindow

    janela = MainWindow(AppState.load())
    try:
        janela._set_language("en")
        assert [janela.tabs.tabText(i) for i in range(4)] == [
            "Enchant", "Tempering", "Masterworking", "Catalog"
        ]
        assert janela.btn_start.text().startswith("Start")

        janela._set_language("pt-BR")
        assert [janela.tabs.tabText(i) for i in range(4)] == [
            "Enchant", "Tempering", "Masterworking", "Catálogo"
        ]
        assert janela.btn_start.text().startswith("Iniciar")
    finally:
        janela.close()


def test_abas_do_ferreiro_trocam_de_idioma(qt_app, config_isolada):
    """As abas do Tempering e do Masterworking são REAPROVEITADAS na troca de
    idioma — uma aba nova perderia a sessão em curso. Isso as fazia ficar na
    língua anterior: dica, títulos dos cartões, rádios e botão de iniciar.
    """
    from d4forge.gui.app import AppState, MainWindow

    janela = MainWindow(AppState.load())
    try:
        janela._set_language("en")

        assert janela.temper_tab.lbl_hint.text().startswith("Open the Blacksmith")
        assert janela.temper_tab.box_goal.title() == "Stop when"
        assert janela.temper_tab.rb_stop.text() == "stop and tell me"
        assert janela.btn_temper.text().startswith("Start Tempering")

        assert janela.mw_tab.lbl_hint.text().startswith("Open the Blacksmith")
        assert janela.mw_tab.box_limits.title() == "Limits"
        assert janela.btn_mw.text().startswith("Start Masterworking")
        # O cabeçalho da tabela de progresso vem junto.
        assert janela.mw_tab.progress.tabela.horizontalHeaderItem(2).text() == "Result"
        # E a linha de estado em repouso também: ela é frase fixa.
        assert janela.mw_tab.status.text().startswith("Ready.")
        assert janela.temper_tab.status.text().startswith("Ready.")

        janela._set_language("pt-BR")
        assert janela.mw_tab.box_limits.title() == "Limites"
        assert janela.temper_tab.rb_stop.text() == "parar e me avisar"
    finally:
        janela.close()


def test_campo_de_afixo_do_masterworking_busca_como_o_do_enchant(
    qt_app, config_isolada
):
    """Digitar tem de filtrar a lista, e por TRECHO — o nome quase nunca começa
    pela palavra que a gente lembra. Sem completador o campo era só uma caixa
    preta muda."""
    from PySide6.QtCore import Qt

    from d4forge.gui.app import AppState, MainWindow

    janela = MainWindow(AppState.load())
    try:
        mw = janela.mw_tab.cmb_affix
        completer = mw.completer()
        assert completer is not None
        assert completer.filterMode() == Qt.MatchFlag.MatchContains
        assert completer.caseSensitivity() == Qt.CaseSensitivity.CaseInsensitive
        # Mesma lista do Enchant, e cheia.
        assert len(janela.mw_tab._affix_model.stringList()) > 800

        # "resist" no meio do nome tem de achar algo.
        completer.setCompletionPrefix("resist")
        assert completer.completionCount() > 0
        assert "resist" in completer.currentCompletion().lower()

        # E o campo continua aceitando texto livre: o Masterwork cai em afixos
        # que o catálogo do Occultist não tem, como os vindos do Tempering.
        mw.setCurrentText("Damage with Two-Handed Slashing Weapons")
        assert janela.mw_tab.goal().affix == "Damage with Two-Handed Slashing Weapons"
    finally:
        janela.close()


def test_troca_de_idioma_nao_apaga_o_que_o_ciclo_escreveu(qt_app, config_isolada):
    """A linha de estado guarda o último evento depois que a sessão roda.

    Traduzi-la de volta para a frase de repouso apagaria justamente a única
    coisa visível quando o ciclo para antes da primeira tentativa.
    """
    from d4forge.gui.app import AppState, MainWindow

    janela = MainWindow(AppState.load())
    try:
        janela.mw_tab.set_status("caiu em +182 Strength", erro=False)
        janela._set_language("en")
        assert janela.mw_tab.status.text() == "caiu em +182 Strength"
    finally:
        janela.close()


def test_troca_de_idioma_preserva_o_alvo_do_masterworking(qt_app, config_isolada):
    """Retraduzir não pode apagar o que o usuário digitou."""
    from d4forge.gui.app import AppState, MainWindow

    janela = MainWindow(AppState.load())
    try:
        janela.mw_tab.cmb_affix.setCurrentText("Strength")
        janela.mw_tab.spin_attempts.setValue(17)
        janela._set_language("en")
        assert janela.mw_tab.cmb_affix.currentText() == "Strength"
        assert janela.mw_tab.spin_attempts.value() == 17
    finally:
        janela.close()


def test_botao_de_idioma_nao_muda_de_largura(qt_app, config_isolada):
    """O rótulo era o nome inteiro ("Português (BR)" vs "English"): o botão
    encolhia ao trocar para inglês e arrastava os botões de janela junto."""
    from d4forge.gui.app import AppState, MainWindow

    janela = MainWindow(AppState.load())
    try:
        janela.show()
        largura_pt = janela.btn_lang.sizeHint().width()
        assert janela.btn_lang.text() == "🌐 PT ▾"

        janela._set_language("en")
        assert janela.btn_lang.text() == "🌐 EN ▾"
        assert janela.btn_lang.sizeHint().width() == largura_pt
        # o nome por extenso continua acessível
        assert janela.btn_lang.toolTip() == "English"
    finally:
        janela.close()


def test_registro_acompanha_a_troca_de_idioma(qt_app, config_isolada):
    """Bug relatado: o Registro continuava em português depois de trocar para
    inglês, porque guardávamos a frase pronta em vez do evento."""
    from d4forge.engine import EngineEvent, EventKind
    from d4forge.gui.app import AppState, MainWindow

    janela = MainWindow(AppState.load())
    try:
        janela.progress.reset()
        janela._on_event(EngineEvent(EventKind.INFO, "eng.rules", {"count": 2}))
        assert "ativa(s)" in janela.progress.detalhes.toPlainText()

        janela._set_language("en")
        texto = janela.progress.detalhes.toPlainText()
        assert "active" in texto and "ativa(s)" not in texto
    finally:
        janela.close()


def test_fechar_espera_o_aquecimento_do_ocr(qt_app, config_isolada):
    """Fechar a janela enquanto a WarmupWorker rodava destruía uma QThread viva
    e derrubava o processo (0xC0000409) no encerramento."""
    from d4forge.gui.app import AppState, MainWindow

    janela = MainWindow(AppState.load())
    janela.close()
    assert not janela._warmup.isRunning()


def test_troca_de_idioma_preserva_o_alvo(qt_app, config_isolada):
    from d4forge.gui.app import AppState, MainWindow

    janela = MainWindow(AppState.load())
    try:
        janela.cmb_affix.setCurrentText("Dodge Chance")
        janela.spin_value.setValue(7.5)
        janela._set_language("en")
        assert janela.cmb_affix.currentText() == "Dodge Chance"
        assert janela.spin_value.value() == pytest.approx(7.5)
    finally:
        janela.close()
