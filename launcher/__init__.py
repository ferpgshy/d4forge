"""O launcher do d4forge: escolhe a edição, baixa e mantém atualizado.

Vive fora do pacote `d4forge` de propósito. Ele é o que a pessoa baixa do
GitHub, e precisa ser pequeno — 10 MB contra os ~141 MB do aplicativo.
Importar qualquer coisa que puxe PySide6, OpenCV ou numpy jogaria isso fora:
por isso a interface é tkinter e tudo aqui é biblioteca padrão.
"""

from __future__ import annotations

__version__ = "1.0.0"
