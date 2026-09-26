"""Uma tecla, um botão do mouse ou a roda — tratados pela mesma porta.

O AutoSkill precisa de duas coisas com a mesma bind, e elas pedem codigos
DIFERENTES no Windows:

* **mandar para o jogo.** Teclado so' funciona por SCANCODE - jogo DirectX
  ignora virtual-key sintetico (ver `sendinput.press_key`). Mouse nao tem
  scancode: vai por MOUSEEVENTF.
* **perguntar se esta' pressionada agora**, que e' o modo "segurar" das
  hotkeys. Isso e' `GetAsyncKeyState`, que so' entende VIRTUAL-KEY - inclusive
  para os botoes do mouse (VK_LBUTTON e companhia).

Guardar so' um dos dois obrigaria a uma tabela de conversao escrita na mao, que
e' exatamente o tipo de coisa que envelhece errado com teclado ABNT2, layout
trocado e tecla estendida. Entao a bind guarda o VIRTUAL-KEY - que e' o que a
captura na interface recebe de graca - e o scancode sai do proprio Windows, por
`MapVirtualKeyW`, na hora de enviar.
"""

from __future__ import annotations

import ctypes
import random
import time
from ctypes import wintypes
from dataclasses import dataclass

from .sendinput import (
    INPUT,
    INPUT_KEYBOARD,
    INPUT_MOUSE,
    KEYBDINPUT,
    KEYEVENTF_KEYUP,
    KEYEVENTF_SCANCODE,
    MOUSEEVENTF_LEFTDOWN,
    MOUSEEVENTF_LEFTUP,
    MOUSEEVENTF_RIGHTDOWN,
    MOUSEEVENTF_RIGHTUP,
    MOUSEINPUT,
    _send,
)

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short

MAPVK_VK_TO_VSC = 0

# Botoes do mouse que faltavam em `sendinput`: la' so' havia esquerdo e direito,
# porque o encantamento nunca precisou de mais.
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_XDOWN = 0x0080
MOUSEEVENTF_XUP = 0x0100
MOUSEEVENTF_WHEEL = 0x0800
XBUTTON1 = 0x0001
XBUTTON2 = 0x0002
WHEEL_DELTA = 120

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_MBUTTON = 0x04
VK_XBUTTON1 = 0x05
VK_XBUTTON2 = 0x06

# Teclas ESTENDIDAS: o scancode delas colide com o do teclado numerico, e o
# Windows so' as separa pelo prefixo 0xE0. Sem isto, Seta-Direita vira "6" do
# numerico e Ctrl-direito vira Ctrl-esquerdo.
VK_ESTENDIDAS = frozenset({
    0x21, 0x22, 0x23, 0x24,        # PgUp PgDn End Home
    0x25, 0x26, 0x27, 0x28,        # setas
    0x2D, 0x2E,                    # Insert Delete
    0x5B, 0x5C, 0x5D,              # Win esquerda/direita, Menu
    0x6F,                          # divisao do numerico
    0xA3, 0xA5,                    # Ctrl e Alt da DIREITA
})

TIPO_TECLA = "key"
TIPO_MOUSE = "mouse"
TIPO_RODA = "wheel"

