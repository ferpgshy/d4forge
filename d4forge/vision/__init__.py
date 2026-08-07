"""Visao computacional: pre-processamento, OCR e leitura de estado de tela."""

from .ocr import OcrEngine, OcrResult, OcrStats, normalize_text
from .preprocess import DEFAULT_THRESHOLD, binarize, prepare_line, to_gray
from .states import ScreenState, StateReading, detect_state, selected_orb

__all__ = [
    "OcrEngine",
    "OcrResult",
    "OcrStats",
    "normalize_text",
    "DEFAULT_THRESHOLD",
    "binarize",
    "prepare_line",
    "to_gray",
    "ScreenState",
    "StateReading",
    "detect_state",
    "selected_orb",
]
