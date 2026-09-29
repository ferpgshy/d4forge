r"""Entrada do launcher.

    .venv\Scripts\python.exe -m launcher
"""

from __future__ import annotations

import sys

from .ui import executar

if __name__ == "__main__":
    sys.exit(executar())
