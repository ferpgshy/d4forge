"""Em qual tela do Tempering o jogo esta', e quais botoes estao ativos.

O fluxo do Tempering se resolve com dois sinais booleanos lidos da tela, sem
depender de OCR de numero:

    Temper Item ativo                    -> da' para temperar
    Temper Item cinza + circular ativo   -> rerolls zeraram; recarregar
    Temper Item cinza + circular cinza   -> acabaram os Pergaminhos; parar

Ler "o botao esta' aceso" custa ~0,1 ms e nao erra; ler "Temper Rerolls
Remaining: 3" custa 70 ms e pode errar o digito. A mesma escolha feita nos
orbes do encantamento.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from ..vision.preprocess import binarize, to_gray

# Fracao de pixels acesos a partir da qual consideramos um botao habilitado.
#
# Medido nas telas de referencia: o "Temper Item" habilitado mede 0.080 e o
# desabilitado mede 0.000 - o texto apagado nem chega ao limiar de brilho. Com
# uma separacao dessas, 0.02 fica longe dos dois lados.
BUTTON_ON = 0.02

# Acima disto o modal de tempering (animacao ou resultado) esta' aberto por
# cima do painel. Medido: o cabecalho ornamentado do modal mede 0.15+ e o
# painel normal, no mesmo lugar, fica proximo de zero.
MODAL_ON = 0.05



class TemperState(Enum):
    UNKNOWN = "unknown"
    # Aba Tempering aberta, sem modal. `can_temper` diz se da' para clicar.
    IDLE = "temper_idle"
    # Lista TEMPERING RECIPES aberta.
    RECIPES = "temper_recipes"
    # Animacao rodando, com o botao Skip.
    ANIMATION = "temper_animation"
    # TEMPER COMPLETE, com o afixo sorteado e o botao Close.
    RESULT = "temper_result"


def ink(frame: np.ndarray, roi, threshold: int = 120) -> float:
    """Fracao de pixels acesos numa regiao."""
    crop = roi.crop(frame)
    if crop.size == 0:
        return 0.0
    return float(binarize(to_gray(crop), threshold).mean())


def button_active(frame: np.ndarray, roi) -> bool:
    """O botao esta' habilitado (aceso) e nao cinza?"""
    return ink(frame, roi) >= BUTTON_ON


@dataclass(frozen=True, slots=True)
class TemperReading:
    """A tela atual, e o que da' para fazer nela.

    Quem manda e' `can_temper`: o botao aceso e' o proprio jogo dizendo que da'
    para agir, e nenhuma outra pergunta vem antes dela. Os outros dois so'
    entram quando o botao esta' apagado, para dizer POR QUE:

        Temper Item  circular  contador   situacao
        -----------  --------  ---------  --------------------------------
        ACESO        -         -          temperar
        cinza        ACESO     -          rerolls zerados -> recarregar
        cinza        cinza     nao        receita nao escolhida -> parar
        cinza        cinza     sim        Pergaminhos acabaram -> parar

    O contador nao serve para saber se ha' receita: num slot LIVRE o jogo
    escreve "Adds your selected affix" e nao mostra contador nenhum, com o
    botao aceso - ali se ADICIONA um afixo em vez de rerrolar. Ele so' separa os
    dois becos da ultima linha.
    """

    state: TemperState
    can_temper: bool = False     # botao Temper Item habilitado
    can_recharge: bool = False   # botao circular habilitado
    has_rerolls: bool = False    # a linha "Temper Rerolls Remaining" existe
    marks: dict = field(default_factory=dict)


# O titulo que so' existe na tela de resultado. Comparar TEXTO nao tem limiar
# para calibrar, e foi um limiar mal escolhido que deixou passar um GA.
COMPLETE_TEXT = "COMPLETE"


def _reads_complete(frame: np.ndarray, prof, ocr) -> bool:
    """O OCR ve' "TEMPER COMPLETE" no titulo do modal?

    Medido nas telas de referencia: as tres de resultado devolvem exatamente
    "TEMPER COMPLETE" e a animacao devolve string vazia - inclusive com o
    brilho multiplicado por 4, que cobre a animacao inteira pulsando.

    Custa 0-1 ms quando a leitura cai no cache, que e' o caso comum: o titulo e'
    sempre o mesmo desenho.
    """
    if ocr is None:
        return False
    try:
        return COMPLETE_TEXT in ocr.read(prof.complete_title.crop(frame)).text.upper()
    except Exception:  # noqa: BLE001 - leitura nunca pode derrubar o ciclo
        return False


def detect_temper_state(frame: np.ndarray, prof, ocr=None) -> TemperReading:
    """Classifica a tela do Ferreiro a partir de um quadro.

    A ordem das perguntas nao e' arbitraria; cada uma vem de uma medida:

    1. O cabecalho BLACKSMITH so' fica aceso quando NENHUM modal esta' por
       cima (medido: 0.352 no painel normal contra 0.000 nas outras tres).
       E' o teste mais limpo que existe aqui, entao vem primeiro.
    2. O cabecalho ornamentado do modal separa animacao e resultado do resto
       (0.536 contra no maximo 0.041).
    3. Sobrou a lista de receitas.
    """
    marks = {
        "blacksmith": ink(frame, prof.blacksmith_header),
        "modal": ink(frame, prof.modal_header),
        "recipes": ink(frame, prof.recipes_title),
        "temper_btn": ink(frame, prof.temper_button),
        "recharge_btn": ink(frame, prof.recharge_button),
        "rerolls_line": ink(frame, prof.rerolls_remaining),
    }

    if marks["blacksmith"] >= MODAL_ON:
        return TemperReading(
            TemperState.IDLE,
            can_temper=marks["temper_btn"] >= BUTTON_ON,
            can_recharge=marks["recharge_btn"] >= BUTTON_ON,
            has_rerolls=marks["rerolls_line"] >= BUTTON_ON,
            marks=marks,
        )

    if marks["modal"] >= MODAL_ON:
        # Animacao e resultado compartilham o cabecalho E o retangulo do botao,
        # entao nenhum dos dois serve de discriminador.
        #
        # A autoridade aqui e' LER o titulo, nao medir tinta: "TEMPER COMPLETE"
        # e' texto fixo, e comparar texto nao tem limiar para calibrar. Foi um
        # limiar mal escolhido - largura minima de linha - que classificou um
        # resultado como animacao e deixou o ciclo rolar por cima de um GA.
        #
        # A forma so' entra quando NAO ha' OCR (testes, e como rede de
        # seguranca). Com o leitor disponivel ele decide sozinho: somar a forma
        # por OU deixava o detector ansioso demais e nao acrescentava nada que
        # a leitura do titulo ja' nao resolvesse.
        from .result import has_text_lines

        if ocr is not None:
            marks["complete_ocr"] = float(_reads_complete(frame, prof, ocr))
            e_resultado = marks["complete_ocr"] > 0
        else:
            marks["result_text"] = float(has_text_lines(frame, prof.result_text))
            e_resultado = marks["result_text"] > 0

        estado = TemperState.RESULT if e_resultado else TemperState.ANIMATION
        return TemperReading(estado, marks=marks)

    if marks["recipes"] >= MODAL_ON:
        return TemperReading(TemperState.RECIPES, marks=marks)

    return TemperReading(TemperState.UNKNOWN, marks=marks)
