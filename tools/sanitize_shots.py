"""Gera as telas de referência dos testes sem nada pessoal.

As capturas originais mostram nome de conta, personagem, ouro, e o nome de
outros jogadores no mundo. Nada disso é lido pelo app — só o painel do
Occultist e o diálogo central importam. Este script preserva exatamente essas
regiões e apaga o resto, para que a suíte continue completa num repositório
público.

    .venv\\Scripts\\python.exe tools\\sanitize_shots.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from d4forge.geometry import Rect  # noqa: E402
from d4forge.imageio import imread, imwrite  # noqa: E402

ORIGEM = ROOT / "PRINTS SEM CORTE (DIMENSAO)"
DESTINO = ROOT / "tests" / "fixtures" / "telas"

TELAS = {
    "enchant_select": "image 5.png",
    "confirm": "image 6.png",
    "replace": "image 7.png",
    "result": "image 8.png",
    "enchant_locked": "image 9.png",
}

# Regiões que o app realmente lê, em pixels de referência (1920x1080).
PAINEL = Rect(0, 0, 700, 968)          # Occultist; termina antes da linha de ouro
DIALOGO = Rect(676, 370, 580, 320)     # janela Accept / Cancel


def sanitizar(img: np.ndarray) -> np.ndarray:
    limpo = np.zeros_like(img)
    for regiao in (PAINEL, DIALOGO):
        r = regiao.clip_to(Rect(0, 0, img.shape[1], img.shape[0]))
        limpo[r.top:r.bottom, r.left:r.right] = img[r.top:r.bottom, r.left:r.right]
    return limpo


def main() -> int:
    if not ORIGEM.is_dir():
        print(f"origem não encontrada: {ORIGEM}")
        return 1

    DESTINO.mkdir(parents=True, exist_ok=True)
    for estado, arquivo in TELAS.items():
        img = imread(ORIGEM / arquivo)
        if img is None:
            print(f"!! não consegui ler {arquivo}")
            continue
        destino = DESTINO / f"{estado}.jpg"
        imwrite(destino, sanitizar(img))
        print(f"{destino.relative_to(ROOT)}  {destino.stat().st_size // 1024} KB")

    print("\nConferindo se a detecção de estado continua correta:")
    from d4forge.profile import DEFAULT_PROFILE
    from d4forge.vision.states import ScreenState, detect_state

    erros = 0
    for estado in TELAS:
        img = imread(DESTINO / f"{estado}.jpg")
        prof = DEFAULT_PROFILE.scaled(Rect(0, 0, img.shape[1], img.shape[0]))
        lido = detect_state(img, prof).state
        ok = lido is ScreenState(estado)
        erros += not ok
        print(f"  {'ok  ' if ok else 'ERRO'} {estado:<16} -> {lido.value}")
    return 1 if erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