# (evento de descer, evento de subir) por botao.
BOTOES_MOUSE = {
    VK_LBUTTON: (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    VK_RBUTTON: (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    VK_MBUTTON: (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
    VK_XBUTTON1: (MOUSEEVENTF_XDOWN, MOUSEEVENTF_XUP),
    VK_XBUTTON2: (MOUSEEVENTF_XDOWN, MOUSEEVENTF_XUP),
}

NOME_DO_BOTAO = {
    VK_LBUTTON: "Mouse esquerdo",
    VK_RBUTTON: "Mouse direito",
    VK_MBUTTON: "Mouse meio",
    VK_XBUTTON1: "Mouse lateral 1",
    VK_XBUTTON2: "Mouse lateral 2",
}


@dataclass(frozen=True)
class Bind:
    """O que apertar. Vazia (`tipo=""`) significa "nao configurado"."""

    tipo: str = ""
    codigo: int = 0          # virtual-key, ou +1/-1 na roda
    rotulo: str = ""         # o que a interface mostra

    # NAO e' `slots=True` de proposito: `frozen + slots` quebra `super()` em
    # subclasse no Python 3.12, e este projeto ja' tropecou nisso uma vez.

    def __bool__(self) -> bool:
        return bool(self.tipo)

    def descreve(self) -> str:
        return self.rotulo or "—"

    # -- ida e volta do JSON ---------------------------------------------
    def to_json(self) -> dict:
        return {"tipo": self.tipo, "codigo": self.codigo, "rotulo": self.rotulo}

    @classmethod
    def from_json(cls, blob) -> "Bind":
        """Qualquer defeito vira bind VAZIA, nunca excecao.

        Isto roda na abertura da janela: um valor estranho aqui nao pode
        impedir o app de abrir - so' de ter aquela bind configurada.
        """
        if not isinstance(blob, dict):
            return cls()
        tipo = blob.get("tipo")
        if tipo not in (TIPO_TECLA, TIPO_MOUSE, TIPO_RODA):
            return cls()
        try:
            codigo = int(blob.get("codigo", 0))
        except (TypeError, ValueError):
            return cls()
        rotulo = blob.get("rotulo")
        return cls(tipo, codigo, rotulo if isinstance(rotulo, str) else "")


def tecla(vk: int, rotulo: str) -> Bind:
    return Bind(TIPO_TECLA, vk, rotulo)


def botao_mouse(vk: int) -> Bind:
    return Bind(TIPO_MOUSE, vk, NOME_DO_BOTAO.get(vk, f"Mouse {vk}"))


def roda(direcao: int) -> Bind:
    return Bind(TIPO_RODA, 1 if direcao >= 0 else -1,
                "Roda para cima" if direcao >= 0 else "Roda para baixo")


def scancode_de(vk: int) -> int:
    """Scancode que o jogo entende, perguntado ao proprio Windows.

    O bit 0xE0 das teclas estendidas nao sai do `MapVirtualKeyW`; ele e'
    aplicado aqui a partir da lista, que e' curta e fixa.
    """
    codigo = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
    if vk in VK_ESTENDIDAS:
        codigo |= 0xE000
    return codigo


def disparar(bind: Bind, hold: tuple[float, float] = (0.03, 0.055)) -> bool:
    """Aperta e solta. Devolve se chegou a mandar alguma coisa.

    O `hold` nao e' enfeite: o jogo IGNORA aperto curto demais - foi medido no
    clique do encantamento e vale igual para tecla de habilidade.
    """
    if not bind:
        return False
    if bind.tipo == TIPO_RODA:
        _send(INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(
            0, 0, WHEEL_DELTA * bind.codigo, MOUSEEVENTF_WHEEL, 0, None)))
        return True

    if bind.tipo == TIPO_MOUSE:
        par = BOTOES_MOUSE.get(bind.codigo)
        if par is None:
            return False
        desce, sobe = par
        # Os laterais compartilham o mesmo evento e se distinguem pelo
        # mouseData - sem ele, X2 chega como X1.
        extra = 0
        if bind.codigo == VK_XBUTTON1:
            extra = XBUTTON1
        elif bind.codigo == VK_XBUTTON2:
            extra = XBUTTON2
        _send(INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, extra, desce, 0, None)))
        time.sleep(random.uniform(*hold))
        _send(INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, extra, sobe, 0, None)))
        return True

    codigo = scancode_de(bind.codigo)
    if not codigo:
        return False
    marca = KEYEVENTF_SCANCODE | (0x0001 if codigo & 0xE000 else 0)
    _send(INPUT(type=INPUT_KEYBOARD,
                ki=KEYBDINPUT(0, codigo & 0xFF, marca, 0, None)))
    time.sleep(random.uniform(*hold))
    _send(INPUT(type=INPUT_KEYBOARD,
                ki=KEYBDINPUT(0, codigo & 0xFF, marca | KEYEVENTF_KEYUP, 0, None)))
    return True


def esta_pressionada(bind: Bind) -> bool:
    """A bind esta' fisicamente pressionada AGORA - o modo "segurar".

    A roda nunca responde True: ela nao tem estado de pressionada, so' eventos.
    Por isso a interface a oferece como acao, e nao como hotkey de controle.
    """
    if not bind or bind.tipo == TIPO_RODA:
        return False
    return bool(user32.GetAsyncKeyState(bind.codigo) & 0x8000)


def foi_pressionada(bind: Bind) -> bool:
    """Foi apertada desde a ultima consulta - o modo "toggle".

    O bit 0x0001 e' zerado pelo Windows na leitura, entao um toque dispara uma
    vez so' por mais que se segure. E' o mesmo mecanismo dos atalhos F9/F12.
    """
    if not bind or bind.tipo == TIPO_RODA:
        return False
    return bool(user32.GetAsyncKeyState(bind.codigo) & 0x0001)


__all__ = [
    "Bind",
    "BOTOES_MOUSE",
    "NOME_DO_BOTAO",
    "TIPO_MOUSE",
    "TIPO_RODA",
    "TIPO_TECLA",
    "botao_mouse",
    "descarta_toque_pendente",
    "disparar",
    "esta_pressionada",
    "foi_pressionada",
    "roda",
    "scancode_de",
    "tecla",
]


def descarta_toque_pendente(bind: Bind) -> None:
    """Zera o bit de "foi pressionada" sem agir.

    Ligar uma hotkey e ja' encontrar o toque que a ligou faria o modo toggle
    desligar no mesmo instante. Chamado uma vez ao comecar a vigiar.
    """
    foi_pressionada(bind)
