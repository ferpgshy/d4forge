"""Travas de seguranca do loop automatico.

O engine so' clica se TODAS as condicoes aqui passarem. A ideia e' que qualquer
coisa inesperada pare o bot em vez de faze-lo clicar no escuro: o custo de uma
parada e' zero, o de um clique errado e' ouro e um afixo bom perdido.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from dataclasses import dataclass, field

from ..geometry import Point
from ..window import find_game_window
from .sendinput import cursor_position

user32 = ctypes.WinDLL("user32")

VK_F12 = 0x7B
VK_ESCAPE = 0x1B


def key_is_down(vk: int) -> bool:
    """Tecla esta' fisicamente pressionada agora."""
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def key_pressed_once(vk: int) -> bool:
    """Tecla foi pressionada desde a ultima consulta.

    Le' o bit 0x0001, que o Windows zera na leitura - e' o que permite usar a
    tecla como atalho global (dispara uma vez por toque) em vez de repetir
    enquanto estiver segurando.
    """
    return bool(user32.GetAsyncKeyState(vk) & 0x0001)


ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
NORMAL_PRIORITY_CLASS = 0x00000020

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
# Sem restype/argtypes o ctypes trata o pseudo-handle de GetCurrentProcess()
# (-1) como int de 32 bits, o handle chega truncado no processo de 64 bits e o
# SetPriorityClass falha silenciosamente - a elevacao de prioridade NUNCA
# funcionou ate' isto ser declarado. Descoberto porque a funcao devolvia False.
kernel32.GetCurrentProcess.restype = wintypes.HANDLE
kernel32.GetCurrentProcess.argtypes = []
kernel32.SetPriorityClass.restype = wintypes.BOOL
kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]


def set_high_priority(enable: bool = True) -> bool:
    """Sobe a prioridade do processo enquanto o ciclo roda.

    O Diablo IV satura os 16 processadores logicos desta maquina, e o OCR
    disputa CPU com ele: medido, a mesma inferencia leva 30 ms com a maquina
    livre e passa de 800 ms com o jogo rodando. Subir a prioridade nao rouba
    quadros do jogo de forma perceptivel, mas tira o OCR da fila de tras.
    """
    try:
        handle = kernel32.GetCurrentProcess()
        priority = ABOVE_NORMAL_PRIORITY_CLASS if enable else NORMAL_PRIORITY_CLASS
        return bool(kernel32.SetPriorityClass(handle, priority))
    except Exception:  # noqa: BLE001 - nunca impedir o ciclo por causa disto
        return False


class StopReason(Exception):
    """Motivo pelo qual o loop parou."""


@dataclass
class Limits:
    """Tetos que o usuario define antes de soltar o bot."""

    max_attempts: int = 200
    max_gold: int | None = None
    max_minutes: float | None = 60.0

    def describe(self) -> str:
        parts = [f"{self.max_attempts} tentativas"]
        if self.max_gold is not None:
            parts.append(f"{self.max_gold:,} de ouro".replace(",", "."))
        if self.max_minutes is not None:
            parts.append(f"{self.max_minutes:g} min")
        return " / ".join(parts)


@dataclass
class Guard:
    """Estado vivo das travas durante uma sessao."""

    limits: Limits = field(default_factory=Limits)
    kill_key: int = VK_F12
    require_foreground: bool = True
    # Se o usuario mexer no mouse, para. Comparamos a posicao atual com onde
    # NOS deixamos o cursor; divergencia grande significa mao humana no mouse.
    abort_on_mouse_move: bool = True
    mouse_tolerance: int = 60
    # Movimento entre duas checagens consecutivas acima disto = mao humana.
    motion_tolerance: int = 10

    started_at: float = field(default_factory=time.monotonic)
    attempts: int = 0
    gold_spent: int = 0
    _last_click: Point | None = field(default=None, repr=False)
    # Primeira posicao "fora do lugar" vista; serve para exigir que o cursor
    # ainda esteja SE MOVENDO antes de abortar.
    _drift_anchor: Point | None = field(default=None, repr=False)

    # -- registro ---------------------------------------------------------
    def note_click(self, where: Point) -> None:
        self._last_click = where
        self._drift_anchor = None

    def note_attempt(self, cost: int = 0) -> None:
        self.attempts += 1
        self.gold_spent += max(0, cost)

    @property
    def elapsed_minutes(self) -> float:
        return (time.monotonic() - self.started_at) / 60.0

    # -- verificacao ------------------------------------------------------
    def check(self) -> None:
        """Levanta StopReason se qualquer trava disparar."""
        if key_is_down(self.kill_key):
            raise StopReason("tecla de parada pressionada")

        if self.attempts >= self.limits.max_attempts:
            raise StopReason(f"limite de {self.limits.max_attempts} tentativas atingido")

        if self.limits.max_gold is not None and self.gold_spent >= self.limits.max_gold:
            raise StopReason(f"limite de ouro atingido ({self.gold_spent:,})".replace(",", "."))

        if self.limits.max_minutes is not None and self.elapsed_minutes >= self.limits.max_minutes:
            raise StopReason(f"limite de tempo atingido ({self.limits.max_minutes:g} min)")

        if self.require_foreground:
            win = find_game_window()
            if win is None:
                raise StopReason("janela do Diablo IV sumiu")
            if not win.is_foreground:
                raise StopReason("o jogo saiu do primeiro plano")

        if self.abort_on_mouse_move and self._last_click is not None:
            now = cursor_position()
            drift = abs(now.x - self._last_click.x) + abs(now.y - self._last_click.y)
            if drift <= self.mouse_tolerance:
                self._drift_anchor = None
            elif self._drift_anchor is None:
                # Primeira amostra fora do lugar: pode ser um salto unico do
                # cursor (o jogo reposiciona, um esbarrao) e nao mao humana.
                # Anotamos e so' abortamos se a PROXIMA checagem mostrar o
                # cursor ainda em movimento - abortar por uma amostra isolada
                # derrubava sessoes "em falso".
                self._drift_anchor = now
            else:
                motion = abs(now.x - self._drift_anchor.x) + abs(now.y - self._drift_anchor.y)
                if motion > self.motion_tolerance:
                    raise StopReason("mouse em movimento — parada de segurança")
                # Parado no novo lugar: foi um salto isolado. O ponto vira a
                # nova referencia; qualquer movimento a partir dele aborta.
                self._drift_anchor = now

    def summary(self) -> str:
        return (
            f"{self.attempts} tentativas, {self.gold_spent:,} de ouro, "
            f"{self.elapsed_minutes:.1f} min".replace(",", ".")
        )
