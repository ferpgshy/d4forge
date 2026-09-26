"""Botão que captura uma bind: tecla, botão do mouse ou roda.

Nada de digitar o nome da tecla numa caixa de texto. O usuário clica, aperta o
que quiser, e o widget guarda o VIRTUAL-KEY que o Qt já entrega pronto no
evento (`nativeVirtualKey`) — que é exatamente o que `automation.binds` precisa
para depois derivar o scancode do jogo.

Capturar mouse tem uma sutileza: o clique que ARMA a captura não pode ser o
clique capturado. Como armar acontece no press e a captura só olha o press
seguinte, o próprio fluxo de eventos resolve — o release intermediário não
conta.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QPushButton

from ..automation import binds
from ..i18n import t

# Qt não expõe virtual-keys de mouse; o mapa é curto e fixo.
BOTOES_QT = {
    Qt.MouseButton.LeftButton: binds.VK_LBUTTON,
    Qt.MouseButton.RightButton: binds.VK_RBUTTON,
    Qt.MouseButton.MiddleButton: binds.VK_MBUTTON,
    Qt.MouseButton.XButton1: binds.VK_XBUTTON1,
    Qt.MouseButton.XButton2: binds.VK_XBUTTON2,
}

# Teclas que não podem virar bind porque são o próprio controle da captura.
TECLAS_RESERVADAS = {Qt.Key.Key_Escape}
TECLAS_QUE_LIMPAM = {Qt.Key.Key_Delete, Qt.Key.Key_Backspace}


class BindButton(QPushButton):
    """Mostra a bind atual; clicado, espera a próxima para substituí-la."""

    mudou = Signal(object)   # Bind

    def __init__(self, bind=None, aceita_roda: bool = True, parent=None) -> None:
        super().__init__(parent)
        self._bind = bind or binds.Bind()
        self._aceita_roda = aceita_roda
        self._capturando = False
        self.setCheckable(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setProperty("bindbtn", True)
        self._redesenhar()

    # -- estado -----------------------------------------------------------
    def bind(self):
        return self._bind

    def set_bind(self, bind) -> None:
        self._bind = bind or binds.Bind()
        self._redesenhar()

    def _guardar(self, bind) -> None:
        self._bind = bind
        self._parar()
        self.mudou.emit(self._bind)

    def _redesenhar(self) -> None:
        if self._capturando:
            self.setText(t("as.capturing"))
        else:
            self.setText(self._bind.descreve() if self._bind else t("as.unset"))
        self.setProperty("capturando", self._capturando)
        self.style().unpolish(self)
        self.style().polish(self)

    # -- captura ----------------------------------------------------------
    def _comecar(self) -> None:
        self._capturando = True
        # grabKeyboard: sem isto, teclas como Tab e as setas iriam para a
        # navegação do Qt e nunca chegariam aqui.
        self.grabKeyboard()
        self._redesenhar()

    def _parar(self) -> None:
        if self._capturando:
            self.releaseKeyboard()
        self._capturando = False
        self._redesenhar()

    def focusOutEvent(self, event) -> None:  # noqa: N802 - assinatura do Qt
        self._parar()
        super().focusOutEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self._capturando:
            if event.button() == Qt.MouseButton.LeftButton:
                self.setFocus(Qt.FocusReason.MouseFocusReason)
                self._comecar()
            event.accept()
            return
        vk = BOTOES_QT.get(event.button())
        if vk is not None:
            self._guardar(binds.botao_mouse(vk))
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        # Engolido de propósito: o release do clique que armou a captura não
        # pode disparar o `clicked` do QPushButton.
        event.accept()

    def wheelEvent(self, event) -> None:  # noqa: N802
        if self._capturando and self._aceita_roda:
            self._guardar(binds.roda(1 if event.angleDelta().y() >= 0 else -1))
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if not self._capturando:
            super().keyPressEvent(event)
            return
        chave = Qt.Key(event.key())
        if chave in TECLAS_RESERVADAS:
            self._parar()
            event.accept()
            return
        if chave in TECLAS_QUE_LIMPAM:
            self._guardar(binds.Bind())
            event.accept()
            return

        vk = event.nativeVirtualKey()
        if not vk:
            event.accept()
            return
        rotulo = QKeySequence(event.key()).toString() or f"VK {vk:#x}"
        self._guardar(binds.tecla(int(vk), rotulo))
        event.accept()

    def keyReleaseEvent(self, event) -> None:  # noqa: N802
        if self._capturando:
            event.accept()
            return
        super().keyReleaseEvent(event)

    def retranslate(self) -> None:
        self._redesenhar()


__all__ = ["BindButton", "BOTOES_QT"]
