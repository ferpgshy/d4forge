"""Ler o "Current Masterwork Affix" e decidir se e' o afixo que voce queria.

O Masterworking sorteia QUAL dos afixos do item recebe o aumento. Entao, ao
contrario do Tempering, nao ha' valor a julgar nem intervalo a comparar: a
pergunta e' so' "caiu no afixo certo?", e ela se responde por NOME.

**Por que o catalogo nao decide aqui.** O catalogo do app lista os afixos que o
Occultist sabe encantar. O Masterwork cai em qualquer afixo do item, inclusive
os que vieram do Tempering - "Damage with Two-Handed Slashing Weapons", o afixo
do print de referencia, nao esta' no catalogo e nunca vai estar. Exigir
casamento com o catalogo reprovaria justamente as leituras boas. Ele continua
entrando como NORMALIZADOR: quando o nome lido casa com uma entrada, usamos a
forma canonica dela; quando nao casa, usamos o nome como foi lido.

A comparacao final e' por similaridade contra o alvo que voce escolheu, porque
o OCR entrega o nome torto - "+&0.0% Damage with Tw0-Handed Slashing Werapons"
foi uma leitura real desta tela.

Na duvida, PARAR. A assimetria e' a mesma do Tempering, e pelo mesmo motivo:

    parar sem precisar    -> voce confere na mao e manda seguir. Custa tempo.
    seguir sem precisar   -> o proximo Masterwork rola por cima do afixo bom,
                             e isso nao tem desfazer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

import numpy as np

from ..affixes import NAME_MATCH_THRESHOLD, AffixCatalog, ParsedAffix, _canon, parse_affix
from ..geometry import Rect
from ..temper.result import read_text_lines

# Folga vertical entre linhas da caixa do Masterwork Affix. Medido: as duas
# linhas ficam a 6 px uma da outra, contra ~9 px na tela de resultado do
# Tempering. Com a folga de la' elas viram uma banda so' - e uma banda de duas
# linhas volta ilegivel do detector ("+8.0Damneweaon-Handd" foi o que saiu).
LINE_GAP = 4

# Sujeira que o OCR pega da borda da caixa e cola na frente da linha.
#
# A regra e' por PRESENCA do que pode comecar um afixo, e nao por lista do que
# nao pode. Enumerar a sujeira ja' falhou duas vezes com o mesmo sintoma: o
# ponto de ".+80.0% Damage with Two-Handed..." entrou na lista, e dias depois
# outro glifo qualquer apareceu em "  +242 Strength" e passou reto. A borda pode
# virar qualquer desenho; o comeco de um afixo, nao.
_INICIO_INVALIDO = re.compile(r"^[^0-9A-Za-z+\-]+")

# Onde um valor comeca: "+242", "x14", "80.0". Usado so' quando a linha inteira
# nao casa - a sujeira pode sair como LETRA ("l +242 Strength"), e ai o corte
# acima nao pega.
_PRIMEIRO_VALOR = re.compile(r"[+\-xX×]?\s*\d")


def _sem_lixo(texto: str) -> str:
    return _INICIO_INVALIDO.sub("", texto.strip())


@dataclass(frozen=True, slots=True)
class MasterworkAffix:
    """O afixo que recebeu o Masterwork, como lido da tela."""

    raw: str
    parsed: ParsedAffix | None = None

    @property
    def readable(self) -> bool:
        """Da' para decidir com esta leitura?

        A prova e' o valor ter saido separado do nome. Isso significa que a
        gramatica reconheceu a linha, e portanto que `name` e' um nome mesmo -
        e nao a linha inteira embolada, que e' o que sobra quando a leitura
        falha ("：173All Resist" devolve valor None e nome igual ao texto todo).
        """
        return self.parsed is not None and self.parsed.value is not None

    @property
    def name(self) -> str:
        return self.parsed.name if self.parsed is not None else ""

    def describe(self) -> str:
        if self.parsed is None:
            return self.raw.strip() or "?"
        return self.parsed.describe()

    def similarity(self, alvo: str) -> float:
        """Quanto o afixo lido parece com o alvo, de 0 a 1."""
        if not self.readable or not alvo.strip():
            return 0.0
        return SequenceMatcher(None, _canon(self.name), _canon(alvo)).ratio()

    def matches(self, alvo: str, limiar: float = NAME_MATCH_THRESHOLD) -> bool:
        """E' o afixo alvo?

        So' responde `True` com a linha reconhecida E o nome parecido o
        bastante: uma leitura ruim nunca pode virar "achei", porque "achei" e'
        o que encerra a sessao e devolve o item ao jogador como pronto.
        """
        return self.similarity(alvo) >= limiar


def parse_masterwork_line(
    texto: str, catalog: AffixCatalog | None = None
) -> MasterworkAffix:
    """Interpreta uma linha ja' lida, limpando a sujeira da borda da caixa.

    Separada da leitura de proposito: e' aqui que mora toda a decisao sobre
    texto torto, e testar isso com strings vale mais do que testar com uma
    imagem so'. Um teste que refizesse estes passos por fora nao provaria que o
    caminho de verdade os executa - foi o que aconteceu na primeira versao.
    """
    limpo = _sem_lixo(texto)
    if not limpo:
        return MasterworkAffix(raw=texto)

    lido = parse_affix(limpo, catalog)
    if lido.value is None:
        # A gramatica quer o valor na frente. Se ela nao casou, sobrou sujeira
        # que o corte acima nao alcancou - tipicamente um glifo de borda lido
        # como letra. Cortar ate' o primeiro valor e' a ultima tentativa.
        m = _PRIMEIRO_VALOR.search(limpo)
        if m is not None and m.start() > 0:
            resto = limpo[m.start():]
            alternativa = parse_affix(resto, catalog)
            if alternativa.value is not None:
                return MasterworkAffix(raw=resto, parsed=alternativa)

    return MasterworkAffix(raw=limpo, parsed=lido)


def read_masterwork_affix(
    frame: np.ndarray,
    roi: Rect,
    ocr,
    catalog: AffixCatalog | None = None,
    ui_scale: float = 1.0,
) -> MasterworkAffix:
    """Le' o afixo do Masterwork, que vem em uma ou duas linhas.

    Reaproveita a varredura por bandas do Tempering: mandar o bloco inteiro
    para o OCR de uma vez devolve vazio quando ha' duas linhas - medido nas
    telas de referencia dos dois fluxos.
    """
    texto = read_text_lines(frame, roi, ocr, ui_scale, gap=LINE_GAP)
    return parse_masterwork_line(texto, catalog)
