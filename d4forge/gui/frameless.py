"""Janela sem a moldura do Windows.

Tirar a barra nativa custa reimplementar o que ela dava de graça: arrastar,
maximizar com duplo clique e redimensionar pelas bordas. É isso que está aqui,
separado da janela principal para não misturar com a lógica do app.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QFrame

# Faixa sensível ao redimensionamento, em pixels a partir da borda.
MARGEM = 6


class FramelessMixin:
    """Arrastar, maximizar e redimensionar numa janela sem moldura.

    Espera que a classe final seja um QWidget/QMainWindow e chame
    `setup_frameless()` no __init__.
    """

    def setup_frameless(self) -> None:
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setMouseTracking(True)
        self._arrastando_de: QPoint | None = None
        self._redimensionando: str = ""
        self._geo_inicial = QRect()
        self._mouse_inicial = QPoint()

    # -- arrastar pela barra de título ------------------------------------
    def start_drag(self, posicao_global: QPoint) -> None:
        if self.isMaximized():
            # Restaura mantendo o cursor sobre o mesmo ponto relativo do
            # título; sem isso a janela pula para longe do mouse.
            largura_max = self.width()
            self.showNormal()
            proporcao = posicao_global.x() / max(1, largura_max)
            novo_x = int(posicao_global.x() - self.width() * proporcao)
            self.move(novo_x, posicao_global.y() - 20)
        self._arrastando_de = posicao_global - self.frameGeometry().topLeft()

    def continue_drag(self, posicao_global: QPoint) -> None:
        if self._arrastando_de is not None:
            self.move(posicao_global - self._arrastando_de)

    def end_drag(self) -> None:
        self._arrastando_de = None

    def toggle_maximize(self) -> None:
        # showMaximized respeita a barra de tarefas; setGeometry(tela) não.
        self.showNormal() if self.isMaximized() else self.showMaximized()

    # -- redimensionar pelas bordas ---------------------------------------
    def _borda_em(self, pos: QPoint) -> str:
        if self.isMaximized():
            return ""
        esquerda = pos.x() <= MARGEM
        direita = pos.x() >= self.width() - MARGEM
        topo = pos.y() <= MARGEM
        base = pos.y() >= self.height() - MARGEM
        return (
            ("t" if topo else "b" if base else "")
            + ("l" if esquerda else "r" if direita else "")
        )

    def _cursor_para(self, borda: str) -> Qt.CursorShape:
        return {
            "t": Qt.CursorShape.SizeVerCursor,
            "b": Qt.CursorShape.SizeVerCursor,
            "l": Qt.CursorShape.SizeHorCursor,
            "r": Qt.CursorShape.SizeHorCursor,
            "tl": Qt.CursorShape.SizeFDiagCursor,
            "br": Qt.CursorShape.SizeFDiagCursor,
            "tr": Qt.CursorShape.SizeBDiagCursor,
            "bl": Qt.CursorShape.SizeBDiagCursor,
        }.get(borda, Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - assinatura do Qt
        if event.button() == Qt.MouseButton.LeftButton:
            borda = self._borda_em(event.position().toPoint())
            if borda:
                self._redimensionando = borda
                self._geo_inicial = self.geometry()
                self._mouse_inicial = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position().toPoint()
        if self._redimensionando:
            self._aplicar_resize(event.globalPosition().toPoint())
        elif not self._arrastando_de:
            self.setCursor(self._cursor_para(self._borda_em(pos)))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._redimensionando = ""
        self.unsetCursor()
        super().mouseReleaseEvent(event)

    def _aplicar_resize(self, global_pos: QPoint) -> None:
        delta = global_pos - self._mouse_inicial
        geo = QRect(self._geo_inicial)
        minimo = self.minimumSize()

        if "l" in self._redimensionando:
            geo.setLeft(min(geo.left() + delta.x(), geo.right() - minimo.width()))
        if "r" in self._redimensionando:
            geo.setRight(max(geo.right() + delta.x(), geo.left() + minimo.width()))
        if "t" in self._redimensionando:
            geo.setTop(min(geo.top() + delta.y(), geo.bottom() - minimo.height()))
        if "b" in self._redimensionando:
            geo.setBottom(max(geo.bottom() + delta.y(), geo.top() + minimo.height()))
        self.setGeometry(geo)


class TitleBarArea(QFrame):
    """Região que arrasta a janela ao ser puxada, e maximiza no duplo clique.

    QFrame e não QWidget: um QWidget puro ignora `background` vindo da folha de
    estilo a menos que se ative WA_StyledBackground, e o cabeçalho ficava sem o
    gradiente.
    """

    def __init__(self, janela, parent=None) -> None:
        super().__init__(parent)
        self._janela = janela

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._janela.start_drag(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._janela.continue_drag(event.globalPosition().toPoint())

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._janela.end_drag()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._janela.toggle_maximize()
