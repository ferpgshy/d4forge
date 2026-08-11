"""Aba do Masterworking: o afixo alvo, os tetos e o progresso.

A configuracao inteira e' um campo - em qual afixo o Masterwork tem de cair.
Nao ha' valor a julgar aqui: o jogo sorteia QUAL afixo do item recebe o
aumento, e a pergunta e' so' se caiu no certo.

O campo e' editavel e nao uma lista fechada, de proposito. O Masterwork cai em
qualquer afixo do item, inclusive os que vieram do Tempering - e esses nao
estao no catalogo do Occultist nem vao estar. O catalogo entra como sugestao
para os nomes que ele conhece, e nao como restricao.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QStringListModel
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t
from ..masterwork.rules import MasterworkGoal, MasterworkLimits
from .mw_panel import MasterworkProgressPanel


class MasterworkTab(QWidget):
    """Configuracao e progresso do Masterworking, numa aba so'."""

    def __init__(self, catalog=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.catalog = catalog

        raiz = QVBoxLayout(self)
        raiz.setSpacing(12)

        # Os widgets com texto ficam guardados em atributos porque a troca de
        # idioma REAPROVEITA esta aba - refaze-la perderia a sessao em curso.
        # Ver `retranslate`.
        self.lbl_hint = QLabel(t("mw.hint"))
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setProperty("role", "hint")
        raiz.addWidget(self.lbl_hint)

        cartoes = QHBoxLayout()
        cartoes.setSpacing(12)
        cartoes.addWidget(self._build_goal(), 1)
        cartoes.addWidget(self._build_limits(), 1)
        raiz.addLayout(cartoes)

        self.status = QLabel(t("mw.idle"))
        # Enquanto nada rodou, o texto do estado é a frase FIXA de repouso e
        # deve acompanhar o idioma. Depois que o ciclo escreve nele, passa a ser
        # o último evento — e reescrevê-lo apagaria o que aconteceu.
        self._status_e_padrao = True
        self.status.setWordWrap(True)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setProperty("role", "accent")
        raiz.addWidget(self.status)

        self.progress = MasterworkProgressPanel()
        raiz.addWidget(self.progress, 1)

    # ------------------------------------------------------------- meta
    def _build_goal(self) -> QGroupBox:
        self.box_goal = caixa = QGroupBox(t("mw.goal_box"))
        col = QVBoxLayout(caixa)

        self.cmb_affix = QComboBox()
        self.cmb_affix.setEditable(True)
        self.cmb_affix.setMinimumWidth(320)
        self.cmb_affix.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

        # Busca por TRECHO, e nao pelo comeco: sao ~880 afixos e o nome quase
        # nunca comeca pela palavra que a gente lembra. Mesmo comportamento do
        # campo de alvo do Enchant.
        completer = QCompleter(self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setMaxVisibleItems(15)
        self._affix_model = QStringListModel(self)
        completer.setModel(self._affix_model)
        self.cmb_affix.setCompleter(completer)
        # O placeholder de um combo editavel mora no lineEdit; posto no combo
        # ele nao aparece, e o campo fica sendo uma caixa preta muda.
        self.cmb_affix.lineEdit().setPlaceholderText(t("mw.affix_ph"))
        self.cmb_affix.setToolTip(t("mw.affix_tip"))
        self.refresh_affixes()
        col.addWidget(self.cmb_affix)

        self.lbl_replace = QLabel(t("mw.replace_warn"))
        self.lbl_replace.setWordWrap(True)
        self.lbl_replace.setProperty("role", "hint")
        col.addSpacing(6)
        col.addWidget(self.lbl_replace)
        col.addStretch()
        return caixa

    # ------------------------------------------------------------ tetos
    def _build_limits(self) -> QGroupBox:
        self.box_limits = caixa = QGroupBox(t("mw.limits_box"))
        col = QVBoxLayout(caixa)

        linha_t = QHBoxLayout()
        self.lbl_attempts = QLabel(t("mw.max_attempts"))
        linha_t.addWidget(self.lbl_attempts)
        self.spin_attempts = QSpinBox()
        self.spin_attempts.setRange(1, 999)
        self.spin_attempts.setValue(50)
        linha_t.addWidget(self.spin_attempts, 1)
        col.addLayout(linha_t)

        linha_m = QHBoxLayout()
        self.lbl_minutes = QLabel(t("mw.max_minutes"))
        linha_m.addWidget(self.lbl_minutes)
        self.spin_minutes = QSpinBox()
        # Zero = sem teto de tempo. Mesma escolha do Tempering: quem quer o
        # afixo e nao se importa com o recurso nao precisa pedir licenca.
        self.spin_minutes.setRange(0, 600)
        self.spin_minutes.setValue(30)
        self.spin_minutes.setSpecialValueText(t("mw.no_cap"))
        linha_m.addWidget(self.spin_minutes, 1)
        col.addLayout(linha_m)

        self.lbl_cost = QLabel(t("mw.cost_warn"))
        self.lbl_cost.setWordWrap(True)
        self.lbl_cost.setProperty("role", "hint")
        col.addSpacing(6)
        col.addWidget(self.lbl_cost)
        col.addStretch()
        return caixa

    def refresh_affixes(self) -> None:
        """Repovoa a lista com o catalogo, preservando o que estava digitado.

        Sem filtro por peca, ao contrario do Enchant: o Masterwork cai em
        qualquer afixo do item, e nao ha' peca escolhida nesta tela.
        """
        if self.catalog is None:
            return
        atual = self.cmb_affix.currentText()
        nomes = sorted(e.name for e in self.catalog)
        self.cmb_affix.blockSignals(True)
        self.cmb_affix.clear()
        self.cmb_affix.addItems(nomes)
        self.cmb_affix.setCurrentText(atual)
        self.cmb_affix.blockSignals(False)
        self._affix_model.setStringList(nomes)

    # ------------------------------------------------------- idioma
    def retranslate(self) -> None:
        """Troca os textos NESTES widgets, sem refazer a aba.

        A aba e' reaproveitada na troca de idioma de proposito: refaze-la
        perderia a tabela de tentativas e o alvo digitado no meio de uma sessao.
        O preco e' este metodo, que precisa alcancar todo rotulo fixo - o que
        ficar de fora continua na lingua anterior.

        `status` so' entra enquanto ainda mostra a frase de repouso - ver
        `_status_e_padrao`.
        """
        if self._status_e_padrao:
            self.status.setText(t("mw.idle"))
        self.lbl_hint.setText(t("mw.hint"))
        self.box_goal.setTitle(t("mw.goal_box"))
        self.cmb_affix.lineEdit().setPlaceholderText(t("mw.affix_ph"))
        self.cmb_affix.setToolTip(t("mw.affix_tip"))
        self.lbl_replace.setText(t("mw.replace_warn"))
        self.box_limits.setTitle(t("mw.limits_box"))
        self.lbl_attempts.setText(t("mw.max_attempts"))
        self.lbl_minutes.setText(t("mw.max_minutes"))
        self.spin_minutes.setSpecialValueText(t("mw.no_cap"))
        self.lbl_cost.setText(t("mw.cost_warn"))
        self.progress.retranslate()

    # ------------------------------------------------------------ estado
    def set_status(self, texto: str, erro: bool = False) -> None:
        self._status_e_padrao = False
        self.status.setText(texto)
        self.status.setProperty("role", "error" if erro else "accent")
        # O Qt so' reaplica a folha de estilo quando a propriedade e' anunciada.
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def goal(self) -> MasterworkGoal:
        return MasterworkGoal(affix=self.cmb_affix.currentText().strip())

    def limits(self) -> MasterworkLimits:
        return MasterworkLimits(
            max_attempts=self.spin_attempts.value(),
            max_minutes=(self.spin_minutes.value() or None),
        )

    def load(self, goal: MasterworkGoal) -> None:
        """Repoe a configuracao salva nos controles."""
        self.cmb_affix.setCurrentText(goal.affix)
