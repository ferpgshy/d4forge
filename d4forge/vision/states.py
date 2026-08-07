"""Classificacao do estado da tela.

Roda antes do OCR e sem ele: so' estatisticas de pixel sobre ROIs pequenas, o
que custa dezenas de microssegundos. O engine nunca age sem saber em que tela
esta', entao esta classificacao e' a principal barreira contra clique errado.

Sinais usados (todos medidos nos prints de referencia):
  * "tinta"    fracao de pixels acima do limiar de texto
  * "redness"  R - (G+B)/2, que isola a UI vermelha do jogo
  * o painel esquerdo escurece quando um dialogo modal abre
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

from ..geometry import Rect
from ..profile import ResolvedProfile
from .preprocess import DEFAULT_THRESHOLD

# Orbe marcado mede redness ~+140; nao marcado ~-4. 50 fica bem no meio.
ORB_SELECTED_REDNESS = 50.0

# Moldura/botao vermelho da UI.
BUTTON_REDNESS = 18.0

# Acima disso a ROI claramente tem texto.
INK_PRESENT = 0.012

# Painel iluminado normalmente passa disso; com modal aberto cai perto de zero.
PANEL_LIT = 0.004


class ScreenState(Enum):
    UNKNOWN = "unknown"
    ENCHANT_SELECT = "enchant_select"   # item cru: escolher qual afixo trocar
    ENCHANT_LOCKED = "enchant_locked"   # afixo ja' fixado: so' apertar Enchant
    CONFIRM = "confirm"                 # dialogo Accept / Cancel
    REPLACE = "replace"                 # 2 opcoes + No Change
    RESULT = "result"                   # dialogo com botao Close

    @property
    def is_enchant(self) -> bool:
        return self in (ScreenState.ENCHANT_SELECT, ScreenState.ENCHANT_LOCKED)


# Acima disto a ROI e' amostrada em vez de varrida inteira. Medido: varrer o
# painel completo (640x960) custa 15,8 ms e domina 97% do custo de detectar o
# estado; amostrando 1 pixel a cada 4 o custo cai para 1,1 ms e a fracao medida
# muda de 0,0516 para 0,0520 - irrelevante perto das margens dos limiares.
MAX_INK_SAMPLES = 24_000


def ink(
    frame: np.ndarray,
    rect: Rect,
    threshold: int = DEFAULT_THRESHOLD,
    max_samples: int = MAX_INK_SAMPLES,
) -> float:
    """Fracao de pixels claros dentro do retangulo (coordenadas do frame).

    ROI grande e' subamostrada: estamos medindo densidade de texto, nao contando
    pixel a pixel, e o poll de estado roda dezenas de vezes por segundo.
    """
    sub = rect.crop(frame)
    if sub.size == 0:
        return 0.0
    area = sub.shape[0] * sub.shape[1]
    if max_samples and area > max_samples:
        step = int((area / max_samples) ** 0.5) + 1
        sub = sub[::step, ::step]
    gray = sub.max(axis=2) if sub.ndim == 3 else sub
    return float((gray >= threshold).mean())


def redness(frame: np.ndarray, rect: Rect) -> float:
    """Media de R - (G+B)/2. Alto = elemento vermelho da UI."""
    sub = rect.crop(frame)
    if sub.size == 0:
        return 0.0
    b = sub[:, :, 0].astype(np.int16)
    g = sub[:, :, 1].astype(np.int16)
    r = sub[:, :, 2].astype(np.int16)
    return float((r - (g + b) // 2).mean())


def peak_redness(frame: np.ndarray, rect: Rect) -> float:
    """Redness do percentil 90 - melhor que a media para achar o orbe aceso,
    que ocupa so' o miolo do circulo."""
    sub = rect.crop(frame)
    if sub.size == 0:
        return 0.0
    b = sub[:, :, 0].astype(np.int16)
    g = sub[:, :, 1].astype(np.int16)
    r = sub[:, :, 2].astype(np.int16)
    return float(np.percentile(r - (g + b) // 2, 90))


def selected_orb(frame: np.ndarray, orbs: list[Rect]) -> int | None:
    """Indice do orbe marcado, ou None se nenhum estiver."""
    scores = [peak_redness(frame, o) for o in orbs]
    if not scores:
        return None
    best = int(np.argmax(scores))
    return best if scores[best] >= ORB_SELECTED_REDNESS else None


@dataclass(frozen=True)
class StateReading:
    """Estado detectado + os sinais crus, para depurar na GUI sem adivinhacao."""

    state: ScreenState
    signals: dict[str, float]

    def describe(self) -> str:
        parts = ", ".join(f"{k}={v:.3f}" for k, v in sorted(self.signals.items()))
        return f"{self.state.value} ({parts})"


def detect_state(frame: np.ndarray, prof: ResolvedProfile) -> StateReading:
    """Identifica a tela atual a partir de um frame do client rect.

    A ordem importa: os dialogos modais sao testados antes das telas de fundo,
    porque quando um modal esta' aberto a tela de fundo continua visivel.
    """
    sig: dict[str, float] = {}

    sig["accept_red"] = redness(frame, prof.confirm_accept)
    sig["cancel_red"] = redness(frame, prof.confirm_cancel)
    sig["confirm_ink"] = ink(frame, prof.confirm_text)
    sig["panel_ink"] = ink(frame, prof.panel_probe)

    # 1. CONFIRM - dois botoes vermelhos lado a lado no centro, painel apagado.
    if (
        sig["accept_red"] >= BUTTON_REDNESS
        and sig["cancel_red"] >= BUTTON_REDNESS
        and sig["confirm_ink"] >= INK_PRESENT
    ):
        return StateReading(ScreenState.CONFIRM, sig)

    # 2. RESULT - barra de titulo "ITEM" clara + botao Close vermelho.
    sig["result_ink"] = ink(frame, prof.result_title)
    sig["close_red"] = redness(frame, prof.result_close)
    if sig["result_ink"] >= 0.10 and sig["close_red"] >= BUTTON_REDNESS:
        return StateReading(ScreenState.RESULT, sig)

    # 3. REPLACE - barra "REPLACE AFFIX" clara e o orbe do No Change aceso.
    sig["replace_ink"] = ink(frame, prof.replace_title)
    orbs = prof.replace_orbs
    sig["orb_max"] = max((peak_redness(frame, o) for o in orbs), default=0.0)
    if sig["replace_ink"] >= 0.10 and sig["orb_max"] >= ORB_SELECTED_REDNESS:
        return StateReading(ScreenState.REPLACE, sig)

    # 4. ENCHANT - barra "OCCULTIST" clara.
    sig["occultist_ink"] = ink(frame, prof.occultist_title)
    if sig["occultist_ink"] >= 0.05 and sig["panel_ink"] >= PANEL_LIT:
        # SELECT vs LOCKED: a SEGUNDA linha de afixo e' o unico sinal que se
        # mostrou limpo em todos os frames reais. Na lista de selecao ha' texto
        # nela (qualquer item com 2+ afixos); na tela travada essa altura cai
        # exatamente no vao entre a caixa do afixo e o texto de explicacao.
        #
        # Sinais que pareciam bons e falharam ao vivo:
        #   * linha 4 - o cursor do jogo parado ali acendia a ROI (0.014);
        #   * coluna dos orbes - afixo de nome longo e' centralizado e comeca
        #     mais a esquerda: "x22% Shadow Damage Multiplier" partia de x=219
        #     e invadia a coluna (0.018 com limiar 0.012).
        # Medido: SELECT row2=0.048; tres frames LOCKED distintos, row2=0.000.
        sig["row2_ink"] = ink(frame, prof.affix_rows[1])
        if sig["row2_ink"] >= INK_PRESENT:
            return StateReading(ScreenState.ENCHANT_SELECT, sig)
        return StateReading(ScreenState.ENCHANT_LOCKED, sig)

    return StateReading(ScreenState.UNKNOWN, sig)
