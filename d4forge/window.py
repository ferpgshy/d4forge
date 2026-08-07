"""Localizacao da janela do Diablo IV.

O jogo aqui roda em 1920x1080 borderless com o cliente colado em (0,0), mas nao
assumimos isso: sempre perguntamos ao Windows onde o retangulo do cliente esta.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from dataclasses import dataclass

from .geometry import Rect

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

SW_RESTORE = 9

# Sem restype/argtypes o ctypes trata todo handle como int de 32 bits. Um HWND
# de 64 bits chega truncado e a chamada falha em silencio - foi exatamente esse
# descuido que manteve `set_high_priority` devolvendo False por semanas.
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

# Nomes de janela/classe que o D4 usa. A classe e' mais estavel que o titulo.
WINDOW_TITLES = ("Diablo IV",)
WINDOW_CLASSES = ("Diablo IV Main Window Class", "D3D Window Class")


class _Found(Exception):
    """Sinaliza fim antecipado do EnumWindows."""


@dataclass(frozen=True, slots=True)
class GameWindow:
    hwnd: int
    title: str
    client: Rect  # em coordenadas de tela (ja convertido de client-space)
    window: Rect  # retangulo externo, com bordas

    @property
    def is_foreground(self) -> bool:
        return user32.GetForegroundWindow() == self.hwnd

    def focus(self, timeout: float = 1.5) -> bool:
        """Traz o jogo para o primeiro plano. Devolve se conseguiu de fato.

        Tres cuidados que a versao ingenua nao tinha:

        * `SW_RESTORE` so' quando a janela esta' MINIMIZADA. Aplicado a uma
          janela maximizada, ele a desmaximiza - o app mudaria o tamanho da tela
          do jogo so' por tentar focar.
        * O Windows nao deixa qualquer processo roubar o primeiro plano.
          Anexar nossa fila de entrada a' da janela em foco satisfaz a regra;
          sem isso `SetForegroundWindow` costuma nao fazer nada e ainda assim
          dizer que deu certo.
        * Conferir o resultado em vez de acreditar no retorno. Quem chama
          precisa saber se o jogo esta' mesmo na frente antes de clicar.
        """
        if self.is_foreground:
            return True

        if user32.IsIconic(self.hwnd):
            user32.ShowWindow(self.hwnd, SW_RESTORE)

        nosso = kernel32.GetCurrentThreadId()
        deles = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
        anexado = bool(deles) and deles != nosso and bool(
            user32.AttachThreadInput(nosso, deles, True)
        )
        try:
            user32.SetForegroundWindow(self.hwnd)
            user32.BringWindowToTop(self.hwnd)
        finally:
            if anexado:
                user32.AttachThreadInput(nosso, deles, False)

        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            if self.is_foreground:
                return True
            time.sleep(0.03)
        return False


def _enable_dpi_awareness() -> None:
    """Sem isso, o Windows mente sobre coordenadas quando ha escala != 100%."""
    try:
        # PER_MONITOR_AWARE_V2
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


_enable_dpi_awareness()


def _window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _client_rect_on_screen(hwnd: int) -> Rect:
    """Retangulo da area util, convertido para coordenadas de tela."""
    rc = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rc)):
        raise OSError(ctypes.get_last_error(), "GetClientRect falhou")
    origin = wintypes.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        raise OSError(ctypes.get_last_error(), "ClientToScreen falhou")
    return Rect(origin.x, origin.y, rc.right - rc.left, rc.bottom - rc.top)


def _window_rect(hwnd: int) -> Rect:
    rc = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rc)):
        raise OSError(ctypes.get_last_error(), "GetWindowRect falhou")
    return Rect.from_ltrb(rc.left, rc.top, rc.right, rc.bottom)


def find_game_window() -> GameWindow | None:
    """Procura a janela do D4. Retorna None se o jogo nao estiver aberto."""
    result: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = _window_text(hwnd)
        cls = _class_name(hwnd)
        if title in WINDOW_TITLES or cls in WINDOW_CLASSES:
            rect = _window_rect(hwnd)
            # Ignora janelas-fantasma de 0px que o jogo cria no boot.
            if rect.w > 200 and rect.h > 200:
                result.append(hwnd)
                return False
        return True

    user32.EnumWindows(_cb, 0)
    if not result:
        return None

    hwnd = result[0]
    return GameWindow(
        hwnd=hwnd,
        title=_window_text(hwnd),
        client=_client_rect_on_screen(hwnd),
        window=_window_rect(hwnd),
    )


def require_game_window() -> GameWindow:
    win = find_game_window()
    if win is None:
        raise RuntimeError(
            "Janela do Diablo IV nao encontrada. Abra o jogo antes de iniciar."
        )
    return win


def foreground_title() -> str:
    """Titulo da janela em foco - usado pelo guard de seguranca do engine."""
    return _window_text(user32.GetForegroundWindow())
