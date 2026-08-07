"""Widgets da interface que têm lógica própria."""

import os

import pytest

# Precisa vir antes de qualquer import do Qt: sem isso a suíte tentaria abrir
# uma janela de verdade.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from d4forge.gui.app import ValueSpinBox  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.mark.parametrize(
    "value, shown",
    [
        (1450, "1450"),
        (1450.0, "1450"),
        (3000, "3000"),
        (2, "2"),
        (0, "0"),
    ],
)
def test_inteiro_nao_ganha_casa_decimal(qt_app, value, shown):
    """Regressão de usabilidade: o campo exibia "1450,0" e não deixava informar
    o valor exato."""
    sb = ValueSpinBox()
    sb.setValue(value)
    assert sb.text() == shown


@pytest.mark.parametrize("value", [15.5, 9.4, 10.1])
def test_decimal_continua_aparecendo(qt_app, value):
    sb = ValueSpinBox()
    sb.setValue(value)
    assert "," in sb.text() or "." in sb.text()
    assert sb.value() == pytest.approx(value)


@pytest.mark.parametrize(
    "text, expected",
    [("1450", 1450.0), ("15,5", 15.5), ("15.5", 15.5), ("3000", 3000.0)],
)
def test_aceita_virgula_e_ponto(qt_app, text, expected):
    """Teclado brasileiro digita vírgula; colar de um site traz ponto."""
    assert ValueSpinBox().valueFromText(text) == pytest.approx(expected)


@pytest.mark.parametrize(
    "termo, esperado",
    [
        ("resist", "Fire Resistance"),
        ("dodge", "Dodge Chance"),
        ("life on", "Life on Kill"),
        ("damage multi", "All Damage Multiplier"),
    ],
)
def test_busca_de_afixo_e_por_trecho(qt_app, termo, esperado):
    """São ~880 afixos e o nome quase nunca começa pela palavra que a gente
    lembra: digitar "resist" tem de achar "Fire Resistance"."""
    from PySide6.QtCore import Qt

    from d4forge.gui.app import AppState, MainWindow

    janela = MainWindow(AppState.load())
    try:
        comp = janela.cmb_affix.completer()
        assert comp.filterMode() == Qt.MatchFlag.MatchContains
        comp.setCompletionPrefix(termo)
        modelo = comp.completionModel()
        achados = [modelo.index(i, 0).data() for i in range(modelo.rowCount())]
        assert esperado in achados, achados[:5]
    finally:
        janela.close()


def test_mouse_instantaneo_e_o_padrao():
    """O movimento humanizado custava 360 ms por volta num ciclo de 1,8 s —
    20% do tempo só disfarçando o mouse. Os outros perfis continuam
    disponíveis na aba Desempenho."""
    from d4forge.automation.sendinput import DEFAULT_PROFILE, INSTANTANEO
    from d4forge.config import Settings

    assert DEFAULT_PROFILE is INSTANTANEO
    assert Settings().input_speed == INSTANTANEO.label
    # Bem abaixo do "rápido" (120 ms): o custo daquele está no percurso.
    assert INSTANTANEO.estimate_ms() < 50


def test_clique_instantaneo_espera_um_quadro():
    """O jogo amostra input por quadro: teleportar e clicar no mesmo instante
    não lhe dá um quadro para registrar o hover. Regressão real — um clique em
    Replace Affix se perdeu na tentativa 71 com o settle zerado."""
    from d4forge.automation.sendinput import INSTANTANEO

    um_quadro_60fps = 1 / 60
    assert INSTANTANEO.settle[0] >= um_quadro_60fps * 0.85
    assert INSTANTANEO.hold[0] >= um_quadro_60fps * 0.4
