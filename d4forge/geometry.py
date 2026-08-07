"""Retangulos e coordenadas relativas.

Toda ROI do app e' guardada como fracao (0..1) de um retangulo de referencia
(o painel do Occultist), nunca como pixel absoluto. Assim o perfil sobrevive a
mudanca de resolucao e a janela do jogo mudar de lugar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple


@dataclass(frozen=True, slots=True)
class Point:
    x: int
    y: int

    def as_tuple(self) -> Tuple[int, int]:
        return (self.x, self.y)

    def offset(self, dx: int, dy: int) -> "Point":
        return Point(self.x + dx, self.y + dy)


@dataclass(frozen=True, slots=True)
class Rect:
    """Retangulo em pixels, canto superior esquerdo + tamanho."""

    x: int
    y: int
    w: int
    h: int

    # -- construcao -------------------------------------------------------
    @classmethod
    def from_ltrb(cls, left: int, top: int, right: int, bottom: int) -> "Rect":
        return cls(left, top, right - left, bottom - top)

    @classmethod
    def bounding(cls, rects: Iterable["Rect"]) -> "Rect":
        rects = list(rects)
        if not rects:
            raise ValueError("bounding() precisa de ao menos um Rect")
        left = min(r.left for r in rects)
        top = min(r.top for r in rects)
        right = max(r.right for r in rects)
        bottom = max(r.bottom for r in rects)
        return cls.from_ltrb(left, top, right, bottom)

    # -- acessores --------------------------------------------------------
    @property
    def left(self) -> int:
        return self.x

    @property
    def top(self) -> int:
        return self.y

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def center(self) -> Point:
        return Point(self.x + self.w // 2, self.y + self.h // 2)

    @property
    def area(self) -> int:
        return max(0, self.w) * max(0, self.h)

    def as_ltrb(self) -> Tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)

    def as_tuple(self) -> Tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)

    # -- transformacoes ---------------------------------------------------
    def offset(self, dx: int, dy: int) -> "Rect":
        return Rect(self.x + dx, self.y + dy, self.w, self.h)

    def inflate(self, dx: int, dy: int | None = None) -> "Rect":
        dy = dx if dy is None else dy
        return Rect(self.x - dx, self.y - dy, self.w + 2 * dx, self.h + 2 * dy)

    def scaled(self, factor: float) -> "Rect":
        return Rect(
            int(round(self.x * factor)),
            int(round(self.y * factor)),
            int(round(self.w * factor)),
            int(round(self.h * factor)),
        )

    def clip_to(self, bounds: "Rect") -> "Rect":
        left = max(self.left, bounds.left)
        top = max(self.top, bounds.top)
        right = min(self.right, bounds.right)
        bottom = min(self.bottom, bounds.bottom)
        return Rect.from_ltrb(left, top, max(left, right), max(top, bottom))

    def contains(self, p: Point) -> bool:
        return self.left <= p.x < self.right and self.top <= p.y < self.bottom

    def crop(self, image):
        """Recorta um array HxW[xC] usando este retangulo (sem copia)."""
        return image[self.top : self.bottom, self.left : self.right]


@dataclass(frozen=True, slots=True)
class RatioBox:
    """Retangulo relativo a um Rect de referencia. Valores em 0..1."""

    rx: float
    ry: float
    rw: float
    rh: float

    def resolve(self, ref: Rect) -> Rect:
        """Converte para pixels absolutos dentro de `ref`."""
        x = ref.x + self.rx * ref.w
        y = ref.y + self.ry * ref.h
        return Rect(
            int(round(x)),
            int(round(y)),
            max(1, int(round(self.rw * ref.w))),
            max(1, int(round(self.rh * ref.h))),
        )

    @classmethod
    def from_rect(cls, box: Rect, ref: Rect) -> "RatioBox":
        if ref.w <= 0 or ref.h <= 0:
            raise ValueError("retangulo de referencia invalido")
        return cls(
            (box.x - ref.x) / ref.w,
            (box.y - ref.y) / ref.h,
            box.w / ref.w,
            box.h / ref.h,
        )

    def to_json(self) -> list[float]:
        return [round(self.rx, 6), round(self.ry, 6), round(self.rw, 6), round(self.rh, 6)]

    @classmethod
    def from_json(cls, data) -> "RatioBox":
        rx, ry, rw, rh = data
        return cls(float(rx), float(ry), float(rw), float(rh))


@dataclass(frozen=True, slots=True)
class RatioPoint:
    """Ponto relativo ao Rect de referencia. Usado para alvos de clique."""

    rx: float
    ry: float

    def resolve(self, ref: Rect) -> Point:
        return Point(
            int(round(ref.x + self.rx * ref.w)),
            int(round(ref.y + self.ry * ref.h)),
        )

    @classmethod
    def from_point(cls, p: Point, ref: Rect) -> "RatioPoint":
        return cls((p.x - ref.x) / ref.w, (p.y - ref.y) / ref.h)

    def to_json(self) -> list[float]:
        return [round(self.rx, 6), round(self.ry, 6)]

    @classmethod
    def from_json(cls, data) -> "RatioPoint":
        rx, ry = data
        return cls(float(rx), float(ry))
