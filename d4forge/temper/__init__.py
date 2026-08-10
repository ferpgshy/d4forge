"""Automacao do Tempering (Ferreiro).

Segundo fluxo do app, ao lado do encantamento do Occultist. A diferenca de
fundo entre os dois:

* No **encantamento** o jogo oferece duas opcoes e voce escolhe uma. A decisao
  compara nome e valor contra um catalogo cadastrado a mao.
* No **tempering** o jogo sorteia um valor dentro de um intervalo e mostra o
  intervalo na propria tela ("+8.4% ... [5.0 - 10.0]"). Nao ha' catalogo: o que
  define se o roll foi bom sai da linha lida.

Isso torna o criterio de aceite mais simples e mais confiavel aqui - um Greater
Affix e' exatamente um valor acima do maximo do intervalo mostrado.
"""

from .profile import DEFAULT_TEMPER_PROFILE, TemperProfile
from .result import TemperResult, parse_temper_result, read_text_lines
from .states import TemperState, button_active, detect_temper_state

__all__ = [
    "DEFAULT_TEMPER_PROFILE",
    "TemperProfile",
    "TemperResult",
    "TemperState",
    "button_active",
    "detect_temper_state",
    "parse_temper_result",
    "read_text_lines",
]
