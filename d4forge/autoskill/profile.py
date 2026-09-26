"""Onde o HUD de combate fica, em pixels de referencia (1920x1080).

Medido por template matching dos recortes dentro das telas cheias, nao chutado:
cada numero aqui saiu de um casamento acima de 0,97 com a imagem de referencia.

A ancora e' `center` para TUDO, ao contrario do painel do Occultist. O bloco do
HUD - orbe de vida, barra de habilidades, orbe de recurso - vai de x 454 a
x 1488, cujo meio e' 971 contra o centro de tela 959. Ou seja: o jogo
CENTRALIZA o HUD e o gruda na base, entao numa ultrawide ele nao acompanha a
borda esquerda. E' o `ANCORA_PADRAO` que diz isso ao `ResolvedProfile`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..geometry import Rect
from ..profile import ANCHOR_CENTER

# Barra de habilidades. O recorte de um slot em cooldown casou a 0,973 em
# x 770..832, e o da barra inteira a 0,979 em x 773..1145 - 372 px para 6
# slots da' exatamente 62 de passo.
SLOTS = 6
SLOT_X0 = 771
SLOT_Y0 = 977
SLOT_PASSO = 62
# A moldura do slot tem uns 3 px de borda decorativa que muda de brilho com o
# tema do jogo; medir so' o miolo tira essa variavel da conta.
SLOT_MARGEM = 3
SLOT_LADO = 56

# Orbe de vida. Quatro telas cheias, disco achado por HoughCircles: centro
# (606,994) (610,994) (610,988) (610,990), raio 68..76. O raio varia porque a
# barreira desenha um anel por fora - por isso o raio util e' bem menor.
ORBE_CX = 609
ORBE_CY = 992
ORBE_RAIO = 71
# Fracao do raio que entra na conta. Fora disso comeca a moldura de metal, que
# nao e' vida nem vazio e so' sujaria o perfil por linha.
ORBE_UTIL = 0.84


def _slot(i: int) -> Rect:
    return Rect(
        SLOT_X0 + SLOT_PASSO * i + SLOT_MARGEM,
        SLOT_Y0 + SLOT_MARGEM,
        SLOT_LADO,
        SLOT_LADO,
    )


@dataclass(frozen=True)
class AutoSkillProfile:
    """ROIs do HUD de combate em coordenadas de referencia."""

    # Todo o HUD e' centralizado; nao ha' excecao a declarar.
    ANCORA_PADRAO: str = ANCHOR_CENTER
    CENTRALIZADAS: frozenset = frozenset()

    skill_slots: tuple[Rect, ...] = field(
        default_factory=lambda: tuple(_slot(i) for i in range(SLOTS))
    )

    # Quadrado que circunscreve o orbe. O disco sai dele em `vision`; guardar
    # um Rect e' o que deixa o `ResolvedProfile` escalar isto de graca, junto
    # com todo o resto do projeto.
    health_orb: Rect = Rect(
        ORBE_CX - ORBE_RAIO, ORBE_CY - ORBE_RAIO, ORBE_RAIO * 2, ORBE_RAIO * 2
    )

    # Contador "4/4" embaixo do frasco. Medido no recorte ampliado: o texto
    # ocupa x 657..685, y 934..946; a folga cobre "10/10" de builds com mais
    # cargas sem encostar no orbe.
    potion_count: Rect = Rect(646, 926, 54, 26)


DEFAULT_AUTOSKILL_PROFILE = AutoSkillProfile()
