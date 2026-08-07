"""Input sintetico e travas de seguranca."""

from .safety import Guard, Limits, StopReason, key_is_down
from .sendinput import click_rect, cursor_position, jittered_point, press_key, smooth_move

__all__ = [
    "Guard",
    "Limits",
    "StopReason",
    "key_is_down",
    "click_rect",
    "cursor_position",
    "jittered_point",
    "press_key",
    "smooth_move",
]
