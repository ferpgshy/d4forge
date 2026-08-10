"""Diz quais teclas de atalho o Windows realmente entrega ao d4forge.

    .venv\\Scripts\\python.exe tools\\testar_teclas.py

Roda por 20 segundos e imprime cada tecla que detectar. Serve para separar dois
problemas que parecem o mesmo: "a tecla nao chega" e "a tecla chega mas a acao
falha". Sem isto so' da' para chutar.

Deixe esta janela aberta e aperte F8, F9, F10, F11 e F12 - uma de cada vez.
Funciona tambem com outra janela em foco, que e' como o app usa: o atalho e'
global.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from d4forge.automation.safety import key_pressed_once  # noqa: E402

TECLAS = {"F8": 0x77, "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B}
DURACAO = 20.0


def main() -> int:
    print(__doc__.split("\n\n", 1)[1].strip())
    print(f"\nOuvindo por {DURACAO:.0f} segundos...\n")

    for vk in TECLAS.values():  # limpa o que estiver pendente
        key_pressed_once(vk)

    vistas: dict[str, int] = {}
    fim = time.monotonic() + DURACAO
    while time.monotonic() < fim:
        for nome, vk in TECLAS.items():
            if key_pressed_once(vk):
                vistas[nome] = vistas.get(nome, 0) + 1
                print(f"  {nome} detectada  (x{vistas[nome]})")
        time.sleep(0.08)  # mesmo ritmo do app

    print("\n--- resultado ---")
    for nome in TECLAS:
        n = vistas.get(nome, 0)
        print(f"  {nome:<5} {'detectada ' + str(n) + 'x' if n else 'NAO detectada'}")

    if not vistas:
        print("\nNenhuma tecla chegou. Se voce apertou alguma, o problema esta'")
        print("na leitura do teclado, nao no d4forge.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
