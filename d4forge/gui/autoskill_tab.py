"""Aba do AutoSkill: as binds, os modos e o que está ativo agora.

Segue o molde das outras abas — os widgets com texto ficam em atributos porque
a troca de idioma REAPROVEITA a aba (refazê-la perderia o que estava ligado),
e tudo o que o usuário mexe é salvo sozinho com um atraso, como o alvo do
Enchant faz.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..autoskill.profile import SLOTS
from ..autoskill.rules import (
    AutoSkillConfig,
    ModoDeAtivacao,
    ModoDoSlot,
    SlotConfig,
)
from ..i18n import t
from . import style
from .bind_button import BindButton
from .responsive import LinhaAdaptavel

# Espera antes de gravar depois da última mexida. Mesmo motivo do alvo do
# Enchant: sem isto, arrastar um spinner escreveria o arquivo a cada passo.
ATRASO_DE_GRAVACAO_MS = 400


class PainelDeEstado(QFrame):
    """O que está ligado agora, e o que o ciclo está enxergando."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("metric")
        linha = QHBoxLayout(self)
        linha.setContentsMargins(12, 8, 12, 8)
        linha.setSpacing(14)

        self.luzes: dict[str, QLabel] = {}
        for chave in ("cast", "potion", "dodge", "tp"):
            luz = QLabel()
            luz.setProperty("role", "hint")
            self.luzes[chave] = luz
            linha.addWidget(luz)
        linha.addStretch()

        self.lbl_vida = QLabel()
        self.lbl_vida.setProperty("role", "accent")
        linha.addWidget(self.lbl_vida)

        self.estado = None
        self.retranslate()

    def atualizar(self, estado) -> None:
        self.estado = estado
        self.retranslate()

    def _nome(self, chave: str) -> str:
        return {
            "cast": "AutoCast",
            "potion": t("as.potion_box"),
            "dodge": t("as.dodge"),
            "tp": t("as.tp"),
        }[chave]

    def retranslate(self) -> None:
        est = self.estado
        ligados = getattr(est, "ligados", {}) or {}
        for chave, luz in self.luzes.items():
            aceso = bool(ligados.get(chave))
            luz.setText(f"{'●' if aceso else '○'} {self._nome(chave)}")
            luz.setStyleSheet(
                f"color: {style.DOURADO};" if aceso else ""
            )

        if est is None:
            self.lbl_vida.setText("")
            return
        if not est.em_foco:
            self.lbl_vida.setText(t("as.no_focus"))
            return
        vida = t("as.unknown") if est.vida_pct is None else f"{est.vida_pct}%"
        texto = f"{t('as.life')}: {vida}"
        if est.escudo_pct:
            texto += f"   ·   {t('as.shield')}: {est.escudo_pct}%"
        prontos = sum(1 for p in est.slots_prontos if p)
        if est.slots_prontos:
            texto += f"   ·   {prontos}/{len(est.slots_prontos)} {t('as.ready')}"
        self.lbl_vida.setText(texto)


class LinhaDeSlot:
    """Os três controles de um slot, guardados juntos."""

    def __init__(self, indice: int, cfg: SlotConfig, ao_mudar) -> None:
        self.indice = indice
        self.rotulo = QLabel(str(indice + 1))
        self.rotulo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.bind = BindButton(cfg.bind)
        self.bind.setMaximumWidth(220)
        self.bind.mudou.connect(lambda _b: ao_mudar())

        self.modo = QComboBox()
        for m in ModoDoSlot:
            self.modo.addItem("", m)
        self.modo.setCurrentIndex(list(ModoDoSlot).index(cfg.modo))
        self.modo.currentIndexChanged.connect(ao_mudar)

        self.prioridade = QSpinBox()
        self.prioridade.setRange(0, 99)
        self.prioridade.setValue(cfg.prioridade)
        self.prioridade.setToolTip(t("as.priority_tip"))
        self.prioridade.valueChanged.connect(ao_mudar)

        self.retranslate()

    def widgets(self):
        return (self.rotulo, self.bind, self.modo, self.prioridade)

    def para_config(self) -> SlotConfig:
        return SlotConfig(
            self.bind.bind(), self.modo.currentData(), self.prioridade.value()
        )

    def retranslate(self) -> None:
        for i, m in enumerate(ModoDoSlot):
            self.modo.setItemText(i, t(f"as.mode_{m.value}"))
        self.prioridade.setToolTip(t("as.priority_tip"))
        self.bind.retranslate()


