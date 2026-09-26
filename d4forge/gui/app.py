"""Janela principal do d4forge."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt, QPoint, QStringListModel, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QValidator
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
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
from ..i18n import LANGUAGE_SHORT, LANGUAGES, set_language, t
from ..profile import DEFAULT_PROFILE
from ..profiling import Profiler
from ..rules import Comparison, RuleSet, TargetRule
from ..vision.ocr import OcrEngine
from . import style
from .frameless import (
    FramelessMixin,
    TitleBarArea,
    encaixar_na_tela,
    geometria_salva,
    restaurar_geometria,
)
from .autoskill_tab import AutoSkillTab
from .mw_tab import MasterworkTab
from .progress import ProgressPanel
from .responsive import (
    LinhaAdaptavel,
    faixa_central,
    pagina_rolavel,
    trocar_conteudo,
)
from .temper_tab import TemperTab
from .worker import (
    AutoSkillWorker,
    EngineWorker,
    TemperWorker,
    WarmupWorker,
)

VK_F9 = 0x78
VK_F10 = 0x79
VK_F11 = 0x7A

# Glifos dos botoes de janela, os MESMOS que o Windows usa nos dele (Segoe
# Fluent Icons no 11, Segoe MDL2 Assets no 10). O "-", "[]" e "X" datilografados
# que estavam aqui tinham cada um a sua altura e o seu peso: de longe a barra
# parecia torta, e era.
GLIFOS_JANELA = {
    "btnMin": ("", "–"),
    "btnMax": ("", "□"),
    "btnClose": ("", "✕"),
}
GLIFO_RESTAURAR = ("", "❐")

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
    # A linha que o Windows 11 desenha em volta da janela. Sem dizer a cor ela
    # vem no cinza do sistema, e um retangulo cinza em volta de uma janela
    # inteira em dourado e preto e' a primeira coisa que o olho acha errada.
    cor_da_borda = QColor(style.DOURADO_FRACO)

    def __init__(self, app_state: AppState) -> None:
        super().__init__()
        self.app = app_state
        self.engine_worker: EngineWorker | None = None
        self.temper_worker: TemperWorker | None = None
        self.mw_worker: TemperWorker | None = None
        self.autoskill_worker: AutoSkillWorker | None = None
        # Enquanto isto está ligado, mexer nos campos do alvo não grava nada -
        # ver `_reload_target`.
        self._carregando_alvo = False
        self._target_timer = QTimer(self)
        self._target_timer.setSingleShot(True)
        self._target_timer.timeout.connect(lambda: self._save_target())
        self._unknown: dict[str, int] = {}
        self._catalog_carregado = False

        self.setWindowTitle(t("app.window"))
        # 880 de largura mínima era o preço de um layout que não encolhia: um
        # mínimo MENOR do que o layout precisa não impede o encolhimento, só
        # deixa os widgets se sobreporem. Agora cada aba mora numa área de
        # rolagem (ver `responsive.pagina_rolavel`) — o que não cabe rola, nada
        # se sobrepõe, e a janela aceita ser tão pequena quanto se queira.
        self.setMinimumSize(520, 420)
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
        # documentMode tira a moldura que o Qt desenha em volta do conteúdo:
        # a folha de estilo já dá a separação, e a moldura virava um risco
        # solto quando a aba passou a rolar.
        self.tabs.setDocumentMode(True)
        # Uma aba por fluxo — Enchant e Tempering —, cada uma com o alvo, os
        # limites e o progresso dela. O Catálogo é dos dois, então fica fora.
        #
        # As três primeiras rolam: são pilhas altas de cartões, e sem rolagem a
        # janela não podia ser menor do que a mais alta delas. O Catálogo não —
        # ele é uma tabela que já rola por dentro, e duas barras de rolagem
        # encaixadas é pior do que o problema que resolveriam.
        self._area_enchant = pagina_rolavel(self._build_panel())
        self._area_temper = pagina_rolavel(self._build_temper())
        self._area_mw = pagina_rolavel(self._build_mw())
        self._area_autoskill = pagina_rolavel(self._build_autoskill())
        self.tabs.addTab(self._area_enchant, t("tab.enchant"))
        self.tabs.addTab(self._area_temper, t("tab.temper"))
        self.tabs.addTab(self._area_mw, t("tab.mw"))
        self.tabs.addTab(self._area_autoskill, t("tab.autoskill"))
        self.tabs.addTab(self._build_catalog(), t("tab.catalog"))
        # A tabela do catálogo tem ~880 linhas: montá-la só quando alguém abre a
        # aba tira quase um segundo da abertura e da troca de idioma.
        self.tabs.currentChanged.connect(self._on_tab_changed)
        corpo_layout.addWidget(self.tabs)
        layout.addWidget(corpo, 1)
        self.setCentralWidget(raiz)

        self._reload_target()

        if self.app.purged:
            self._note("msg.purged", names=", ".join(self.app.purged))
        self._note("msg.catalog_loaded", count=len(self.app.catalog))

        # Atalho global: funciona com o Diablo IV em foco, que é quando a
        # janela do app está inacessível.
        self._hotkeys = QTimer(self)
        self._hotkeys.timeout.connect(self._poll_hotkeys)
        self._hotkeys.start(80)
        key_pressed_once(VK_F9)
        key_pressed_once(VK_F10)
        key_pressed_once(VK_F12)

        # Carrega o leitor agora, para o custo de partida não cair sobre a
        # primeira leitura do ciclo.
        self._iniciar_autoskill()

        self._warmup = WarmupWorker(self.app)
        self._warmup.ready.connect(lambda ms: self._note("msg.ocr_ready", ms=ms))
        self._warmup.start()

        # Por último, com o layout já montado: antes disto o Qt ainda não sabe
        # o mínimo da janela e `encaixar_na_tela` teria de adivinhá-lo.
        #
        # A janela abre onde foi fechada. Não havendo onde (primeira vez, ou
        # monitor que sumiu), o tamanho pedido é cortado pela tela e o resto é
        # centralizado — 1040x840 passava da altura útil de um 1080p, e a
        # janela nascia com a barra de título acima do alcance do mouse.
        if not restaurar_geometria(self, self.app.settings.window_geometry):
            encaixar_na_tela(self, 1040, 840)
        # Estado inicial anunciado À MÃO: `changeEvent` só avisa sobre
        # MUDANÇAS, e uma propriedade que nunca foi escrita não casa com regra
        # de folha de estilo alguma, nem com a negação dela.
        self.sincronizar_maximizada()

    # ---------------------------------------------------------- cabeçalho
    def _build_header(self) -> QWidget:
        """Cabeçalho e barra de título ao mesmo tempo: a janela não tem moldura
        do Windows, então arrastar, maximizar e fechar moram aqui."""
        header = TitleBarArea(self)
        header.setObjectName("header")
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
        self.btn_lang.setFixedHeight(28)
        # Sem setMenu(): o Qt reservaria espaço para a seta nativa por baixo do
        # nosso "▾" e o rótulo ficava espremido. Abrimos o menu na mão, o que de
        # quebra deixa alinhá-lo pela direita do botão.
        self.btn_lang.clicked.connect(self._open_lang_menu)
        self._refresh_lang_button()
        topo.addWidget(self.btn_lang)
        topo.addSpacing(10)

        self._botoes_janela: dict[str, QPushButton] = {}
        for nome, dica, slot in (
            ("btnMin", "window.minimize", self.showMinimized),
            ("btnMax", "window.maximize", self.toggle_maximize),
            ("btnClose", "window.close", self.close),
        ):
            botao = QPushButton(_glifo(nome))
            botao.setObjectName(nome)
            botao.setProperty("titlebar", True)
            botao.setCursor(Qt.CursorShape.ArrowCursor)
            # Tab não deve parar nos botões de janela: eles não fazem parte do
            # preenchimento, e o foco pousando neles desenhava um retângulo no
            # canto ao abrir o app.
            botao.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            botao.setToolTip(t(dica))
            botao.clicked.connect(slot)
            topo.addWidget(botao)
            self._botoes_janela[nome] = botao
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

        # Altura travada no que o conteúdo PEDE, em vez dos 82 chutados de
        # antes: naqueles 82 não cabiam a fila de botões e as duas linhas da
        # marca, e a descida do "g" de "d4forge" saía cortada pela borda
        # dourada. Travada, e não livre, para o cabeçalho não encolher junto
        # quando o subtítulo se esconde numa janela estreita.
        for w in (header, titulo, self.lbl_subtitle):
            w.ensurePolished()
        header.setFixedHeight(max(82, header.sizeHint().height()))

        # A partir daqui o Windows sabe que esta faixa é a barra de título, e
        # devolve de graça o que a versão anterior não tinha: arrastar com
        # encaixe nas bordas, Win+Seta, duplo clique para maximizar, sacudir,
        # Alt+Espaço e o menu do botão direito. O botão de maximizar entra
        # junto porque é dele que sai o Snap Layouts do Windows 11.
        self.register_title_bar(header, self._botoes_janela["btnMax"])
        return header

    def on_maximize_changed(self, maximizada: bool) -> None:
        """Ajusta o que só faz sentido num dos dois estados."""
        # Encostada nas bordas da tela, a linha da moldura vira um risco no
        # meio do nada: nenhuma janela do Windows desenha isso maximizada.
        #
        # "maximizada" e nao "maximized": o QWidget JA' tem uma propriedade
        # `maximized`, so' de leitura, e `setProperty` sobre ela nao cria
        # propriedade dinamica nenhuma - falha calada, e a folha de estilo
        # nunca casava. Vale para `minimized` e `fullScreen` tambem.
        shell = self.centralWidget()
        if shell is None:  # estado trocado antes de a janela estar montada
            return
        shell.setProperty("maximizada", maximizada)
        shell.style().unpolish(shell)
        shell.style().polish(shell)

        botao = getattr(self, "_botoes_janela", {}).get("btnMax")
        if botao is not None:
            botao.setText(
                _glifo("btnRestore") if maximizada else _glifo("btnMax")
            )
            botao.setToolTip(
                t("window.restore" if maximizada else "window.maximize")
            )

    # Abaixo disto o subtítulo do cabeçalho não cabe sem espremer os botões de
    # janela contra a marca.
    LARGURA_COM_SUBTITULO = 620

    def resizeEvent(self, event) -> None:  # noqa: N802 - assinatura do Qt
        super().resizeEvent(event)
        # getattr: `setup_frameless` cria a janela nativa, e isso já rende um
        # evento de tamanho — antes de o cabeçalho existir.
        subtitulo = getattr(self, "lbl_subtitle", None)
        if subtitulo is None:
            return
        # O subtítulo é explicação, não identidade: sacrificá-lo primeiro
        # preserva a marca e os botões, que é o que precisa continuar legível.
        cabe = event.size().width() >= self.LARGURA_COM_SUBTITULO
        if subtitulo.isVisible() != cabe:
            subtitulo.setVisible(cabe)

    def _refresh_lang_button(self) -> None:
        atual = self.app.settings.language
        self.btn_lang.setText(f"🌐 {LANGUAGE_SHORT.get(atual, atual)} ▾")
        self.btn_lang.setToolTip(LANGUAGES.get(atual, atual))

    def _open_lang_menu(self) -> None:
        """Menu ancorado pela direita do botão, com o idioma atual marcado."""
        menu = QMenu(self)
        atual = self.app.settings.language
        for code, nome in LANGUAGES.items():
            acao = menu.addAction(nome)
            acao.setCheckable(True)
            acao.setChecked(code == atual)
            acao.triggered.connect(lambda _=False, c=code: self._set_language(c))

        canto = self.btn_lang.mapToGlobal(self.btn_lang.rect().bottomRight())
        largura = menu.sizeHint().width()
        menu.exec(canto + QPoint(-largura, 4))

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

        self.setUpdatesEnabled(False)
        try:
            # As abas não são mais removidas e recriadas, só renomeadas: tirar
            # e repor quatro páginas deixava as antigas penduradas no
            # QTabWidget a cada troca de idioma, e devolvia o foco e a posição
            # de rolagem ao início. Só o conteúdo do Enchant é refeito — ele é
            # o único montado a partir dos textos.
            trocar_conteudo(self._area_enchant, self._build_panel())
            self._retranslate_catalog()
            for i, chave in enumerate(
                ("tab.enchant", "tab.temper", "tab.mw", "tab.autoskill",
                 "tab.catalog")
            ):
                self.tabs.setTabText(i, t(chave))
            self.tabs.setCurrentIndex(indice)

            self._reload_target()
            self.progress.retranslate()
            # As abas do Ferreiro são REAPROVEITADAS (uma aba nova perderia a
            # sessão), então elas não trocam de idioma sozinhas ao serem
            # readicionadas: os rótulos internos continuam os de antes. Sem
            # estas chamadas, metade do app ficava na língua anterior — era
            # assim desde que a aba do Tempering existe.
            self.temper_tab.retranslate()
            self.btn_temper.setText(f"{t('temper.start')}   ·   F10")
            self.btn_temper_stop.setText(f"{t('panel.stop')}   ·   F12")
            self.autoskill_tab.retranslate()
            self.mw_tab.retranslate()
            self.btn_mw.setText(f"{t('mw.start')}   ·   F11")
            self.btn_mw_stop.setText(f"{t('panel.stop')}   ·   F12")
            self.lbl_subtitle.setText(t("app.subtitle"))
            self._refresh_lang_button()
            for nome, chave in (
                ("btnMin", "window.minimize"), ("btnClose", "window.close"),
            ):
                self._botoes_janela[nome].setToolTip(t(chave))
            self._botoes_janela["btnMax"].setToolTip(
                t("window.restore" if self.isMaximized() else "window.maximize")
            )
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
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color: {style.COR_ESTADO['idle']};")
        layout.addWidget(self.status)

        self.substatus = QLabel(t("panel.hint"))
        self.substatus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.substatus.setProperty("role", "hint")
        # Quebra em vez de fixar a largura da aba: esta linha troca de texto a
        # cada evento do ciclo, e o evento mais comprido definia sozinho o
        # quanto a janela podia encolher.
        self.substatus.setWordWrap(True)
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
        layout.addWidget(faixa_central(botoes, self.LARGURA_ACAO))

        dica = QLabel(t("panel.hotkey_hint"))
        dica.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dica.setProperty("role", "accent")
        dica.setWordWrap(True)
        layout.addWidget(dica)

        layout.addWidget(self._build_target())

        # Lado a lado enquanto couberem os dois; empilhados quando não (ver
        # `LinhaAdaptavel`). Espremidos a meia largura, "Tentativas" e o campo
        # ao lado brigavam pelo mesmo pixel e o número ficava ilegível.
        cartoes = LinhaAdaptavel(espaco=12)

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
        cartoes.add(limites, 1)

        seguranca = QGroupBox(t("panel.safety"))
        col2 = QVBoxLayout(seguranca)
        self.chk_foreground = QCheckBox(t("panel.abort_focus"))
        self.chk_foreground.setChecked(self.app.settings.require_foreground)
        self.chk_mouse = QCheckBox(t("panel.abort_mouse"))
        self.chk_mouse.setChecked(self.app.settings.abort_on_mouse_move)
        self.chk_focus = QCheckBox(t("panel.focus_game"))
        self.chk_focus.setChecked(self.app.settings.focus_game_on_start)
        self.chk_focus.setToolTip(t("panel.focus_game_tip"))
        col2.addWidget(self.chk_foreground)
        col2.addWidget(self.chk_mouse)
        col2.addWidget(self.chk_focus)

        self.cmb_speed = QComboBox()
        # O texto visível é traduzido; o valor guardado continua sendo o rótulo
        # do perfil, que é a chave de PROFILES e do settings.json.
        for label in PROFILES:
            self.cmb_speed.addItem(t(f"speed.{label}"), label)
        atual = self.cmb_speed.findData(self.app.settings.input_speed)
        self.cmb_speed.setCurrentIndex(max(0, atual))
        self.cmb_speed.setToolTip(t("panel.mouse_speed_tip"))
        col2.addLayout(_campo(t("panel.mouse_speed"), self.cmb_speed))
        col2.addStretch()
        cartoes.add(seguranca, 1)
        layout.addWidget(cartoes)

        # Um só painel para a vida toda da janela: trocar de idioma recria as
        # abas, e um painel novo perderia as tentativas da sessão em curso.
        if not hasattr(self, "progress"):
            self.progress = ProgressPanel()
        layout.addWidget(self.progress, 1)

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

    # Teto da dupla Iniciar/Parar. Solta, ela acompanhava a janela inteira:
    # maximizada, "Iniciar" virava uma faixa vermelha de 1230 pixels.
    LARGURA_ACAO = 780

    # --------------------------------------------------------------- alvo
    def _build_target(self) -> QWidget:
        """O alvo como CARTAO dentro do Enchant, e nao como aba separada.

        O Occultist troca um afixo por vez, entao o alvo e' um so' - e escolher
        o alvo e apertar Iniciar sao partes do mesmo gesto. Em abas separadas,
        conferir o que estava configurado exigia ir e voltar.
        """
        box = QGroupBox(t("target.box"))
        form = QVBoxLayout(box)
        form.setSpacing(10)

        # Peça e Afixo lado a lado enquanto couberem; empilhados quando não.
        # Juntas as duas pediam uns 500 pixels e eram elas que traziam a barra
        # de rolagem horizontal antes de qualquer outra coisa apertar.
        linha1 = LinhaAdaptavel(espaco=14)
        caixa_slot = QWidget()
        col_slot = QHBoxLayout(caixa_slot)
        col_slot.setContentsMargins(0, 0, 0, 0)
        col_slot.addWidget(QLabel(t("target.slot") + ":"))
        self.cmb_slot = QComboBox()
        self.cmb_slot.addItem(t("target.slot_all"), None)
        for slot in Slot:
            self.cmb_slot.addItem(slot.label, slot)
        self.cmb_slot.setToolTip(t("target.slot_tip"))
        self.cmb_slot.currentIndexChanged.connect(self._refresh_affix_choices)
        col_slot.addWidget(self.cmb_slot, 1)
        linha1.add(caixa_slot, 0)

        caixa_afixo = QWidget()
        col_afixo = QHBoxLayout(caixa_afixo)
        col_afixo.setContentsMargins(0, 0, 0, 0)
        col_afixo.addWidget(QLabel(t("target.affix") + ":"))
        self.cmb_affix = QComboBox()
        self.cmb_affix.setEditable(True)
        # 320 fixos obrigavam a linha inteira a ter 320 + rótulos + o seletor
        # de slot, e era daí que vinha metade da largura mínima da janela. O
        # peso 1 no layout já lhe dá todo o espaço que sobrar.
        self.cmb_affix.setMinimumWidth(180)
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
        col_afixo.addWidget(self.cmb_affix, 1)
        linha1.add(caixa_afixo, 1)
        form.addWidget(linha1)

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
        self.lbl_unit.setWordWrap(True)
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
        # A explicação sai de dentro da caixa de marcar: ali ela não quebrava
        # linha e fixava a largura mínima da aba inteira. Aqui quebra.
        climb_hint = QLabel(t("target.climb_hint"))
        climb_hint.setProperty("role", "hint")
        climb_hint.setWordWrap(True)
        climb_hint.setIndent(23)
        form.addWidget(climb_hint)

        self.lbl_target_summary = QLabel("")
        self.lbl_target_summary.setProperty("role", "hint")
        self.lbl_target_summary.setWordWrap(True)
        form.addWidget(self.lbl_target_summary)

        # Alvo salvo sozinho: o botão "Salvar alvo" só persistia em disco, já
        # que Iniciar/F9 sempre chamou `_save_target` antes de rodar. Na
        # prática ele era uma lembrança a mais para dar errado — quem fechasse
        # o app sem apertá-lo perdia o alvo, e o botão em nada avisava disso.
        #
        # Ligado DEPOIS de os widgets terem seus valores iniciais: ligar antes
        # faria o próprio nascimento deles disparar uma gravação.
        for w, sinal in (
            (self.cmb_affix, "currentTextChanged"),
            (self.cmb_slot, "currentIndexChanged"),
            (self.cmb_comparison, "currentIndexChanged"),
            (self.spin_value, "valueChanged"),
            (self.spin_quality, "valueChanged"),
            (self.chk_climb, "toggled"),
        ):
            getattr(w, sinal).connect(self._on_target_edited)
        return box

    # Espera antes de gravar em disco depois da última tecla.
    #
    # O resumo na tela atualiza na hora; só a gravação espera. Sem isto,
    # digitar "Dodge Chance" escreveria rules.json doze vezes, uma por letra, e
    # cada nome pela metade viraria uma regra salva no caminho.
    TARGET_SAVE_DELAY_MS = 500

    def _on_target_edited(self, *_args) -> None:
        if self._carregando_alvo:
            return
        # O resumo é o retorno visual de que o alvo foi entendido, então ele não
        # espera o temporizador.
        self._save_target(silencioso=True)
        self._target_timer.start(self.TARGET_SAVE_DELAY_MS)

    def _refresh_affix_choices(self, *_args) -> None:
        # O Masterworking come do mesmo catálogo, então ele acompanha: salvar o
        # catálogo ou absorver um afixo novo tem de aparecer nas duas listas.
        # A aba é construída depois desta chamada na primeira montagem.
        if hasattr(self, "mw_tab"):
            self.mw_tab.catalog = self.app.catalog
            self.mw_tab.refresh_affixes()

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
        """Repõe o alvo salvo nos controles.

        A trava impede que encher os campos conte como edição: eles disparam os
        mesmos sinais que o usuário dispararia.

        Hoje ela não muda o resultado, e vale dizer por quê: o afixo é o
        PRIMEIRO campo reposto, então todo sinal que dispara daqui já carrega o
        nome certo e a gravação automática regrava a mesma regra. O que a trava
        compra é que essa ordem deixe de ser load-bearing — inverter duas linhas
        aqui salvaria uma regra sem afixo, que é o mesmo que apagar o alvo.
        """
        self._carregando_alvo = True
        try:
            self._refresh_affix_choices()
            rule = self.app.ruleset.rules[0] if self.app.ruleset.rules else None
            if rule is None:
                self.lbl_target_summary.setText(t("target.none"))
                return
            self.cmb_affix.setCurrentText(rule.affix_name)
            self.cmb_comparison.setCurrentIndex(list(Comparison).index(rule.comparison))
            self.spin_value.setValue(rule.threshold)
            self.spin_quality.setValue(
                0 if rule.min_quality is None else rule.min_quality * 100
            )
            self.chk_climb.setChecked(rule.climb)
            self.lbl_target_summary.setText(t("target.saved", rule=rule.describe()))
            self._update_unit_hint()
        finally:
            self._carregando_alvo = False

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
                    self._note("catalog.unknown_slot", slot=token)

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
        self._note("catalog.saved", count=len(catalogo))

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
        self._note("unknown.added", count=adicionados)

    # ------------------------------------------------------ atalho global
    def _poll_hotkeys(self) -> None:
        rodando = bool(self.engine_worker and self.engine_worker.isRunning())
        temperando = bool(self.temper_worker and self.temper_worker.isRunning())
        masterizando = bool(self.mw_worker and self.mw_worker.isRunning())
        if key_pressed_once(VK_F9):
            self._stop() if rodando else self._start()
        elif key_pressed_once(VK_F10):
            self._stop_temper() if temperando else self._start_temper()
        elif key_pressed_once(VK_F11):
            self._stop_mw() if masterizando else self._start_mw()
        elif key_pressed_once(VK_F12):
            # F12 é o freio de todos: quem aperta em pânico não escolhe qual.
            if rodando:
                self._stop()
            if temperando:
                self._stop_temper()
            if masterizando:
                self._stop_mw()

    # ---------------------------------------------------------- ciclo/vida
    def _collect_settings(self) -> None:
        s = self.app.settings
        s.max_attempts = self.spin_attempts.value()
        s.max_minutes = self.spin_minutes.value() or None
        s.start_delay_s = self.spin_delay.value()
        s.require_foreground = self.chk_foreground.isChecked()
        s.abort_on_mouse_move = self.chk_mouse.isChecked()
        s.focus_game_on_start = self.chk_focus.isChecked()
        s.input_speed = self.cmb_speed.currentData() or DEFAULT_INPUT.label
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

        self.progress.reset()
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

    # ------------------------------------------------------------ tempering
    def _build_temper(self) -> QWidget:
        # Um só painel para a vida toda da janela, como o do encantamento:
        # trocar de idioma recria as abas e um painel novo perderia a sessão.
        if not hasattr(self, "temper_tab"):
            self.temper_tab = TemperTab(self.app.settings)
            self.temper_tab.load(config.load_temper_goal())

            botoes = QHBoxLayout()
            self.btn_temper = QPushButton(f"{t('temper.start')}   ·   F10")
            self.btn_temper.setObjectName("start")
            self.btn_temper.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_temper.clicked.connect(self._start_temper)
            self.btn_temper_stop = QPushButton(f"{t('panel.stop')}   ·   F12")
            self.btn_temper_stop.setObjectName("stop")
            self.btn_temper_stop.setEnabled(False)
            self.btn_temper_stop.clicked.connect(self._stop_temper)
            botoes.addWidget(self.btn_temper, 2)
            botoes.addWidget(self.btn_temper_stop, 1)
            self.temper_tab.layout().insertWidget(
                1, faixa_central(botoes, self.LARGURA_ACAO)
            )
        return self.temper_tab

    def _start_temper(self) -> None:
        if self.temper_worker and self.temper_worker.isRunning():
            return
        goal = self.temper_tab.goal()
        config.save_temper_goal(goal)
        s = self.app.settings

        from ..temper.engine import TemperEngine
        from ..temper.rules import TemperLimits

        engine = TemperEngine(
            goal=goal,
            ocr=self.app.ocr,
            limits=TemperLimits(
                max_attempts=s.max_attempts, max_minutes=s.max_minutes
            ),
            profiler=self.app.profiler,
            input_profile=PROFILES.get(s.input_speed, DEFAULT_INPUT),
            require_foreground=s.require_foreground,
        )

        self.temper_tab.progress.reset()
        self.temper_tab.set_status(t("temper.running"))
        self.temper_worker = TemperWorker(engine)
        self.temper_worker.event.connect(self._on_temper_event)
        self.temper_worker.finished_run.connect(self._on_temper_finished)
        self.temper_worker.start()

    def _on_temper_event(self, evt) -> None:
        self.temper_tab.progress.push(evt)
        # O que o ciclo está fazendo agora, em cima da tabela: sem isto, uma
        # sessão que para antes da primeira tentativa não deixa nada visível.
        if evt.kind in (EventKind.STATE, EventKind.INFO):
            self.temper_tab.set_status(evt.message)

        self.btn_temper.setEnabled(False)
        self.btn_temper_stop.setEnabled(True)

    def _stop_temper(self) -> None:
        if self.temper_worker:
            self.temper_worker.stop()
            self.btn_temper_stop.setEnabled(False)

    def _on_temper_finished(self, outcome) -> None:
        self.btn_temper.setEnabled(True)
        self.btn_temper_stop.setEnabled(False)
        self.temper_tab.progress.finish(outcome)
        self.temper_tab.progress.note(
            "temper.done", count=outcome.count, seconds=outcome.elapsed_s
        )
        self.temper_tab.progress.note(outcome.reason_key, **outcome.params)
        # O motivo em destaque, não só dentro dos detalhes técnicos: quando o
        # ciclo para sem nenhuma tentativa, esta linha é a única coisa que
        # distingue "falhou" de "não fez nada".
        self.temper_tab.set_status(outcome.reason, erro=not outcome.found)
        self.app.save()

    # --------------------------------------------------------- masterworking
    def _build_mw(self) -> QWidget:
        # Um só painel para a vida toda da janela, como os outros dois: trocar
        # de idioma recria as abas e um painel novo perderia a sessão.
        if not hasattr(self, "mw_tab"):
            self.mw_tab = MasterworkTab(self.app.catalog)
            self.mw_tab.load(config.load_mw_goal())

            botoes = QHBoxLayout()
            self.btn_mw = QPushButton(f"{t('mw.start')}   ·   F11")
            self.btn_mw.setObjectName("start")
            self.btn_mw.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_mw.clicked.connect(self._start_mw)
            self.btn_mw_stop = QPushButton(f"{t('panel.stop')}   ·   F12")
            self.btn_mw_stop.setObjectName("stop")
            self.btn_mw_stop.setEnabled(False)
            self.btn_mw_stop.clicked.connect(self._stop_mw)
            botoes.addWidget(self.btn_mw, 2)
            botoes.addWidget(self.btn_mw_stop, 1)
            self.mw_tab.layout().insertWidget(
                1, faixa_central(botoes, self.LARGURA_ACAO)
            )
        return self.mw_tab

    def _start_mw(self) -> None:
        if self.mw_worker and self.mw_worker.isRunning():
            return
        goal = self.mw_tab.goal()
        # Sem alvo, o ciclo aceitaria a primeira leitura boa e pararia na hora —
        # o usuário teria gasto uma rodada para nada. Pior: se ele apertasse de
        # novo achando que ia perseguir algo, cada aperto seria mais uma rodada.
        if not goal.affix:
            QMessageBox.warning(self, t("mw.start"), t("mw.no_target"))
            return
        config.save_mw_goal(goal)
        s = self.app.settings

        from ..masterwork.engine import MasterworkEngine

        engine = MasterworkEngine(
            goal=goal,
            ocr=self.app.ocr,
            catalog=self.app.catalog,
            limits=self.mw_tab.limits(),
            profiler=self.app.profiler,
            input_profile=PROFILES.get(s.input_speed, DEFAULT_INPUT),
            require_foreground=s.require_foreground,
        )

        self.mw_tab.progress.reset()
        self.mw_tab.set_status(t("mw.running"))
        self.mw_worker = TemperWorker(engine)
        self.mw_worker.event.connect(self._on_mw_event)
        self.mw_worker.finished_run.connect(self._on_mw_finished)
        self.mw_worker.start()

    def _on_mw_event(self, evt) -> None:
        self.mw_tab.progress.push(evt)
        if evt.kind in (EventKind.STATE, EventKind.INFO):
            self.mw_tab.set_status(evt.message)

        self.btn_mw.setEnabled(False)
        self.btn_mw_stop.setEnabled(True)

    def _stop_mw(self) -> None:
        if self.mw_worker:
            self.mw_worker.stop()
            self.btn_mw_stop.setEnabled(False)

    def _on_mw_finished(self, outcome) -> None:
        self.btn_mw.setEnabled(True)
        self.btn_mw_stop.setEnabled(False)
        self.mw_tab.progress.finish(outcome)
        self.mw_tab.progress.note(
            "mw.done", count=outcome.count, seconds=outcome.elapsed_s
        )
        self.mw_tab.progress.note(outcome.reason_key, **outcome.params)
        self.mw_tab.set_status(outcome.reason, erro=not outcome.found)
        self.app.save()

    # ----------------------------------------------------------- autoskill
    def _build_autoskill(self) -> QWidget:
        # Um so' painel para a vida toda da janela, como os outros tres: a
        # troca de idioma reaproveita a aba, e uma aba nova perderia o que
        # estava ligado e as binds ainda nao gravadas.
        # Sem par Ligar/Desligar, de proposito. As hotkeys JA' sao o
        # liga/desliga, uma por recurso - um botao antes delas significaria
        # abrir o app, clicar aqui, e so' entao ir para o jogo. O laco sobe
        # junto com a janela (ver `_iniciar_autoskill`) e custa 0,3% de um
        # nucleo parado, entao nao ha' o que economizar deixando-o desligado.
        if not hasattr(self, "autoskill_tab"):
            self.autoskill_tab = AutoSkillTab(config.load_autoskill())
            self.autoskill_tab.mudou.connect(self._save_autoskill)
        return self.autoskill_tab

    def _save_autoskill(self) -> None:
        """Grava o que a aba mostra.

        `goal()` edita a MESMA configuracao que o motor esta' segurando, entao
        a troca de uma bind vale no laco em andamento - nao ha' o que
        reiniciar (ver `AutoSkillEngine._sincronizar`).
        """
        config.save_autoskill(self.autoskill_tab.goal())

    def _salvar_tudo(self) -> None:
        """Grava o que CADA aba tem na tela agora.

        Cada uma gravava num momento diferente: o alvo do Enchant com meio
        segundo de atraso, Tempering e Masterworking so' ao apertar Iniciar, o
        catalogo so' pelo botao, o AutoSkill com 400 ms de atraso. Fechar a
        janela logo depois de mexer perdia a mexida - e "mexer e fechar" e'
        justamente o que se faz com configuracao.

        Estar tudo num lugar so' e' o ponto: a aba seguinte que alguem criar
        entra aqui, em vez de nascer com o mesmo buraco.
        """
        # `silencioso`: quem escreve o rules.json e' o `app.save()` logo
        # adiante, e gravar duas vezes so' dobraria a escrita.
        self._save_target(silencioso=True)
        if hasattr(self, "temper_tab"):
            config.save_temper_goal(self.temper_tab.goal())
        if hasattr(self, "mw_tab"):
            config.save_mw_goal(self.mw_tab.goal())
        if hasattr(self, "autoskill_tab"):
            self._save_autoskill()
        # Nao faz nada se a tabela nunca foi montada - ver `_save_catalog`.
        self._save_catalog()

    def _iniciar_autoskill(self) -> None:
        """Poe o laco no ar junto com a janela.

        O que decide se algo acontece sao as hotkeys de cada recurso, e elas
        so' podem ser ouvidas por um laco que ja' esteja rodando. Exigir um
        clique antes disso obrigaria a voltar ao app toda vez que o jogo
        fechasse a sessao - era o passo que nao servia para nada.
        """
        if self.autoskill_worker and self.autoskill_worker.isRunning():
            return
        from ..autoskill.engine import AutoSkillEngine

        engine = AutoSkillEngine(self.autoskill_tab.goal(), self.app.settings)
        self.autoskill_worker = AutoSkillWorker(engine)
        self.autoskill_worker.estado.connect(self.autoskill_tab.mostrar_estado)
        self.autoskill_worker.start()
        self.autoskill_tab.set_status(t("as.listening"))

    def _on_event(self, evt: EngineEvent) -> None:
        self.progress.push(evt)
        if evt.kind is EventKind.READ:
            self._note_unknown(evt)
        elif evt.kind in (EventKind.STATE, EventKind.INFO):
            self.substatus.setText(evt.message)

    def _on_finished(self, outcome: Outcome) -> None:
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._set_status("found" if outcome.found else "idle")
        self.progress.finish(outcome)
        resumo = t("panel.attempts_done", count=outcome.count, seconds=outcome.elapsed_s)
        self.substatus.setText(f"{resumo} — {outcome.reason}")
        self.app.save()

    def _note(self, key: str, **data) -> None:
        self.progress.note(key, **data)

    def closeEvent(self, event) -> None:  # noqa: N802 - assinatura do Qt
        self._hotkeys.stop()
        if self.engine_worker and self.engine_worker.isRunning():
            self.engine_worker.stop()
            self.engine_worker.wait(2000)
        # O laco do AutoSkill nao termina sozinho: sem isto, fechar a janela
        # deixaria uma thread apertando teclas no jogo.
        if self.autoskill_worker and self.autoskill_worker.isRunning():
            self.autoskill_worker.stop()
            self.autoskill_worker.wait(2000)
        # O aquecimento do OCR leva ~300 ms depois de a janela abrir. Fechar
        # nesse intervalo destruía uma QThread em execução — comportamento
        # indefinido, e o processo caía com 0xC0000409 no encerramento.
        if self._warmup.isRunning():
            self._warmup.wait(3000)
        self._salvar_tudo()
        self._collect_settings()
        # Onde e de que tamanho a janela estava, para reabrir assim. Gravado
        # antes de `save`, que é quem escreve o settings.json.
        self.app.settings.window_geometry = geometria_salva(self)
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
    # Teto no campo: sem ele, rótulo e valor acabam em pontas opostas da tela
    # numa janela maximizada, e a dupla deixa de ser lida como uma dupla.
    widget.setMaximumWidth(300)
    linha.addWidget(texto)
    # Peso alto no campo e uma sobra de peso 1 no fim: o campo fica com tudo o
    # que puder até o teto, e o que passar disso vira espaço vazio À DIREITA —
    # sem a sobra, o teto empurrava o campo para a borda do cartão e abria um
    # vão entre ele e o rótulo.
    linha.addWidget(widget, 1000)
    linha.addStretch(1)
    return linha


def _glifo(nome: str) -> str:
    """O glifo do botão de janela, ou o símbolo de texto se a fonte faltar.

    As fontes de ícone vêm com o Windows 10 1809 e com o 11. Numa máquina sem
    elas, o glifo apareceria como um retângulo vazio — e um retângulo vazio no
    lugar do botão de fechar é pior do que um "X" datilografado.
    """
    icone, reserva = (
        GLIFO_RESTAURAR if nome == "btnRestore" else GLIFOS_JANELA[nome]
    )
    return icone if _tem_fonte_de_icones() else reserva


def _tem_fonte_de_icones() -> bool:
    global _FONTE_DE_ICONES
    if _FONTE_DE_ICONES is None:
        try:
            familias = set(QFontDatabase.families())
        except (AttributeError, TypeError):  # pragma: no cover - PySide antigo
            familias = set()
        _FONTE_DE_ICONES = bool(
            familias & {"Segoe Fluent Icons", "Segoe MDL2 Assets"}
        )
    return _FONTE_DE_ICONES


# Resolvido uma vez: `families()` varre as fontes instaladas e custa dezenas de
# milissegundos, e isto é consultado uma vez por botão e a cada maximizar.
_FONTE_DE_ICONES: bool | None = None


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
    # Nome e organização entram no que o Windows mostra na barra de tarefas e
    # nas caixas de diálogo do sistema; sem eles aparecia "python".
    app.setApplicationName("d4forge")
    app.setApplicationDisplayName("d4forge")
    app.setStyleSheet(style.QSS)
    janela = MainWindow(AppState.load())
    janela.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
