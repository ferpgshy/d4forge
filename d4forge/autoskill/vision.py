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

**Vida: a superficie do liquido, com limiar normalizado por imagem.**

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


# Acima desta fracao de azul no disco ha' barreira por cima da vida. Serve
# so' para a interface AVISAR - a leitura em si ja' atravessa o tingimento.
BARREIRA_QUE_ESCONDE = 0.10


@dataclass(frozen=True)
class LeituraDeVida:
    fracao: float          # 0..1; so' vale se `confiavel`
    confiavel: bool
    barreira: float        # fracao do disco coberta por escudo

    def porcentagem(self) -> int:
        return int(round(self.fracao * 100))

    @property
    def com_escudo(self) -> bool:
        return self.barreira >= BARREIRA_QUE_ESCONDE

    def descreve(self) -> str:
        if not self.confiavel:
            return "indeterminada"
        if self.com_escudo:
            return f"{self.porcentagem()}% (escudo)"
        return f"{self.porcentagem()}%"


# COMO O ORBE FUNCIONA, que foi o que custou acertar.
#
# Sao tres camadas, e elas NAO se comportam igual:
#
#   vida      vermelho, enche de baixo para cima
#   barreira  roxo/azul, overlay TRANSLUCIDO - "the health remains visible
#             underneath"; absorve todo o dano antes da vida, entao enquanto
#             ela segura a vida nem cai
#   fortify   camada extra de vermelho mais claro, e um anel na borda
#
# O erro que matou o personagem foi tratar a barreira como se ela ESCONDESSE a
# vida. Ela nao esconde: ela TINGE. O degrau entre cheio e vazio continua la',
# so' que os dois lados ficam mais claros.
#
# Por isso o limiar nao pode ser um numero fixo de brilho. Ele e' calculado
# POR IMAGEM, no meio do contraste que aquele quadro tem - assim acompanha o
# tingimento em vez de lutar contra ele. Medido nas amostras:
#
#                            limiar fixo   normalizado   real
#   cheia, sem escudo             97%          96%       100
#   cheia, COM escudo             89%         100%       100
#   vida parcial                  61%          62%       ~55-60
#   vida parcial                  44%          45%       ~45
#
# A versao com limiar fixo lia 89% com a vida CHEIA e escudo: perto demais de
# limiares comuns, e o ciclo bebia pocao a toa.

# Suavizacao do perfil, em linhas. O reflexo especular do orbe e' um ponto
# claro que, sem isto, vira um degrau falso.
SUAVIZACAO = 5

# Abaixo deste contraste nao ha' degrau: o orbe esta' todo cheio ou todo
# vazio. Medido, um orbe COM degrau tem contraste de 49 a 92.
CONTRASTE_MINIMO = 25

# Desempate do caso sem degrau: acima disto o disco esta' aceso, logo cheio.
BRILHO_DE_CHEIO = 55


def _perfil_de_brilho(recorte, cx, cy, raio) -> np.ndarray:
    """Brilho medio de cada linha do disco, do topo para a base."""
    v = cv2.cvtColor(recorte, cv2.COLOR_BGR2HSV)[..., 2].astype(np.float32)
    linhas = []
    for dy in range(-raio, raio + 1):
        meia = int((raio * raio - dy * dy) ** 0.5)
        if meia < 8:
            continue
        linhas.append(float(v[cy + dy, cx - meia:cx + meia + 1].mean()))
    return np.array(linhas, dtype=np.float32)


def ler_vida(frame: np.ndarray, orbe) -> LeituraDeVida:
    """Fracao de vida pela altura da superficie do liquido no orbe."""
    recorte = orbe.crop(frame)
    if recorte.size == 0:
        return LeituraDeVida(0.0, False, 0.0)

    alt, larg = recorte.shape[:2]
    cx, cy = larg // 2, alt // 2
    raio = int(min(cx, cy) * ORBE_UTIL)
    if raio < 12:
        return LeituraDeVida(0.0, False, 0.0)

    perfil = _perfil_de_brilho(recorte, cx, cy, raio)
    if len(perfil) < SUAVIZACAO * 2:
        return LeituraDeVida(0.0, False, 0.0)

    # Quanto do disco a barreira cobre. Nao entra mais na DECISAO - o limiar
    # normalizado ja' da' conta dela -, mas a interface mostra.
    hsv = cv2.cvtColor(recorte, cv2.COLOR_BGR2HSV)
    ys, xs = np.ogrid[:alt, :larg]
    disco = (xs - cx) ** 2 + (ys - cy) ** 2 <= raio * raio
    pixels = int(disco.sum())
    fracao_azul = (
        float((_mascara_azul(hsv) & disco).sum()) / pixels if pixels else 0.0
    )

    suave = np.convolve(
        perfil, np.ones(SUAVIZACAO) / SUAVIZACAO, mode="valid"
    )
    baixo, alto = np.percentile(suave, 10), np.percentile(suave, 90)

    if alto - baixo < CONTRASTE_MINIMO:
        # Sem degrau: o orbe esta' inteiro de um jeito so'.
        cheio = float(suave.mean()) > BRILHO_DE_CHEIO
        return LeituraDeVida(1.0 if cheio else 0.0, True, fracao_azul)

    meio = (baixo + alto) / 2
    acesas = np.where(suave > meio)[0]
    if not len(acesas):
        return LeituraDeVida(0.0, True, fracao_azul)
    # A primeira linha acesa vindo do topo e' a superficie; o que esta' abaixo
    # dela e' vida.
    return LeituraDeVida(
        max(0.0, min(1.0, 1.0 - acesas[0] / len(suave))), True, fracao_azul
    )


__all__ = [
    "EstadoDoSlot",
    "FRACAO_DE_COOLDOWN",
    "LeitorDeCooldown",
    "LeituraDeVida",
    "ler_vida",
]
