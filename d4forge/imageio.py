"""Leitura/escrita de imagem que aguenta caminho com acento.

`cv2.imread` e `cv2.imwrite` passam o caminho para a API C do OpenCV como bytes
na codificacao local, entao qualquer caractere fora de ASCII faz a chamada
falhar silenciosamente (imread devolve None). Este projeto mora em
"Area de Trabalho" com acento, entao todo acesso a disco passa por aqui.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def imread(path: str | Path, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
    """Le uma imagem de qualquer caminho. Devolve None se nao der."""
    path = Path(path)
    try:
        buf = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if buf.size == 0:
        return None
    return cv2.imdecode(buf, flags)


def imwrite(path: str | Path, image: np.ndarray) -> bool:
    """Grava uma imagem em qualquer caminho. Devolve True se deu certo."""
    path = Path(path)
    ok, buf = cv2.imencode(path.suffix or ".png", image)
    if not ok:
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        buf.tofile(path)
    except OSError:
        return False
    return True
