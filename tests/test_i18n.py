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
        # três abas: Diagnóstico e Desempenho saíram
        assert janela.tabs.count() == 3
        # modo simulação saiu da interface
        assert not hasattr(janela, "chk_dry")
        # velocidade do mouse foi para o painel
        assert janela.cmb_speed is not None
        # catálogo já vem cheio, sem precisar importar
        assert len(janela.app.catalog) > 800
        assert not hasattr(janela, "_import_catalog")
    finally:
        janela.close()


def test_troca_de_idioma_redesenha_a_janela(qt_app, config_isolada):
    from d4forge.gui.app import AppState, MainWindow

    janela = MainWindow(AppState.load())
    try:
        janela._set_language("en")
        assert [janela.tabs.tabText(i) for i in range(3)] == ["Panel", "Target", "Catalog"]
        assert janela.btn_start.text().startswith("Start")

        janela._set_language("pt-BR")
        assert [janela.tabs.tabText(i) for i in range(3)] == ["Painel", "Alvo", "Catálogo"]
        assert janela.btn_start.text().startswith("Iniciar")
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
