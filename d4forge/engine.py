"""Maquina de estados do encantamento.

Cobre o ciclo de como-funciona-enchant.md:

    Enchant -> [Accept] -> [le as 2 opcoes] -> Replace Affix -> Close -> repete

O `Accept` esta' entre colchetes porque **o dialogo de confirmacao nem sempre
aparece**: observado no jogo, o clique em Enchant as vezes leva direto para a
tela Replace Affix. Por isso isto aqui nao e' uma sequencia fixa e sim um
despachante - a cada volta ele olha em que tela o jogo ESTA' e escolhe a acao
correspondente. Uma sequencia rigida travava na primeira volta esperando um
dialogo que nunca vinha.

Regras de conducao:

* O engine nunca clica sem antes confirmar em que tela esta'. Depois de agir,
  espera a tela mudar; se ela nao mudar, ele para - o clique errou o alvo.
* Depois de marcar uma opcao, ele RECONFERE que o orbe certo acendeu antes de
  apertar Replace Affix. Sem essa checagem, um clique perdido trocaria o afixo
  pela opcao errada - e isso nao tem desfazer.
* Leitura duvidosa vira No Change. Perder uma tentativa custa ouro; trocar o
  afixo bom por engano custa o item.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

import numpy as np

from .affixes import AffixCatalog, ParsedAffix, parse_affix
from .automation import safety
from .automation.sendinput import DEFAULT_PROFILE as DEFAULT_INPUT
from .automation.sendinput import InputProfile, click_rect, jittered_point, move_to
from .capture import ScreenCapture
from .geometry import Point
from .profile import EnchantProfile, ResolvedProfile
from .profiling import Profiler
from .rules import Action, Decision, RuleSet
from .vision.ocr import OcrEngine
from .vision.states import ScreenState, detect_state, selected_orb
from .window import find_game_window

log = logging.getLogger(__name__)


def _same_reading(raw: str, shown: str) -> bool:
    """Duas grafias da mesma leitura? Ignora '+', virgula de milhar e caixa."""
    strip = lambda s: re.sub(r"[^a-z0-9.%]", "", s.lower())  # noqa: E731
    return strip(raw) == strip(shown)


class EventKind(Enum):
    INFO = "info"
    STATE = "state"
    READ = "read"
    DECISION = "decision"
    CLICK = "click"
    ATTEMPT = "attempt"
    SUCCESS = "success"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class EngineEvent:
    """Chave de traducao + argumentos, nao texto pronto.

    A interface guarda os eventos para reapresentar tudo quando o idioma muda;
    com a frase ja' montada, o historico ficaria congelado na lingua antiga.
    """

    kind: EventKind
    key: str
    data: dict = field(default_factory=dict)

    @property
    def message(self) -> str:
        from .i18n import t

        return t(self.key, **self.data)


Listener = Callable[[EngineEvent], None]


@dataclass
class Attempt:
    index: int
    options: list[ParsedAffix]
    decision: Decision
    cost: int = 0

    def describe(self) -> str:
        from .i18n import t

        opts = " | ".join(o.describe() for o in self.options) or t("progress.none")
        return t("eng.attempt", index=self.index, options=opts,
                 reason=self.decision.reason)


@dataclass
class Outcome:
    found: bool
    # Chave de traducao do motivo; `reason` renderiza no idioma corrente.
    reason_key: str
    params: dict = field(default_factory=dict)
    attempts: list[Attempt] = field(default_factory=list)
    gold_spent: int = 0
    elapsed_s: float = 0.0

    @property
    def reason(self) -> str:
        from .i18n import t

        return t(self.reason_key, **self.params)

    @property
    def count(self) -> int:
        return len(self.attempts)


class EnchantEngine:
    """Roda o ciclo de encantamento ate' achar o afixo ou bater uma trava."""

    def __init__(
        self,
        ruleset: RuleSet,
        catalog: AffixCatalog,
        ocr: OcrEngine,
        guard: safety.Guard,
        profile: EnchantProfile,
        capture: ScreenCapture | None = None,
        dry_run: bool = True,
        listener: Listener | None = None,
        poll_interval: float = 0.06,
        state_timeout: float = 8.0,
        start_delay: float = 4.0,
        focus_game_on_start: bool = True,
        profiler: Profiler | None = None,
        input_profile: InputProfile = DEFAULT_INPUT,
    ) -> None:
        self.ruleset = ruleset
        self.catalog = catalog
        self.ocr = ocr
        self.guard = guard
        self.profile = profile
        self.capture = capture or ScreenCapture()
        self.dry_run = dry_run
        self.poll_interval = poll_interval
        self.state_timeout = state_timeout
        self.start_delay = start_delay
        self.focus_game_on_start = focus_game_on_start
        self.profiler = profiler if profiler is not None else Profiler()
        self.input_profile = input_profile

        self._listener = listener
        self._cancel = threading.Event()
        self._resolved: ResolvedProfile | None = None
        self._dumped_tags: set[str] = set()
        self._read_seq = 0

    # -- infraestrutura ---------------------------------------------------
    def cancel(self) -> None:
        self._cancel.set()

    def _emit(self, kind: EventKind, key: str, **data) -> None:
        evento = EngineEvent(kind, key, data)
        log.debug("%s: %s", kind.value, evento.message)
        if self._listener is not None:
            self._listener(evento)

    def _refresh_profile(self) -> ResolvedProfile:
        win = find_game_window()
        if win is None:
            raise safety.StopReason("stop.no_window")
        if self._resolved is None or self._resolved.client != win.client:
            self._resolved = self.profile.scaled(win.client)
            self._emit(EventKind.INFO, "eng.window", w=win.client.w, h=win.client.h,
                       x=win.client.x, y=win.client.y, scale=self._resolved.scale)
            # Fora de 16:9 a posicao horizontal das ROIs vem do modelo de
            # ancoragem, nao de medicao numa tela dessa proporcao. Dizer isso e'
            # mais util do que deixar o usuario descobrir por um clique perdido.
            if self._resolved.widescreen:
                self._emit(EventKind.INFO, "eng.widescreen",
                           w=win.client.w, h=win.client.h)
        return self._resolved

    def _frame(self) -> tuple[np.ndarray, ResolvedProfile]:
        prof = self._refresh_profile()
        with self.profiler.measure("captura de tela"):
            frame = self.capture.grab(prof.client)
        if frame is None:
            raise safety.StopReason("stop.capture_failed")
        return frame, prof

    def _sleep(self, seconds: float) -> None:
        if self._cancel.wait(seconds):
            raise safety.StopReason("stop.cancelled")

    def _verify_parse(self, text: str) -> bool:
        return parse_affix(text, self.catalog).confident

    # -- observacao da tela -----------------------------------------------
    def _observe(self):
        """Le' a tela agora: devolve (frame, perfil, estado)."""
        frame, prof = self._frame()
        with self.profiler.measure("detectar estado"):
            state = detect_state(frame, prof).state
        return frame, prof, state

    def _wait_stable(self, rois, timeout: float = 0.8, interval: float = 0.015):
        """Espera as regioes pararem de mudar - fim da animacao.

        Substitui os `sleep` de tempo fixo que eu tinha chutado. Aqui o custo e'
        o que a animacao realmente leva na maquina do usuario: costuma resolver
        em ~30 ms, contra os 200 ms que eu dormia antes.
        """
        deadline = time.monotonic() + timeout
        previous = None
        frame, prof = self._frame()
        with self.profiler.measure("esperar tela estabilizar"):
            while time.monotonic() < deadline:
                frame, prof = self._frame()
                current = [np.ascontiguousarray(r.crop(frame)) for r in rois]
                if previous is not None and all(
                    np.array_equal(a, b) for a, b in zip(previous, current)
                ):
                    break
                previous = current
                self._sleep(interval)
        return frame, prof

    def _act(self, rect, label: str, state: ScreenState, attempts: int = 3) -> None:
        """Clica e espera a tela mudar; repete o clique se ela nao mudar.

        Clique isolado se perde: o jogo pode estar num quadro de animacao, ou o
        botao ainda nao aceitar entrada. Antes disso, um unico clique perdido
        encerrava a sessao inteira - aconteceu na tentativa 71 de uma sessao
        real, com o Replace Affix. Repetir e' seguro porque so' repetimos
        enquanto a tela NAO mudou: se o primeiro clique tivesse funcionado, ja'
        teriamos saido daqui.
        """
        for i in range(attempts):
            sufixo = "" if i == 0 else f" (tentativa {i + 1})"
            self._click(rect, f"{label}{sufixo}")
            if self._wait_until_leaves(state, f"clicar em {label}", fatal=False):
                return
            if i + 1 < attempts:
                self._emit(
                    EventKind.INFO,
                    "eng.click_retry", label=label,
                )
        self._dump_frame(f"clique_perdido_{label.replace(' ', '_').lower()}")
        raise safety.StopReason(
            "stop.click_lost", label=label, attempts=attempts, state=state.value
        )

    def _wait_until_leaves(self, previous: ScreenState, what: str, fatal: bool = True):
        """Espera a tela SAIR do estado atual, seja para qual for.

        O fluxo do Occultist nao e' uma sequencia fixa: o dialogo de confirmacao
        as vezes nao aparece e o jogo vai direto de Enchant para Replace Affix.
        Por isso esperamos "mudou de tela" em vez de exigir uma tela especifica -
        quem decide o que fazer com a tela nova e' o despachante do run().
        """
        started = time.monotonic()
        deadline = started + self.state_timeout
        while time.monotonic() < deadline:
            if self._cancel.is_set():
                raise safety.StopReason("stop.cancelled")
            self.guard.check()
            frame, prof, state = self._observe()
            if state is not previous and state is not ScreenState.UNKNOWN:
                # Quanto o JOGO levou para responder ao clique. E' desta medida
                # que saem as esperas ajustadas.
                self.profiler.record(
                    f"reação: {previous.value} → {state.value}",
                    (time.monotonic() - started) * 1000,
                )
                self._emit(EventKind.STATE, "eng.screen", state=state.value)
                return frame, prof, state
            self._sleep(self.poll_interval)

        if self.dry_run:
            # Em simulacao nada foi clicado, entao a tela nao tinha por que mudar.
            # Continuar observando deixa voce avancar as telas na mao e ver o que
            # o bot faria em cada uma.
            self._emit(
                EventKind.INFO,
                "eng.sim_manual",
            )
            return None

        if not fatal:
            return None

        # Era o unico caminho de parada sem evidencia gravada: o log dizia que a
        # tela nao mudou e nao sobrava nada para conferir depois.
        self._dump_frame(f"tela_travada_em_{previous.value}")
        raise safety.StopReason(
            "stop.screen_stuck", what=what, state=previous.value,
            seconds=self.state_timeout,
        )

    def _dump_frame(self, tag: str) -> None:
        """Salva o quadro atual quando algo inesperado acontece.

        Diagnosticar por deducao a partir do log nao funciona: precisamos ver os
        pixels que o app viu no momento em que decidiu parar.
        """
        try:
            from .config import CAPTURES_DIR
            from .imageio import imwrite

            frame, _prof = self._frame()
            stamp = time.strftime("%H%M%S")
            path = CAPTURES_DIR / f"debug_{tag}_{stamp}.png"
            if imwrite(path, frame):
                self._emit(EventKind.INFO, "eng.frame_saved", name=path.name)
        except Exception as exc:  # noqa: BLE001 - diagnostico nunca pode derrubar o bot
            log.debug("falha ao salvar quadro de diagnostico: %s", exc)

    def _confirm_no_selection(self, samples: int = 5) -> bool:
        """Confirma, em varios quadros, que realmente nao ha' afixo marcado.

        Um unico quadro nao serve: logo depois de fechar o dialogo o painel
        reaparece com fade, e durante a transicao a leitura pode acusar a lista
        de selecao sem orbe aceso. Parar o ciclo por causa de um quadro assim
        interrompia a sessao sem motivo.
        """
        for _ in range(samples):
            self._sleep(0.25)
            frame, prof, state = self._observe()
            if state is not ScreenState.ENCHANT_SELECT:
                return False
            if selected_orb(frame, prof.affix_orbs) is not None:
                return False
        return True

    # -- acoes ------------------------------------------------------------
    def _click(self, rect, label: str, park: bool = True) -> None:
        if self.dry_run:
            self._emit(EventKind.CLICK, "eng.click_sim", label=label)
            return
        with self.profiler.measure(f"clique: {label}"):
            where = click_rect(rect, self.input_profile)
        self.guard.note_click(where)
        self._emit(EventKind.CLICK, "eng.click", label=label, x=where.x, y=where.y)
        if park:
            self._park_cursor(where)

    def _reads_from(self, prof) -> list:
        """ROIs cujo conteudo o app le' - onde o cursor atrapalha."""
        return [
            prof.locked_affix, prof.replace_current, prof.occultist_title,
            prof.replace_title, prof.result_title, prof.enchant_cost,
            *prof.replace_options, *prof.replace_orbs,
            *prof.affix_rows, *prof.affix_orbs,
        ]

    def _park_cursor(self, after: Point | None = None) -> None:
        """Tira o cursor de cima da interface depois de clicar.

        O cursor do jogo faz parte do quadro renderizado, entao onde ele para
        vira ruido para a deteccao de estado e para o OCR.

        Se o clique caiu longe de tudo que lemos, nao ha' o que corrigir e o
        passeio ate' o ponto de estacionamento e' so' tempo perdido - e e' o que
        fazia o movimento parecer que ia e voltava a cada volta. Medido: dos
        tres cliques do ciclo, so' o do Close cai dentro de uma ROI lida.
        """
        try:
            if after is not None:
                prof = self._refresh_profile()
                if not any(roi.contains(after) for roi in self._reads_from(prof)):
                    return
        except Exception as exc:  # noqa: BLE001
            log.debug("não consegui decidir sobre estacionar: %s", exc)
        try:
            prof = self._refresh_profile()
            spot = jittered_point(prof.cursor_park)
            move_to(spot.x, spot.y)
            # O guard compara a posicao do cursor com a do ultimo clique para
            # detectar mao humana no mouse; sem atualizar, ele acusaria a si
            # mesmo de ter movido o mouse.
            self.guard.note_click(spot)
        except Exception as exc:  # noqa: BLE001 - nunca derrubar o ciclo por isto
            log.debug("não consegui estacionar o cursor: %s", exc)

    def _read_cost(self, frame, prof) -> int:
        """Le' o preco do Enchant - so' quando ele muda alguma decisao.

        O preco sobe a cada encantamento, entao esta leitura nunca acerta o
        cache: e' uma terceira chamada ao modelo por volta, do mesmo custo das
        outras duas. Como ela so' alimenta o limite de ouro, pular quando nao ha'
        limite corta um terco do trabalho de OCR do ciclo.
        """
        if self.guard.limits.max_gold is None:
            return 0
        with self.profiler.measure("ler custo (OCR)"):
            result = self.ocr.read(prof.enchant_cost.crop(frame), ui_scale=prof.scale)
        digits = "".join(c for c in result.text if c.isdigit())
        return int(digits) if digits else 0

    def _read_current(self, frame, prof, locked: bool = False) -> ParsedAffix | None:
        """Le' o afixo que o item tem AGORA (base da escalada).

        Devolve None quando a leitura nao e' confiavel - e sem saber o que o
        item tem, a escalada fica desligada naquela rodada: trocar as cegas e'
        como se rebaixa um roll bom sem perceber.
        """
        roi = prof.locked_affix if locked else prof.replace_current
        with self.profiler.measure("ler afixo (OCR)"):
            res = self.ocr.read(roi.crop(frame), self._verify_parse, ui_scale=prof.scale)
        parsed = parse_affix(res.text, self.catalog)
        if not parsed.confident:
            return None
        self._emit(EventKind.READ, "eng.current", affix=parsed.describe(), raw=res.text)
        return parsed

    def _read_options(self, frame, prof) -> list[ParsedAffix]:
        options: list[ParsedAffix] = []
        self._read_seq += 1
        for i, roi in enumerate(prof.replace_options, 1):
            with self.profiler.measure("ler afixo (OCR)"):
                res = self.ocr.read(roi.crop(frame), self._verify_parse, ui_scale=prof.scale)
            # Separar o tempo dentro do modelo do resto revela se a lentidao e'
            # do OCR ou de disputa de CPU com o jogo.
            self.profiler.record("  ├ modelo", res.backend_ms)
            self.profiler.record("  └ preparo/cache", res.overhead_ms)
            if res.retried:
                self.profiler.record("  ! repescagem de OCR", res.backend_ms)
            parsed = parse_affix(res.text, self.catalog)
            options.append(parsed)
            # Mostra o texto cru so' quando ele diverge de verdade da
            # interpretacao. Comparar as strings direto enchia o log de ruido,
            # porque a exibicao acrescenta "+" e tira a virgula de milhar.
            shown = parsed.describe()
            extra = "" if _same_reading(res.text, shown) else f"   [ocr: {res.text!r}]"
            flag = "" if parsed.confident else "  (duvidoso)"
            self._emit(
                EventKind.READ,
                "eng.option" if parsed.confident else "eng.option_doubt",
                index=i, affix=shown,
                raw=res.text, source=res.source, ms=res.elapsed_ms,
                name=parsed.name, known=parsed.entry is not None,
            )
            # Guarda TODO recorte que o OCR leu, nao so' os duvidosos: e' o que
            # permite conferir depois se a leitura bateu com a tela. Sao ~20 KB
            # cada e a pasta e' esvaziada no inicio de cada sessao.
            marca = "duvidoso" if not parsed.confident else "ok"
            self._dump_crop(roi.crop(frame), f"{self._read_seq:03d}_opcao{i}_{marca}")
        if any(not p.confident for p in options):
            # O quadro inteiro, uma vez por sessao: se um afixo de duas linhas
            # deslocar o layout da tela, so' o recorte nao mostra isso.
            self._dump_frame_once("opcao_duvidosa")
        return options

    def _dump_frame_once(self, tag: str) -> None:
        if tag in self._dumped_tags:
            return
        self._dumped_tags.add(tag)
        self._dump_frame(tag)

    def _clear_session_crops(self) -> None:
        """Esvazia captures/ ao comecar: a pasta reflete so' a sessao atual.

        Uma versao anterior rotacionava para captures/sessao_anterior/ em vez de
        apagar, porque o material tinha ido embora bem quando queriamos analisa-
        lo. Com a limpeza tambem no fechamento normal da janela, a evidencia
        continua disponivel enquanto o app esta' aberto - que e' quando ela
        serve - e a pasta para de acumular.
        """
        try:
            from .config import clear_captures, ensure_dirs

            removed = clear_captures()
            ensure_dirs()
            if removed:
                self._emit(
                    EventKind.INFO,
                    "eng.captures_cleared", count=removed,
                )
        except Exception as exc:  # noqa: BLE001 - limpeza nunca derruba o ciclo
            log.debug("falha ao limpar captures: %s", exc)

    def _dump_crop(self, crop, tag: str) -> None:
        """Guarda o recorte exato que foi para o OCR.

        E' a unica forma de distinguir recorte mal posicionado de erro do
        modelo. O nome comeca com o numero da leitura para os arquivos ficarem
        na ordem em que apareceram, e nao na ordem alfabetica do relogio.
        """
        try:
            from .config import CAPTURES_DIR
            from .imageio import imwrite

            imwrite(CAPTURES_DIR / f"ocr_{tag}.png", crop)
        except Exception as exc:  # noqa: BLE001
            log.debug("falha ao salvar recorte: %s", exc)

    def _apply_decision(self, decision: Decision, prof) -> bool:
        """Marca a opcao escolhida e confere que ela realmente acendeu."""
        if decision.action is Action.NO_CHANGE:
            # No Change ja' vem marcado por padrao; nao mexemos em nada.
            self._emit(EventKind.DECISION, "eng.keeping", reason=decision.reason)
            return True

        index = decision.action.orb_index
        self._click(prof.replace_orbs[index], f"opção {index + 1}")

        if self.dry_run:
            return True

        # Reconferencia: o orbe certo tem que estar aceso antes de confirmar.
        #
        # Amostrada varias vezes de proposito. O orbe acende com animacao, e
        # julgar num quadro so' pegava o instante em que a selecao antiga ainda
        # estava acesa e a nova ainda nao - foi assim que uma troca correta para
        # "+400 Resistance to All Elements" abortou dizendo que a tela mostrava
        # o No Change.
        if self._confirm_selection(index):
            self._emit(EventKind.DECISION, "eng.option_confirmed", index=index + 1)
            return True

        self._dump_frame(f"selecao_nao_confirmada_op{index + 1}")
        self._emit(
            EventKind.ERROR,
            "eng.option_unconfirmed", index=index + 1,
        )
        return False

    def _confirm_selection(self, index: int, samples: int = 8) -> bool:
        """Espera o orbe pedido acender. True assim que confirmar."""
        seen: list[str] = []
        for _ in range(samples):
            frame, prof = self._frame()
            marked = selected_orb(frame, prof.replace_orbs)
            if marked == index:
                return True
            seen.append("nenhuma" if marked is None else f"op{marked + 1}")
            self._sleep(0.1)
        self._emit(EventKind.INFO, "eng.orb_samples", samples=", ".join(seen))
        return False

    # Tempo para o jogo terminar de vir para frente depois de um foco
    # confirmado. Medido: a janela responde em ~120 ms; 0,4 s cobre com folga.
    FOCUS_SETTLE_S = 0.4

    def _countdown(self) -> None:
        """Traz o jogo para frente e espera o necessario - nao mais que isso.

        Quem esta' em primeiro plano quando voce aperta Iniciar e' a janela do
        proprio app, nao o Diablo IV; sem foco o guard aborta na hora. A espera
        existe para voce ter tempo de voltar ao jogo na mao.

        Mas se o foco automatico funcionou - e agora `focus()` CONFIRMA que
        funcionou, em vez de supor - nao ha' nada para esperar, e a contagem
        inteira vira atraso a' toa. Ela so' e' cumprida quando o Windows recusa
        o foco, que e' justamente o caso em que voce precisa do Alt+Tab.
        """
        win = find_game_window()
        if win is None:
            raise safety.StopReason("stop.no_window")

        focado = win.is_foreground
        if self.focus_game_on_start and not focado:
            try:
                focado = win.focus()
            except Exception:  # noqa: BLE001 - o Windows pode recusar o foco
                focado = False
            self._emit(
                EventKind.INFO, "eng.focusing" if focado else "eng.focus_failed"
            )

        remaining = self.FOCUS_SETTLE_S if focado else self.start_delay
        while remaining > 0:
            if not focado:
                self._emit(EventKind.INFO, "eng.countdown", seconds=remaining)
            step = min(1.0, remaining)
            self._sleep(step)
            remaining -= step

        # O cursor pode ter ficado em qualquer lugar da interface; a primeira
        # leitura da tela precisa dele fora do caminho.
        if not self.dry_run:
            self._park_cursor()

        # Se ainda assim o jogo não está em foco, avisa com clareza em vez de
        # deixar o guard abortar com uma mensagem genérica.
        win = find_game_window()
        if self.guard.require_foreground and (win is None or not win.is_foreground):
            raise safety.StopReason("stop.not_foreground")

    # -- ciclo principal --------------------------------------------------
    def run(self) -> Outcome:
        started = time.monotonic()
        attempts: list[Attempt] = []
        self._cancel.clear()

        if self.dry_run:
            self._emit(EventKind.INFO, "eng.sim_manual")
        self._emit(EventKind.INFO, "eng.limits", limits=self.guard.limits.describe())
        self._emit(EventKind.INFO, "eng.rules", count=len(self.ruleset.active))

        # Despachante: age pelo que ESTA' na tela, nao por uma ordem fixa.
        # O jogo pula o dialogo de confirmacao dependendo do item/estado, entao
        # exigir a sequencia completa quebrava o ciclo na primeira volta.
        last_cost = 0
        found: Decision | None = None
        idle_since = time.monotonic()
        last_acted: ScreenState | None = None

        self._clear_session_crops()
        self._dumped_tags.clear()
        self._read_seq = 0

        try:
            if not self.dry_run and safety.set_high_priority(True):
                self._emit(EventKind.INFO, "eng.priority")
            self._countdown()
            self.guard.started_at = time.monotonic()

            while True:
                self.guard.check()
                frame, prof, state = self._observe()

                if state is ScreenState.UNKNOWN:
                    if time.monotonic() - idle_since > self.state_timeout:
                        self._dump_frame("tela_desconhecida")
                        raise safety.StopReason("stop.unknown_screen")
                    self._sleep(self.poll_interval)
                    continue
                idle_since = time.monotonic()

                # Em simulacao a tela nunca avanca sozinha; sem isto o log
                # encheria repetindo a mesma acao para sempre.
                if self.dry_run and state is last_acted:
                    self._sleep(0.3)
                    continue
                last_acted = state

                # --- tela de encantamento: dispara a tentativa
                if state.is_enchant:
                    if found is not None:
                        self._emit(
                            EventKind.SUCCESS,
                            "eng.found", count=len(attempts), reason=found.reason,
                        )
                        return Outcome(
                            True, found.key, dict(found.params), attempts,
                            self.guard.gold_spent, time.monotonic() - started,
                        )
                    if state is ScreenState.ENCHANT_LOCKED:
                        # Se o afixo que o item JA' tem cumpre a meta, encantar
                        # de novo so' queimaria ouro e material - e, com azar,
                        # a propria meta.
                        held = self._read_current(frame, prof, locked=True)
                        rule = self.ruleset.first_match(held) if held else None
                        if rule is not None:
                            from .i18n import t

                            self._emit(EventKind.SUCCESS, "eng.already_ok",
                                       affix=held.describe(), rule=rule.describe())
                            reason = t("eng.already_ok", affix=held.describe(),
                                       rule=rule.describe())
                            return Outcome(
                                True, "eng.already_ok",
                                {"affix": held.describe(), "rule": rule.describe()},
                                attempts, self.guard.gold_spent,
                                time.monotonic() - started,
                            )
                    if state is ScreenState.ENCHANT_SELECT and selected_orb(
                        frame, prof.affix_orbs
                    ) is None:
                        if not self._confirm_no_selection():
                            continue  # era um quadro de transicao, ignora
                        if not attempts:
                            self._dump_frame("sem_selecao")
                            raise safety.StopReason("stop.no_selection")
                        # Ja' encantamos antes, entao havia afixo selecionado e o
                        # jogo mantem a escolha durante todo o processo. Nao
                        # reconhecer o orbe aqui e' mais provavel de ser falha de
                        # leitura do que a selecao ter sumido - seguimos, e se o
                        # clique nao surtir efeito a trava de "tela nao mudou"
                        # interrompe com seguranca.
                        self._dump_frame("orbe_nao_lido")
                        self._emit(
                            EventKind.INFO,
                            "eng.orb_unread",
                        )
                    last_cost = self._read_cost(frame, prof)
                    self._act(prof.enchant_button, "Enchant", state)
                    continue

                # --- confirmacao: pode simplesmente nao aparecer
                if state is ScreenState.CONFIRM:
                    _frame, prof = self._wait_stable([prof.confirm_accept])
                    self._act(prof.confirm_accept, "Accept", state)
                    continue

                # --- Replace Affix: ler, decidir, confirmar
                if state is ScreenState.REPLACE:
                    # As opcoes entram com animacao; ler antes dela terminar
                    # produz texto pela metade.
                    frame, prof = self._wait_stable(list(prof.replace_options))
                    current = self._read_current(frame, prof)
                    options = self._read_options(frame, prof)
                    decision = self.ruleset.decide(options, current)
                    self._emit(EventKind.DECISION, decision.reason)

                    if not self._apply_decision(decision, prof):
                        raise safety.StopReason("stop.unconfirmed")

                    self._click(prof.replace_button, "Replace Affix")

                    attempt = Attempt(len(attempts) + 1, options, decision, last_cost)
                    attempts.append(attempt)
                    self.guard.note_attempt(last_cost)
                    # A tentativa vai inteira no evento: a interface monta a
                    # tabela do histórico a partir daqui, não de texto.
                    self._emit(
                        EventKind.ATTEMPT, "eng.attempt",
                        index=attempt.index,
                        options=" | ".join(o.describe() for o in options),
                        reason=decision.reason,
                        attempt=attempt,
                    )

                    # Um degrau de escalada e' aceito mas nao encerra a sessao:
                    # so' a meta da regra termina.
                    if decision.goal_reached:
                        found = decision
                    if self._wait_until_leaves(
                        state, "clicar em Replace Affix", fatal=False
                    ) is None:
                        # A tentativa ja' foi contada e paga; repetir o clique
                        # aqui apenas confirma a troca que o jogo ainda nao
                        # registrou.
                        self._act(prof.replace_button, "Replace Affix", state)
                    continue

                # --- resultado: fechar e voltar ao inicio
                if state is ScreenState.RESULT:
                    _frame, prof = self._wait_stable([prof.result_close])
                    self._act(prof.result_close, "Close", state)
                    continue

        except safety.StopReason as stop:
            self._emit(EventKind.STOPPED, stop.key, **stop.params)
            return Outcome(
                False, stop.key, dict(stop.params), attempts,
                self.guard.gold_spent, time.monotonic() - started,
            )
        except Exception as exc:  # noqa: BLE001 - a GUI precisa ver qualquer falha
            log.exception("engine quebrou")
            self._emit(EventKind.ERROR, "eng.error", error=str(exc))
            return Outcome(
                False, "eng.error", {"error": str(exc)}, attempts,
                self.guard.gold_spent, time.monotonic() - started,
            )
        finally:
            safety.set_high_priority(False)
            self.ocr.save()
