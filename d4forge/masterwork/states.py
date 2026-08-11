"""Em qual tela do Masterworking o jogo esta', e o que da' para fazer nela.

Tres telas, separadas por medidas com folga larga:

                        blacksmith   modal    next_rank
    PASSO                   0.360    0.011       0.081
    MASTERWORK              0.360    0.011       0.000
    ANIMACAO                0.000    0.541       0.000

`next_rank` e' a linha "NEXT RANK", que existe no passo comum e some quando o
jogo troca aquele bloco pelo "Current Masterwork Affix". A pergunta que o ciclo
faz - "acabei de tirar um Masterwork?" - se responde pela PRESENCA dessa linha,
nao pela ausencia dela: presenca nao depende de o OCR acertar digito.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from ..vision.preprocess import binarize, to_gray

# Fracao de pixels acesos a partir da qual um botao conta como habilitado.
# Medido: "NEXT RANK" presente da' 0.0808 e ausente da' 0.0000; o Upgrade
# habilitado da' 0.0395. 0.02 fica longe dos dois lados.
BUTTON_ON = 0.02

# Acima disto ha' modal por cima do painel. Medido: o cabecalho do modal da'
# 0.541 e o painel, no mesmo lugar, da' 0.011.
MODAL_ON = 0.05


class MasterworkState(Enum):
    UNKNOWN = "unknown"
    # Aba Masterworking aberta, mostrando "NEXT RANK / QUALITY x/25".
    STEP = "mw_idle"
    # Aba Masterworking aberta, mostrando "Current Masterwork Affix".
    AFFIX = "mw_affix"
    # Animacao rodando, com o botao Skip.
    ANIMATION = "mw_animation"


def ink(frame: np.ndarray, roi, threshold: int = 120) -> float:
    """Fracao de pixels acesos numa regiao."""
    crop = roi.crop(frame)
    if crop.size == 0:
        return 0.0
    return float(binarize(to_gray(crop), threshold).mean())


@dataclass(frozen=True, slots=True)
class MasterworkReading:
    """A tela atual e o que da' para fazer nela."""

    state: MasterworkState
    can_upgrade: bool = False    # botao Upgrade habilitado
    marks: dict = field(default_factory=dict)

    @property
    def showing_affix(self) -> bool:
        """A tela esta' mostrando o Masterwork Affix atual?"""
        return self.state is MasterworkState.AFFIX


def detect_masterwork_state(frame: np.ndarray, prof) -> MasterworkReading:
    """Classifica a tela do Masterworking a partir de um quadro.

    Nenhuma pergunta aqui depende de OCR. As tres telas se separam por tinta
    com margens de uma ordem de grandeza, e medir tinta custa ~0,1 ms contra os
    ~70 ms de uma leitura - alem de nao ter digito para errar.
    """
    marks = {
        "blacksmith": ink(frame, prof.blacksmith_header),
        "modal": ink(frame, prof.modal_header),
        "next_rank": ink(frame, prof.next_rank),
        "upgrade_btn": ink(frame, prof.upgrade_button),
    }

    if marks["blacksmith"] >= MODAL_ON:
        estado = (
            MasterworkState.STEP
            if marks["next_rank"] >= BUTTON_ON
            else MasterworkState.AFFIX
        )
        return MasterworkReading(
            estado,
            can_upgrade=marks["upgrade_btn"] >= BUTTON_ON,
            marks=marks,
        )

    if marks["modal"] >= MODAL_ON:
        return MasterworkReading(MasterworkState.ANIMATION, marks=marks)

    return MasterworkReading(MasterworkState.UNKNOWN, marks=marks)
