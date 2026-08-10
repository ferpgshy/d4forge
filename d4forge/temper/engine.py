"""Ciclo do Tempering.

    Temper Item -> Skip -> le' o resultado -> Close -> repete

Despachante, nao sequencia fixa - mesma escolha do encantamento, e pelo mesmo
motivo: a tela e' quem manda. Aqui isso importa ainda mais, porque a animacao
tem duracao variavel e o resultado so' aparece quando ela termina.

**A regra de conducao que vale mais que todas.** O Tempering SUBSTITUI o afixo
que ja' esta' no item ("Note: Existing affix will be replaced"). Entao, na
duvida, o ciclo PARA - nunca continua rolando. Parar sem necessidade custa o
tempo do usuario; continuar sem necessidade rola por cima do resultado bom.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from ..automation import safety
from ..automation.sendinput import DEFAULT_PROFILE as DEFAULT_INPUT
from ..automation.sendinput import InputProfile, click_rect, jittered_point, move_to
from ..capture import ScreenCapture
from ..engine import EngineEvent, EventKind
from ..profiling import Profiler
from ..window import find_game_window
from .profile import DEFAULT_TEMPER_PROFILE, TemperProfile
from .result import TemperResult, parse_temper_result, read_text_lines
from .rules import Recharge, TemperGoal, TemperLimits
from .states import TemperState, detect_temper_state

log = logging.getLogger(__name__)

Listener = Callable[[EngineEvent], None]


@dataclass
class TemperAttempt:
    index: int
    result: TemperResult
    accepted: bool = False
    reason_key: str = ""
    params: dict = field(default_factory=dict)

    @property
    def reason(self) -> str:
        from ..i18n import t

        return t(self.reason_key, **self.params) if self.reason_key else ""


@dataclass
class TemperOutcome:
    found: bool
    reason_key: str
    params: dict = field(default_factory=dict)
    attempts: list[TemperAttempt] = field(default_factory=list)
    recharges: int = 0
    elapsed_s: float = 0.0

    @property
    def reason(self) -> str:
        from ..i18n import t

        return t(self.reason_key, **self.params)

    @property
    def count(self) -> int:
        return len(self.attempts)


class TemperEngine:
    """Roda o ciclo do Tempering ate' bater a meta ou uma trava."""

    # Espera antes de reclicar quando a tela nao muda. Mesmo raciocinio do
    # encantamento: `state_timeout` e' o prazo para desistir da sessao, e
    # gasta-lo entre duas tentativas so' faz o ciclo parecer travado.
    RETRY_AFTER_S = 1.0

    def __init__(
        self,
        goal: TemperGoal,
        ocr,
        limits: TemperLimits | None = None,
        profile: TemperProfile = DEFAULT_TEMPER_PROFILE,
        capture: ScreenCapture | None = None,
        listener: Listener | None = None,
        poll_interval: float = 0.06,
        state_timeout: float = 12.0,
        profiler: Profiler | None = None,
        input_profile: InputProfile = DEFAULT_INPUT,
        require_foreground: bool = True,
    ) -> None:
        self.goal = goal
        self.ocr = ocr
        self.limits = limits or TemperLimits()
        self.profile = profile
        self.capture = capture or ScreenCapture()
        self.poll_interval = poll_interval
        # Mais folgado que o encantamento: a animacao do Tempering e' bem mais
        # longa que a troca de tela do Occultist.
        self.state_timeout = state_timeout
        self.profiler = profiler if profiler is not None else Profiler()
        self.input_profile = input_profile
        self.require_foreground = require_foreground

        self._listener = listener
        self._cancel = threading.Event()
        self._resolved = None
        self.recharges = 0
        # Cliques de recarga seguidos que nao acenderam o Temper Item, e o
        # total da rajada. Ambos zeram quando o ciclo consegue temperar.
        self._dead = 0
        self._burst = 0
        # Intervalo que a receita ja' mostrou nesta sessao. A receita nao muda
        # no meio do caminho, entao ele serve de segundo voto sobre a unica
        # leitura que encerra o ciclo - ver TemperResult.corroborated.
        self._known_range: tuple[float, float] | None = None

    # -- infraestrutura ---------------------------------------------------
    def cancel(self) -> None:
        self._cancel.set()

    def _emit(self, kind: EventKind, key: str, **data) -> None:
        evento = EngineEvent(kind, key, data)
        log.debug("%s: %s", kind.value, evento.message)
        if self._listener is not None:
            self._listener(evento)

    def _sleep(self, seconds: float) -> None:
        if self._cancel.wait(seconds):
            raise safety.StopReason("stop.cancelled")

    def _frame(self):
        win = find_game_window()
        if win is None:
            raise safety.StopReason("stop.no_window")
        if self.require_foreground and not win.is_foreground:
            raise safety.StopReason("stop.lost_focus")
        if self._resolved is None or self._resolved.client != win.client:
            self._resolved = self.profile.scaled(win.client)
            self._emit(EventKind.INFO, "eng.window", w=win.client.w, h=win.client.h,
                       x=win.client.x, y=win.client.y, scale=self._resolved.scale)
            if self._resolved.widescreen:
                self._emit(EventKind.INFO, "eng.widescreen",
                           w=win.client.w, h=win.client.h)
        with self.profiler.measure("captura de tela"):
            frame = self.capture.grab(win.client)
        if frame is None:
            raise safety.StopReason("stop.capture_failed")
        return frame, self._resolved

    def _observe(self):
        frame, prof = self._frame()
        with self.profiler.measure("detectar estado"):
            leitura = detect_temper_state(frame, prof, self.ocr)
        return frame, prof, leitura

    def _click(self, rect, label: str, park: bool = True) -> None:
        onde = click_rect(rect, self.input_profile)
        self._emit(EventKind.CLICK, "eng.click", label=label, x=onde.x, y=onde.y)
        if park:
            self._park_cursor()

    def _park_cursor(self) -> None:
        """Tira o cursor de cima do que vamos ler.

        O cursor do jogo entra na captura, entao deixa-lo sobre um botao faz a
        leitura daquele botao medir o cursor junto - ver `cursor_park` no
        perfil. Aqui ele e' estacionado depois de TODO clique: os dois botoes em
        que clicamos no painel (Temper Item e o circular) sao exatamente os dois
        que lemos para decidir o que fazer em seguida.
        """
        if self._resolved is None:
            return
        destino = jittered_point(self._resolved.cursor_park)
        move_to(destino.x, destino.y)

    # Enquanto a ANIMACAO roda, sondar custa caro: o brilho dela invade a
    # regiao do titulo, entao o OCR que decide "animacao ou resultado" roda
    # inteiro a cada volta - medido, 37,5 ms contra 3-5 ms nas outras telas, e
    # com o jogo disputando CPU isso piora muito. Espacar as sondagens corta o
    # custo sem mexer em NENHUM criterio de deteccao; o preco e' detectar o fim
    # da animacao ate' 120 ms mais tarde, que nao muda nada num ciclo de
    # segundos.
    ANIMATION_POLL_FACTOR = 3

    def _wait_state_change(self, previous: TemperState, timeout: float):
        """Espera a tela sair do estado atual. None se nao mudar a tempo."""
        started = time.monotonic()
        deadline = started + timeout
        intervalo = self.poll_interval * (
            self.ANIMATION_POLL_FACTOR if previous is TemperState.ANIMATION else 1
        )
        while time.monotonic() < deadline:
            if self._cancel.is_set():
                raise safety.StopReason("stop.cancelled")
            frame, prof, leitura = self._observe()
            if leitura.state is not previous and leitura.state is not TemperState.UNKNOWN:
                self.profiler.record(
                    f"reação: {previous.value} → {leitura.state.value}",
                    (time.monotonic() - started) * 1000,
                )
                self._emit(EventKind.STATE, "eng.screen", state=leitura.state.value)
                return frame, prof, leitura
            self._sleep(intervalo)
        return None

    def _act(self, rect, label: str, state: TemperState, attempts: int = 3):
        """Clica e espera a tela mudar; repete o clique se ela nao mudar."""
        for i in range(attempts):
            ultima = i + 1 == attempts
            self._click(rect, label if i == 0 else f"{label} ({i + 1})")
            mudou = self._wait_state_change(
                state, self.state_timeout if ultima else self.RETRY_AFTER_S
            )
            if mudou is not None:
                return mudou
            if not ultima:
                self._emit(EventKind.INFO, "eng.click_retry", label=label)
        raise safety.StopReason(
            "stop.click_lost", label=label, attempts=attempts, state=state.value
        )

    # -- leitura do resultado ---------------------------------------------
    # Quanto esperar o afixo aparecer depois de a tela virar "resultado".
    #
    # O TEMPER COMPLETE nao surge inteiro de uma vez: o titulo aparece ANTES da
    # linha do afixo. Lendo no primeiro quadro em que o titulo esta' legivel, a
    # regiao do afixo ainda esta' vazia - e o ciclo parava dizendo que nao
    # conseguiu ler, 0,6 s depois de comecar. Isto e' esperar a tela terminar de
    # se desenhar, nao insistir numa leitura ruim: assim que sai algo legivel a
    # espera acaba.
    RESULT_SETTLE_S = 3.0

    def _read_result(self, frame: np.ndarray, prof) -> TemperResult:
        with self.profiler.measure("ler afixo (OCR)"):
            texto = read_text_lines(frame, prof.result_text, self.ocr, prof.scale)
        lido = parse_temper_result(texto)
        if lido.has_range:
            self._known_range = (lido.low, lido.high)
        return lido.corroborated(self._known_range)

    def _read_result_settled(self, frame: np.ndarray, prof) -> TemperResult:
        """Le' o afixo, esperando a tela acabar de aparecer."""
        resultado = self._read_result(frame, prof)
        if resultado.readable:
            return resultado

        limite = time.monotonic() + self.RESULT_SETTLE_S
        while time.monotonic() < limite:
            self._sleep(self.poll_interval)
            frame, prof, leitura = self._observe()
            if leitura.state is not TemperState.RESULT:
                # A tela saiu do resultado enquanto esperavamos; devolve o que
                # havia para quem chamou decidir.
                return resultado
            tentativa = self._read_result(frame, prof)
            if tentativa.readable:
                return tentativa
            resultado = tentativa
        return resultado

    # -- ciclo principal --------------------------------------------------
    def run(self) -> TemperOutcome:
        started = time.monotonic()
        attempts: list[TemperAttempt] = []
        self._cancel.clear()
        self.recharges = 0
        self._burst = self._dead = 0

        def fim(found: bool, key: str, **params) -> TemperOutcome:
            return TemperOutcome(
                found, key, params, attempts, self.recharges,
                time.monotonic() - started,
            )

        self._emit(EventKind.INFO, "temper.goal", goal=self.goal.describe())

        try:
            while True:
                if self._cancel.is_set():
                    raise safety.StopReason("stop.cancelled")
                if len(attempts) >= self.limits.max_attempts:
                    raise safety.StopReason(
                        "stop.max_attempts", count=self.limits.max_attempts
                    )
                if self.limits.max_minutes is not None:
                    if (time.monotonic() - started) / 60 >= self.limits.max_minutes:
                        raise safety.StopReason(
                            "stop.max_time", minutes=self.limits.max_minutes
                        )

                frame, prof, leitura = self._observe()

                if leitura.state is TemperState.UNKNOWN:
                    raise safety.StopReason("temper.unknown_screen")

                if leitura.state is TemperState.RECIPES:
                    # O usuario escolhe a receita; o app so' repete o ciclo.
                    # Clicar numa receita sozinho gastaria rerolls num afixo que
                    # ele nao pediu.
                    raise safety.StopReason("temper.recipes_open")

                if leitura.state is TemperState.ANIMATION:
                    self._act(prof.skip_or_close, "Skip", TemperState.ANIMATION)
                    continue

                if leitura.state is TemperState.RESULT:
                    resultado = self._read_result_settled(frame, prof)
                    aceita, chave, params = self.goal.accepts(resultado)
                    tentativa = TemperAttempt(
                        index=len(attempts) + 1, result=resultado,
                        accepted=aceita, reason_key=chave, params=params,
                    )
                    attempts.append(tentativa)
                    self._emit(
                        EventKind.ATTEMPT, "temper.attempt",
                        index=tentativa.index, affix=resultado.describe(),
                        reason=tentativa.reason, attempt=tentativa,
                    )

                    if aceita:
                        self._emit(EventKind.SUCCESS, chave, **params)
                        return fim(True, chave, **params)

                    if not resultado.readable:
                        # Nao da' para dizer o que saiu. Continuar rolaria por
                        # cima de um resultado que pode ser o bom.
                        self._dump(frame, "resultado_ilegivel")
                        raise safety.StopReason(
                            "temper.unreadable_stop", raw=resultado.raw
                        )

                    self._act(prof.skip_or_close, "Close", TemperState.RESULT)
                    continue

                # IDLE: quem manda e' o botao.
                #
                # "Temper Item aceso" e' o proprio jogo dizendo que da' para
                # agir, e nada pode vir antes disso. Perguntar primeiro se ha'
                # contador de rerolls me custou um bug: num slot LIVRE o jogo
                # escreve "Adds your selected affix", nao mostra contador
                # nenhum - e mesmo assim o botao esta' aceso, porque ali se
                # ADICIONA um afixo em vez de rerrolar. O ciclo parava dizendo
                # que nao havia receita escolhida, com a receita escolhida.
                if leitura.can_temper:
                    # Temperou: a recarga cumpriu o papel, os contadores de
                    # descontrole voltam a zero.
                    self._burst = self._dead = 0
                    self._act(prof.temper_button, "Temper Item", TemperState.IDLE)
                    continue

                if leitura.can_recharge:
                    acao = self._recharge(prof, leitura)
                    if acao is not None:
                        raise acao
                    continue

                # Botao apagado e sem recarga possivel. O contador de rerolls
                # so' existe depois de uma receita escolhida, entao a ausencia
                # dele aqui separa "escolha a receita" de "acabaram os
                # Pergaminhos" - dois becos que pedem acoes opostas.
                if not leitura.has_rerolls:
                    raise safety.StopReason("temper.no_recipe")
                raise safety.StopReason("temper.no_scrolls")

        except safety.StopReason as stop:
            self._emit(EventKind.STOPPED, stop.key, **stop.params)
            return fim(False, stop.key, **stop.params)
        except Exception as exc:  # noqa: BLE001 - a GUI precisa ver qualquer falha
            log.exception("engine de tempering quebrou")
            self._emit(EventKind.ERROR, "eng.error", error=str(exc))
            return fim(False, "eng.error", error=str(exc))
        finally:
            self.capture.close()

    # Tempo para o jogo atualizar o botao circular depois de um clique.
    #
    # Curto de proposito: encher um item e' varios cliques seguidos e 0,4 s
    # entre eles fazia a recarga parecer travada. Nao da' para zerar - a leitura
    # seguinte pegaria o estado velho do botao e clicariamos a' toa, e cada
    # clique a' toa e' um Pergaminho. 0,12 s e' uma volta de tela com folga.
    RECHARGE_SETTLE_S = 0.12

    # Cliques de recarga seguidos SEM EFEITO antes de desistir.
    #
    # "Sem efeito" tem um sinal exato: uma recarga bem-sucedida da' ao item pelo
    # menos um reroll, e com um reroll o Temper Item ACENDE. Se ele continua
    # cinza depois do clique, aquele clique nao fez nada.
    #
    # Isto nao e' preferencia do usuario e ele nao pode desligar. O teto que ele
    # escolhe pode ser "sem limite", e ai a unica saida do laco era o botao
    # circular apagar - o que o proprio jogo faz quando o item enche, ja' que
    # cada item tem seu limite de rerolls. Mas se o clique nao esta' pegando, o
    # botao nunca apaga e o ciclo clica para sempre, gastando um Pergaminho por
    # volta. Tres cliques inuteis ja' provam o problema.
    MAX_DEAD_CLICKS = 3

    # Rede por cima: nenhum item guarda tantos rerolls, entao chegar aqui
    # significa que algo escapou da checagem acima.
    MAX_RECHARGE_BURST = 12

    def _recharge(self, prof, leitura) -> safety.StopReason | None:
        """Recarrega os Temper Rerolls conforme a politica. Devolve a parada.

        No modo FULL o botao circular e' clicado ENQUANTO seguir aceso: ele
        apaga sozinho ao bater o limite do item, e e' esse apagar que define
        "cheio". Clicar uma vez so' e voltar ao ciclo - como fazia antes - dava
        na pratica o mesmo que "1 por vez".
        """
        if self.goal.recharge is Recharge.STOP:
            return safety.StopReason("temper.out_of_rerolls")

        antes = self.recharges
        teto = self.goal.max_recharges
        while True:
            if self._burst >= self.MAX_RECHARGE_BURST:
                return safety.StopReason(
                    "temper.recharge_runaway", count=self._burst
                )
            if teto is not None and self.recharges >= teto:
                # So' e' beco sem saida se nao conseguimos adicionar NADA nesta
                # parada; tendo adicionado algo, o ciclo segue com o que deu.
                if self.recharges == antes:
                    return safety.StopReason("temper.recharge_limit", count=teto)
                break

            self._click(prof.recharge_button, "recarregar")
            self.recharges += 1
            self._burst += 1
            self._emit(EventKind.INFO, "temper.recharged", count=self.recharges)
            self._sleep(self.RECHARGE_SETTLE_S)

            _frame, prof, leitura = self._observe()

            # O clique surtiu efeito? Um reroll a mais acende o Temper Item.
            if leitura.can_temper:
                self._dead = 0
            else:
                self._dead += 1
                if self._dead >= self.MAX_DEAD_CLICKS:
                    return safety.StopReason(
                        "temper.recharge_runaway", count=self._dead
                    )

            if self.goal.recharge is Recharge.ONE:
                break

            # FULL: o proprio botao diz quando parar - ele apaga quando o item
            # bate o proprio limite de rerolls.
            if leitura.state is not TemperState.IDLE or not leitura.can_recharge:
                break
        return None

    def _dump(self, frame, tag: str) -> None:
        try:
            from ..config import CAPTURES_DIR
            from ..imageio import imwrite

            caminho = CAPTURES_DIR / f"debug_temper_{tag}_{time.strftime('%H%M%S')}.png"
            if imwrite(caminho, frame):
                self._emit(EventKind.INFO, "eng.frame_saved", name=caminho.name)
        except Exception as exc:  # noqa: BLE001 - diagnostico nao derruba o bot
            log.debug("falha ao salvar quadro: %s", exc)
