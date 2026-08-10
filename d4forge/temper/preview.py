"""Leitura do item pelo tooltip, durante a animacao do Tempering.

    NAO ESTA' LIGADO NO CICLO, E NAO DEVE SER ATE' O PROBLEMA ABAIXO CAIR.

**O que falta.** Um afixo cujo texto quebra em varias linhas e' lido so' na
primeira, e o intervalo costuma estar na continuacao. Medido em
`preview_lucky_hit`: a linha temperada sai como "* Lucky Hit: Up to a +5.0%
Chance to Make Enemies Vulnerable for 2" e o "[2.5 - 5.0]" fica de fora - o
afixo e' julgado GREATER AFFIX sem ser. E' o erro caro: o Tempering substitui
o afixo anterior, entao parar achando que ganhou e' o de menos; o oposto rola
por cima do resultado bom.

Agrupar as continuacoes pela coluna nao resolve: elas comecam na MESMA coluna
dos afixos comuns (x=58), entao "linha nova" e "continuacao" sao
indistinguiveis por geometria. Precisa de outro criterio - espacamento
vertical entre linhas, ou ler o bloco inteiro de uma vez com a segmentacao
certa.

Enquanto isso o ciclo decide pela tela TEMPER COMPLETE, que mostra so' o afixo
temperado e nao tem essa ambiguidade.


Parar o mouse no centro do anel faz o jogo mostrar o item completo antes de a
animacao terminar. Isso permite decidir sem esperar a tela de resultado.

**Como o afixo temperado e' encontrado.** Nao pelo nome (o mesmo nome pode
aparecer duas vezes no item), nem pela estrela (afixos que o item ja' tinha
tambem sao GA), nem pelo icone (ele muda conforme a categoria temperada) - as
tres pistas foram testadas contra capturas reais e as tres falham.

O que sobra e' geometria: o glifo do afixo temperado e' mais largo que o
losango dos comuns, entao a linha dele comeca MAIS A' ESQUERDA. Medido nos
quatro itens capturados: afixo comum em x=58, temperado em x=35.

O texto do tooltip e' claro sobre fundo escuro, ao contrario do painel: aqui o
limiar e' 170, nao os 120 do resto do app. Com 120 as linhas nao se separam.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..geometry import Rect
from ..vision.preprocess import to_gray
from .result import TemperResult, parse_temper_result

# Texto claro sobre fundo escuro - ver cabecalho.
PREVIEW_THRESHOLD = 170

# Altura minima de uma linha; abaixo disso e' respingo.
MIN_LINE = 7

# Onde cada tipo de linha comeca, em pixels da ROI do tooltip. A folga de 6 px
# absorve a variacao entre itens.
ICON_X = 35      # afixo temperado: glifo largo, empurra a linha para a esquerda
TEXT_X = 58      # afixo comum: losango estreito
X_SLACK = 6


@dataclass(frozen=True, slots=True)
class PreviewLine:
    x: int
    y0: int
    y1: int
    text: str

    @property
    def tempered(self) -> bool:
        """Comeca na coluna do glifo largo?"""
        return abs(self.x - ICON_X) <= X_SLACK

    @property
    def plain_affix(self) -> bool:
        return abs(self.x - TEXT_X) <= X_SLACK


def _lines(frame: np.ndarray, roi: Rect) -> list[tuple[int, int, int, int]]:
    """Faixas de texto do tooltip: (y0, y1, x_inicio, x_fim)."""
    crop = roi.crop(frame)
    if crop.size == 0:
        return []
    mask = to_gray(crop) >= PREVIEW_THRESHOLD

    saida, inicio = [], None
    for y, tem in enumerate(list(mask.any(axis=1)) + [False]):
        if tem and inicio is None:
            inicio = y
        elif not tem and inicio is not None:
            if y - inicio >= MIN_LINE:
                cols = np.flatnonzero(mask[inicio:y].any(axis=0))
                if len(cols):
                    saida.append((inicio, y, int(cols[0]), int(cols[-1]) + 1))
            inicio = None
    return saida


def read_preview(frame: np.ndarray, roi: Rect, ocr, ui_scale: float = 1.0):
    """Le' todas as linhas do tooltip, com a coluna em que cada uma comeca."""
    linhas: list[PreviewLine] = []
    for y0, y1, x0, x1 in _lines(frame, roi):
        alvo = Rect(
            roi.x + max(0, x0 - 4), roi.y + max(0, y0 - 4),
            (x1 - x0) + 8, (y1 - y0) + 8,
        ).clip_to(Rect(0, 0, frame.shape[1], frame.shape[0]))
        texto = ocr.read(alvo.crop(frame), ui_scale=ui_scale).text.strip()
        if texto:
            linhas.append(PreviewLine(x0, y0, y1, texto))
    return linhas


def tempered_affix(linhas: list[PreviewLine]) -> TemperResult | None:
    """O afixo que acabou de ser temperado, entre as linhas do tooltip.

    E' a ULTIMA linha na coluna do glifo largo. "Ultima" porque o cabecalho do
    item ("1,899 Damage Per Second") tambem comeca ali, e ele vem antes de
    qualquer afixo - entao pegar a ultima descarta o cabecalho sem precisar
    saber o que ele e'.
    """
    candidatas = [linha for linha in linhas if linha.tempered]
    if not candidatas:
        return None
    return parse_temper_result(candidatas[-1].text)