class ControleWidgets:
    """Hotkey + modo de ativação, o par que se repete em todo recurso."""

    def __init__(self, controle, ao_mudar) -> None:
        self.rotulo = QLabel()
        self.bind = BindButton(controle.hotkey, aceita_roda=False)
        self.bind.mudou.connect(lambda _b: ao_mudar())
        self.modo = QComboBox()
        for m in ModoDeAtivacao:
            self.modo.addItem("", m)
        self.modo.setCurrentIndex(list(ModoDeAtivacao).index(controle.ativacao))
        self.modo.currentIndexChanged.connect(ao_mudar)
        self.retranslate()

    def em_linha(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.addWidget(self.rotulo)
        linha.addWidget(self.bind, 1)
        linha.addWidget(self.modo, 1)
        return linha

    def para_config(self, Controle):
        return Controle(self.bind.bind(), self.modo.currentData())

    def retranslate(self) -> None:
        self.rotulo.setText(t("as.control") + ":")
        self.rotulo.setProperty("role", "hint")
        for i, m in enumerate(ModoDeAtivacao):
            self.modo.setItemText(i, t("as.toggle") if m is ModoDeAtivacao.TOGGLE
                                 else t("as.hold"))
        self.bind.retranslate()


class AutoSkillTab(QWidget):
    """Configuração e estado do AutoSkill."""

    mudou = Signal()

    def __init__(self, config: AutoSkillConfig | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config or AutoSkillConfig()

        self._gravar = QTimer(self)
        self._gravar.setSingleShot(True)
        self._gravar.timeout.connect(self.mudou.emit)
        self._carregando = True

        raiz = QVBoxLayout(self)
        raiz.setSpacing(12)

        self.lbl_hint = QLabel(t("as.hint"))
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setProperty("role", "hint")
        raiz.addWidget(self.lbl_hint)

        self.painel = PainelDeEstado()
        raiz.addWidget(self.painel)

        raiz.addWidget(self._build_skills())

        cartoes = LinhaAdaptavel(espaco=12)
        cartoes.add(self._build_potion(), 1)
        cartoes.add(self._build_repeaters(), 1)
        raiz.addWidget(cartoes)

        self.status = QLabel(t("as.idle"))
        self.status.setWordWrap(True)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setProperty("role", "accent")
        self._status_e_padrao = True
        raiz.addWidget(self.status)
        raiz.addStretch(1)

        # Os cabecalhos da grade e os rotulos dos repetidores nascem vazios e
        # so' ganham texto aqui: e' a MESMA rotina que a troca de idioma usa, e
        # ter duas fontes de texto era como eles acabavam em branco na
        # abertura.
        self.retranslate()
        self._carregando = False

    # ------------------------------------------------------------- avisos
    def _ao_mudar(self) -> None:
        if not self._carregando:
            self._gravar.start(ATRASO_DE_GRAVACAO_MS)

    # ---------------------------------------------------------- habilidades
    def _build_skills(self) -> QGroupBox:
        self.box_skills = caixa = QGroupBox(t("as.skills_box"))
        col = QVBoxLayout(caixa)

        grade = QGridLayout()
        grade.setHorizontalSpacing(10)
        grade.setVerticalSpacing(6)
        self.cab_slot = QLabel()
        self.cab_bind = QLabel()
        self.cab_modo = QLabel()
        self.cab_prio = QLabel()
        for coluna, rotulo in enumerate(
            (self.cab_slot, self.cab_bind, self.cab_modo, self.cab_prio)
        ):
            rotulo.setProperty("role", "hint")
            grade.addWidget(rotulo, 0, coluna)
        grade.setColumnStretch(1, 2)
        grade.setColumnStretch(2, 2)

        self.linhas: list[LinhaDeSlot] = []
        for i in range(SLOTS):
            linha = LinhaDeSlot(i, self.config.cast.slots[i], self._ao_mudar)
            self.linhas.append(linha)
            for coluna, w in enumerate(linha.widgets()):
                grade.addWidget(w, i + 1, coluna)
        col.addLayout(grade)

        self.lbl_extras = QLabel(t("as.extras_hint"))
        self.lbl_extras.setWordWrap(True)
        self.lbl_extras.setProperty("role", "hint")
        col.addSpacing(6)
        col.addWidget(self.lbl_extras)

        self.caixa_extras = QVBoxLayout()
        col.addLayout(self.caixa_extras)
        self.linhas_extras: list[tuple[QWidget, BindButton, QComboBox]] = []
        for extra in self.config.cast.extras:
            self._add_extra(extra)

        self.btn_extra = QPushButton(t("as.add_extra"))
        self.btn_extra.clicked.connect(lambda: self._add_extra(None))
        col.addWidget(self.btn_extra, 0, Qt.AlignmentFlag.AlignLeft)

        linha_int = QHBoxLayout()
        self.lbl_intervalo = QLabel(t("as.interval"))
        self.lbl_intervalo.setProperty("role", "hint")
        self.spin_intervalo = QSpinBox()
        self.spin_intervalo.setRange(30, 2000)
        self.spin_intervalo.setSingleStep(10)
        self.spin_intervalo.setSuffix(" ms")
        self.spin_intervalo.setValue(self.config.cast.intervalo_ms)
        self.spin_intervalo.setToolTip(t("as.interval_tip"))
        self.spin_intervalo.valueChanged.connect(self._ao_mudar)
        linha_int.addWidget(self.lbl_intervalo)
        linha_int.addWidget(self.spin_intervalo, 1)
        linha_int.addStretch(1)
        col.addSpacing(6)
        col.addLayout(linha_int)

        self.ctrl_cast = ControleWidgets(self.config.cast.controle, self._ao_mudar)
        col.addLayout(self.ctrl_cast.em_linha())
        return caixa

    def _add_extra(self, cfg: SlotConfig | None) -> None:
        cfg = cfg or SlotConfig(modo=ModoDoSlot.SPAM)
        linha_w = QWidget()
        linha = QHBoxLayout(linha_w)
        linha.setContentsMargins(0, 0, 0, 0)

        bind = BindButton(cfg.bind)
        bind.mudou.connect(lambda _b: self._ao_mudar())
        modo = QComboBox()
        # Sem slot na barra não há cooldown para ler: só spam ou manual.
        for m in (ModoDoSlot.SPAM, ModoDoSlot.MANUAL):
            modo.addItem(t(f"as.mode_{m.value}"), m)
        modo.setCurrentIndex(0 if cfg.modo is not ModoDoSlot.MANUAL else 1)
        modo.currentIndexChanged.connect(self._ao_mudar)

        remover = QPushButton(t("as.remove"))
        linha.addWidget(bind, 2)
        linha.addWidget(modo, 2)
        linha.addWidget(remover, 0)
        self.caixa_extras.addWidget(linha_w)
        item = (linha_w, bind, modo)
        self.linhas_extras.append(item)

        def tirar() -> None:
            self.linhas_extras.remove(item)
            linha_w.setParent(None)
            linha_w.deleteLater()
            self._ao_mudar()

        remover.clicked.connect(tirar)
        self._ao_mudar()

    # ---------------------------------------------------------------- poção
    def _build_potion(self) -> QGroupBox:
        self.box_potion = caixa = QGroupBox(t("as.potion_box"))
        col = QVBoxLayout(caixa)
        p = self.config.potion

        linha_b = QHBoxLayout()
        self.lbl_potion_bind = QLabel(t("as.bind"))
        self.lbl_potion_bind.setProperty("role", "hint")
        self.bind_potion = BindButton(p.bind, aceita_roda=False)
        self.bind_potion.mudou.connect(lambda _b: self._ao_mudar())
        linha_b.addWidget(self.lbl_potion_bind)
        linha_b.addWidget(self.bind_potion, 1)
        col.addLayout(linha_b)

        linha_l = QHBoxLayout()
        self.lbl_limiar = QLabel(t("as.potion_below"))
        self.lbl_limiar.setProperty("role", "hint")
        self.spin_limiar = QSpinBox()
        self.spin_limiar.setRange(1, 99)
        self.spin_limiar.setSuffix(" %")
        self.spin_limiar.setValue(p.limiar_pct)
        self.spin_limiar.valueChanged.connect(self._ao_mudar)
        linha_l.addWidget(self.lbl_limiar)
        linha_l.addWidget(self.spin_limiar, 1)
        col.addLayout(linha_l)

        linha_c = QHBoxLayout()
        self.lbl_potion_cd = QLabel(t("as.potion_cd"))
        self.lbl_potion_cd.setProperty("role", "hint")
        self.spin_potion_cd = QDoubleSpinBox()
        self.spin_potion_cd.setRange(0.0, 60.0)
        self.spin_potion_cd.setDecimals(1)
        self.spin_potion_cd.setSingleStep(0.5)
        self.spin_potion_cd.setSuffix(" s")
        self.spin_potion_cd.setValue(p.cooldown_s)
        self.spin_potion_cd.valueChanged.connect(self._ao_mudar)
        linha_c.addWidget(self.lbl_potion_cd)
        linha_c.addWidget(self.spin_potion_cd, 1)
        col.addLayout(linha_c)

        self.chk_escudo = QCheckBox(t("as.potion_shield"))
        self.chk_escudo.setToolTip(t("as.potion_shield_tip"))
        self.chk_escudo.setChecked(p.beber_com_escudo)
        self.chk_escudo.toggled.connect(self._ao_mudar)
        col.addWidget(self.chk_escudo)

        self.ctrl_potion = ControleWidgets(p.controle, self._ao_mudar)
        col.addLayout(self.ctrl_potion.em_linha())
        col.addStretch()
        return caixa

    # --------------------------------------------------------- repetidores
    def _build_repeaters(self) -> QGroupBox:
        self.box_rep = caixa = QGroupBox(t("as.repeaters_box"))
        col = QVBoxLayout(caixa)
        self.lbl_rep_hint = QLabel(t("as.repeaters_hint"))
        self.lbl_rep_hint.setWordWrap(True)
        self.lbl_rep_hint.setProperty("role", "hint")
        col.addWidget(self.lbl_rep_hint)

        self.repetidores: dict[str, dict] = {}
        for rep in self.config.repetidores:
            titulo = QLabel()
            titulo.setProperty("role", "accent")
            col.addSpacing(4)
            col.addWidget(titulo)

            linha = QHBoxLayout()
            bind = BindButton(rep.bind)
            bind.mudou.connect(lambda _b: self._ao_mudar())
            intervalo = QSpinBox()
            intervalo.setRange(20, 5000)
            intervalo.setSingleStep(10)
            intervalo.setSuffix(" ms")
            intervalo.setValue(rep.intervalo_ms)
            intervalo.valueChanged.connect(self._ao_mudar)
            linha.addWidget(bind, 2)
            linha.addWidget(intervalo, 1)
            col.addLayout(linha)

            ctrl = ControleWidgets(rep.controle, self._ao_mudar)
            col.addLayout(ctrl.em_linha())
            self.repetidores[rep.nome] = {
                "titulo": titulo, "bind": bind,
                "intervalo": intervalo, "ctrl": ctrl,
            }
        col.addStretch()
        return caixa

    # -------------------------------------------------------------- estado
    def goal(self) -> AutoSkillConfig:
        """A configuração como está na tela."""
        from ..autoskill.rules import Controle

        cfg = self.config
        cfg.cast.slots = [linha.para_config() for linha in self.linhas]
        cfg.cast.extras = [
            SlotConfig(bind.bind(), modo.currentData(), 0)
            for _w, bind, modo in self.linhas_extras
            if bind.bind()
        ]
        cfg.cast.intervalo_ms = self.spin_intervalo.value()
        cfg.cast.controle = self.ctrl_cast.para_config(Controle)

        cfg.potion.bind = self.bind_potion.bind()
        cfg.potion.limiar_pct = self.spin_limiar.value()
        cfg.potion.cooldown_s = self.spin_potion_cd.value()
        cfg.potion.beber_com_escudo = self.chk_escudo.isChecked()
        cfg.potion.controle = self.ctrl_potion.para_config(Controle)

        for rep in cfg.repetidores:
            w = self.repetidores.get(rep.nome)
            if w is None:
                continue
            rep.bind = w["bind"].bind()
            rep.intervalo_ms = w["intervalo"].value()
            rep.controle = w["ctrl"].para_config(Controle)
        return cfg

    def set_status(self, texto: str, erro: bool = False) -> None:
        self._status_e_padrao = False
        self.status.setText(texto)
        self.status.setProperty("role", "error" if erro else "accent")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def mostrar_estado(self, estado) -> None:
        self.painel.atualizar(estado)

    # -------------------------------------------------------------- idioma
    def retranslate(self) -> None:
        if self._status_e_padrao:
            self.status.setText(t("as.idle"))
        self.lbl_hint.setText(t("as.hint"))
        self.box_skills.setTitle(t("as.skills_box"))
        self.cab_slot.setText(t("as.slot"))
        self.cab_bind.setText(t("as.bind"))
        self.cab_modo.setText(t("as.mode"))
        self.cab_prio.setText(t("as.priority"))
        for linha in self.linhas:
            linha.retranslate()
        self.lbl_extras.setText(t("as.extras_hint"))
        self.btn_extra.setText(t("as.add_extra"))
        self.lbl_intervalo.setText(t("as.interval"))
        self.spin_intervalo.setToolTip(t("as.interval_tip"))
        self.ctrl_cast.retranslate()

        self.box_potion.setTitle(t("as.potion_box"))
        self.lbl_potion_bind.setText(t("as.bind"))
        self.lbl_limiar.setText(t("as.potion_below"))
        self.lbl_potion_cd.setText(t("as.potion_cd"))
        self.chk_escudo.setText(t("as.potion_shield"))
        self.chk_escudo.setToolTip(t("as.potion_shield_tip"))
        self.bind_potion.retranslate()
        self.ctrl_potion.retranslate()

        self.box_rep.setTitle(t("as.repeaters_box"))
        self.lbl_rep_hint.setText(t("as.repeaters_hint"))
        for nome, w in self.repetidores.items():
            w["titulo"].setText(t(f"as.{nome}"))
            w["bind"].retranslate()
            w["ctrl"].retranslate()
        self.painel.retranslate()


__all__ = ["AutoSkillTab", "PainelDeEstado"]
