"""Janela principal do d4forge."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QValidator
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..affixes import AffixCatalog, AffixEntry, Slot, Unit, looks_like_affix_name
from ..catalog_import import import_full_catalog
from ..automation.safety import VK_F12, Guard, Limits, key_pressed_once
from ..automation.sendinput import PROFILES
from ..benchmark import cycle_estimate
from ..engine import EnchantEngine, EngineEvent, EventKind, Outcome
from ..profile import DEFAULT_PROFILE
from ..profiling import Profiler
from ..rules import Comparison, RuleSet, TargetRule
from ..vision.ocr import OcrEngine
from .worker import BenchWorker, EngineWorker, MonitorWorker

VK_F9 = 0x78

STYLE = """
QWidget { background: #16130f; color: #d8cfc0; font-size: 13px; }
QGroupBox { border: 1px solid #3a3128; border-radius: 4px; margin-top: 10px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #b99a63; }
QPushButton { background: #2a241c; border: 1px solid #4a3f30; border-radius: 3px; padding: 7px 14px; }
QPushButton:hover { background: #3a3126; }
QPushButton:disabled { color: #6b6155; border-color: #2e281f; }
QPushButton#start { background: #5a2320; border-color: #8c3a30; font-weight: bold; }
QPushButton#start:hover { background: #752d28; }
QPushButton#stop { background: #4a3a18; border-color: #7a6228; font-weight: bold; }
QPlainTextEdit, QTableWidget { background: #0f0d0a; border: 1px solid #3a3128; }
QHeaderView::section { background: #2a241c; padding: 4px; border: 0; }
QTabBar::tab { background: #221c16; padding: 8px 16px; }
QTabBar::tab:selected { background: #3a3126; color: #e8c98d; }
"""


@dataclass
class AppState:
    settings: config.Settings
    catalog: AffixCatalog
    ruleset: RuleSet
    ocr: OcrEngine
    profiler: Profiler
    profile: object = DEFAULT_PROFILE

    @classmethod
    def load(cls) -> "AppState":
        config.ensure_dirs()
        return cls(
            settings=config.Settings.load(),
            catalog=AffixCatalog.load(config.CATALOG_PATH),
            ruleset=RuleSet.load(config.RULES_PATH),
            ocr=OcrEngine(data_dir=config.DATA_DIR),
            profiler=Profiler.load(config.TIMINGS_PATH),
        )

    def save(self) -> None:
        self.settings.save()
        self.catalog.save(config.CATALOG_PATH)
        self.ruleset.save(config.RULES_PATH)
        self.ocr.save()
        self.profiler.save(config.TIMINGS_PATH)


class MainWindow(QMainWindow):
    def __init__(self, app_state: AppState) -> None:
        super().__init__()
        self.app = app_state
        self.engine_worker: EngineWorker | None = None
        self.monitor: MonitorWorker | None = None
        self._unknown: dict[str, int] = {}

        self.setWindowTitle("d4forge — encantamento")
        self.resize(1000, 720)

        tabs = QTabWidget()
        tabs.addTab(self._build_panel(), "Painel")
        tabs.addTab(self._build_targets(), "Alvos")
        tabs.addTab(self._build_catalog(), "Catálogo")
        tabs.addTab(self._build_diagnostics(), "Diagnóstico")
        tabs.addTab(self._build_performance(), "Desempenho")
        self.setCentralWidget(tabs)

        self._reload_targets()
        self._reload_catalog()

        # Atalho global: funciona mesmo com o Diablo IV em foco, que é
        # justamente quando a janela do app está inacessível.
        self._hotkeys = QTimer(self)
        self._hotkeys.timeout.connect(self._poll_hotkeys)
        self._hotkeys.start(80)
        key_pressed_once(VK_F9)   # limpa estado pendente das teclas
        key_pressed_once(VK_F12)

    # ------------------------------------------------------------ Painel
    def _build_panel(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.status = QLabel("parado")
        self.status.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)

        self.substatus = QLabel(
            "Abra o Occultist, escolha o afixo a trocar e aperte F9 (ou Iniciar)."
        )
        self.substatus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.substatus.setStyleSheet("color: #8d8375;")
        layout.addWidget(self.substatus)

        controls = QHBoxLayout()
        self.btn_start = QPushButton("Iniciar  (F9)")
        self.btn_start.setObjectName("start")
        self.btn_start.clicked.connect(self._start)
        self.btn_stop = QPushButton("Parar  (F9 ou F12)")
        self.btn_stop.setObjectName("stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)
        controls.addWidget(self.btn_start)
        controls.addWidget(self.btn_stop)
        layout.addLayout(controls)

        tip = QLabel(
            "F9 e F12 funcionam com o jogo em foco — você não precisa voltar nesta janela."
        )
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tip.setStyleSheet("color: #b99a63;")
        layout.addWidget(tip)

        self.chk_dry = QCheckBox("Modo simulação (lê a tela mas não clica)")
        self.chk_dry.setChecked(self.app.settings.dry_run)
        self.chk_dry.setToolTip(
            "Deixe ligado até confirmar no log que a leitura e a detecção de tela "
            "estão corretas. Só desligue quando confiar."
        )
        layout.addWidget(self.chk_dry)

        # --- travas
        box = QGroupBox("Travas de segurança")
        grid = QHBoxLayout(box)

        self.spin_attempts = QSpinBox()
        self.spin_attempts.setRange(1, 100_000)
        self.spin_attempts.setValue(self.app.settings.max_attempts)
        grid.addWidget(QLabel("Máx. tentativas:"))
        grid.addWidget(self.spin_attempts)

        self.spin_minutes = QDoubleSpinBox()
        self.spin_minutes.setRange(0, 1440)
        self.spin_minutes.setDecimals(0)
        self.spin_minutes.setValue(self.app.settings.max_minutes or 0)
        self.spin_minutes.setSpecialValueText("sem limite")
        grid.addWidget(QLabel("Máx. minutos:"))
        grid.addWidget(self.spin_minutes)

        self.spin_delay = QDoubleSpinBox()
        self.spin_delay.setRange(0, 30)
        self.spin_delay.setDecimals(0)
        self.spin_delay.setSuffix(" s")
        self.spin_delay.setValue(self.app.settings.start_delay_s)
        self.spin_delay.setToolTip(
            "Tempo entre apertar Iniciar e o bot começar a agir, para dar chance "
            "de voltar o foco ao jogo."
        )
        grid.addWidget(QLabel("Espera ao iniciar:"))
        grid.addWidget(self.spin_delay)
        grid.addStretch()
        layout.addWidget(box)

        box2 = QGroupBox("Abortar quando")
        row2 = QHBoxLayout(box2)
        self.chk_foreground = QCheckBox("o jogo sair do foco")
        self.chk_foreground.setChecked(self.app.settings.require_foreground)
        row2.addWidget(self.chk_foreground)
        self.chk_mouse = QCheckBox("eu mexer no mouse")
        self.chk_mouse.setChecked(self.app.settings.abort_on_mouse_move)
        row2.addWidget(self.chk_mouse)
        self.chk_focus = QCheckBox("trazer o jogo para frente ao iniciar")
        self.chk_focus.setChecked(self.app.settings.focus_game_on_start)
        row2.addWidget(self.chk_focus)
        row2.addStretch()
        layout.addWidget(box2)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        self.log.setFont(QFont("Consolas", 10))
        layout.addWidget(self.log, 1)

        # Afixos que apareceram no jogo mas nao estao no catálogo. Sem eles no
        # catálogo toda leitura vira "duvidosa" e o bot nunca aceita nada.
        self.box_unknown = QGroupBox("Afixos vistos que não estão no catálogo")
        self.box_unknown.setVisible(False)
        row = QHBoxLayout(self.box_unknown)
        self.lbl_unknown = QLabel("")
        self.lbl_unknown.setWordWrap(True)
        row.addWidget(self.lbl_unknown, 1)
        btn = QPushButton("Adicionar ao catálogo")
        btn.clicked.connect(self._absorb_unknown)
        row.addWidget(btn)
        layout.addWidget(self.box_unknown)

        return page

    # ---------------------------------------------- afixos desconhecidos
    def _note_unknown(self, evt: EngineEvent) -> None:
        name = evt.data.get("name", "")
        if evt.data.get("known") or not looks_like_affix_name(name):
            return
        if name in self.app.catalog.entries:
            return
        self._unknown[name] = self._unknown.get(name, 0) + 1
        # Exigir duas aparições filtra leitura corrompida: nome de verdade
        # repete, lixo de OCR quase nunca sai igual duas vezes.
        repeated = sorted(n for n, c in self._unknown.items() if c >= 2)
        if repeated:
            self.lbl_unknown.setText(", ".join(repeated))
            self.box_unknown.setVisible(True)

    def _absorb_unknown(self) -> None:
        added = 0
        for name, count in sorted(self._unknown.items()):
            if count >= 2 and name not in self.app.catalog.entries:
                self.app.catalog.add(AffixEntry(name=name, unit=_guess_unit(name)))
                added += 1
        self.app.catalog.save(config.CATALOG_PATH)
        self._reload_catalog()
        self._refresh_affix_choices()
        self._unknown.clear()
        self.box_unknown.setVisible(False)
        self._append_log(
            f"{added} afixo(s) adicionado(s) ao catálogo — revise a unidade e as "
            f"faixas de roll na aba Catálogo"
        )

    # -------------------------------------------------------------- Alvo
    def _build_targets(self) -> QWidget:
        """Um alvo só: o encantamento troca um único afixo por vez."""
        page = QWidget()
        layout = QVBoxLayout(page)

        hint = QLabel(
            "O Occultist troca um afixo de cada vez, então o alvo é um só.\n"
            "Escolha na caixa abaixo — ela lista o que o app já aprendeu do seu jogo."
        )
        hint.setStyleSheet("color: #8d8375;")
        layout.addWidget(hint)

        box = QGroupBox("Parar quando aparecer")
        form = QVBoxLayout(box)

        line1 = QHBoxLayout()
        line1.addWidget(QLabel("Slot:"))
        self.cmb_slot = QComboBox()
        self.cmb_slot.addItem("Todos", None)
        for slot in Slot:
            self.cmb_slot.addItem(slot.label, slot)
        self.cmb_slot.setToolTip(
            "Filtra a lista de afixos pelo espaço do item que você vai encantar.\n"
            "Afixo sem slot cadastrado no Catálogo aparece em todos os filtros."
        )
        self.cmb_slot.currentIndexChanged.connect(self._refresh_affix_choices)
        line1.addWidget(self.cmb_slot)

        line1.addWidget(QLabel("Afixo:"))
        self.cmb_affix = QComboBox()
        self.cmb_affix.setEditable(True)  # dá para digitar um que ainda não foi visto
        self.cmb_affix.setMinimumWidth(280)
        self.cmb_affix.currentTextChanged.connect(self._update_unit_hint)
        line1.addWidget(self.cmb_affix, 1)
        form.addLayout(line1)

        line2 = QHBoxLayout()
        line2.addWidget(QLabel("Condição:"))
        self.cmb_comparison = QComboBox()
        for comp in Comparison:
            self.cmb_comparison.addItem(comp.label, comp)
        # ">=" e' o caso normal: aceitar o afixo a partir de um valor.
        self.cmb_comparison.setCurrentIndex(list(Comparison).index(Comparison.GE))
        line2.addWidget(self.cmb_comparison)

        self.spin_value = ValueSpinBox()
        line2.addWidget(self.spin_value)

        self.lbl_unit = QLabel("")
        self.lbl_unit.setStyleSheet("color: #b99a63;")
        line2.addWidget(self.lbl_unit)
        line2.addStretch()
        form.addLayout(line2)

        line3 = QHBoxLayout()
        line3.addWidget(QLabel("Roll mínimo:"))
        self.spin_quality = QDoubleSpinBox()
        self.spin_quality.setRange(0, 100)
        self.spin_quality.setDecimals(0)
        self.spin_quality.setSuffix(" % do máximo")
        self.spin_quality.setSpecialValueText("ignorar")
        self.spin_quality.setToolTip(
            "Só funciona se o afixo tiver Roll mín/máx preenchidos na aba Catálogo."
        )
        line3.addWidget(self.spin_quality)
        line3.addStretch()
        form.addLayout(line3)

        self.chk_climb = QCheckBox(
            "Escalada: pegar o afixo-alvo com qualquer valor e só trocar por "
            "valores maiores, até a meta acima"
        )
        self.chk_climb.setChecked(True)
        self.chk_climb.setToolTip(
            "Enquanto o item não tem o afixo-alvo, aceita-o com qualquer valor.\n"
            "Depois só aceita valor estritamente maior que o atual.\n"
            "Para quando o valor do alvo for atingido. Cada tentativa custa o\n"
            "mesmo escolhendo ou não, então segurar o afixo cedo não sai mais caro."
        )
        form.addWidget(self.chk_climb)

        layout.addWidget(box)

        self.lbl_target_summary = QLabel("")
        self.lbl_target_summary.setStyleSheet("color: #8d8375;")
        layout.addWidget(self.lbl_target_summary)

        save = QPushButton("Salvar alvo")
        save.clicked.connect(self._save_targets)
        layout.addWidget(save)
        layout.addStretch(1)
        return page

    def _refresh_affix_choices(self, *_args) -> None:
        """Repovoa a caixa (respeitando o slot) mantendo o que já estava escolhido."""
        current = self.cmb_affix.currentText()
        slot = self.cmb_slot.currentData() if hasattr(self, "cmb_slot") else None
        names = sorted(e.name for e in self.app.catalog.for_slot(slot))
        self.cmb_affix.blockSignals(True)
        self.cmb_affix.clear()
        self.cmb_affix.addItems(names)
        self.cmb_affix.setCurrentText(current)
        self.cmb_affix.blockSignals(False)
        self._update_unit_hint()

    def _update_unit_hint(self, *_args) -> None:
        """Mostra a unidade e a faixa conhecida do afixo escolhido."""
        entry = self.app.catalog.entries.get(self.cmb_affix.currentText().strip())
        if entry is None:
            self.lbl_unit.setText("(afixo fora do catálogo)")
            return
        parts = {"flat": "pontos", "percent": "%", "rank": "níveis"}[entry.unit.value]
        if entry.vmin is not None and entry.vmax is not None:
            parts += f"   —  faixa conhecida {entry.vmin:g} a {entry.vmax:g}"
        else:
            parts += "   —  faixa não cadastrada"
        self.lbl_unit.setText(parts)

    def _reload_targets(self) -> None:
        self._refresh_affix_choices()
        rule = self.app.ruleset.rules[0] if self.app.ruleset.rules else None
        if rule is None:
            return
        self.cmb_affix.setCurrentText(rule.affix_name)
        self.cmb_comparison.setCurrentIndex(list(Comparison).index(rule.comparison))
        self.spin_value.setValue(rule.threshold)
        self.spin_quality.setValue(0 if rule.min_quality is None else rule.min_quality * 100)
        self.chk_climb.setChecked(rule.climb)
        self._update_unit_hint()

    def _save_targets(self) -> None:
        name = self.cmb_affix.currentText().strip()
        if not name:
            self.app.ruleset.rules = []
            self.lbl_target_summary.setText("nenhum alvo definido")
            return
        quality = self.spin_quality.value()
        rule = TargetRule(
            affix_name=name,
            comparison=self.cmb_comparison.currentData(),
            threshold=self.spin_value.value(),
            min_quality=None if quality <= 0 else quality / 100.0,
            climb=self.chk_climb.isChecked(),
        )
        self.app.ruleset.rules = [rule]
        self.app.ruleset.save(config.RULES_PATH)
        self.lbl_target_summary.setText(f"alvo atual:  {rule.describe()}")

    # ---------------------------------------------------------- Catálogo
    def _build_catalog(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        hint = QLabel(
            "Nomes conhecidos de afixos: corrigem erro de OCR e, com mín/máx, dão a\n"
            "qualidade do roll. Não existe API oficial da Blizzard para o D4 — o botão\n"
            "abaixo importa a lista da comunidade (d4lf, ~870 afixos). Faixas de roll\n"
            "continuam manuais (d4builds.gg tem os números).\n"
            "Slots: separe por vírgula (helm, chest, gloves, pants, boots, amulet,\n"
            "ring, weapon, offhand). Vazio = aparece em todos os filtros."
        )
        hint.setStyleSheet("color: #8d8375;")
        layout.addWidget(hint)

        self.tbl_catalog = QTableWidget(0, 5)
        self.tbl_catalog.setHorizontalHeaderLabels(
            ["Afixo", "Unidade", "Roll mín", "Roll máx", "Slots"]
        )
        self.tbl_catalog.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tbl_catalog, 1)

        row = QHBoxLayout()
        imp = QPushButton("Importar catálogo completo")
        imp.setToolTip(
            "Acrescenta os afixos da lista enUS do d4lf que ainda não estão aqui.\n"
            "Nunca sobrescreve o que você já editou. Funciona offline."
        )
        imp.clicked.connect(self._import_catalog)
        row.addWidget(imp)
        add = QPushButton("Adicionar afixo")
        add.clicked.connect(lambda: self._append_catalog_row(AffixEntry("Novo afixo")))
        rem = QPushButton("Remover selecionado")
        rem.clicked.connect(
            lambda: self.tbl_catalog.removeRow(self.tbl_catalog.currentRow())
            if self.tbl_catalog.currentRow() >= 0 else None
        )
        save = QPushButton("Salvar catálogo")
        save.clicked.connect(self._save_catalog)
        row.addWidget(add)
        row.addWidget(rem)
        row.addStretch()
        row.addWidget(save)
        layout.addLayout(row)
        return page

    def _reload_catalog(self) -> None:
        self.tbl_catalog.setRowCount(0)
        for entry in self.app.catalog:
            self._append_catalog_row(entry)

    def _append_catalog_row(self, entry: AffixEntry) -> None:
        table = self.tbl_catalog
        r = table.rowCount()
        table.insertRow(r)
        table.setItem(r, 0, QTableWidgetItem(entry.name))
        combo = QComboBox()
        for unit in Unit:
            combo.addItem(unit.value, unit)
        combo.setCurrentIndex(list(Unit).index(entry.unit))
        table.setCellWidget(r, 1, combo)
        table.setItem(r, 2, QTableWidgetItem("" if entry.vmin is None else f"{entry.vmin:g}"))
        table.setItem(r, 3, QTableWidgetItem("" if entry.vmax is None else f"{entry.vmax:g}"))
        table.setItem(
            r, 4, QTableWidgetItem(", ".join(sorted(s.value for s in entry.slots)))
        )

    def _import_catalog(self) -> None:
        added = import_full_catalog(self.app.catalog)
        self.app.catalog.save(config.CATALOG_PATH)
        self._reload_catalog()
        self._refresh_affix_choices()
        self._append_log(
            f"catálogo importado: {added} afixo(s) novo(s), total {len(self.app.catalog)}"
        )

    def _save_catalog(self) -> None:
        old = self.app.catalog.entries
        catalog = AffixCatalog()
        table = self.tbl_catalog
        for r in range(table.rowCount()):
            name = (table.item(r, 0).text() if table.item(r, 0) else "").strip()
            if not name:
                continue
            combo = table.cellWidget(r, 1)
            unit = combo.currentData() if combo else Unit.FLAT

            slots: set[Slot] = set()
            slots_text = table.item(r, 4).text() if table.item(r, 4) else ""
            for token in slots_text.replace(";", ",").split(","):
                token = token.strip().lower()
                if not token:
                    continue
                try:
                    slots.add(Slot(token))
                except ValueError:
                    self._append_log(f"slot desconhecido ignorado: {token!r} ({name})")

            # A tabela não exibe unit_confirmed; sem este cuidado, salvar o
            # catálogo apagaria as confirmações. Trocar a unidade na tabela
            # conta como confirmação manual.
            previous = old.get(name)
            confirmed = (previous.unit_confirmed if previous else False) or (
                previous is not None and previous.unit is not unit
            )
            catalog.add(
                AffixEntry(
                    name=name,
                    unit=unit,
                    vmin=_as_float(table.item(r, 2), None),
                    vmax=_as_float(table.item(r, 3), None),
                    slots=slots,
                    unit_confirmed=confirmed,
                )
            )
        self.app.catalog = catalog
        catalog.save(config.CATALOG_PATH)
        self._refresh_affix_choices()
        self._append_log(f"catálogo salvo ({len(catalog)} afixo(s))")

    # ------------------------------------------------------- Diagnóstico
    def _build_diagnostics(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        hint = QLabel(
            "Lê a tela sem clicar em nada. Use para conferir se o app enxerga\n"
            "a tela certa e lê os afixos corretamente, antes de ligar a automação."
        )
        hint.setStyleSheet("color: #8d8375;")
        layout.addWidget(hint)

        self.btn_monitor = QPushButton("Começar a observar")
        self.btn_monitor.setCheckable(True)
        self.btn_monitor.toggled.connect(self._toggle_monitor)
        layout.addWidget(self.btn_monitor)

        self.diag_state = QLabel("—")
        self.diag_state.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        layout.addWidget(self.diag_state)

        self.diag_text = QPlainTextEdit()
        self.diag_text.setReadOnly(True)
        self.diag_text.setFont(QFont("Consolas", 10))
        layout.addWidget(self.diag_text, 1)
        return page

    def _toggle_monitor(self, on: bool) -> None:
        if on:
            self.btn_monitor.setText("Parar de observar")
            self.monitor = MonitorWorker(self.app)
            self.monitor.reading.connect(self._on_monitor)
            self.monitor.start()
        else:
            self.btn_monitor.setText("Começar a observar")
            if self.monitor:
                self.monitor.stop()
                self.monitor.wait(1500)
                self.monitor = None

    def _on_monitor(self, reading, lines, extra) -> None:
        self.diag_state.setText(f"tela: {reading.state.value}")
        body = "\n".join(lines) if lines else "(sem texto para ler nesta tela)"
        signals = "\n".join(f"  {k} = {v:.4f}" for k, v in sorted(reading.signals.items()))
        self.diag_text.setPlainText(f"{body}\n\nsinais de detecção:\n{signals}")

    # -------------------------------------------------------- Desempenho
    def _build_performance(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        hint = QLabel(
            "Mede quanto cada etapa custa. As medições se acumulam entre sessões,\n"
            "e os tempos de \"reação\" são quanto o JOGO leva para responder a um clique —\n"
            "é o piso que nenhuma otimização do app consegue baixar."
        )
        hint.setStyleSheet("color: #8d8375;")
        layout.addWidget(hint)

        row = QHBoxLayout()
        self.btn_bench = QPushButton("Testar tempo de resposta")
        self.btn_bench.clicked.connect(self._run_benchmark)
        row.addWidget(self.btn_bench)

        row.addWidget(QLabel("Velocidade do mouse:"))
        self.cmb_speed = QComboBox()
        for label in PROFILES:
            self.cmb_speed.addItem(label)
        self.cmb_speed.setCurrentText(self.app.settings.input_speed)
        self.cmb_speed.setToolTip(
            "Movimento humanizado custa 125–305 ms por clique, e são 4 cliques por "
            "volta. 'instantâneo' remove esse custo."
        )
        row.addWidget(self.cmb_speed)

        clear = QPushButton("Limpar medições")
        clear.clicked.connect(self._clear_timings)
        row.addStretch()
        row.addWidget(clear)
        layout.addLayout(row)

        self.lbl_bench = QLabel("Nenhuma medição ainda.")
        self.lbl_bench.setStyleSheet("color: #b99a63;")
        self.lbl_bench.setWordWrap(True)
        layout.addWidget(self.lbl_bench)

        self.tbl_timings = QTableWidget(0, 6)
        self.tbl_timings.setHorizontalHeaderLabels(
            ["Etapa", "n", "média", "p50", "p95", "máximo"]
        )
        self.tbl_timings.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.tbl_timings, 1)
        self._reload_timings()
        return page

    def _reload_timings(self) -> None:
        table = self.tbl_timings
        table.setRowCount(0)
        for timing in self.app.profiler.rows():
            r = table.rowCount()
            table.insertRow(r)
            table.setItem(r, 0, QTableWidgetItem(timing.name))
            table.setItem(r, 1, QTableWidgetItem(str(timing.count)))
            for col, value in enumerate(
                (timing.mean, timing.percentile(50), timing.percentile(95), timing.maximum),
                start=2,
            ):
                table.setItem(r, col, QTableWidgetItem(f"{value:.2f} ms"))

        estimate = cycle_estimate(self.app.profiler)
        if estimate > 0:
            self.lbl_bench.setText(
                f"Estimativa por volta: {estimate / 1000:.2f} s  "
                f"→  ~{3600 / max(0.01, estimate / 1000):,.0f} tentativas/hora".replace(",", ".")
            )

    def _run_benchmark(self) -> None:
        self.btn_bench.setEnabled(False)
        self.btn_bench.setText("medindo…")
        self._bench_worker = BenchWorker(self.app)
        self._bench_worker.done.connect(self._on_benchmark)
        self._bench_worker.start()

    def _on_benchmark(self, profiler, notes) -> None:
        for name, timing in profiler.timings.items():
            for sample in timing.samples:
                self.app.profiler.record(name, sample)
        self.app.profiler.save(config.TIMINGS_PATH)
        self._reload_timings()
        self.btn_bench.setEnabled(True)
        self.btn_bench.setText("Testar tempo de resposta")
        if notes:
            self.lbl_bench.setText(self.lbl_bench.text() + "\n" + " · ".join(notes))

    def _clear_timings(self) -> None:
        self.app.profiler.clear()
        self.app.profiler.save(config.TIMINGS_PATH)
        self.lbl_bench.setText("Medições apagadas.")
        self._reload_timings()

    # ------------------------------------------------------ atalho global
    def _poll_hotkeys(self) -> None:
        running = bool(self.engine_worker and self.engine_worker.isRunning())
        if key_pressed_once(VK_F9):
            self._stop() if running else self._start()
        elif key_pressed_once(VK_F12) and running:
            self._stop()

    # -------------------------------------------------------- ciclo/vida
    def _collect_settings(self) -> None:
        s = self.app.settings
        s.dry_run = self.chk_dry.isChecked()
        s.max_attempts = self.spin_attempts.value()
        s.max_minutes = self.spin_minutes.value() or None
        s.start_delay_s = self.spin_delay.value()
        s.require_foreground = self.chk_foreground.isChecked()
        s.abort_on_mouse_move = self.chk_mouse.isChecked()
        s.focus_game_on_start = self.chk_focus.isChecked()
        s.input_speed = self.cmb_speed.currentText()
        s.save()

    def _start(self) -> None:
        if self.engine_worker and self.engine_worker.isRunning():
            return

        # O observador do Diagnóstico faz OCR a cada 400 ms numa thread própria.
        # Deixá-lo ligado durante o ciclo é disputar CPU com o próprio bot —
        # e a CPU já está saturada pelo jogo.
        if self.btn_monitor.isChecked():
            self.btn_monitor.setChecked(False)
            self._append_log("observador do Diagnóstico desligado (disputava CPU)")

        self._save_targets()
        self._collect_settings()

        if not self.app.ruleset.active:
            QMessageBox.warning(
                self, "Sem alvos",
                "Cadastre ao menos um alvo na aba Alvos antes de iniciar.",
            )
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
            dry_run=s.dry_run,
            poll_interval=s.poll_interval,
            state_timeout=s.state_timeout,
            start_delay=s.start_delay_s,
            focus_game_on_start=s.focus_game_on_start,
            profiler=self.app.profiler,
            input_profile=PROFILES.get(s.input_speed, PROFILES["rápido"]),
        )

        self.log.clear()
        self.engine_worker = EngineWorker(engine)
        self.engine_worker.event.connect(self._on_event)
        self.engine_worker.finished_run.connect(self._on_finished)
        self.engine_worker.start()

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.status.setText("simulando…" if s.dry_run else "rodando…")
        self.substatus.setText("F9 ou F12 para parar a qualquer momento.")

    def _stop(self) -> None:
        if self.engine_worker:
            self.engine_worker.stop()
            self.btn_stop.setEnabled(False)
            self.status.setText("parando…")

    def _on_event(self, evt: EngineEvent) -> None:
        prefix = {
            EventKind.SUCCESS: ">>>",
            EventKind.ERROR: "!!!",
            EventKind.STOPPED: "---",
            EventKind.ATTEMPT: " * ",
        }.get(evt.kind, "   ")
        self._append_log(f"{prefix} {evt.message}")
        if evt.kind is EventKind.READ:
            self._note_unknown(evt)
        elif evt.kind in (EventKind.STATE, EventKind.INFO):
            self.substatus.setText(evt.message)

    def _on_finished(self, outcome: Outcome) -> None:
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.status.setText("achou!" if outcome.found else "parado")
        self.substatus.setText(
            f"{outcome.count} tentativa(s) em {outcome.elapsed_s:.0f}s — {outcome.reason}"
        )
        if outcome.count:
            por_volta = outcome.elapsed_s / outcome.count
            self._append_log(f"    ritmo: {por_volta:.2f} s por tentativa")
        self._reload_timings()
        self.app.save()

    def _append_log(self, text: str) -> None:
        self.log.appendPlainText(text)

    def closeEvent(self, event) -> None:  # noqa: N802 - assinatura do Qt
        self._hotkeys.stop()
        if self.engine_worker and self.engine_worker.isRunning():
            self.engine_worker.stop()
            self.engine_worker.wait(2000)
        if self.monitor:
            self.monitor.stop()
            self.monitor.wait(1500)
        self._collect_settings()
        self.app.save()
        super().closeEvent(event)


class ValueSpinBox(QDoubleSpinBox):
    """Campo de valor que não força casa decimal.

    A maioria dos afixos é inteira ("+1450 Maximum Life") e um QDoubleSpinBox
    comum exibiria "1450,0", obrigando a conviver com uma casa que não existe.
    Aqui o inteiro aparece como inteiro e o decimal só aparece quando existe.
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
        # Estados intermediários deixam digitar "1," antes de virar "1,5".
        if text.strip() in ("", "-", ",", "."):
            return (QValidator.State.Intermediate, text, pos)
        try:
            float(text.strip().replace(",", "."))
        except ValueError:
            return (QValidator.State.Invalid, text, pos)
        return (QValidator.State.Acceptable, text, pos)


def _guess_unit(name: str) -> Unit:
    """Palpite inicial da unidade, só para poupar cliques — dá para trocar na aba."""
    lowered = name.lower()
    if lowered.endswith(" skills") or lowered.endswith(" trap"):
        return Unit.RANK
    if "reduction" in lowered or "generation" in lowered or "received" in lowered:
        return Unit.PERCENT
    return Unit.FLAT


def _as_float(item, default):
    """Lê uma célula da tabela como número, tolerando vazio e vírgula decimal."""
    if item is None:
        return default
    text = item.text().strip().replace(",", ".")
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    window = MainWindow(AppState.load())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
