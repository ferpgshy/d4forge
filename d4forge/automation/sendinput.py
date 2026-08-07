"""Mouse e teclado sinteticos via SendInput.

Por que ctypes e nao pyautogui: jogos DirectX ignoram boa parte do input
sintetico. `mouse_event`/`keybd_event` sao APIs legadas e o D4 costuma nao
reagir; SendInput com coordenada absoluta normalizada e scancode de teclado e' o
caminho que funciona.

Coordenada absoluta aqui e' normalizada em 0..65535 sobre a *area virtual*
(todos os monitores), nao sobre o monitor primario - esta maquina tem tres telas
e sem MOUSEEVENTF_VIRTUALDESK o clique cairia no lugar errado.
"""

from __future__ import annotations

import ctypes
import random
import time
from ctypes import wintypes
from dataclasses import dataclass

from ..geometry import Point, Rect

user32 = ctypes.WinDLL("user32", use_last_error=True)

# --- constantes do Win32 ---------------------------------------------------
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

# Scancodes (set 1) das teclas que usamos.
SCAN_ESCAPE = 0x01
SCAN_SPACE = 0x39


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _send(*inputs: INPUT) -> int:
    array = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        raise OSError(ctypes.get_last_error(), "SendInput nao entregou todos os eventos")
    return sent


def virtual_screen() -> Rect:
    return Rect(
        user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )


def _normalize(x: int, y: int) -> tuple[int, int]:
    """Pixel de tela -> 0..65535 sobre a area virtual."""
    vs = virtual_screen()
    nx = (x - vs.x) * 65535 // max(1, vs.w - 1)
    ny = (y - vs.y) * 65535 // max(1, vs.h - 1)
    return max(0, min(65535, nx)), max(0, min(65535, ny))


def cursor_position() -> Point:
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return Point(pt.x, pt.y)


def move_to(x: int, y: int) -> None:
    nx, ny = _normalize(x, y)
    _send(
        INPUT(
            type=INPUT_MOUSE,
            mi=MOUSEINPUT(nx, ny, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, 0, None),
        )
    )


def click(
    x: int | None = None,
    y: int | None = None,
    button: str = "left",
    hold: tuple[float, float] = (0.035, 0.075),
) -> None:
    if x is not None and y is not None:
        move_to(x, y)
    down, up = (
        (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)
        if button == "left"
        else (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)
    )
    _send(INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, down, 0, None)))
    time.sleep(random.uniform(*hold))  # o jogo ignora clique curto demais
    _send(INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, up, 0, None)))


def press_key(scancode: int) -> None:
    """Tecla por scancode - jogos DirectX ignoram virtual-key sintetico."""
    _send(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, scancode, KEYEVENTF_SCANCODE, 0, None)))
    time.sleep(random.uniform(0.03, 0.06))
    _send(
        INPUT(
            type=INPUT_KEYBOARD,
            ki=KEYBDINPUT(0, scancode, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, None),
        )
    )


# --- perfis de velocidade --------------------------------------------------


@dataclass(frozen=True, slots=True)
class InputProfile:
    """Quanto tempo gastar para parecer humano.

    O custo aqui domina o ciclo: medido, um clique "humano" gasta 125-305 ms
    entre mover, assentar e soltar o botao, o que da' 0,5-1,2 s por volta so' de
    mouse. Quem escolhe o compromisso e' o usuario.
    """

    label: str
    px_per_step: int          # 0 = vai direto ao alvo
    max_steps: int
    duration: tuple[float, float]
    settle: tuple[float, float]
    hold: tuple[float, float]

    def estimate_ms(self, distance: float = 400.0) -> float:
        mid = lambda pair: (pair[0] + pair[1]) / 2  # noqa: E731
        move = mid(self.duration) + (distance / 6000.0 if self.px_per_step else 0.0)
        return (move + mid(self.settle) + mid(self.hold)) * 1000


HUMANO = InputProfile("humano", 45, 18, (0.05, 0.13), (0.04, 0.10), (0.035, 0.075))
RAPIDO = InputProfile("rápido", 140, 6, (0.012, 0.030), (0.008, 0.020), (0.012, 0.025))
INSTANTANEO = InputProfile("instantâneo", 0, 1, (0.0, 0.0), (0.0, 0.0), (0.004, 0.010))

PROFILES = {p.label: p for p in (HUMANO, RAPIDO, INSTANTANEO)}
DEFAULT_PROFILE = RAPIDO


# --- movimento com aparencia humana ---------------------------------------

def jittered_point(rect: Rect, inset: float = 0.28) -> Point:
    """Ponto aleatorio no miolo do retangulo.

    Sempre clicar no pixel central deixa um padrao obvio e, pior, se a ROI
    estiver 1-2 px torta o clique erra sempre no mesmo lugar. Sortear dentro do
    miolo resolve os dois.
    """
    mx = max(1, int(rect.w * inset))
    my = max(1, int(rect.h * inset))
    return Point(
        random.randint(rect.left + mx, max(rect.left + mx, rect.right - mx - 1)),
        random.randint(rect.top + my, max(rect.top + my, rect.bottom - my - 1)),
    )


def smooth_move(target: Point, profile: InputProfile = DEFAULT_PROFILE) -> None:
    """Move ate' o alvo conforme o perfil de velocidade."""
    start = cursor_position()
    dx, dy = target.x - start.x, target.y - start.y
    distance = (dx * dx + dy * dy) ** 0.5

    if distance < 2 or profile.px_per_step <= 0:
        move_to(target.x, target.y)
        return

    steps = max(2, min(profile.max_steps, int(distance / profile.px_per_step) + 2))
    duration = random.uniform(*profile.duration) + distance / 6000.0

    for i in range(1, steps + 1):
        t = i / steps
        ease = 1 - (1 - t) ** 3  # desacelera no fim
        wobble = 0 if i == steps else random.uniform(-1.5, 1.5)
        move_to(
            int(round(start.x + dx * ease + wobble)),
            int(round(start.y + dy * ease + wobble)),
        )
        time.sleep(duration / steps)


def click_rect(rect: Rect, profile: InputProfile = DEFAULT_PROFILE) -> Point:
    """Clica num ponto sorteado dentro do retangulo. Devolve onde clicou."""
    target = jittered_point(rect)
    smooth_move(target, profile)
    if profile.settle[1] > 0:
        time.sleep(random.uniform(*profile.settle))
    click(hold=profile.hold)
    return target
