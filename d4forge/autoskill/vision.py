"""Ler o HUD de combate: o que esta' em cooldown e quanta vida sobrou.

Duas leituras, duas tecnicas diferentes, cada uma escolhida pelo que o sinal
permite.

**Cooldown: estatistica de brilho, sem OCR e sem cor.**

Um icone em cooldown fica ESCURECIDO e ganha um numero por cima. Ler o numero
com OCR custaria 20-30 ms por slot - inviavel num laco que roda dez vezes por
segundo - e e' redundante: o escurecimento sozinho ja' separa os dois estados.
Medido nos tres prints de referencia, seis slots cada:

    V p90 (brilho do decil mais claro)   disponivel 226..234   cooldown 89..94

Sao 130 pontos de margem, sem uma unica sobreposicao.

A metrica e' o percentil 90 do V do HSV, e NAO a cor: ha' mais de cem
habilidades no jogo, cada uma com a sua paleta, e um criterio de matiz ("quanto
do icone e' laranja") separava lindamente este build de fogo e quebraria no
primeiro build de gelo. Brilho e' a unica propriedade que o cooldown muda em
TODOS eles.

Mesmo assim um limiar fixo seria uma aposta - existe icone naturalmente escuro.
Por isso a comparacao e' com o proprio slot: guarda-se o maior V p90 ja' visto
ali e cooldown passa a ser "caiu para menos da metade do seu proprio brilho
normal". Converge no primeiro segundo de jogo e nao pede calibracao nenhuma.

**Vida: a linha de preenchimento, nao a proporcao de vermelho.**

O orbe enche de baixo para cima e a borda entre o vermelho e o vazio e' nitida.
Procurar essa BORDA e' mais robusto do que contar vermelho, e a diferenca nao e'
teorica: com barreira ativa a proporcao de vermelho cai de 22,4% para 13,5%
_com a vida cheia nos dois casos_. Um limiar sobre proporcao tomaria pocao a
100% de vida toda vez que subisse escudo.

Validado nos recortes reais: 99,1% na vida cheia, 60,7% e 44,1% nos dois de
vida parcial - batendo com a conferencia visual.

O que este metodo NAO resolve e' barreira forte: quando o escudo cobre o orbe
inteiro, nao ha' borda para achar. Nesse caso a leitura se declara
INDETERMINADA em vez de inventar um numero, e quem decide o que fazer com isso
e' a politica do usuario.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .profile import ORBE_UTIL

# Abaixo desta fracao do proprio brilho normal, o slot esta' em cooldown. Com
# 226..234 disponivel contra 89..94 em cooldown, a razao medida e' 0,39 - 0,55
# fica no meio do vao, longe das duas pontas.
FRACAO_DE_COOLDOWN = 0.55

# Partida, ate' o slot revelar o proprio brilho normal. Fica entre as duas
# faixas medidas e so' vale para o primeiro quadro.
BRILHO_INICIAL = 150

def _mascara_azul(hsv: np.ndarray) -> np.ndarray:
    """Barreira. Azul e roxo, que e' como o escudo pinta o orbe."""
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return (h >= 95) & (h <= 145) & (s > 55) & (v > 45)


@dataclass(frozen=True)
class EstadoDoSlot:
    indice: int
    brilho: float          # V p90 agora
    referencia: float      # maior V p90 ja' visto neste slot
    em_cooldown: bool

    def descreve(self) -> str:
        estado = "cooldown" if self.em_cooldown else "pronta"
        return f"slot {self.indice + 1}: {estado} ({self.brilho:.0f}/{self.referencia:.0f})"


