"""Captura frames de referencia do Diablo IV em resolucao cheia.

Serve pra calibrar o app com pixels reais da SUA tela em vez de estimativa.

Uso:
    .venv\\Scripts\\python.exe tools\\snap.py

Deixe o jogo aberto, va' pra tela que quer registrar e aperte a tecla. O script
roda em segundo plano, entao a janela do jogo pode ficar em foco.

    F9   salva o frame atual
    F10  sai

Os PNGs vao pra captures/ com nome sequencial e timestamp.
"""

from __future__ import annotations

import ctypes
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402

from d4forge.capture import ScreenCapture  # noqa: E402
from d4forge.window import find_game_window  # noqa: E402

VK_F9 = 0x78
VK_F10 = 0x79

user32 = ctypes.WinDLL("user32")
OUT_DIR = Path(__file__).resolve().parent.parent / "captures"


def key_pressed(vk: int) -> bool:
    """True apenas na transicao (bit 0 = 'foi pressionada desde a ultima leitura')."""
    return bool(user32.GetAsyncKeyState(vk) & 0x0001)


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)

    win = find_game_window()
    if win is None:
        print("[!] Diablo IV nao encontrado. Abra o jogo e rode de novo.")
        return 1

    print(f"[ok] janela: {win.title}  client={win.client.as_tuple()}")
    cap = ScreenCapture(prefer="dxcam")
    print(f"[ok] backend de captura: {cap.backend_name}")
    print()
    print("  F9  = salvar frame")
    print("  F10 = sair")
    print()

    # Zera o estado das teclas pra nao disparar com um F9 antigo do buffer.
    key_pressed(VK_F9)
    key_pressed(VK_F10)

    count = 0
    try:
        while True:
            if key_pressed(VK_F10):
                break

            if key_pressed(VK_F9):
                fresh = find_game_window() or win
                frame = cap.grab(fresh.client)
                if frame is None:
                    print("[!] captura falhou, tenta de novo")
                    continue
                count += 1
                stamp = datetime.now().strftime("%H%M%S")
                name = f"snap_{count:02d}_{stamp}.png"
                cv2.imwrite(str(OUT_DIR / name), frame)
                h, w = frame.shape[:2]
                print(f"[{count:02d}] {name}  ({w}x{h})")

            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        cap.close()

    print(f"\n{count} frame(s) em {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
