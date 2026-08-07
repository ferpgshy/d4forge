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