class LeitorDeCooldown:
    """Guarda o brilho normal de cada slot entre quadros.

    Tem estado de proposito: e' esse historico que dispensa o usuario de
    calibrar e que faz a leitura valer para qualquer icone.
    """

    def __init__(self, slots: int) -> None:
        self._referencia = [0.0] * slots

    def esquecer(self) -> None:
        """Zera o aprendizado - usar ao trocar de build ou de personagem."""
        self._referencia = [0.0] * len(self._referencia)

    def ler(self, frame: np.ndarray, rois) -> list[EstadoDoSlot]:
        estados = []
        for i, roi in enumerate(rois):
            recorte = roi.crop(frame)
            if recorte.size == 0:
                estados.append(EstadoDoSlot(i, 0.0, self._referencia[i], False))
                continue
            v = cv2.cvtColor(recorte, cv2.COLOR_BGR2HSV)[..., 2]
            brilho = float(np.percentile(v, 90))

            # Decide com a referencia de ANTES deste quadro. Atualizar primeiro
            # parecia inofensivo e nao era: no primeiro quadro da sessao a
            # referencia valia zero, virava o proprio brilho do icone
            # ESCURECIDO (93), e o limiar de partida nunca era alcancado - o
            # slot nascia "pronto" estando em cooldown, e ainda ficava
            # ancorado em 93 ate' ser visto disponivel uma vez.
            anterior = self._referencia[i]
            limite = (
                anterior * FRACAO_DE_COOLDOWN if anterior > 0 else BRILHO_INICIAL
            )
            em_cooldown = brilho < limite

            # So' quadro SEM cooldown ensina o brilho normal, e a referencia
            # so' sobe: aprender com o icone apagado seria aprender errado.
            if not em_cooldown and brilho > anterior:
                self._referencia[i] = brilho

            estados.append(
                EstadoDoSlot(i, brilho, self._referencia[i], em_cooldown)
            )
        return estados


@dataclass(frozen=True)
class LeituraDeVida:
    fracao: float          # 0..1; so' vale se `confiavel`
    confiavel: bool
    barreira: float        # fracao do disco coberta por escudo

    def porcentagem(self) -> int:
        return int(round(self.fracao * 100))

    def descreve(self) -> str:
        if not self.confiavel:
            return f"indeterminada (escudo em {self.barreira * 100:.0f}% do orbe)"
        return f"{self.porcentagem()}%"


# Vida VAZIA e' preta. O criterio e' esse, e nao "cheia e' vermelha".
#
# Parece a mesma coisa invertida, mas nao e': o que enche o orbe muda de cor
# (vermelho normal, rosa dessaturado sob escudo, azul quando a barreira cobre
# tudo), enquanto o VAZIO e' sempre o mesmo preto. Medido, com vida cheia e
# escudo ativo: o criterio por vermelho lia 89%, o criterio por escuro le' 99%.
#
# Em compensacao, barreira que cobre o orbe inteiro le' como vida cheia. Isso
# nao e' um defeito deste metodo - e' o que a tela mostra: com o escudo por
# cima, a vida embaixo nao esta' visivel para ninguem. A fracao de azul vai
# junto na leitura para a interface poder avisar.
V_DE_VAZIO = 60
LINHA_VAZIA = 0.6


def ler_vida(frame: np.ndarray, orbe) -> LeituraDeVida:
    """Fracao de vida pela altura da borda do liquido dentro do orbe."""
    recorte = orbe.crop(frame)
    if recorte.size == 0:
        return LeituraDeVida(0.0, False, 0.0)

    alt, larg = recorte.shape[:2]
    cx, cy = larg // 2, alt // 2
    raio = int(min(cx, cy) * ORBE_UTIL)
    if raio < 8:
        return LeituraDeVida(0.0, False, 0.0)

    hsv = cv2.cvtColor(recorte, cv2.COLOR_BGR2HSV)
    escuro = hsv[..., 2] < V_DE_VAZIO
    azul = _mascara_azul(hsv)

    # So' o disco entra na conta: os cantos do recorte sao cenario, e cenario
    # escuro seria lido como orbe vazio.
    ys, xs = np.ogrid[:alt, :larg]
    disco = (xs - cx) ** 2 + (ys - cy) ** 2 <= raio * raio
    pixels = int(disco.sum())
    if not pixels:
        return LeituraDeVida(0.0, False, 0.0)
    fracao_azul = float((azul & disco).sum()) / pixels

    # De cima para baixo: a primeira linha que NAO e' majoritariamente escura
    # e' a superficie do liquido. O que esta' abaixo dela e' vida.
    topo, base = cy - raio, cy + raio
    for y in range(topo, base + 1):
        largura = int((raio * raio - (y - cy) ** 2) ** 0.5)
        if largura < 6:
            continue
        linha = escuro[y, cx - largura:cx + largura + 1]
        if linha.size and linha.mean() < LINHA_VAZIA:
            return LeituraDeVida(
                max(0.0, min(1.0, (base - y) / (base - topo))), True, fracao_azul
            )

    # Disco escuro de ponta a ponta: vida no fim.
    return LeituraDeVida(0.0, True, fracao_azul)


__all__ = [
    "EstadoDoSlot",
    "FRACAO_DE_COOLDOWN",
    "LeitorDeCooldown",
    "LeituraDeVida",
    "ler_vida",
]
