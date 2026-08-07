"""Captura de tela.

Dois backends:
  * dxcam  - Desktop Duplication (DXGI). Rapido, ~1-2 ms por regiao pequena.
  * mss    - GDI. Mais lento (~5-10 ms) mas funciona em qualquer lugar.

Detalhe importante do dxcam: `grab()` devolve None quando NAO houve frame novo
desde a ultima chamada. Numa tela de menu parada isso acontece o tempo todo, e
`None` ali significa "nada mudou", nao "falhou" - por isso guardamos o ultimo
frame bom e o reentregamos.
"""

from __future__ import annotations

import logging
import threading
from typing import Protocol

import numpy as np

from .geometry import Rect

log = logging.getLogger(__name__)


class CaptureBackend(Protocol):
    name: str

    def grab(self, region: Rect) -> np.ndarray | None:
        """Retorna a regiao como array BGR (H, W, 3) uint8."""
        ...

    def close(self) -> None: ...


class DXCamBackend:
    """Desktop Duplication. Um device por output; region grab e' feito na GPU."""

    name = "dxcam"

    def __init__(self, output_idx: int = 0) -> None:
        import dxcam

        self._camera = dxcam.create(output_idx=output_idx, output_color="BGR")
        if self._camera is None:
            raise RuntimeError(f"dxcam nao conseguiu abrir o output {output_idx}")
        self._last: np.ndarray | None = None
        self._last_region: tuple[int, int, int, int] | None = None

    def grab(self, region: Rect) -> np.ndarray | None:
        box = region.as_ltrb()
        frame = self._camera.grab(region=box)
        if frame is None:
            # Sem frame novo. Se a regiao e' a mesma, o conteudo tambem e'.
            if self._last is not None and self._last_region == box:
                return self._last
            # Regiao mudou e nao veio frame: forca um novo ciclo.
            frame = self._camera.grab(region=box)
            if frame is None:
                return None
        self._last = frame
        self._last_region = box
        return frame

    def close(self) -> None:
        try:
            self._camera.release()
        except Exception:
            pass


class MSSBackend:
    """Fallback GDI. `mss` nao e' thread-safe, entao criamos um por thread."""

    name = "mss"

    def __init__(self) -> None:
        import mss

        self._mss = mss
        self._local = threading.local()

    def _sct(self):
        sct = getattr(self._local, "sct", None)
        if sct is None:
            sct = self._mss.mss()
            self._local.sct = sct
        return sct

    def grab(self, region: Rect) -> np.ndarray | None:
        shot = self._sct().grab(
            {"left": region.x, "top": region.y, "width": region.w, "height": region.h}
        )
        # mss entrega BGRA; descartamos o alpha.
        return np.asarray(shot, dtype=np.uint8)[:, :, :3]

    def close(self) -> None:
        sct = getattr(self._local, "sct", None)
        if sct is not None:
            sct.close()
            self._local.sct = None


class ScreenCapture:
    """Fachada que escolhe o backend e cai pro mss se o dxcam falhar."""

    def __init__(self, prefer: str = "dxcam", output_idx: int = 0) -> None:
        self._backend: CaptureBackend
        if prefer == "dxcam":
            try:
                self._backend = DXCamBackend(output_idx)
                log.info("captura via dxcam (output %d)", output_idx)
            except Exception as exc:
                log.warning("dxcam indisponivel (%s); usando mss", exc)
                self._backend = MSSBackend()
        else:
            self._backend = MSSBackend()

    @property
    def backend_name(self) -> str:
        return self._backend.name

    def grab(self, region: Rect) -> np.ndarray | None:
        if region.w <= 0 or region.h <= 0:
            return None
        try:
            return self._backend.grab(region)
        except Exception as exc:
            log.error("falha na captura de %s: %s", region, exc)
            return None

    def grab_or_raise(self, region: Rect) -> np.ndarray:
        frame = self.grab(region)
        if frame is None:
            raise RuntimeError(f"nao foi possivel capturar a regiao {region}")
        return frame

    def close(self) -> None:
        self._backend.close()

    def __enter__(self) -> "ScreenCapture":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
