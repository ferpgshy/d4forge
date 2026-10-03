"""A roda do mouse rola a página. Ela não mexe no valor de campo nenhum.

Por padrão o Qt deixa `QSpinBox`, `QDoubleSpinBox` e `QComboBox` responderem
à roda mesmo sem foco e mesmo sem clique. Numa tela que rola — e as quatro
abas rolam — isso vira uma armadilha: passar a roda para descer a página
altera o número que estava embaixo do ponteiro, em silêncio. Num app que
clica e aperta tecla no jogo, um "60 minutos" virando "48" sem ninguém
perceber é defeito, não detalhe.

Aqui a roda é tirada desses campos **sempre**, e não só quando falta foco:
clicar num campo e depois rolar a página cairia na mesma armadilha. O valor
continua editável por digitação, pelas setas do teclado e pelos botõezinhos
do próprio campo.

O evento não é simplesmente engolido: ele é reenviado à área de rolagem que
estiver acima na hierarquia. Engolir faria a página parar de rolar quando o
ponteiro passasse por cima de um campo, que é o oposto do que se quer.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QSlider,
)

# `QSlider` entra; `QScrollBar` **não**, apesar de ambos serem
# `QAbstractSlider` — tirar a roda da barra de rolagem seria quebrar
# justamente o que este filtro existe para preservar.
ALVOS = (QAbstractSpinBox, QComboBox, QSlider)


class FiltroDeRoda(QObject):
    """Intercepta a roda nos campos e devolve o gesto para a rolagem."""

    def eventFilter(self, obj: QObject, evento: QEvent) -> bool:  # noqa: N802
        if evento.type() != QEvent.Type.Wheel or not isinstance(obj, ALVOS):
            return False

        area = _area_de_rolagem(obj)
        if area is not None:
            QApplication.sendEvent(area.viewport(), evento)
        return True


def _area_de_rolagem(widget) -> QAbstractScrollArea | None:
    """A área de rolagem mais próxima acima do campo, se houver alguma."""
    pai = widget.parentWidget()
    while pai is not None:
        if isinstance(pai, QAbstractScrollArea):
            return pai
        pai = pai.parentWidget()
    return None


def proteger(app: QApplication | None) -> FiltroDeRoda | None:
    """Liga o filtro no aplicativo inteiro.

    No aplicativo, e não em cada campo: metade deles nasce depois, quando a
    aba é remontada ou uma linha do catálogo aparece, e um filtro por campo
    deixaria esses de fora — que é exatamente o tipo de proteção que falha
    sem avisar.

    Sem aplicativo não há o que proteger, e isto nunca pode ser o motivo de
    a janela não abrir: devolve `None` e segue.
    """
    if app is None:
        return None
    filtro = FiltroDeRoda(app)
    app.installEventFilter(filtro)
    return filtro
