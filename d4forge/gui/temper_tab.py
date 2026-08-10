"""Aba do Tempering: a meta, a politica de recarga e o progresso.

Recarregar Temper Rerolls consome Pergaminhos. O padrao continua sendo PARAR e
avisar - gastar recurso sozinho nao pode ser o comportamento de fabrica -, mas
quem liga a recarga nao precisa passar por confirmacao nem por teto: as vezes
se quer o afixo e o Pergaminho e' o de menos, e a escolha e' de quem joga. O
aviso sobre o custo fica na tela como informacao, nao como pedagio.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t
from ..temper.rules import Recharge, TemperGoal
from .temper_panel import TemperProgressPanel


class TemperTab(QWidget):
    """Configuracao e progresso do Tempering, numa aba so'."""

    def __init__(self, settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings

        raiz = QVBoxLayout(self)
        raiz.setSpacing(12)

        dica = QLabel(t("temper.hint"))
        dica.setWordWrap(True)
        dica.setProperty("role", "hint")
        raiz.addWidget(dica)

        cartoes = QHBoxLayout()
        cartoes.setSpacing(12)
        cartoes.addWidget(self._build_goal(), 1)
        cartoes.addWidget(self._build_recharge(), 1)
        raiz.addLayout(cartoes)

        # Linha de estado, e nao so' o painel.
        #
        # A tabela de tentativas so' ganha linha quando um RESULTADO e' lido.
        # Quando o ciclo para antes disso - tela nao reconhecida, receita nao
        # escolhida, jogo noutra aba - nao ha' tentativa nenhuma, a tabela fica
        # vazia e a aba fica identica a parada. O motivo existia, mas so' dentro
        # dos detalhes tecnicos, que vem recolhidos: na pratica o app parecia
        # nao fazer nada.
        self.status = QLabel(t("temper.idle"))
        self.status.setWordWrap(True)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setProperty("role", "accent")
        raiz.addWidget(self.status)

        self.progress = TemperProgressPanel()
        raiz.addWidget(self.progress, 1)

        # Os sinais só entram depois que os DOIS cartões existem: `_sync` olha
        # widgets dos dois, e ligá-los dentro dos construtores fazia o primeiro
        # rádio marcado disparar `_sync` antes de o segundo cartão nascer.
        self.rb_ga.setChecked(True)
        self.rb_stop.setChecked(True)
        for rb in (self.rb_ga, self.rb_fraction, self.rb_value,
                   self.rb_stop, self.rb_one, self.rb_full):
            rb.toggled.connect(self._sync)
        self._sync()

    # ------------------------------------------------------------- meta
    def _build_goal(self) -> QGroupBox:
        caixa = QGroupBox(t("temper.goal_box"))
        col = QVBoxLayout(caixa)

        self.grupo_modo = QButtonGroup(self)
        self.rb_ga = QRadioButton(t("temper.mode_ga"))
        self.rb_ga.setToolTip(t("temper.mode_ga_tip"))
        self.rb_fraction = QRadioButton(t("temper.mode_fraction"))
        self.rb_value = QRadioButton(t("temper.mode_value"))
        for i, rb in enumerate((self.rb_ga, self.rb_fraction, self.rb_value)):
            self.grupo_modo.addButton(rb, i)

        # Os três em linhas próprias, e os dois com campo dentro de um HBox: o
        # rádio precisa ficar alinhado com os vizinhos, não colado no texto.
        linha_ga = QHBoxLayout()
        linha_ga.addWidget(self.rb_ga)
        linha_ga.addStretch()
        col.addLayout(linha_ga)

        linha_f = QHBoxLayout()
        linha_f.addWidget(self.rb_fraction)
        self.spin_fraction = QDoubleSpinBox()
        self.spin_fraction.setRange(1, 100)
        self.spin_fraction.setDecimals(0)
        self.spin_fraction.setValue(90)
        self.spin_fraction.setSuffix(t("temper.mode_fraction_suffix"))
        linha_f.addWidget(self.spin_fraction, 1)
        col.addLayout(linha_f)

        linha_v = QHBoxLayout()
        linha_v.addWidget(self.rb_value)
        self.spin_value = QDoubleSpinBox()
        self.spin_value.setRange(0, 1_000_000)
        self.spin_value.setDecimals(1)
        linha_v.addWidget(self.spin_value, 1)
        col.addLayout(linha_v)

        self.lbl_affix = QLabel(t("temper.affix_filter"))
        self.txt_affix = QLineEdit()
        self.txt_affix.setPlaceholderText(t("temper.affix_filter_ph"))
        self.txt_affix.setToolTip(t("temper.affix_filter_tip"))
        col.addSpacing(6)
        col.addWidget(self.lbl_affix)
        col.addWidget(self.txt_affix)
        col.addStretch()
        return caixa

    # -------------------------------------------------------- recarga
    def _build_recharge(self) -> QGroupBox:
        caixa = QGroupBox(t("temper.rerolls_box"))
        col = QVBoxLayout(caixa)

        self.grupo_recarga = QButtonGroup(self)
        self.rb_stop = QRadioButton(t("temper.recharge_stop"))
        self.rb_one = QRadioButton(t("temper.recharge_one"))
        self.rb_full = QRadioButton(t("temper.recharge_full"))
        for i, rb in enumerate((self.rb_stop, self.rb_one, self.rb_full)):
            self.grupo_recarga.addButton(rb, i)
            col.addWidget(rb)

        linha = QHBoxLayout()
        self.lbl_cap = QLabel(t("temper.recharge_cap"))
        self.spin_cap = QSpinBox()
        # Zero = sem teto, e e' o padrao: as vezes se quer o afixo e o
        # Pergaminho e' o de menos. Quem quiser um limite digita um.
        self.spin_cap.setRange(0, 999)
        self.spin_cap.setValue(0)
        self.spin_cap.setSpecialValueText(t("temper.recharge_no_cap"))
        self.spin_cap.setSuffix(t("temper.recharge_cap_suffix"))
        linha.addWidget(self.lbl_cap)
        linha.addWidget(self.spin_cap, 1)
        col.addLayout(linha)

        self.lbl_warn = QLabel(t("temper.recharge_warn"))
        self.lbl_warn.setWordWrap(True)
        self.lbl_warn.setProperty("role", "hint")
        col.addWidget(self.lbl_warn)

        col.addStretch()
        return caixa

    # ------------------------------------------------------------ estado
    def _sync(self) -> None:
        """Deixa visivel so' o que a escolha atual usa."""
        self.spin_fraction.setEnabled(self.rb_fraction.isChecked())
        self.spin_value.setEnabled(self.rb_value.isChecked())

        gasta = not self.rb_stop.isChecked()
        for w in (self.lbl_cap, self.spin_cap, self.lbl_warn):
            w.setVisible(gasta)

    def set_status(self, texto: str, erro: bool = False) -> None:
        self.status.setText(texto)
        self.status.setProperty("role", "error" if erro else "accent")
        # O Qt so' reaplica a folha de estilo quando a propriedade e' anunciada.
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def goal(self) -> TemperGoal:
        politica = (
            Recharge.STOP if self.rb_stop.isChecked()
            else Recharge.ONE if self.rb_one.isChecked()
            else Recharge.FULL
        )
        return TemperGoal(
            require_greater=self.rb_ga.isChecked(),
            min_fraction=(
                self.spin_fraction.value() / 100 if self.rb_fraction.isChecked()
                else None
            ),
            min_value=self.spin_value.value() if self.rb_value.isChecked() else None,
            affix_contains=self.txt_affix.text().strip(),
            recharge=politica,
            max_recharges=(self.spin_cap.value() or None),
        )

    def load(self, goal: TemperGoal) -> None:
        """Repõe a configuração salva nos controles."""
        self.rb_ga.setChecked(goal.require_greater)
        if goal.min_fraction is not None:
            self.rb_fraction.setChecked(True)
            self.spin_fraction.setValue(goal.min_fraction * 100)
        if goal.min_value is not None:
            self.rb_value.setChecked(True)
            self.spin_value.setValue(goal.min_value)
        self.txt_affix.setText(goal.affix_contains)

        {
            Recharge.STOP: self.rb_stop,
            Recharge.ONE: self.rb_one,
            Recharge.FULL: self.rb_full,
        }[goal.recharge].setChecked(True)
        self.spin_cap.setValue(goal.max_recharges or 0)
        self._sync()
