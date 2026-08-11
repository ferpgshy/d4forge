"""Ciclo do Masterworking.

    Upgrade -> ESC (pula a animacao) -> ESC (fecha o reveal) -> le' o painel

Despachante, nao sequencia fixa - mesma escolha dos outros dois fluxos, e pelo
mesmo motivo: a tela e' quem manda.

**Por que ESC e nao o botao Skip.** O segundo ESC fecha o modal que exibiria o
Masterwork, e isso pousa direto no painel, onde o "Current Masterwork Affix"
ja' esta' escrito. O reveal inteiro e' pulado - nao esperamos animacao nenhuma
terminar para saber o que saiu.

    ESC so' e' enviado com o painel COBERTO. Com o painel a' mostra, ESC fecha
    o Masterworking, e o segundo fecha o Ferreiro - o ciclo terminaria cego,
    fora de qualquer tela conhecida. A trava esta' em `_escape_to_panel`.

**A regra de conducao que vale mais que todas.** Um reroll SUBSTITUI o
Masterwork Affix atual. Entao, na duvida, o ciclo PARA. Parar sem necessidade
custa o tempo do usuario; continuar sem necessidade rola por cima do afixo bom,
e isso nao tem desfazer - e custa 10.000.000 por volta.
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
from ..automation.sendinput import (
    SCAN_ESCAPE,
    InputProfile,
    click_rect,
    jittered_point,
    move_to,
    press_key,
)
from ..capture import ScreenCapture
from ..engine import EngineEvent, EventKind
from ..profiling import Profiler
from ..window import find_game_window
from .profile import DEFAULT_MW_PROFILE, MasterworkProfile
from .result import MasterworkAffix, read_masterwork_affix
from .rules import MasterworkGoal, MasterworkLimits
from .states import MasterworkState, detect_masterwork_state

log = logging.getLogger(__name__)

Listener = Callable[[EngineEvent], None]

# Estados em que o painel do Ferreiro esta' visivel. So' aqui o Upgrade existe,
# e so' FORA daqui o ESC pode ser enviado.
PANEL_STATES = (MasterworkState.STEP, MasterworkState.AFFIX)


@dataclass
class MasterworkAttempt:
    index: int
    affix: MasterworkAffix
    accepted: bool = False
    reason_key: str = ""
    params: dict = field(default_factory=dict)

    @property
    def reason(self) -> str:
        from ..i18n import t

        return t(self.reason_key, **self.params) if self.reason_key else ""


@dataclass
class MasterworkOutcome:
    found: bool
    reason_key: str
    params: dict = field(default_factory=dict)
    attempts: list[MasterworkAttempt] = field(default_factory=list)
    elapsed_s: float = 0.0

    @property
    def reason(self) -> str:
        from ..i18n import t

        return t(self.reason_key, **self.params)

    @property
    def count(self) -> int:
        return len(self.attempts)


class MasterworkEngine:
    """Rerrola o Masterwork Affix ate' cair no afixo alvo ou bater uma trava."""

    RETRY_AFTER_S = 1.0

    # Quantos ESC seguidos sem chegar ao painel antes de desistir.
    #
    # Dois bastam pelo caminho conhecido (animacao, depois reveal). O terceiro e
    # o quarto cobrem uma tela intermediaria que ainda nao vimos em print. Alem
    # disso, teclas estao sendo enviadas as cegas - e mandar tecla as cegas e'
    # exatamente o que nao se faz. Isto nao e' preferencia e nao da' para
    # desligar.
    MAX_ESCAPES = 4

    # Pausa antes de CADA ESC: 250 ms, ESC, 250 ms, ESC.
    #
    # Fixa de proposito, e antes da tecla tambem no primeiro - senao ele sai
    # colado na troca de tela que acabou de acontecer, que e' onde o jogo
    # ignora a tecla. Antes o intervalo era o tempo que a tela levava para sair
    # do estado anterior, o que dava de ~100 ms a 1 s conforme a rodada; era o
    # "as vezes falha o ESC e ele se perde".
    ESCAPE_BEAT_S = 0.25

    # Depois do ultimo ESC, quanto esperar o painel voltar antes de desistir.
    ESCAPE_SETTLE_S = 1.2

    # Tempo maximo esperando o afixo aparecer depois de voltar ao painel.
    AFFIX_SETTLE_S = 3.0

    # Quanto insistir antes de acreditar que o Upgrade esta' cinza.
    #
    # "Cinza" e' uma AUSENCIA de tinta, e ausencia e' o sinal fragil - a mesma
    # licao que o Greater Affix do Tempering cobrou caro. Num quadro salvo pelo
    # proprio ciclo, o painel inteiro havia desenhado (dava para ler o
    # "Current Masterwork Affix" sem esforco) e SO' o interior do botao veio
    # preto, com a moldura vermelha intacta: quadro rasgado na captura, nao
    # botao desabilitado. Uma volta depois ele media 0.0461 de novo.
    #
    # Aceso decide na hora, porque presenca de tinta nao mente. So' o apagado
    # precisa de confirmacao.
    UPGRADE_CONFIRM_S = 1.5

    def __init__(
        self,
        goal: MasterworkGoal,
        ocr,
        catalog=None,
        limits: MasterworkLimits | None = None,
        profile: MasterworkProfile = DEFAULT_MW_PROFILE,
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
        self.catalog = catalog
        self.limits = limits or MasterworkLimits()
        self.profile = profile
        self.capture = capture or ScreenCapture()
        self.poll_interval = poll_interval
        self.state_timeout = state_timeout
        self.profiler = profiler if profiler is not None else Profiler()
        self.input_profile = input_profile
        self.require_foreground = require_foreground

        self._listener = listener
        self._cancel = threading.Event()
        self._resolved = None

    # -- infraestrutura ---------------------------------------------------
    def cancel(self) -> None:
        self._cancel.set()

    def _emit(self, kind: EventKind, key: str, **params) -> None:
        if self._listener is not None:
            self._listener(EngineEvent(kind, key, params))

    def _sleep(self, seconds: float) -> None:
        self._cancel.wait(seconds)

    def _frame(self):
        win = find_game_window()
        if win is None:
            raise safety.StopReason("stop.no_window")
        if self.require_foreground and not win.is_foreground:
            # `stop.lost_focus`, e nao `stop.not_foreground`: a segunda manda
            # apertar F9, que e' a tecla do encantamento. Aqui e' F11.
            raise safety.StopReason("stop.lost_focus")
        if self._resolved is None or self._resolved.client != win.client:
            self._resolved = self.profile.scaled(win.client)
        with self.profiler.measure("captura de tela"):
            frame = self.capture.grab(win.client)
        if frame is None:
            raise safety.StopReason("stop.capture_failed")
        return frame, self._resolved

    def _observe(self):
        frame, prof = self._frame()
        with self.profiler.measure("detectar estado"):
            leitura = detect_masterwork_state(frame, prof)
        return frame, prof, leitura

    def _park_cursor(self) -> None:
        """Tira o cursor de cima do que vamos ler.

        O Diablo IV desenha o proprio cursor DENTRO do quadro, entao deixa-lo
        sobre o Upgrade faria a leitura daquele botao medir o cursor junto. No
        Tempering isso fez o ciclo clicar sem parar num botao ja' apagado.
        """
        if self._resolved is None:
            return
        destino = jittered_point(self._resolved.cursor_park)
        move_to(destino.x, destino.y)

    def _click(self, rect, label: str) -> None:
        onde = click_rect(rect, self.input_profile)
        self._emit(EventKind.CLICK, "eng.click", label=label, x=onde.x, y=onde.y)
        self._park_cursor()

    def _wait_state_change(self, previous: MasterworkState, timeout: float):
        """Espera a tela sair do estado atual. None se nao mudar a tempo."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._cancel.is_set():
                raise safety.StopReason("stop.cancelled")
            frame, prof, leitura = self._observe()
            if leitura.state is not previous:
                self._emit(EventKind.STATE, "eng.screen", state=leitura.state.value)
                return frame, prof, leitura
            self._sleep(self.poll_interval)
        return None

    def _act(self, rect, label: str, state: MasterworkState, attempts: int = 3):
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

    # -- ESC ate' o painel -------------------------------------------------
    def _escape_to_panel(self):
        """Manda ESC ate' o painel do Ferreiro reaparecer.

        O caminho conhecido tem dois passos: o primeiro ESC pula a animacao, o
        segundo fecha o modal que mostraria o Masterwork. Como o segundo modal
        nunca foi capturado em print, o laco nao conta passos - ele olha a tela
        e para quando o painel esta' de volta.

        A guarda vem antes de qualquer tecla: com o painel VISIVEL, ESC fecha o
        Masterworking, e o proximo fecharia o Ferreiro. Nesse caso nao ha' nada
        a pular e a funcao devolve na hora.
        """
        for i in range(self.MAX_ESCAPES):
            # A pausa vem ANTES da tecla: 200 ms, ESC, 200 ms, ESC. O jogo
            # ignora tecla mandada em cima da troca de tela, e era isso que
            # fazia o segundo ESC se perder.
            self._sleep(self.ESCAPE_BEAT_S)

            # Olhada final antes de apertar. Custa ~20 ms e evita o unico erro
            # grave possivel aqui: com o painel de volta, ESC fecha o
            # Masterworking e o proximo fecha o Ferreiro.
            frame, prof, leitura = self._observe()
            if leitura.state in PANEL_STATES:
                return frame, prof, leitura

            self._emit(EventKind.CLICK, "mw.escape", index=i + 1)
            press_key(SCAN_ESCAPE)

        # Mandados os ESC, da' tempo do painel voltar antes de desistir.
        achou = self._wait_for_panel(self.ESCAPE_SETTLE_S)
        if achou is not None:
            return achou

        raise safety.StopReason("mw.stuck_modal", presses=self.MAX_ESCAPES)

    def _wait_for_panel(self, timeout: float):
        """Espera o painel do Ferreiro aparecer. None se nao aparecer a tempo.

        Espera o PAINEL, e nao "a tela mudar". Entre a animacao e o reveal a
        tela muda sem sair do modal, e tratar isso como progresso fazia o ciclo
        achar que o ESC funcionou quando nao tinha funcionado.
        """
        deadline = time.monotonic() + timeout
        while True:
            if self._cancel.is_set():
                raise safety.StopReason("stop.cancelled")
            frame, prof, leitura = self._observe()
            if leitura.state in PANEL_STATES:
                self._emit(EventKind.STATE, "eng.screen", state=leitura.state.value)
                return frame, prof, leitura
            if time.monotonic() >= deadline:
                return None
            self._sleep(self.poll_interval)

    # -- leitura -----------------------------------------------------------
    def _read_affix(self, frame: np.ndarray, prof) -> MasterworkAffix:
        with self.profiler.measure("ler afixo (OCR)"):
            return read_masterwork_affix(
                frame, prof.affix_text, self.ocr, self.catalog, prof.scale
            )

    @staticmethod
    def _mesma_leitura(a: MasterworkAffix, b: MasterworkAffix | None) -> bool:
        """Duas leituras dizem a MESMA coisa?

        Compara o que a decisao usa - nome e valor -, e nao o texto cru. Exigir
        o texto cru igual e' exigir que o OCR erre exatamente igual duas vezes:
        um glifo de borda que aparece numa leitura e some na outra fazia a
        confirmacao nunca fechar, e o ciclo parava dizendo que nao conseguiu ler
        um afixo que estava escrito na tela.
        """
        if b is None or not (a.readable and b.readable):
            return False
        return a.name == b.name and a.parsed.value == b.parsed.value

    def _read_affix_settled(self, frame: np.ndarray, prof) -> MasterworkAffix:
        """Le' o afixo esperando o painel terminar de se desenhar, e CONFIRMA.

        A confirmacao existe por causa de um erro que nao teria conserto. Se
        lermos antes de o jogo repintar a caixa, sai o afixo ANTERIOR - ou nada,
        porque a caixa fica em branco durante a repintura (visto num quadro de
        depuracao: a regiao do afixo saiu preta). Quando o anterior nao era o
        alvo e o novo era, o ciclo concluiria "nao e' o que eu quero" e
        rerrolaria por cima do acerto.

        Duas leituras concordantes custam ~70 ms a mais por volta, contra
        10.000.000 e um Masterwork perdido. O preco nem se discute.
        """
        limite = time.monotonic() + self.AFFIX_SETTLE_S
        anterior: MasterworkAffix | None = None
        while time.monotonic() < limite:
            atual = self._read_affix(frame, prof)
            if self._mesma_leitura(atual, anterior):
                return atual
            # Uma leitura ilegivel nao apaga a boa que veio antes: durante a
            # repintura a caixa fica em branco, e guardar esse branco jogaria
            # fora a leitura anterior e reiniciaria a confirmacao do zero.
            if atual.readable or anterior is None or not anterior.readable:
                anterior = atual

            self._sleep(self.poll_interval)
            frame, prof, leitura = self._observe()
            if leitura.state is not MasterworkState.AFFIX:
                # A tela saiu do painel enquanto esperavamos; devolve o que ha'
                # para quem chamou decidir.
                return atual
        return anterior if anterior is not None else MasterworkAffix(raw="")

    def _upgrade_disponivel(self, leitura):
        """O Upgrade esta' mesmo clicavel? Insiste antes de dizer que nao.

        Devolve `(pode, frame, prof, leitura)` com a ultima observacao feita -
        a de entrada ja' esta' velha de segundos quando chegamos aqui, porque a
        leitura do afixo espera a tela assentar antes de devolver.
        """
        if leitura.can_upgrade:
            return True, None, None, leitura

        limite = time.monotonic() + self.UPGRADE_CONFIRM_S
        while time.monotonic() < limite:
            self._sleep(self.poll_interval)
            frame, prof, nova = self._observe()
            if nova.state not in PANEL_STATES:
                # Saiu do painel: quem manda agora e' o laco principal.
                return False, frame, prof, nova
            if nova.can_upgrade:
                return True, frame, prof, nova
            leitura = nova
        return False, None, None, leitura

    def _dump(self, frame: np.ndarray, tag: str) -> None:
        try:
            from ..config import CAPTURES_DIR
            from ..imageio import imwrite

            CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
            nome = f"debug_mw_{tag}_{time.strftime('%H%M%S')}.png"
            imwrite(CAPTURES_DIR / nome, frame)
        except Exception:  # noqa: BLE001 - salvar print nunca derruba o ciclo
            log.exception("nao consegui salvar o print de depuracao")

    # -- ciclo principal ---------------------------------------------------
    def _check_limits(self, attempts: list, started: float) -> None:
        """Levanta a parada se algum teto da sessao estourou.

        Chamado no topo do laco E logo antes de clicar em Upgrade. As duas
        chamadas nao sao redundantes: so' com a segunda a sessao termina LOGO
        DEPOIS de ler a ultima tentativa, em vez de rerrolar uma vez mais e
        parar sem olhar o que saiu. Esse reroll a mais custava 10.000.000 e
        deixava o item com um afixo que o relatorio nem menciona.
        """
        if self._cancel.is_set():
            raise safety.StopReason("stop.cancelled")
        if len(attempts) >= self.limits.max_attempts:
            raise safety.StopReason("stop.max_attempts", count=self.limits.max_attempts)
        if self.limits.max_minutes is not None:
            if (time.monotonic() - started) / 60 >= self.limits.max_minutes:
                raise safety.StopReason("stop.max_time", minutes=self.limits.max_minutes)

    def run(self) -> MasterworkOutcome:
        started = time.monotonic()
        attempts: list[MasterworkAttempt] = []
        self._cancel.clear()

        def fim(found: bool, key: str, **params) -> MasterworkOutcome:
            return MasterworkOutcome(
                found, key, params, attempts, time.monotonic() - started
            )

        self._emit(EventKind.INFO, "mw.goal", goal=self.goal.describe())

        try:
            while True:
                self._check_limits(attempts, started)

                frame, prof, leitura = self._observe()

                # Qualquer coisa que nao seja o painel: animacao, o reveal, ou
                # uma tela que ainda nao vimos. ESC ate' voltar.
                if leitura.state not in PANEL_STATES:
                    frame, prof, leitura = self._escape_to_panel()

                if leitura.state is MasterworkState.AFFIX:
                    lido = self._read_affix_settled(frame, prof)
                    aceita, chave, params = self.goal.accepts(lido)
                    tentativa = MasterworkAttempt(
                        index=len(attempts) + 1, affix=lido,
                        accepted=aceita, reason_key=chave, params=params,
                    )
                    attempts.append(tentativa)
                    self._emit(
                        EventKind.ATTEMPT, "mw.attempt",
                        index=tentativa.index, affix=lido.describe(),
                        reason=tentativa.reason, attempt=tentativa,
                    )

                    if aceita:
                        self._emit(EventKind.SUCCESS, chave, **params)
                        return fim(True, chave, **params)

                    if not lido.readable:
                        # Nao da' para dizer qual afixo esta' no item. Rerrolar
                        # aqui pode estar passando por cima do afixo certo.
                        self._dump(frame, "afixo_ilegivel")
                        raise safety.StopReason("mw.unreadable_stop", raw=lido.raw)

                # Nao e' o alvo: rerrolar. A ordem daqui em diante e' a do
                # jogador - clica Upgrade, ESC, ESC, le' o Current Masterwork
                # Affix, valida. Os dois ESC acontecem no topo da volta
                # seguinte, quando a tela ja' nao e' o painel.
                pode, novo_frame, novo_prof, leitura = self._upgrade_disponivel(leitura)
                if novo_frame is not None:
                    frame, prof = novo_frame, novo_prof

                if leitura.state not in PANEL_STATES:
                    # A tela mudou sozinha enquanto confirmavamos; recomeca.
                    continue

                if not pode:
                    # Insistimos e o botao continuou apagado: agora sim e' o
                    # jogo dizendo que nao da' para subir.
                    self._dump(frame, "upgrade_cinza")
                    raise safety.StopReason("mw.cannot_upgrade")

                # Antes de gastar, e nao so' no topo do laco - ver _check_limits.
                self._check_limits(attempts, started)
                self._act(prof.upgrade_button, "Upgrade", leitura.state)

        except safety.StopReason as stop:
            self._emit(EventKind.STOPPED, stop.key, **stop.params)
            return fim(False, stop.key, **stop.params)
        except Exception as exc:  # noqa: BLE001 - a GUI precisa ver qualquer falha
            log.exception("engine de masterworking quebrou")
            self._emit(EventKind.ERROR, "eng.error", error=str(exc))
            return fim(False, "eng.error", error=str(exc))
        finally:
            self.capture.close()
