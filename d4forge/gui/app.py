"""Janela principal do d4forge."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt, QStringListModel, QTimer
from PySide6.QtGui import QFont, QIcon, QValidator
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..affixes import AffixCatalog, AffixEntry, Slot, Unit, looks_like_affix_name
from ..automation.safety import VK_F12, Guard, Limits, key_pressed_once
from ..automation.sendinput import DEFAULT_PROFILE as DEFAULT_INPUT
from ..automation.sendinput import PROFILES
from ..catalog_import import import_full_catalog, purge_ocr_garbage
from ..engine import EnchantEngine, EngineEvent, EventKind, Outcome
from ..i18n import LANGUAGES, set_language, t
from ..profile import DEFAULT_PROFILE
from ..profiling import Profiler
from ..rules import Comparison, RuleSet, TargetRule
from ..vision.ocr import OcrEngine
from . import style
from .frameless import FramelessMixin, TitleBarArea
from .worker import EngineWorker, WarmupWorker

VK_F9 = 0x78

log = logging.getLogger(__name__)


@dataclass
class AppState:
    settings: config.Settings
    catalog: AffixCatalog
    ruleset: RuleSet
    ocr: OcrEngine
    profiler: Profiler
    profile: object = DEFAULT_PROFILE
    purged: list[str] = field(default_factory=list)
    imported: int = 0

    @classmethod
    def load(cls) -> "AppState":
        config.ensure_dirs()
        settings = config.Settings.load()
        set_language(settings.language)

        catalog = AffixCatalog.load(config.CATALOG_PATH)
        # O catálogo já vem completo: importar era um passo que todo mundo
        # precisava dar e ninguém adivinhava. É idempotente e nunca sobrescreve
        # o que você editou.
        imported = import_full_catalog(catalog)
        purged = purge_ocr_garbage(catalog)
        if imported or purged:
            catalog.save(config.CATALOG_PATH)

        return cls(
            settings=settings,
            catalog=catalog,
            ruleset=RuleSet.load(config.RULES_PATH),
            ocr=OcrEngine(data_dir=config.DATA_DIR),
            profiler=Profiler.load(config.TIMINGS_PATH),
            purged=purged,
            imported=imported,
        )

    def save(self) -> None:
        self.settings.save()
        self.catalog.save(config.CATALOG_PATH)
        self.ruleset.save(config.RULES_PATH)
        self.ocr.save()
        self.profiler.save(config.TIMINGS_PATH)


class UnitDelegate(QStyledItemDelegate):
    """Editor de unidade criado só quando a célula entra em edição.

    Um QComboBox por linha custava 3,2 s para montar as ~880 linhas do
    catálogo, e o mesmo tanto a cada troca de idioma. O delegate cria um
    widget de cada vez, quando alguém realmente vai mexer.
    """

    def createEditor(self, parent, option, index):  # noqa: N802 - assinatura do Qt
        combo = QComboBox(parent)
        for unit in Unit:
            combo.addItem(unit.value, unit)
        return combo

    def setEditorData(self, editor, index):  # noqa: N802
        texto = index.data() or Unit.FLAT.value
        posicao = editor.findText(texto)
        editor.setCurrentIndex(max(0, posicao))

    def setModelData(self, editor, model, index):  # noqa: N802
        model.setData(index, editor.currentText())


class ValueSpinBox(QDoubleSpinBox):
    """Campo de valor que não força casa decimal.

    A maioria dos afixos é inteira ("+1450 Maximum Life") e um QDoubleSpinBox
    comum exibiria "1450,0", obrigando a conviver com uma casa que não existe.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setDecimals(2)
        self.setRange(0, 1_000_000)
        self.setGroupSeparatorShown(False)
        self.setKeyboardTracking(False)

    def textFromValue(self, value: float) -> str:
        if abs(value - round(value)) < 1e-9:
            return str(int(round(value)))
        return f"{value:g}".replace(".", self.locale().decimalPoint())

    def valueFromText(self, text: str) -> float:
        try:
            return float(text.strip().replace(",", "."))
        except ValueError:
            return 0.0

    def validate(self, text: str, pos: int):
        if text.strip() in ("", "-", ",", "."):
            return (QValidator.State.Intermediate, text, pos)
        try:
            float(text.strip().replace(",", "."))
        except ValueError:
            return (QValidator.State.Invalid, text, pos)
        return (QValidator.State.Acceptable, text, pos)


