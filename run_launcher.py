r"""Ponto de entrada do launcher do d4forge.

    .venv\Scripts\python.exe run_launcher.py

Existe separado de `launcher/__main__.py` por um motivo concreto: o
PyInstaller executa o script de entrada COMO `__main__`, sem contexto de
pacote, e os imports relativos de dentro do pacote (`from .ui import ...`)
estouram. Medido: o executável abria a caixa de "unhandled exception" e
morria. Um arquivo na raiz, importando pelo nome completo, resolve.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    from launcher.ui import executar

    return executar()


if __name__ == "__main__":
    raise SystemExit(main())
