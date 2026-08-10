"""Painel de progresso da sessao.

Substitui o registro em texto corrido. O texto corrido tinha dois problemas: a
informacao que importa (quantas tentativas, ha quanto tempo, o que saiu em cada
rodada) ficava diluida entre dezenas de linhas de diagnostico, e o historico
congelava no idioma em que foi escrito.

A solucao para os dois e' a mesma: guardar os EVENTOS, nao as frases. O painel
mantem os dados estruturados (`_attempts`, `_current`, `_events`) e desenha a
partir deles; trocar de idioma so' pede um redesenho.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..engine import Attempt, EngineEvent, EventKind, Outcome
from ..i18n import t
from . import style

# Eventos que nao dizem nada ao usuario comum: existem para depurar e ficam
# guardados atras de "Detalhes tecnicos".
TECNICOS = {EventKind.CLICK, EventKind.STATE, EventKind.READ, EventKind.DECISION}


class Metric(QFrame):
    """Um numero grande com um rotulo pequeno embaixo."""

    def __init__(self, chave: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.chave = chave
        self.setObjectName("metric")
        col = QVBoxLayout(self)
        col.setContentsMargins(12, 10, 12, 10)
        col.setSpacing(2)

        self.valor = QLabel("—")
        self.valor.setFont(QFont("Segoe UI", 17, QFont.Weight.Bold))
        self.valor.setStyleSheet(f"color: {style.DOURADO};")
        self.valor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Afixo longo nao pode esticar o cartao e empurrar os vizinhos.
        self.valor.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        self.rotulo = QLabel(t(chave))
        self.rotulo.setProperty("role", "hint")
        self.rotulo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        col.addWidget(self.valor)
        col.addWidget(self.rotulo)

    def set(self, texto: str) -> None:
        self.valor.setText(texto)
        self.valor.setToolTip(texto)

    def retranslate(self) -> None:
        self.rotulo.setText(t(self.chave))


class ProgressPanel(QGroupBox):
    """Metricas + tabela de tentativas + detalhes tecnicos recolhiveis."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(t("progress.title"), parent)
        self._attempts: list[Attempt] = []
        self._events: list[EngineEvent] = []
        self._current: str = ""
        self._started: float | None = None
        self._elapsed: float = 0.0

        raiz = QVBoxLayout(self)
        raiz.setSpacing(10)

        linha = QHBoxLayout()
        linha.setSpacing(8)
        self._metricas = {
            nome: Metric(f"progress.{nome}")
            for nome in ("attempts", "elapsed", "rate", "current")
        }
        for nome, m in self._metricas.items():
            # O afixo e' texto de tamanho variavel; ganha o dobro do espaco.
            linha.addWidget(m, 2 if nome == "current" else 1)
        raiz.addLayout(linha)

        self.tabela = QTableWidget(0, len(self.COLUNAS))
        self.tabela.setObjectName("attempts")
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tabela.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.setShowGrid(False)
        cab = self.tabela.horizontalHeader()
        # Por padrao o ResizeToContents remede TODAS as linhas a cada insercao,
        # e o custo por tentativa cresce com a sessao (medido: 2,5 ms na linha
        # 50, 7,4 ms na 400). As duas colunas dimensionadas assim tem conteudo
        # de largura limitada - "#" e o veredito -, entao olhar as primeiras
        # linhas basta e o custo para de crescer.
        cab.setResizeContentsPrecision(20)
        # Primeira ("#") e última (veredito) têm conteúdo de largura limitada;
        # as do meio, que carregam o texto do afixo, dividem o que sobra.
        ultima = len(self.COLUNAS) - 1
        for coluna in range(len(self.COLUNAS)):
            modo = (
                QHeaderView.ResizeMode.ResizeToContents
                if coluna in (0, ultima) else QHeaderView.ResizeMode.Stretch
            )
            cab.setSectionResizeMode(coluna, modo)
        # Sem um mínimo, abrir os detalhes espremia a tabela até sobrar só o
        # cabeçalho — o painel perdia justamente o que veio mostrar.
        self.tabela.setMinimumHeight(130)
        raiz.addWidget(self.tabela, 1)

        self.vazio = QLabel(t("progress.empty"))
        self.vazio.setProperty("role", "hint")
        self.vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        raiz.addWidget(self.vazio)

        self.btn_detalhes = QToolButton()
        self.btn_detalhes.setText(t("progress.details"))
        self.btn_detalhes.setCheckable(True)
        self.btn_detalhes.setProperty("role", "link")
        self.btn_detalhes.setArrowType(Qt.ArrowType.RightArrow)
        self.btn_detalhes.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.btn_detalhes.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_detalhes.toggled.connect(self._toggle_detalhes)
        raiz.addWidget(self.btn_detalhes, 0, Qt.AlignmentFlag.AlignLeft)

        self.detalhes = QPlainTextEdit()
        self.detalhes.setReadOnly(True)
        self.detalhes.setMaximumBlockCount(3000)
        self.detalhes.setFixedHeight(110)
        self.detalhes.setVisible(False)
        raiz.addWidget(self.detalhes)

        # O relogio anda mesmo sem eventos: uma rodada demora ~1,5 s e sem isto
        # o "Tempo" so' pularia quando algo acontecesse.
        self._relogio = QTimer(self)
        self._relogio.setInterval(500)
        self._relogio.timeout.connect(self._tick)

        self.retranslate()

    # ------------------------------------------------------------- entrada
    def reset(self) -> None:
        self._attempts.clear()
        self._events.clear()
        self._current = ""
        self._started = time.monotonic()
        self._elapsed = 0.0
        self.tabela.setRowCount(0)
        self.detalhes.clear()
        self._relogio.start()
        self._redraw()

    def push(self, evt: EngineEvent) -> None:
        self._events.append(evt)
        if evt.kind is EventKind.ATTEMPT:
            tentativa = evt.data.get("attempt")
            if tentativa is not None:
                self._attempts.append(tentativa)
                self._add_row(tentativa)
        elif evt.kind is EventKind.READ and evt.data.get("affix"):
            self._current = str(evt.data["affix"])
        self._append_detail(evt)
        self._redraw()

    def note(self, key: str, **data) -> None:
        """Recado da propria interface (catalogo carregado, OCR pronto…).

        Entra pela mesma porta dos eventos do engine para que a troca de idioma
        o alcance tambem.
        """
        self.push(EngineEvent(EventKind.INFO, key, data))

    def finish(self, outcome: Outcome) -> None:
        self._relogio.stop()
        self._elapsed = outcome.elapsed_s
        self._redraw()

    # -------------------------------------------------------------- tabela
    #
    # O que muda entre o encantamento e o tempering e' SO' a linha da tabela: as
    # metricas, o relogio, os detalhes tecnicos e a troca de idioma sao os
    # mesmos. Por isso o painel expoe tres ganchos e a subclasse do tempering
    # sobrescreve apenas eles, em vez de duplicar a tela inteira.
    COLUNAS = ("progress.col_n", "progress.col_opt1",
               "progress.col_opt2", "progress.col_result")

    def _celulas(self, tentativa) -> list[str]:
        opcoes = [o.describe() for o in tentativa.options]
        return [
            str(tentativa.index),
            opcoes[0] if len(opcoes) > 0 else t("progress.none"),
            opcoes[1] if len(opcoes) > 1 else t("progress.none"),
            self._resultado(tentativa),
        ]

    def _destaques(self, tentativa) -> tuple[int, ...]:
        """Colunas em dourado: a opcao levada e o veredito.

        O resto fica em cinza para o olho achar a rodada que mudou algo.
        """
        if not tentativa.decision.accepted:
            return ()
        return (tentativa.decision.action.orb_index + 1, 3)

    def _dica(self, tentativa) -> str:
        return tentativa.decision.reason

    def _add_row(self, tentativa) -> None:
        """Tentativa nova entra no topo: e' a que o usuario quer ver."""
        self.tabela.insertRow(0)
        celulas = self._celulas(tentativa)
        dica = self._dica(tentativa)
        for coluna, texto in enumerate(celulas):
            item = QTableWidgetItem(texto)
            item.setToolTip(dica or texto)
            if coluna == 0:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabela.setItem(0, coluna, item)

        for coluna in self._destaques(tentativa):
            celula = self.tabela.item(0, coluna)
            if celula is not None:
                celula.setForeground(QColor(style.DOURADO))
        self.tabela.scrollToTop()

    def _resultado(self, tentativa) -> str:
        d = tentativa.decision
        if d.goal_reached:
            return t("progress.goal")
        if d.accepted:
            return t("progress.took_n", index=d.action.orb_index + 1)
        return t("progress.kept")

    def _append_detail(self, evt: EngineEvent) -> None:
        marca = {
            EventKind.SUCCESS: ">>>",
            EventKind.ERROR: "!!!",
            EventKind.STOPPED: "---",
            EventKind.ATTEMPT: " * ",
        }.get(evt.kind, "   ")
        self.detalhes.appendPlainText(f"{marca} {evt.message}")

    def _toggle_detalhes(self, aberto: bool) -> None:
        self.detalhes.setVisible(aberto)
        self.btn_detalhes.setArrowType(
            Qt.ArrowType.DownArrow if aberto else Qt.ArrowType.RightArrow
        )

    # -------------------------------------------------------------- desenho
    def _tick(self) -> None:
        if self._started is not None:
            self._elapsed = time.monotonic() - self._started
        self._metricas["elapsed"].set(_clock(self._elapsed))

    def _redraw(self) -> None:
        n = len(self._attempts)
        self._metricas["attempts"].set(str(n) if self._started else "—")
        self._metricas["elapsed"].set(_clock(self._elapsed) if self._started else "—")
        self._metricas["rate"].set(
            t("progress.rate_unit", seconds=self._elapsed / n) if n else "—"
        )
        self._metricas["current"].set(self._current or t("progress.none"))
        self.vazio.setVisible(n == 0)
        self.tabela.setVisible(n > 0)

    def retranslate(self) -> None:
        """Redesenha tudo no idioma corrente, a partir dos dados guardados."""
        self.setTitle(t("progress.title"))
        for m in self._metricas.values():
            m.retranslate()
        self.tabela.setHorizontalHeaderLabels([t(c) for c in self.COLUNAS])
        self.vazio.setText(t("progress.empty"))
        self.btn_detalhes.setText(t("progress.details"))

        # A ultima coluna e' a unica traduzida na tabela; as outras sao texto do
        # jogo e nao mudam de idioma.
        ultima = len(self.COLUNAS) - 1
        for linha, tentativa in enumerate(reversed(self._attempts)):
            celula = self.tabela.item(linha, ultima)
            if celula is not None:
                celula.setText(self._celulas(tentativa)[ultima])

        self.detalhes.clear()
        for evt in self._events:
            self._append_detail(evt)
        self._redraw()


def _clock(segundos: float) -> str:
    minutos, s = divmod(int(segundos), 60)
    return f"{minutos}:{s:02d}"