class MainWindow(FramelessMixin, QMainWindow):
    def __init__(self, app_state: AppState) -> None:
        super().__init__()
        self.app = app_state
        self.engine_worker: EngineWorker | None = None
        self._unknown: dict[str, int] = {}
        self._catalog_carregado = False

        self.setWindowTitle(t("app.window"))
        self.resize(1020, 760)
        self.setMinimumSize(860, 620)
        self.setup_frameless()

        icone = Path(config.RESOURCE_DIR) / "d4forge" / "resources" / "d4forge.ico"
        if not icone.exists():
            icone = Path(__file__).resolve().parent.parent / "resources" / "d4forge.ico"
        if icone.exists():
            self.setWindowIcon(QIcon(str(icone)))

        raiz = QWidget()
        raiz.setObjectName("shell")
        layout = QVBoxLayout(raiz)
        layout.setContentsMargins(1, 1, 1, 1)  # deixa a borda do shell aparecer
        layout.setSpacing(0)
        layout.addWidget(self._build_header())

        corpo = QWidget()
        corpo_layout = QVBoxLayout(corpo)
        corpo_layout.setContentsMargins(18, 12, 18, 16)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_panel(), t("tab.panel"))
        self.tabs.addTab(self._build_target(), t("tab.target"))
        self.tabs.addTab(self._build_catalog(), t("tab.catalog"))
        # A tabela do catálogo tem ~880 linhas: montá-la só quando alguém abre a
        # aba tira quase um segundo da abertura e da troca de idioma.
        self.tabs.currentChanged.connect(self._on_tab_changed)
        corpo_layout.addWidget(self.tabs)
        layout.addWidget(corpo, 1)
        self.setCentralWidget(raiz)

        self._reload_target()

        if self.app.purged:
            self._log(t("msg.purged", names=", ".join(self.app.purged)))
        self._log(t("msg.catalog_loaded", count=len(self.app.catalog)))

        # Atalho global: funciona com o Diablo IV em foco, que é quando a
        # janela do app está inacessível.
        self._hotkeys = QTimer(self)
        self._hotkeys.timeout.connect(self._poll_hotkeys)
        self._hotkeys.start(80)
        key_pressed_once(VK_F9)
        key_pressed_once(VK_F12)

        # Carrega o leitor agora, para o custo de partida não cair sobre a
        # primeira leitura do ciclo.
        self._warmup = WarmupWorker(self.app)
        self._warmup.ready.connect(lambda ms: self._log(t("msg.ocr_ready", ms=ms)))
        self._warmup.start()

    # ---------------------------------------------------------- cabeçalho
    def _build_header(self) -> QWidget:
        """Cabeçalho e barra de título ao mesmo tempo: a janela não tem moldura
        do Windows, então arrastar, maximizar e fechar moram aqui."""
        header = TitleBarArea(self)
        header.setObjectName("header")
        header.setFixedHeight(82)
        fora = QVBoxLayout(header)
        fora.setContentsMargins(0, 0, 0, 0)
        fora.setSpacing(0)

        # Faixa de cima: idioma e botões da janela.
        topo = QHBoxLayout()
        topo.setContentsMargins(0, 0, 0, 0)
        topo.setSpacing(0)
        topo.addStretch()

        self.btn_lang = QPushButton()
        self.btn_lang.setObjectName("globe")
        self.btn_lang.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(self)
        for code, nome in LANGUAGES.items():
            menu.addAction(nome, lambda checked=False, c=code: self._set_language(c))
        self.btn_lang.setMenu(menu)
        self._refresh_lang_button()
        topo.addWidget(self.btn_lang)
        topo.addSpacing(10)

        for nome, simbolo, slot in (
            ("btnMin", "–", self.showMinimized),
            ("btnMax", "□", self.toggle_maximize),
            ("btnClose", "✕", self.close),
        ):
            botao = QPushButton(simbolo)
            botao.setObjectName(nome)
            botao.setProperty("titlebar", True)
            botao.setCursor(Qt.CursorShape.ArrowCursor)
            botao.clicked.connect(slot)
            topo.addWidget(botao)
        fora.addLayout(topo)

        # Faixa de baixo: a marca.
        marca_linha = QHBoxLayout()
        marca_linha.setContentsMargins(22, 0, 18, 10)
        marca = QVBoxLayout()
        marca.setSpacing(0)
        titulo = QLabel(t("app.title"))
        titulo.setObjectName("brand")
        self.lbl_subtitle = QLabel(t("app.subtitle"))
        self.lbl_subtitle.setObjectName("brandSub")
        marca.addWidget(titulo)
        marca.addWidget(self.lbl_subtitle)
        marca_linha.addLayout(marca)
        marca_linha.addStretch()
        fora.addLayout(marca_linha)
        return header

    def _refresh_lang_button(self) -> None:
        self.btn_lang.setText(f"  {LANGUAGES.get(self.app.settings.language, '')}  ▾")

    def _set_language(self, code: str) -> None:
        if code == self.app.settings.language:
            return
        self.app.settings.language = set_language(code)
        self.app.settings.save()
        self._rebuild_ui()

    def _rebuild_ui(self) -> None:
        """Recria as abas no idioma novo, preservando o que estava preenchido.

        A tabela do catálogo NÃO é repovoada aqui: são ~880 linhas com um
        combo em cada, e refazê-las travava a janela por mais de um segundo a
        cada troca de idioma. Só os cabeçalhos mudam de língua; as linhas são
        as mesmas.
        """
        indice = self.tabs.currentIndex()
        self._save_target(silencioso=True)
        registro = self.log.toPlainText()

        self.setUpdatesEnabled(False)
        try:
            while self.tabs.count():
                self.tabs.removeTab(0)
            self.tabs.addTab(self._build_panel(), t("tab.panel"))
            self.tabs.addTab(self._build_target(), t("tab.target"))
            # A aba do catálogo é a MESMA de antes, só com os rótulos trocados:
            # o conteúdo dela não depende de idioma.
            self._retranslate_catalog()
            self.tabs.addTab(self._catalog_page, t("tab.catalog"))
            self.tabs.setCurrentIndex(indice)

            self._reload_target()
            self.log.setPlainText(registro)
            self.lbl_subtitle.setText(t("app.subtitle"))
            self._refresh_lang_button()
        finally:
            self.setUpdatesEnabled(True)

    def _on_tab_changed(self, indice: int) -> None:
        if self.tabs.tabText(indice) == t("tab.catalog") and not self._catalog_carregado:
            self._reload_catalog()

    def _retranslate_catalog(self) -> None:
        self.lbl_catalog_hint.setText(t("catalog.hint"))
        self.tbl_catalog.setHorizontalHeaderLabels([
            t("catalog.affix"), t("catalog.unit"),
            t("catalog.min"), t("catalog.max"), t("catalog.slots"),
        ])
        self.btn_catalog_add.setText(t("catalog.add"))
        self.btn_catalog_remove.setText(t("catalog.remove"))
        self.btn_catalog_save.setText(t("catalog.save"))
        if self._catalog_carregado:
            self.lbl_catalog_count.setText(
                t("catalog.count", count=self.tbl_catalog.rowCount())
            )

    # -------------------------------------------------------------- painel
    def _build_panel(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        self.status = QLabel(t("panel.idle"))
        self.status.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet(f"color: {style.COR_ESTADO['idle']};")
        layout.addWidget(self.status)

        self.substatus = QLabel(t("panel.hint"))
        self.substatus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.substatus.setProperty("role", "hint")
        layout.addWidget(self.substatus)

        botoes = QHBoxLayout()
        botoes.setSpacing(10)
        self.btn_start = QPushButton(f"{t('panel.start')}   ·   F9")
        self.btn_start.setObjectName("start")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.clicked.connect(self._start)
        self.btn_stop = QPushButton(f"{t('panel.stop')}   ·   F12")
        self.btn_stop.setObjectName("stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)
        botoes.addWidget(self.btn_start, 2)
        botoes.addWidget(self.btn_stop, 1)
        layout.addLayout(botoes)

        dica = QLabel(t("panel.hotkey_hint"))
        dica.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dica.setProperty("role", "accent")
        layout.addWidget(dica)

        cartoes = QHBoxLayout()
        cartoes.setSpacing(12)

        limites = QGroupBox(t("panel.limits"))
        col = QVBoxLayout(limites)
        self.spin_attempts = QSpinBox()
        self.spin_attempts.setRange(1, 100_000)
        self.spin_attempts.setValue(self.app.settings.max_attempts)
        col.addLayout(_campo(t("panel.max_attempts"), self.spin_attempts))

        self.spin_minutes = QDoubleSpinBox()
        self.spin_minutes.setRange(0, 1440)
        self.spin_minutes.setDecimals(0)
        self.spin_minutes.setValue(self.app.settings.max_minutes or 0)
        self.spin_minutes.setSpecialValueText(t("panel.no_limit"))
        col.addLayout(_campo(t("panel.max_minutes"), self.spin_minutes))

        self.spin_delay = QDoubleSpinBox()
        self.spin_delay.setRange(0, 30)
        self.spin_delay.setDecimals(0)
        self.spin_delay.setSuffix(" s")
        self.spin_delay.setValue(self.app.settings.start_delay_s)
        self.spin_delay.setToolTip(t("panel.start_delay_tip"))
        col.addLayout(_campo(t("panel.start_delay"), self.spin_delay))
        col.addStretch()
        cartoes.addWidget(limites, 1)

        seguranca = QGroupBox(t("panel.safety"))
        col2 = QVBoxLayout(seguranca)
        self.chk_foreground = QCheckBox(t("panel.abort_focus"))
        self.chk_foreground.setChecked(self.app.settings.require_foreground)
        self.chk_mouse = QCheckBox(t("panel.abort_mouse"))
        self.chk_mouse.setChecked(self.app.settings.abort_on_mouse_move)
        self.chk_focus = QCheckBox(t("panel.focus_game"))
        self.chk_focus.setChecked(self.app.settings.focus_game_on_start)
        col2.addWidget(self.chk_foreground)
        col2.addWidget(self.chk_mouse)
        col2.addWidget(self.chk_focus)

        self.cmb_speed = QComboBox()
        for label in PROFILES:
            self.cmb_speed.addItem(label)
        self.cmb_speed.setCurrentText(self.app.settings.input_speed)
        self.cmb_speed.setToolTip(t("panel.mouse_speed_tip"))
        col2.addLayout(_campo(t("panel.mouse_speed"), self.cmb_speed))
        col2.addStretch()
        cartoes.addWidget(seguranca, 1)
        layout.addLayout(cartoes)

        registro = QGroupBox(t("panel.log"))
        col3 = QVBoxLayout(registro)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        col3.addWidget(self.log)
        layout.addWidget(registro, 1)

        self.box_unknown = QGroupBox(t("unknown.box"))
        self.box_unknown.setVisible(False)
        linha = QHBoxLayout(self.box_unknown)
        self.lbl_unknown = QLabel("")
        self.lbl_unknown.setWordWrap(True)
        linha.addWidget(self.lbl_unknown, 1)
        btn = QPushButton(t("unknown.add"))
        btn.clicked.connect(self._absorb_unknown)
        linha.addWidget(btn)
        layout.addWidget(self.box_unknown)
        return page

    # --------------------------------------------------------------- alvo
    def _build_target(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        hint = QLabel(t("target.hint"))
        hint.setProperty("role", "hint")
        layout.addWidget(hint)

        box = QGroupBox(t("target.box"))
        form = QVBoxLayout(box)
        form.setSpacing(10)

        linha1 = QHBoxLayout()
        linha1.addWidget(QLabel(t("target.slot") + ":"))
        self.cmb_slot = QComboBox()
        self.cmb_slot.addItem(t("target.slot_all"), None)
        for slot in Slot:
            self.cmb_slot.addItem(slot.label, slot)
        self.cmb_slot.setToolTip(t("target.slot_tip"))
        self.cmb_slot.currentIndexChanged.connect(self._refresh_affix_choices)
        linha1.addWidget(self.cmb_slot)

        linha1.addSpacing(14)
        linha1.addWidget(QLabel(t("target.affix") + ":"))
        self.cmb_affix = QComboBox()
        self.cmb_affix.setEditable(True)
        self.cmb_affix.setMinimumWidth(320)
        self.cmb_affix.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

        # Busca por trecho, não por começo: são ~880 afixos e o nome quase nunca
        # começa pela palavra que a gente lembra.
        completer = QCompleter(self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setMaxVisibleItems(15)
        self._affix_model = QStringListModel(self)
        completer.setModel(self._affix_model)
        self.cmb_affix.setCompleter(completer)
        self.cmb_affix.lineEdit().setPlaceholderText(t("target.search_placeholder"))
        self.cmb_affix.currentTextChanged.connect(self._update_unit_hint)
        linha1.addWidget(self.cmb_affix, 1)
        form.addLayout(linha1)

        linha2 = QHBoxLayout()
        linha2.addWidget(QLabel(t("target.condition") + ":"))
        self.cmb_comparison = QComboBox()
        for comp in Comparison:
            self.cmb_comparison.addItem(comp.label, comp)
        self.cmb_comparison.setCurrentIndex(list(Comparison).index(Comparison.GE))
        linha2.addWidget(self.cmb_comparison)
        self.spin_value = ValueSpinBox()
        linha2.addWidget(self.spin_value)
        self.lbl_unit = QLabel("")
        self.lbl_unit.setProperty("role", "accent")
        linha2.addWidget(self.lbl_unit)
        linha2.addStretch()
        form.addLayout(linha2)

        linha3 = QHBoxLayout()
        linha3.addWidget(QLabel(t("target.min_roll") + ":"))
        self.spin_quality = QDoubleSpinBox()
        self.spin_quality.setRange(0, 100)
        self.spin_quality.setDecimals(0)
        self.spin_quality.setSuffix(t("target.min_roll_suffix"))
        self.spin_quality.setSpecialValueText(t("target.min_roll_ignore"))
        self.spin_quality.setToolTip(t("target.min_roll_tip"))
        linha3.addWidget(self.spin_quality)
        linha3.addStretch()
        form.addLayout(linha3)

        self.chk_climb = QCheckBox(t("target.climb"))
        self.chk_climb.setChecked(True)
        self.chk_climb.setToolTip(t("target.climb_tip"))
        form.addWidget(self.chk_climb)
        layout.addWidget(box)

        self.lbl_target_summary = QLabel("")
        self.lbl_target_summary.setProperty("role", "hint")
        layout.addWidget(self.lbl_target_summary)

        salvar = QPushButton(t("target.save"))
        salvar.clicked.connect(self._save_target)
        layout.addWidget(salvar)
        layout.addStretch(1)
        return page

    def _refresh_affix_choices(self, *_args) -> None:
        atual = self.cmb_affix.currentText()
        slot = self.cmb_slot.currentData() if hasattr(self, "cmb_slot") else None
        nomes = sorted(e.name for e in self.app.catalog.for_slot(slot))
        self.cmb_affix.blockSignals(True)
        self.cmb_affix.clear()
        self.cmb_affix.addItems(nomes)
        self.cmb_affix.setCurrentText(atual)
        self.cmb_affix.blockSignals(False)
        if hasattr(self, "_affix_model"):
            self._affix_model.setStringList(nomes)
        self._update_unit_hint()

    def _update_unit_hint(self, *_args) -> None:
        entry = self.app.catalog.entries.get(self.cmb_affix.currentText().strip())
        if entry is None:
            self.lbl_unit.setText(f"({t('target.off_catalog')})")
            return
        unidade = {
            "flat": t("target.unit_flat"),
            "percent": t("target.unit_percent"),
            "rank": t("target.unit_rank"),
        }[entry.unit.value]
        if entry.vmin is not None and entry.vmax is not None:
            faixa = t("target.range", vmin=entry.vmin, vmax=entry.vmax)
        else:
            faixa = t("target.no_range")
        self.lbl_unit.setText(f"{unidade}  ·  {faixa}")

    def _reload_target(self) -> None:
        self._refresh_affix_choices()
        rule = self.app.ruleset.rules[0] if self.app.ruleset.rules else None
        if rule is None:
            self.lbl_target_summary.setText(t("target.none"))
            return
        self.cmb_affix.setCurrentText(rule.affix_name)
        self.cmb_comparison.setCurrentIndex(list(Comparison).index(rule.comparison))
        self.spin_value.setValue(rule.threshold)
        self.spin_quality.setValue(0 if rule.min_quality is None else rule.min_quality * 100)
        self.chk_climb.setChecked(rule.climb)
        self.lbl_target_summary.setText(t("target.saved", rule=rule.describe()))
        self._update_unit_hint()

    def _save_target(self, silencioso: bool = False) -> None:
        nome = self.cmb_affix.currentText().strip()
        if not nome:
            self.app.ruleset.rules = []
            self.lbl_target_summary.setText(t("target.none"))
            return
        qualidade = self.spin_quality.value()
        rule = TargetRule(
            affix_name=nome,
            comparison=self.cmb_comparison.currentData(),
            threshold=self.spin_value.value(),
            min_quality=None if qualidade <= 0 else qualidade / 100.0,
            climb=self.chk_climb.isChecked(),
        )
        self.app.ruleset.rules = [rule]
        if not silencioso:
            self.app.ruleset.save(config.RULES_PATH)
        self.lbl_target_summary.setText(t("target.saved", rule=rule.describe()))

    # ----------------------------------------------------------- catálogo
    def _build_catalog(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        self.lbl_catalog_hint = QLabel(t("catalog.hint"))
        self.lbl_catalog_hint.setProperty("role", "hint")
        self.lbl_catalog_hint.setWordWrap(True)
        layout.addWidget(self.lbl_catalog_hint)

        self.tbl_catalog = QTableWidget(0, 5)
        self.tbl_catalog.setHorizontalHeaderLabels([
            t("catalog.affix"), t("catalog.unit"),
            t("catalog.min"), t("catalog.max"), t("catalog.slots"),
        ])
        self.tbl_catalog.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.tbl_catalog.verticalHeader().setVisible(False)
        self.tbl_catalog.setItemDelegateForColumn(1, UnitDelegate(self))
        layout.addWidget(self.tbl_catalog, 1)

        linha = QHBoxLayout()
        self.lbl_catalog_count = QLabel("")
        self.lbl_catalog_count.setProperty("role", "hint")
        linha.addWidget(self.lbl_catalog_count)
        linha.addStretch()
        self.btn_catalog_add = QPushButton(t("catalog.add"))
        self.btn_catalog_add.clicked.connect(
            lambda: self._append_catalog_row(AffixEntry(t("catalog.new_affix")))
        )
        self.btn_catalog_remove = QPushButton(t("catalog.remove"))
        self.btn_catalog_remove.clicked.connect(self._remove_catalog_row)
        self.btn_catalog_save = QPushButton(t("catalog.save"))
        self.btn_catalog_save.clicked.connect(self._save_catalog)
        linha.addWidget(self.btn_catalog_add)
        linha.addWidget(self.btn_catalog_remove)
        linha.addWidget(self.btn_catalog_save)
        layout.addLayout(linha)
        self._catalog_page = page
        return page

    def _remove_catalog_row(self) -> None:
        linha = self.tbl_catalog.currentRow()
        if linha >= 0:
            self.tbl_catalog.removeRow(linha)

    def _reload_catalog(self) -> None:
        # setUpdatesEnabled: sem isso o Qt redesenha a cada uma das ~880 linhas.
        self.tbl_catalog.setUpdatesEnabled(False)
        try:
            self.tbl_catalog.setRowCount(0)
            for entry in self.app.catalog:
                self._append_catalog_row(entry)
        finally:
            self.tbl_catalog.setUpdatesEnabled(True)
        self._catalog_carregado = True
        self.lbl_catalog_count.setText(t("catalog.count", count=len(self.app.catalog)))

    def _append_catalog_row(self, entry: AffixEntry) -> None:
        tabela = self.tbl_catalog
        r = tabela.rowCount()
        tabela.insertRow(r)
        tabela.setItem(r, 0, QTableWidgetItem(entry.name))
        tabela.setItem(r, 1, QTableWidgetItem(entry.unit.value))
        tabela.setItem(r, 2, QTableWidgetItem("" if entry.vmin is None else f"{entry.vmin:g}"))
        tabela.setItem(r, 3, QTableWidgetItem("" if entry.vmax is None else f"{entry.vmax:g}"))
        tabela.setItem(r, 4, QTableWidgetItem(", ".join(sorted(s.value for s in entry.slots))))

    def _save_catalog(self) -> None:
        if not self._catalog_carregado:
            return  # tabela ainda nem foi montada; nada a salvar
        antigo = self.app.catalog.entries
        catalogo = AffixCatalog()
        tabela = self.tbl_catalog
        for r in range(tabela.rowCount()):
            nome = (tabela.item(r, 0).text() if tabela.item(r, 0) else "").strip()
            if not nome:
                continue
            texto_unidade = (tabela.item(r, 1).text() if tabela.item(r, 1) else "").strip()
            try:
                unidade = Unit(texto_unidade)
            except ValueError:
                unidade = Unit.FLAT

            slots: set[Slot] = set()
            texto = tabela.item(r, 4).text() if tabela.item(r, 4) else ""
            for token in texto.replace(";", ",").split(","):
                token = token.strip().lower()
                if not token:
                    continue
                try:
                    slots.add(Slot(token))
                except ValueError:
                    self._log(t("catalog.unknown_slot", slot=token))

            # A tabela não exibe unit_confirmed; sem este cuidado, salvar
            # apagaria as confirmações. Trocar a unidade conta como confirmar.
            anterior = antigo.get(nome)
            confirmado = (anterior.unit_confirmed if anterior else False) or (
                anterior is not None and anterior.unit is not unidade
            )
            catalogo.add(AffixEntry(
                name=nome,
                unit=unidade,
                vmin=_as_float(tabela.item(r, 2), None),
                vmax=_as_float(tabela.item(r, 3), None),
                slots=slots,
                unit_confirmed=confirmado,
            ))
        self.app.catalog = catalogo
        catalogo.save(config.CATALOG_PATH)
        self._refresh_affix_choices()
        self.lbl_catalog_count.setText(t("catalog.count", count=len(catalogo)))
        self._log(t("catalog.saved", count=len(catalogo)))

    # ------------------------------------------------- afixos novos vistos
    def _note_unknown(self, evt: EngineEvent) -> None:
        nome = evt.data.get("name", "")
        if evt.data.get("known") or not looks_like_affix_name(nome):
            return
        if nome in self.app.catalog.entries:
            return
        # Parecido demais com um afixo existente = erro de leitura, não afixo
        # novo. Sem isto o catálogo se envenena sozinho.
        parecido, score = self.app.catalog.match(nome)
        if parecido is not None and score >= 0.80:
            return
        self._unknown[nome] = self._unknown.get(nome, 0) + 1
        # Duas aparições: nome real repete, leitura corrompida quase nunca sai
        # igual duas vezes.
        repetidos = sorted(n for n, c in self._unknown.items() if c >= 2)
        if repetidos:
            self.lbl_unknown.setText(", ".join(repetidos))
            self.box_unknown.setVisible(True)

    def _absorb_unknown(self) -> None:
        adicionados = 0
        for nome, vezes in sorted(self._unknown.items()):
            if vezes >= 2 and nome not in self.app.catalog.entries:
                self.app.catalog.add(AffixEntry(name=nome, unit=_guess_unit(nome)))
                adicionados += 1
        self.app.catalog.save(config.CATALOG_PATH)
        self._reload_catalog()
        self._refresh_affix_choices()
        self._unknown.clear()
        self.box_unknown.setVisible(False)
        self._log(t("unknown.added", count=adicionados))

    # ------------------------------------------------------ atalho global
    def _poll_hotkeys(self) -> None:
        rodando = bool(self.engine_worker and self.engine_worker.isRunning())
        if key_pressed_once(VK_F9):
            self._stop() if rodando else self._start()
        elif key_pressed_once(VK_F12) and rodando:
            self._stop()

    # ---------------------------------------------------------- ciclo/vida
    def _collect_settings(self) -> None:
        s = self.app.settings
        s.max_attempts = self.spin_attempts.value()
        s.max_minutes = self.spin_minutes.value() or None
        s.start_delay_s = self.spin_delay.value()
        s.require_foreground = self.chk_foreground.isChecked()
        s.abort_on_mouse_move = self.chk_mouse.isChecked()
        s.focus_game_on_start = self.chk_focus.isChecked()
        s.input_speed = self.cmb_speed.currentText()
        s.save()

    def _set_status(self, chave: str) -> None:
        self.status.setText(t(f"panel.{chave}"))
        self.status.setStyleSheet(f"color: {style.COR_ESTADO.get(chave, style.TEXTO)};")

    def _start(self) -> None:
        if self.engine_worker and self.engine_worker.isRunning():
            return
        self._save_target()
        self._collect_settings()

        if not self.app.ruleset.active:
            QMessageBox.warning(self, t("msg.no_target_title"), t("msg.no_target"))
            return

        s = self.app.settings
        guard = Guard(
            limits=Limits(
                max_attempts=s.max_attempts,
                max_gold=s.max_gold,
                max_minutes=s.max_minutes,
            ),
            require_foreground=s.require_foreground,
            abort_on_mouse_move=s.abort_on_mouse_move,
        )
        engine = EnchantEngine(
            ruleset=self.app.ruleset,
            catalog=self.app.catalog,
            ocr=self.app.ocr,
            guard=guard,
            profile=self.app.profile,
            dry_run=False,
            poll_interval=s.poll_interval,
            state_timeout=s.state_timeout,
            start_delay=s.start_delay_s,
            focus_game_on_start=s.focus_game_on_start,
            profiler=self.app.profiler,
            input_profile=PROFILES.get(s.input_speed, DEFAULT_INPUT),
        )

        self.log.clear()
        self.engine_worker = EngineWorker(engine)
        self.engine_worker.event.connect(self._on_event)
        self.engine_worker.finished_run.connect(self._on_finished)
        self.engine_worker.start()

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._set_status("running")

    def _stop(self) -> None:
        if self.engine_worker:
            self.engine_worker.stop()
            self.btn_stop.setEnabled(False)
            self._set_status("stopping")

    def _on_event(self, evt: EngineEvent) -> None:
        prefixo = {
            EventKind.SUCCESS: ">>>",
            EventKind.ERROR: "!!!",
            EventKind.STOPPED: "---",
            EventKind.ATTEMPT: " * ",
        }.get(evt.kind, "   ")
        self._log(f"{prefixo} {evt.message}")
        if evt.kind is EventKind.READ:
            self._note_unknown(evt)
        elif evt.kind in (EventKind.STATE, EventKind.INFO):
            self.substatus.setText(evt.message)

    def _on_finished(self, outcome: Outcome) -> None:
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._set_status("found" if outcome.found else "idle")
        resumo = t("panel.attempts_done", count=outcome.count, seconds=outcome.elapsed_s)
        self.substatus.setText(f"{resumo} — {outcome.reason}")
        if outcome.count:
            self._log("    " + t("panel.rate", seconds=outcome.elapsed_s / outcome.count))
        self.app.save()

    def _log(self, texto: str) -> None:
        self.log.appendPlainText(texto)

    def closeEvent(self, event) -> None:  # noqa: N802 - assinatura do Qt
        self._hotkeys.stop()
        if self.engine_worker and self.engine_worker.isRunning():
            self.engine_worker.stop()
            self.engine_worker.wait(2000)
        self._collect_settings()
        self.app.save()

        # Fechamento normal leva o material de depuração junto. Num crash este
        # trecho não roda, e é aí que a evidência importa.
        removidos = config.clear_captures()
        if removidos:
            log.info("captures/ esvaziada ao fechar (%d arquivo(s))", removidos)
        super().closeEvent(event)


def _campo(rotulo: str, widget: QWidget) -> QHBoxLayout:
    """Rótulo à esquerda, campo à direita — o par que se repete na janela."""
    linha = QHBoxLayout()
    texto = QLabel(rotulo)
    texto.setProperty("role", "hint")
    texto.setMinimumWidth(120)
    linha.addWidget(texto)
    linha.addWidget(widget, 1)
    return linha


def _guess_unit(name: str) -> Unit:
    lowered = name.lower()
    if lowered.endswith(" skills") or lowered.endswith(" trap"):
        return Unit.RANK
    if "reduction" in lowered or "generation" in lowered or "received" in lowered:
        return Unit.PERCENT
    return Unit.FLAT


def _as_float(item, default):
    """Lê uma célula como número, tolerando vazio e vírgula decimal."""
    if item is None:
        return default
    texto = item.text().strip().replace(",", ".")
    if not texto:
        return default
    try:
        return float(texto)
    except ValueError:
        return default


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(style.QSS)
    janela = MainWindow(AppState.load())
    janela.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
