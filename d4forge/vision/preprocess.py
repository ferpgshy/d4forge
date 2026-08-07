"""Pre-processamento das ROIs de texto.

O painel do Occultist e' quase preto (brilho medio ~4) e o texto dos afixos fica
entre 150 e 217. Esse contraste enorme e' o que torna o OCR barato aqui: um
limiar fixo em ~120 ja' separa texto de fundo e ainda descarta a marca d'agua
"PUBLIC TEST BUILD", que e' renderizada com alpha baixissimo.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import cv2
import numpy as np

from ..geometry import Rect

# Medido em image 5.png (1918x1079): fundo p50=4, texto p90=163, marca <10.
DEFAULT_THRESHOLD = 120

# Limite de "tinta" abaixo do qual consideramos a ROI vazia.
MIN_INK_PIXELS = 12


def to_gray(bgr: np.ndarray) -> np.ndarray:
    """BGR -> cinza. Usa o canal maximo em vez de luma ponderada porque o texto
    do D4 tem tom levemente amarelado e o luma padrao o escurece demais."""
    if bgr.ndim == 2:
        return bgr
    return bgr.max(axis=2)


def binarize(gray: np.ndarray, threshold: int = DEFAULT_THRESHOLD) -> np.ndarray:
    """Mascara booleana do texto (True = tinta)."""
    return gray >= threshold


def ink_bbox(mask: np.ndarray) -> Rect | None:
    """Menor retangulo que contem toda a tinta. None se a ROI estiver vazia."""
    if mask.sum() < MIN_INK_PIXELS:
        return None
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    if len(rows) == 0 or len(cols) == 0:
        return None
    return Rect.from_ltrb(int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1)


def trim(mask: np.ndarray, pad: int = 0) -> tuple[np.ndarray, Rect] | tuple[None, None]:
    """Recorta a mascara na bbox da tinta. Devolve (mascara, bbox_original)."""
    box = ink_bbox(mask)
    if box is None:
        return None, None
    if pad:
        box = box.inflate(pad).clip_to(Rect(0, 0, mask.shape[1], mask.shape[0]))
    return mask[box.top : box.bottom, box.left : box.right], box


def prepare_line(bgr: np.ndarray, threshold: int = DEFAULT_THRESHOLD):
    """Pipeline padrao de uma linha de texto: cinza -> binario -> aparado."""
    mask = binarize(to_gray(bgr), threshold)
    return trim(mask)


@dataclass(frozen=True, slots=True)
class RenderSpec:
    """Como transformar a mascara binaria na imagem que vai para o modelo."""

    scale: int
    margin: int
    smooth: int = 0  # raio do desfoque; 0 = borda dura

    def span(self, mask_width: int) -> tuple[int, int]:
        """Onde a tinta deve estar na imagem gerada, em pixels."""
        return self.margin, self.margin + mask_width * self.scale



# Padrao. Borda dura em 4x acerta a grande maioria das linhas.
PRIMARY_RENDER = RenderSpec(scale=4, margin=16)

# Repescagem. Ampliar mais e suavizar a borda faz o detector tratar a linha como
# uma caixa unica; quando ele parte a linha em varias, caracteres se perdem.
# Medido: "+1,431 Maximum Life" saia como "431 Maximum . Life" no padrao.
FALLBACK_RENDER = RenderSpec(scale=6, margin=16, smooth=3)

# Escada de repescagem, na ordem de tentativa. Varrida contra recortes de
# sessoes reais (5 escalas x 3 margens x 4 desfoques): nenhum ajuste unico le'
# todos os casos dificeis, mas estes tres cobrem os quatro conhecidos.
#
#   4x duro    o mais rapido; resolve a maioria das linhas
#   6x suave   "+2 to Invigorating Strike" (saia "-2 to Strike") e
#              "+1,431 Maximum Life" (saia "431 Maximum . Life")
#   4x muito   "7.2% / 7.0% Dodge Chance" (saia ".2% Dodgei Chance", sem o
#     suave    digito da frente) - so' este degrau recupera o primeiro digito
#
# Margem maior que 16 piorou tudo na varredura: o detector volta a partir a
# linha em varias caixas, e e' na emenda que os caracteres se perdem.
RENDER_LADDER: tuple[RenderSpec, ...] = (
    PRIMARY_RENDER,
    FALLBACK_RENDER,
    RenderSpec(scale=4, margin=16, smooth=4),
)


def render_for_ocr(mask: np.ndarray, spec: RenderSpec = PRIMARY_RENDER) -> np.ndarray:
    """Amplia a mascara para o backend pesado.

    O texto tem so' 12 px de altura; modelos de OCR generico erram muito nesse
    tamanho.

    A margem branca nao e' cosmetica: a mascara chega aparada rente a tinta, e
    sem folga o detector de caixas corta os caracteres das pontas - foi assim
    que "+151 Dexterity" virou "ext" no teste contra os prints reais. Margem
    grande demais tambem atrapalha: com 40 px o detector volta a partir a linha.
    """
    big = np.repeat(np.repeat(mask, spec.scale, axis=0), spec.scale, axis=1)
    # Backends esperam texto escuro em fundo claro.
    img = np.where(big, np.uint8(0), np.uint8(255))
    if spec.smooth:
        k = 2 * spec.smooth + 1
        img = cv2.GaussianBlur(img, (k, k), 0)
    if spec.margin > 0:
        img = np.pad(img, spec.margin, mode="constant", constant_values=255)
    return img


def ink_ratio(mask: np.ndarray) -> float:
    """Fracao de pixels com tinta - util para descartar ROIs vazias rapido."""
    return float(mask.mean()) if mask.size else 0.0


def content_hash(mask: np.ndarray) -> str:
    """Hash exato do conteudo binario, usado como chave de cache.

    Nao e' perceptual de proposito: a mesma linha renderizada pelo jogo produz
    exatamente os mesmos pixels, entao o hash exato tem 0 falso positivo e o
    lookup fica em ~microssegundos.

    Usa blake2b em vez de hash() nativo porque hash() de bytes e' aleatorizado
    por processo (PYTHONHASHSEED) - o cache em disco nao sobreviveria a reiniciar
    o app.
    """
    h, w = mask.shape
    digest = hashlib.blake2b(np.packbits(mask).tobytes(), digest_size=8)
    digest.update(f"{h}x{w}".encode("ascii"))
    return digest.hexdigest()
