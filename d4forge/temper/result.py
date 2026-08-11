"""Leitura e interpretacao do afixo sorteado no Tempering.

Duas coisas moram aqui:

1. **Ler texto de altura desconhecida.** O resultado tem uma ou duas linhas,
   conforme o afixo. Medido nos prints: uma ROI unica cobrindo as duas linhas
   volta VAZIA do detector, em qualquer escala de render (1x le' so' a primeira,
   2x a 6x nao acham caixa nenhuma), enquanto cada linha isolada le' perfeito.
   Entao a regiao e' varrida em busca de bandas de tinta e cada banda vira uma
   leitura - o que tambem dispensa saber de antemao quantas linhas sao.

2. **Decidir se o roll foi bom.** Diferente do encantamento, aqui o jogo mostra
   o intervalo na propria tela:

       Lucky Hit: Up to a +8.4% Chance to Make Enemies Vulnerable
       for 2 Seconds [5.0 - 10.0]%[2]

   Um Greater Affix e' exatamente um valor acima do maximo do intervalo. Isso
   sai da linha lida, sem catalogo e sem cadastro manual de faixas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from ..geometry import Rect
from ..vision.preprocess import binarize, to_gray

# Uma banda precisa desta altura minima para valer como linha de texto; abaixo
# disso e' serifa solta ou borda do painel.
MIN_LINE_HEIGHT = 8
# Linhas separadas por menos que isto sao a mesma banda. O espaco entre as duas
# linhas do resultado mede ~9 px nos prints, entao 6 as mantem separadas.
LINE_GAP = 6
# Folga em volta de cada banda: o detector corta as pontas sem margem branca.
LINE_PAD = 4


def text_bands(mask: np.ndarray) -> list[tuple[int, int]]:
    """Faixas verticais contiguas com tinta, de cima para baixo."""
    linhas = mask.any(axis=1)
    bandas: list[tuple[int, int]] = []
    inicio, vazio = None, 0
    for y, tem in enumerate(linhas):
        if tem:
            if inicio is None:
                inicio = y
            vazio = 0
        elif inicio is not None:
            vazio += 1
            if vazio > LINE_GAP:
                if y - vazio - inicio >= MIN_LINE_HEIGHT:
                    bandas.append((inicio, y - vazio))
                inicio = None
    if inicio is not None and len(linhas) - inicio >= MIN_LINE_HEIGHT:
        bandas.append((inicio, len(linhas)))
    return bandas


# Uma linha de texto e' BAIXA; o brilho da animacao e' um bloco alto. Medido na
# regiao do resultado: as linhas do afixo dao 21 px de altura, contra 84 da
# animacao. A altura sozinha ja' separa os dois.
#
# A largura minima existe so' para descartar respingo solto, e por isso e'
# baixa. Ela ja' foi 150 px, e isso custou um Greater Affix: a linha
# "+10.0% Attack Speed" mede 201 px, mas um GA curto - "+3,125 Armor" - fica
# abaixo de 150, a tela era tomada por animacao, o motor clicava Skip (que ali
# e' o Close) e rolava por cima do GA sem nunca te-lo lido.
TEXT_MAX_HEIGHT = 34
TEXT_MIN_WIDTH = 40


def has_text_lines(frame: np.ndarray, roi: Rect) -> bool:
    """Ha' texto de verdade nesta regiao, e nao so' o brilho da animacao?

    Serve para separar a tela de resultado da animacao, e o vies e' deliberado:
    na duvida, RESULTADO.

    O raciocinio anterior era o inverso e estava errado. Eu argumentei que
    confundir resultado com animacao nao machucava, porque Skip e Close sao o
    mesmo retangulo e o clique faz a coisa certa de qualquer forma. O clique
    faz - mas a LEITURA nao acontece, que e' para o que a tela existe. O custo
    de cada troca, medido pelas consequencias:

        animacao lida como resultado -> le' lixo -> `readable` falha -> o ciclo
            para. Chato, reversivel, nao perde nada.
        resultado lido como animacao -> o afixo nunca e' lido, o ciclo fecha a
            tela e rola de novo. Se era um GA, ele foi embora, e o Tempering
            SUBSTITUI o afixo anterior: nao tem desfazer.

    Assimetria dessas nao se decide por elegancia; decide-se pelo lado que da'
    para consertar depois.
    """
    crop = roi.crop(frame)
    if crop.size == 0:
        return False
    mask = binarize(to_gray(crop), 120)
    for y0, y1 in text_bands(mask):
        cols = np.flatnonzero(mask[y0:y1].any(axis=0))
        if len(cols) == 0:
            continue
        largura = int(cols[-1] - cols[0]) + 1
        if (y1 - y0) <= TEXT_MAX_HEIGHT and largura >= TEXT_MIN_WIDTH:
            return True
    return False


def read_text_lines(frame: np.ndarray, roi: Rect, ocr, ui_scale: float = 1.0) -> str:
    """Le' uma regiao que pode ter 1, 2 ou 3 linhas, e junta o texto.

    Encontrar as linhas antes de ler, em vez de mandar o bloco inteiro para o
    OCR, e' o que faz o resultado de duas linhas ser lido - ver o cabecalho
    deste modulo.
    """
    crop = roi.crop(frame)
    if crop.size == 0:
        return ""
    mask = binarize(to_gray(crop), 120)

    partes: list[str] = []
    for y0, y1 in text_bands(mask):
        cols = np.flatnonzero(mask[y0:y1].any(axis=0))
        if len(cols) == 0:
            continue
        linha = Rect(
            roi.x + max(0, int(cols[0]) - LINE_PAD),
            roi.y + max(0, y0 - LINE_PAD),
            int(cols[-1] - cols[0]) + 1 + 2 * LINE_PAD,
            (y1 - y0) + 2 * LINE_PAD,
        ).clip_to(Rect(0, 0, frame.shape[1], frame.shape[0]))
        texto = ocr.read(linha.crop(frame), ui_scale=ui_scale).text.strip()
        if texto:
            partes.append(texto)
    return " ".join(partes)


# Um numero, com separador de milhar ou decimal: "8.4", "2,404", "1,500".
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# O valor sorteado: primeiro numero com sinal na frente ("+8.4%", "+1,738").


def _number(texto: str) -> float | None:
    """Converte "1,738" / "8.4" / "3,125" num float.

    O separador e' decidido pela contagem de digitos depois dele, nao pelo
    caractere: o OCR troca virgula por ponto o tempo todo, e "3,000" (tres mil)
    e "3.0" precisam sair certos dos dois jeitos. Mesma regra do encantamento.
    """
    limpo = texto.strip().replace(" ", "")
    if not limpo:
        return None
    match = re.fullmatch(r"(\d+)(?:[.,](\d+))?", limpo)
    if not match:
        return None
    inteiro, resto = match.group(1), match.group(2)
    if resto is None:
        return float(inteiro)
    # 3 digitos depois do separador = milhar; 1 ou 2 = decimal.
    if len(resto) == 3:
        return float(inteiro + resto)
    return float(f"{inteiro}.{resto}")


@dataclass(frozen=True, slots=True)
class TemperResult:
    """O que o Tempering entregou nesta tentativa.

    O sinal de Greater Affix e' ESTRUTURAL, nao numerico: num roll normal o jogo
    escreve o intervalo junto do valor ("+68.0% Damage while Berserking
    [40.0 - 80.0]%"); num GA ele mostra so' o valor. Entao GA e' a AUSENCIA do
    intervalo, e nao "valor maior que o maximo".

    Isso e' melhor do que comparar numeros - um digito lido errado nao inverte
    a decisao -, mas exige cuidado numa direcao: o Tempering SUBSTITUI o afixo
    que ja' esta' no item. Se um GA fosse lido como roll normal, o ciclo
    continuaria e rolaria por cima dele. Por isso `readable` e' exigente: sem
    uma leitura que se sustente, a decisao e' parar, nunca seguir rolando.
    """

    raw: str
    value: float | None = None
    low: float | None = None
    high: float | None = None
    # O jogo mostrou uma faixa que nao conseguimos montar. Nao sabemos os
    # limites, mas sabemos o que basta: nao e' Greater Affix.
    range_hidden: bool = False

    @property
    def has_range(self) -> bool:
        """O jogo mostrou o intervalo? A resposta e' o que define o GA."""
        return self.low is not None and self.high is not None

    @property
    def readable(self) -> bool:
        """Da' para decidir com esta leitura?

        Exige o valor sempre. Quando o intervalo aparece, ele tambem tem de
        estar coerente - intervalo invertido ou zerado significa leitura suja,
        e leitura suja aqui vale um item.
        """
        if self.value is None:
            return False
        # `high < low`, e nao `<=`. Um intervalo com as pontas iguais vem de um
        # digito comido ("[2.5 - 5.0]" lido como ". 5 - 5.0"), mas ele responde
        # a pergunta que importa: HAVIA um intervalo, logo nao e' Greater
        # Affix. Recusar a leitura inteira por causa disso parava a sessao sem
        # necessidade; so' o intervalo invertido e' incoerente de verdade.
        if self.has_range and self.high < self.low:
            return False
        return True

    @property
    def bracketed(self) -> bool:
        """A linha tem colchete, mesmo que nao tenhamos lido o intervalo dele.

        Colchete e' EVIDENCIA de que o jogo mostrou uma faixa. Quando ele
        aparece e mesmo assim nao conseguimos montar o intervalo, o que houve
        foi falha de leitura - nao ausencia de faixa.
        """
        return "[" in self.raw or "]" in self.raw

    @property
    def greater(self) -> bool:
        """Greater Affix: veio o valor e o jogo NAO mostrou faixa nenhuma."""
        return self.readable and not self.has_range and not self.range_hidden

    @property
    def fraction(self) -> float | None:
        """Onde o roll caiu dentro do intervalo, de 0 a 1. None se for GA."""
        if not self.readable or not self.has_range or self.high <= self.low:
            return None
        return (self.value - self.low) / (self.high - self.low)

    def corroborated(self, known: tuple[float, float] | None = None) -> "TemperResult":
        """Decide, para uma linha sem intervalo montado, se ela e' Greater Affix.

        Quem responde e' o COLCHETE, nao o numero.

        Colchete e' uma PRESENCA, e presenca nao depende de acertar digito: se
        ele esta' na linha, o jogo mostrou uma faixa, logo nao e' GA - mesmo
        que o intervalo tenha saido ilegivel. Se nao esta', e' assim que o jogo
        escreve um GA ("+10.0% Attack Speed", "7.5% Cooldown Reduction").

        Isso cobre os dois erros vistos no jogo, que puxavam para lados opostos:

            "[5 - 12]" lido como "[52]"        -> colchete presente, nao e' GA
            "+50.0% Damage with ... Weapons"   -> sem colchete, E' GA

        `known` nao entra mais nessa decisao, de proposito. Comparar o valor
        com o teto da receita so' sabe SUPRIMIR um GA, e para isso precisa do
        teto certo - que e' justamente o que o OCR erra: "[20.0 - 40.0]%" saia
        como "[20.0 - 401%" (o "]" virando "1") rodada apos rodada, ate' virar
        maioria. Com o teto em 401, um "+50.0%" legitimo foi julgado dentro da
        faixa e o ciclo ia rolar por cima dele - o erro que destroi o item. O
        parametro fica na assinatura porque a faixa conhecida continua util
        para o criterio de fracao.
        """
        if self.has_range or self.value is None:
            return self
        if self.bracketed:
            return TemperResult(raw=self.raw, value=self.value, range_hidden=True)
        return self

    def describe(self) -> str:
        if not self.readable:
            return self.raw or "?"
        if self.greater:
            return f"{self.value:g}  GA"
        if not self.has_range:
            # Havia faixa na tela, mas ela nao foi lida. Dizer isso e' melhor
            # do que mostrar um intervalo inventado.
            return f"{self.value:g}  [?]"
        return f"{self.value:g}  [{self.low:g} - {self.high:g}]"


def _is_separator(gap: str) -> bool:
    """O que ha' entre dois numeros os torna um intervalo?

    Nao exigimos hifen nem colchete. Exigir custou caro: com "[1,500 - 2,500]"
    na tela, bastava o OCR ler travessao no lugar do hifen, parentese no lugar
    do colchete, ou perder um colchete, para o intervalo "sumir" - e sumir e'
    exatamente o que este codigo entende por Greater Affix. Um roll comum de
    2.404 virava GA e encerrava a sessao.

    A pontuacao e' o que o reconhecedor menos acerta; os digitos sao o que ele
    mais acerta. Entao o criterio olha o TAMANHO e a NATUREZA do intervalo
    entre os numeros, nao qual sinal ele escolheu desenhar:

        curto, sem letra e sem digito -> separador de intervalo
        qualquer outra coisa          -> sao dois numeros da mesma frase
    """
    miolo = gap.strip()
    if not miolo or len(miolo) > 3:
        return False
    # So' ponto ou virgula significa que partimos um numero ao meio: o "3,125"
    # de um GA nao pode virar "intervalo de 3 a 125".
    return not any(c.isalnum() for c in miolo) and any(c not in ".," for c in miolo)


def _find_range(texto: str):
    """Ultimo par de numeros vizinhos que se sustenta como intervalo.

    "Ultimo" porque o intervalo fica no fim da linha. "Que se sustenta" porque
    exigimos low < high, o que descarta o par (10.0, 2) formado com o sufixo
    "%[2]" da familia Lucky Hit.
    """
    numeros = [
        (m.start(), m.end(), _number(m.group()))
        for m in _NUMBER.finditer(texto)
    ]
    melhor = None
    for (ini_a, fim_a, a), (ini_b, _, b) in zip(numeros, numeros[1:]):
        # `a <= b`, e nao `a < b`. Um intervalo de verdade sempre tem low
        # menor que high, entao `low == high` so' aparece quando o OCR comeu um
        # digito - e aceitar mesmo assim e' o lado seguro, porque significa
        # "havia um intervalo aqui", que e' o oposto de Greater Affix.
        #
        # Foi por um pixel desses que uma sessao parou achando que ganhou:
        # "[2.5 - 5.0]" saiu como ". 5 - 5.0", o par virou (5, 5.0), `a < b`
        # reprovou, o intervalo "sumiu" e um roll comum virou GA.
        if a is None or b is None or not (a <= b):
            continue
        if _is_separator(texto[fim_a:ini_b]):
            # Onde o intervalo COMECA, nao onde o primeiro numero dele termina:
            # e' o corte usado para procurar o valor, e incluir o proprio
            # limite inferior faria "Something [1,500 - 2,500]" render 1.500
            # como se fosse o roll.
            melhor = (a, b, ini_a)
    return melhor


def parse_temper_result(texto: str) -> TemperResult:
    """Extrai valor e intervalo da linha do TEMPER COMPLETE."""
    intervalo = _find_range(texto)
    low = high = None
    corte = len(texto)
    if intervalo:
        low, high, corte = intervalo

    # O valor e' o PRIMEIRO numero da frase, e o trecho olhado termina onde o
    # intervalo comeca - senao pegariamos o limite inferior dele.
    #
    # Nao exigimos sinal na frente. Exigir custou uma sessao: "4.1% Cooldown
    # Reduction [3.0 - 6.0]%" nao tem "+", assim como "x25% Critical Strike
    # Damage Multiplier". O valor ficava None, a leitura era dada como
    # duvidosa e o ciclo parava - com o texto lido corretamente na tela.
    primeiro = _NUMBER.search(texto[:corte])
    value = _number(primeiro.group()) if primeiro else None

    return TemperResult(raw=texto.strip(), value=value, low=low, high=high)
