"""Janela sem a moldura do Windows — mas com os gestos do Windows.

Tirar a barra nativa custa reimplementar o que ela dava de graça. A primeira
versão daqui reimplementava só metade: arrastar e redimensionar respondendo a
`mouseMoveEvent`. O resultado era uma janela que MOVIA, e nada mais — não
encaixava ao chegar na borda, não obedecia Win+Seta, não mostrava o cursor de
redimensionar, não abria o Snap Layouts, não tinha sombra. Parecia um app; não
se comportava como um.

Agora quem manda na janela é o Windows outra vez (ver `win32frame`), e o que
sobra aqui é a ponte: dizer o que é barra de título, o que é botão, e devolver
ao Qt o que muda quando a janela maximiza. O caminho antigo, todo em Qt, ficou
como reserva — é o que roda nos testes (plataforma `offscreen`) e fora do
Windows.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QByteArray, QEvent, QPoint, QRect, QSize, Qt
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QComboBox,
    QFrame,
    QLineEdit,
    QWidget,
)

from . import win32frame

log = logging.getLogger(__name__)

# Faixa sensível ao redimensionamento no caminho reserva, em pixels.
MARGEM = 6


class FramelessMixin:
    """Arrastar, maximizar e redimensionar numa janela sem moldura.

    Espera que a classe final seja um QWidget/QMainWindow e chame
    `setup_frameless()` no __init__.
    """

    # A janela pode sobrescrever para que a borda do Windows 11 acompanhe o
    # tema em vez de destoar em cinza de sistema.
    cor_da_borda = None

    def setup_frameless(self) -> None:
        # FramelessWindowHint continua: é ele que faz o Qt parar de contar com
        # margens de moldura no cálculo de geometria. Os estilos que devolvem
        # os gestos ao Windows entram por baixo, em `win32frame`.
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self._barra_titulo: QWidget | None = None
        self._botao_maximizar: QWidget | None = None
        self._arrastando_de: QPoint | None = None
        self._redimensionando: str = ""
        self._geo_inicial = QRect()
        self._mouse_inicial = QPoint()
        self._maximizada = False
        # Atribuido ANTES de instalar: criar a janela nativa ja' faz o Windows
        # despachar WM_NCCALCSIZE, e `nativeEvent` roda no meio desta linha.
        self._moldura = None

        self._moldura = self._instalar_moldura()
        if self._moldura is None:
            # Só o caminho reserva precisa saber onde o cursor está a cada
            # instante; no nativo quem responde isso é o Windows.
            self.setMouseTracking(True)

    def _instalar_moldura(self):
        """A moldura nativa, ou None quando ela não se aplica.

        Fora do Windows e sob a plataforma `offscreen` dos testes não há HWND
        para configurar — e o caminho reserva dá conta.
        """
        if not win32frame.DISPONIVEL:
            return None
        if QGuiApplication.platformName() != "windows":
            return None
        moldura = win32frame.MolduraNativa(self)
        # winId() força o Qt a criar a janela nativa agora; sem isso não há
        # HWND antes do primeiro show, e o primeiro show já desenharia a
        # moldura do sistema por um quadro.
        if not moldura.instalar(int(self.winId())):
            return None
        return moldura

    # -- o que a moldura nativa precisa saber -----------------------------
    def register_title_bar(
        self, barra: QWidget, botao_maximizar: QWidget | None = None
    ) -> None:
        """Marca a região que faz as vezes de barra de título."""
        self._barra_titulo = barra
        self._botao_maximizar = botao_maximizar

    def regiao_da_barra(self, x: int, y: int) -> str:
        """'titulo', 'maximizar' ou '' para um ponto da área do cliente.

        Recebe pixels FÍSICOS (a régua do Windows) e responde sobre widgets, que
        vivem em pixels lógicos: a divisão pela escala da tela é o que faz isto
        funcionar igual a 100% e a 150%.
        """
        barra = self._barra_titulo
        if barra is None or not barra.isVisible():
            return ""

        escala = self.devicePixelRatioF() or 1.0
        ponto = QPoint(round(x / escala), round(y / escala))
        canto = barra.mapTo(self, QPoint(0, 0))
        if not QRect(canto, barra.size()).contains(ponto):
            return ""

        filho = self.childAt(ponto)
        if filho is None:
            return "titulo"

        botao = self._botao_maximizar
        if botao is not None and (filho is botao or botao.isAncestorOf(filho)):
            return "maximizar"

        # Qualquer coisa em que se clica devolve o ponto ao Qt: marcado como
        # título, o Windows engoliria o clique e o botão nunca dispararia.
        atual: QWidget | None = filho
        while atual is not None and atual is not barra:
            if isinstance(
                atual, (QAbstractButton, QComboBox, QAbstractSpinBox, QLineEdit)
            ):
                return ""
            atual = atual.parentWidget()
        return "titulo"

    def destacar_maximizar(self, aceso: bool) -> None:
        """Aceso/apagado do botão de maximizar.

        Com o Snap Layouts ligado o botão fica na área não-cliente e o Qt nunca
        vê o cursor passar por ele, então `:hover` não acontece sozinho. A
        propriedade dinâmica reproduz o efeito a partir do que o Windows conta.
        """
        botao = self._botao_maximizar
        if botao is None:
            return
        botao.setProperty("hover", aceso)
        botao.style().unpolish(botao)
        botao.style().polish(botao)

    def on_maximize_changed(self, maximizada: bool) -> None:
        """Gancho para a janela; por padrão não faz nada."""

    def sincronizar_maximizada(self) -> None:
        """Anuncia o estado ATUAL, sem esperar uma mudança.

        `changeEvent` só fala sobre MUDANÇAS. Uma janela que abre normal e
        nunca maximiza jamais ouviria o estado inicial, e quem depende dele
        para decidir a aparência ficaria sem valor nenhum para consultar.
        """
        self._maximizada = self.isMaximized() or self.isFullScreen()
        self.on_maximize_changed(self._maximizada)

    # -- eventos ----------------------------------------------------------
    def nativeEvent(self, tipo, mensagem):  # noqa: N802 - assinatura do Qt
        # getattr, e nao o atributo direto: o Qt ja' despacha mensagens durante
        # a criacao da janela nativa, antes de `setup_frameless` terminar.
        moldura = getattr(self, "_moldura", None)
        if moldura is not None and tipo in (
            b"windows_generic_MSG", b"windows_dispatcher_MSG"
        ):
            endereco = win32frame._int_do_ponteiro(mensagem)
            if endereco:
                tratado, resposta = moldura.processar(endereco)
                if tratado:
                    return True, resposta
        return super().nativeEvent(tipo, mensagem)

    def showEvent(self, event) -> None:  # noqa: N802
        # O Qt recria a janela nativa em algumas trocas de estado, e o HWND
        # novo nasce com a moldura do sistema de volta.
        if self._moldura is not None:
            atual = int(self.winId())
            if atual and atual != self._moldura.hwnd:
                self._moldura.instalar(atual)
        super().showEvent(event)

    def changeEvent(self, event) -> None:  # noqa: N802
        if event.type() == QEvent.Type.WindowStateChange:
            agora = self.isMaximized() or self.isFullScreen()
            if agora != self._maximizada:
                self._maximizada = agora
                self.on_maximize_changed(agora)
        super().changeEvent(event)

    # -- arrastar pela barra de título (caminho reserva) ------------------
    def start_drag(self, posicao_global: QPoint) -> None:
        if self._moldura is not None:
            return
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

    # -- redimensionar pelas bordas (caminho reserva) ---------------------
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
        if self._moldura is None and event.button() == Qt.MouseButton.LeftButton:
            borda = self._borda_em(event.position().toPoint())
            if borda:
                self._redimensionando = borda
                self._geo_inicial = self.geometry()
                self._mouse_inicial = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._moldura is None:
            pos = event.position().toPoint()
            if self._redimensionando:
                self._aplicar_resize(event.globalPosition().toPoint())
            elif not self._arrastando_de:
                self.setCursor(self._cursor_para(self._borda_em(pos)))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._moldura is None:
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

    No Windows estes tratadores não chegam a rodar — o arrasto vira HTCAPTION e
    nunca vira evento de mouse do Qt. Eles são o caminho reserva.
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


# --------------------------------------------------------------- geometria
#
# Uma janela que abre maior que a tela é o defeito mais visível que existe:
# metade dela fica inalcançável, inclusive os botões de fechar. O tamanho
# pedido aqui é um PEDIDO, e a tela decide.

def tela_sob_o_cursor():
    """Onde o usuário está olhando agora, e não onde o Windows chama de 1."""
    return (
        QGuiApplication.screenAt(QCursor.pos())
        or QGuiApplication.primaryScreen()
    )


def encaixar_na_tela(janela: QWidget, largura: int, altura: int) -> None:
    """Abre a janela no tamanho pedido, cortado pela tela, e centralizada."""
    tela = tela_sob_o_cursor()
    if tela is None:  # sem tela nenhuma (offscreen), o pedido vale
        janela.resize(largura, altura)
        return

    livre = tela.availableGeometry()
    # 0,94: sobra uma borda de respiro em vez de a janela colar nos cantos.
    tamanho = QSize(
        max(janela.minimumWidth(), min(largura, int(livre.width() * 0.94))),
        max(janela.minimumHeight(), min(altura, int(livre.height() * 0.94))),
    )
    area = QRect(QPoint(0, 0), tamanho)
    area.moveCenter(livre.center())
    janela.setGeometry(area)


def dentro_de_alguma_tela(janela: QWidget) -> bool:
    """A janela está acessível?

    Monitor desligado desde a última sessão, notebook que saiu da dock: a
    geometria salva aponta para uma área que não existe mais, e a janela abre
    onde ninguém a alcança. Basta uma faixa razoável visível para valer.
    """
    quadro = janela.frameGeometry()
    for tela in QGuiApplication.screens():
        visivel = quadro.intersected(tela.availableGeometry())
        if visivel.width() >= 120 and visivel.height() >= 60:
            return True
    return False


def restaurar_geometria(janela: QWidget, blob: str) -> bool:
    """Repõe a geometria salva. Devolve False se não deu para usar."""
    if not blob:
        return False
    try:
        dados = QByteArray.fromBase64(QByteArray(blob.encode("ascii")))
    except (UnicodeEncodeError, ValueError):
        return False
    if dados.isEmpty() or not janela.restoreGeometry(dados):
        return False
    if not dentro_de_alguma_tela(janela):
        log.info("geometria salva estava fora das telas atuais; recentrando")
        return False
    return True


def geometria_salva(janela: QWidget) -> str:
    """A geometria de agora em texto, para caber no settings.json.

    `saveGeometry` guarda também o monitor e o estado maximizado, e é o único
    formato que o Qt sabe repor corretamente em telas com escalas diferentes.
    """
    return bytes(janela.saveGeometry().toBase64()).decode("ascii")


__all__ = [
    "FramelessMixin",
    "TitleBarArea",
    "dentro_de_alguma_tela",
    "encaixar_na_tela",
    "geometria_salva",
    "restaurar_geometria",
    "tela_sob_o_cursor",
]
