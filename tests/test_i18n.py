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

def test_versao_final_da_interface(qt_app):
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


def test_troca_de_idioma_redesenha_a_janela(qt_app):
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


def test_troca_de_idioma_preserva_o_alvo(qt_app):
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
