"""Peças que fazem a janela caber em qualquer tamanho.

Um layout de Qt já estica e encolhe sozinho — até o ponto em que o conteúdo não
cabe mais. Dali em diante ele para de encolher e os widgets se sobrepõem, que é
o que fazia esta janela exigir 880 pixels de largura e não aceitar ser menor que
a tela em altura.

São dois remédios, e eles resolvem eixos diferentes:

* `pagina_rolavel` cuida da ALTURA. O que não cabe rola, em vez de ser espremido
  até o texto encavalar. É o que deixa a janela ser redimensionada à vontade.
* `LinhaAdaptavel` cuida da LARGURA. Dois cartões lado a lado ficam ilegíveis
  muito antes de o layout desistir; abaixo da largura em que os dois cabem
  inteiros, eles viram uma coluna.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QWidget,
)


class LinhaAdaptavel(QWidget):
    """Cartões lado a lado que viram uma coluna quando a janela aperta."""

    # Histerese. Sem ela, a largura exata da virada faz o layout piscar entre
    # linha e coluna a cada pixel do arrasto.
    FOLGA = 48
    # Respiro por cartão: o mínimo do Qt é o tamanho em que o conteúdo ainda
    # cabe espremido, e virar a coluna um pouco antes disso fica melhor.
    CONFORTO = 24

    def __init__(self, espaco: int = 12, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._caixa = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._caixa.setContentsMargins(0, 0, 0, 0)
        self._caixa.setSpacing(espaco)
        self._itens: list[tuple[QWidget, int]] = []
        self._limiar = 0

    def add(self, widget: QWidget, peso: int = 1) -> QWidget:
        self._itens.append((widget, peso))
        self._caixa.addWidget(widget, peso)
        return widget

    def em_linha(self) -> bool:
        return self._caixa.direction() == QBoxLayout.Direction.LeftToRight

    # ------------------------------------------------------------- decisão
    def largura_para_caber(self) -> int:
        """Largura a partir da qual os cartões cabem lado a lado."""
        if not self._itens:
            return 0
        total = self._caixa.spacing() * (len(self._itens) - 1)
        for widget, _ in self._itens:
            minimo = max(
                widget.minimumSizeHint().width(), widget.minimumWidth()
            )
            total += minimo + self.CONFORTO
        return total

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - assinatura do Qt
        """A largura mínima é a da COLUNA, mesmo estando em linha.

        Sem isto a linha nunca chega a virar coluna dentro de uma área de
        rolagem: o pai pergunta o mínimo, ouve a largura dos dois cartões lado
        a lado, e reserva essa largura para sempre — barra de rolagem
        horizontal permanente, e a virada que existe para evitá-la sem chance
        de acontecer. O mínimo honesto é o do arranjo mais estreito que este
        widget sabe assumir, e esse é o empilhado.
        """
        base = super().minimumSizeHint()
        if not self._itens:
            return base
        largura = max(
            max(w.minimumSizeHint().width(), w.minimumWidth())
            for w, _ in self._itens
        )
        margens = self.contentsMargins()
        return QSize(
            largura + margens.left() + margens.right(), base.height()
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 - assinatura do Qt
        super().resizeEvent(event)
        self.reavaliar(event.size().width())

    def reavaliar(self, largura: int) -> None:
        if self.em_linha():
            # Recalculado enquanto está em linha, e só então: empilhados, os
            # rótulos que quebram linha respondem outro mínimo e o limiar
            # derreteria a cada virada.
            self._limiar = self.largura_para_caber()
            if largura < self._limiar:
                self._virar(QBoxLayout.Direction.TopToBottom)
        elif largura >= self._limiar + self.FOLGA:
            self._virar(QBoxLayout.Direction.LeftToRight)

    def _virar(self, direcao: QBoxLayout.Direction) -> None:
        em_linha = direcao == QBoxLayout.Direction.LeftToRight
        self._caixa.setDirection(direcao)
        for i, (_, peso) in enumerate(self._itens):
            # Empilhados os cartões têm de ficar do tamanho do conteúdo: com
            # peso, dividiriam a altura sobrando e um cartão de três linhas
            # viraria um retângulo quase vazio.
            self._caixa.setStretch(i, peso if em_linha else 0)
        self.updateGeometry()


def faixa_central(interno, largura_maxima: int) -> QWidget:
    """Um bloco que cresce até um limite e depois para, centralizado.

    Esticar sem limite é tão ruim quanto não esticar. Maximizada num monitor
    de 1920, a janela dava 1230 pixels de largura ao botão "Iniciar" e 750 a
    uma caixa de três dígitos: a linha inteira virava um borrão horizontal e o
    olho perdia a relação entre o rótulo e o campo do outro lado.
    """
    miolo = QWidget()
    miolo.setMaximumWidth(largura_maxima)
    miolo.setLayout(interno)

    fora = QWidget()
    linha = QHBoxLayout(fora)
    linha.setContentsMargins(0, 0, 0, 0)
    # Peso alto no miolo e 1 nas sobras: ele fica com tudo o que puder até o
    # máximo, e só o que passar disso é que vira margem dos dois lados.
    linha.addStretch(1)
    linha.addWidget(miolo, 1000)
    linha.addStretch(1)
    return fora


def pagina_rolavel(conteudo: QWidget, nome: str = "pagina") -> QScrollArea:
    """Embrulha uma aba para que o que não couber role em vez de ser espremido.

    É isto que permite baixar o mínimo da janela: o mínimo de uma área de
    rolagem é o dela mesma, não o do conteúdo, então a janela passa a poder
    encolher até onde o usuário quiser sem nada se sobrepor.
    """
    area = QScrollArea()
    area.setObjectName(nome)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    area.setWidget(conteudo)
    return area


def trocar_conteudo(area: QScrollArea, novo: QWidget) -> None:
    """Põe outra página na área de rolagem e descarta a anterior.

    `takeWidget` antes de `setWidget` de propósito: a versão direta apaga a
    página velha NA HORA, e ela ainda pode estar no meio do despacho de um
    evento. `deleteLater` espera a volta ao laço principal.
    """
    antigo = area.takeWidget()
    area.setWidget(novo)
    if antigo is not None and antigo is not novo:
        antigo.setParent(None)
        antigo.deleteLater()


__all__ = [
    "LinhaAdaptavel",
    "faixa_central",
    "pagina_rolavel",
    "trocar_conteudo",
]
