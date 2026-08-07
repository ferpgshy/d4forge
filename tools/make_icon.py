"""Gera o icone do aplicativo (.ico multi-resolucao), sem dependencia externa.

Desenha uma bigorna estilizada sobre o vermelho escuro do Diablo IV. E' arte
simples de proposito: o icone existe para voce achar a janela na barra de
tarefas, nao para ganhar premio.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402

FUNDO = (18, 16, 22)        # BGR quase preto
BORDA = (48, 58, 140)       # vermelho escuro do D4
METAL = (150, 170, 190)     # cinza claro
BRILHO = (110, 200, 245)    # dourado


def desenhar(tam: int) -> np.ndarray:
    """Desenha em 4x e reduz: a suavizacao vem da reducao, nao de anti-alias."""
    s = tam * 4
    img = np.zeros((s, s, 4), dtype=np.uint8)

    centro = (s // 2, s // 2)
    cv2.circle(img, centro, int(s * 0.47), (*FUNDO, 255), -1, cv2.LINE_AA)
    cv2.circle(img, centro, int(s * 0.47), (*BORDA, 255), max(2, s // 28), cv2.LINE_AA)

    u = s / 100.0  # unidade relativa, para a forma escalar junto

    # Corpo da bigorna
    corpo = np.array([
        [28 * u, 44 * u], [72 * u, 44 * u], [78 * u, 52 * u],
        [64 * u, 52 * u], [60 * u, 62 * u], [40 * u, 62 * u],
        [36 * u, 52 * u], [22 * u, 52 * u],
    ], dtype=np.int32)
    cv2.fillPoly(img, [corpo], (*METAL, 255), cv2.LINE_AA)

    # Base
    cv2.rectangle(img, (int(38 * u), int(62 * u)), (int(62 * u), int(70 * u)),
                  (*METAL, 255), -1, cv2.LINE_AA)
    cv2.rectangle(img, (int(30 * u), int(70 * u)), (int(70 * u), int(78 * u)),
                  (*METAL, 255), -1, cv2.LINE_AA)

    # Faisca: o afixo que a gente procura
    cv2.circle(img, (int(72 * u), int(32 * u)), int(6 * u), (*BRILHO, 255), -1, cv2.LINE_AA)
    for ang in range(0, 360, 45):
        rad = np.deg2rad(ang)
        p1 = (int(72 * u + np.cos(rad) * 8 * u), int(32 * u + np.sin(rad) * 8 * u))
        p2 = (int(72 * u + np.cos(rad) * 14 * u), int(32 * u + np.sin(rad) * 14 * u))
        cv2.line(img, p1, p2, (*BRILHO, 255), max(1, int(2 * u)), cv2.LINE_AA)

    return cv2.resize(img, (tam, tam), interpolation=cv2.INTER_AREA)


def main() -> int:
    from PIL import Image

    destino = ROOT / "d4forge" / "resources" / "d4forge.ico"
    destino.parent.mkdir(parents=True, exist_ok=True)

    tamanhos = [256, 128, 64, 48, 32, 16]
    quadros = []
    for tam in tamanhos:
        bgra = desenhar(tam)
        rgba = cv2.cvtColor(bgra, cv2.COLOR_BGRA2RGBA)
        quadros.append(Image.fromarray(rgba))

    quadros[0].save(destino, format="ICO",
                    sizes=[(t, t) for t in tamanhos],
                    append_images=quadros[1:])
    print(f"{destino.relative_to(ROOT)}  ({destino.stat().st_size / 1024:.1f} KB, "
          f"{len(tamanhos)} resoluções)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
