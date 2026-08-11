"""Masterworking: detecção das três telas e leitura do afixo sorteado.

Tudo aqui roda contra as capturas reais do jogo, higienizadas — não contra
imagens sintéticas. Um limiar só vale o que a medição dele vale.
"""

import pytest

from d4forge.geometry import Rect
from d4forge.masterwork.profile import DEFAULT_MW_PROFILE
from d4forge.masterwork.result import MasterworkAffix, read_masterwork_affix
from d4forge.masterwork.states import (
    BUTTON_ON,
    MODAL_ON,
    MasterworkState,
    detect_masterwork_state,
    ink,
)


def _perfil(img):
    return DEFAULT_MW_PROFILE.scaled(Rect(0, 0, img.shape[1], img.shape[0]))


# ------------------------------------------------------------- estados

@pytest.mark.parametrize(
    "tela,esperado",
    [
        ("mw_idle", MasterworkState.STEP),
        ("mw_affix", MasterworkState.AFFIX),
        ("mw_animation", MasterworkState.ANIMATION),
    ],
)
def test_reconhece_as_tres_telas(mw_shots, tela, esperado):
    img = mw_shots[tela]
    assert detect_masterwork_state(img, _perfil(img)).state is esperado


def test_nenhum_estado_depende_de_ocr(mw_shots):
    """Medir tinta custa ~0,1 ms e não erra dígito; ler custa ~70 ms e erra.

    A assinatura nem aceita um `ocr` — este teste existe para que passar a
    aceitar seja uma decisão consciente, e não um deslize.
    """
    import inspect

    assert "ocr" not in inspect.signature(detect_masterwork_state).parameters


def test_next_rank_e_o_que_separa_passo_de_masterwork(mw_shots):
    """O sinal é a PRESENÇA da linha "NEXT RANK", não a ausência dela.

    Foi a lição cara do Tempering: lá o Greater Affix era o jogo NÃO mostrar o
    intervalo, e cada dígito comido pelo OCR virava um falso positivo. Aqui a
    linha existe ou não existe, e a medida separa os dois lados por completo.
    """
    passo = ink(mw_shots["mw_idle"], _perfil(mw_shots["mw_idle"]).next_rank)
    mw = ink(mw_shots["mw_affix"], _perfil(mw_shots["mw_affix"]).next_rank)

    assert passo >= BUTTON_ON, passo
    assert mw < BUTTON_ON, mw
    # Não é "passou raspando": a separação é de duas ordens de grandeza.
    assert passo > 0.05 and mw < 0.005, (passo, mw)


def test_cabecalho_separa_painel_de_animacao(mw_shots):
    aceso = [
        ink(mw_shots[t], _perfil(mw_shots[t]).blacksmith_header)
        for t in ("mw_idle", "mw_affix")
    ]
    apagado = ink(
        mw_shots["mw_animation"], _perfil(mw_shots["mw_animation"]).blacksmith_header
    )
    assert min(aceso) > MODAL_ON < 0.3
    assert apagado < 0.005, apagado


def test_upgrade_ativo_nas_duas_telas_de_painel(mw_shots):
    """Nos dois prints o botão está clicável — é o que permite continuar."""
    for tela in ("mw_idle", "mw_affix"):
        img = mw_shots[tela]
        assert detect_masterwork_state(img, _perfil(img)).can_upgrade, tela


def test_animacao_nao_oferece_upgrade(mw_shots):
    img = mw_shots["mw_animation"]
    assert not detect_masterwork_state(img, _perfil(img)).can_upgrade


# -------------------------------------------------------------- leitura

def test_le_o_afixo_do_masterwork_nas_duas_linhas(mw_shots, ocr, catalog):
    """"+80.0% Damage with Two-Handed Slashing Weapons" quebra em duas linhas."""
    img = mw_shots["mw_affix"]
    lido = read_masterwork_affix(img, _perfil(img).affix_text, ocr, catalog)

    assert lido.readable, lido.raw
    assert lido.name == "Damage with Two-Handed Slashing Weapons", lido.raw
    assert lido.parsed.value == pytest.approx(80.0)
    # O texto da dica de reroll fica logo abaixo e NÃO pode entrar na leitura.
    assert "Reroll" not in lido.raw


def test_o_alvo_certo_casa_e_o_parecido_nao(mw_shots, ocr, catalog):
    """A barra tem que separar o afixo certo de um vizinho de nome parecido.

    "Damage with Slashing Weapons" é outro afixo — falta o "Two-Handed" —, e
    dá 0.847 contra o lido. Passar essa leitura por boa faria a sessão parar
    num Masterwork que não é o pedido.
    """
    img = mw_shots["mw_affix"]
    lido = read_masterwork_affix(img, _perfil(img).affix_text, ocr, catalog)

    assert lido.matches("Damage with Two-Handed Slashing Weapons")
    # Hífen não pode decidir nada: o OCR troca hífen por espaço à vontade.
    assert lido.matches("Damage with Two Handed Slashing Weapons")
    assert not lido.matches("Damage with Slashing Weapons")


@pytest.mark.parametrize(
    "prefixo",
    [
        ".",        # o ponto da borda, visto em "+80.0% Damage with Two-Handed"
        "` ",       # o glifo que derrubou "+242 Strength" no jogo
        "⌐ ",
        "  ",
        "·",
        ":",
        "|",
        "~ ",
        "l ",       # sujeira lida como LETRA: o corte por caractere não pega
        "J",
    ],
)
def test_sujeira_na_frente_nao_derruba_a_leitura(prefixo, catalog):
    """A borda da caixa pode virar qualquer desenho no OCR.

    Enumerar os desenhos já falhou duas vezes com o mesmo sintoma: o ponto
    entrou na lista, e dias depois outro glifo apareceu na frente de
    "+242 Strength" e passou reto — o valor saía None, a linha inteira virava
    nome, e o ciclo parava dizendo que não conseguiu ler um afixo que estava
    escrito na tela.
    """
    from d4forge.masterwork.result import parse_masterwork_line

    linha = prefixo + "+242 Strength"
    lido = parse_masterwork_line(linha, catalog)

    assert lido.readable, (linha, lido.raw)
    assert lido.parsed.value == pytest.approx(242), (linha, lido.raw)
    assert lido.name == "Strength", (linha, lido.raw)
    # E o que importa no fim: a sessão consegue reconhecer o alvo.
    assert lido.matches("Strength"), (linha, lido.raw)


def test_leitura_com_sujeira_casa_com_o_alvo(mw_shots, ocr, catalog):
    """O caminho inteiro, e não só as peças: sujeira na frente, leitura, alvo."""
    import numpy as np

    from d4forge.masterwork.result import read_masterwork_affix

    img = mw_shots["mw_affix"]
    lido = read_masterwork_affix(img, _perfil(img).affix_text, ocr, catalog)
    assert lido.matches("Damage with Two-Handed Slashing Weapons")


def test_lixo_de_borda_nao_engole_a_linha(mw_shots, ocr, catalog):
    """O OCR pega um "." da borda da caixa e cola na frente do "+80.0%".

    Com ele a gramática não casa, o valor sai None e a linha INTEIRA vira
    nome — o afixo deixa de casar com qualquer alvo, e a sessão nunca para.
    """
    img = mw_shots["mw_affix"]
    lido = read_masterwork_affix(img, _perfil(img).affix_text, ocr, catalog)
    assert not lido.raw.startswith(".")
    assert lido.parsed.value is not None


def test_a_dica_de_reroll_fica_fora_da_roi(mw_shots, ocr):
    """Texto fixo dentro da ROI entraria em toda leitura e envenenaria o nome."""
    img = mw_shots["mw_affix"]
    prof = _perfil(img)
    assert prof.affix_text.bottom <= prof.reroll_hint.top


def test_leitura_ilegivel_nao_casa_com_nada():
    """Uma leitura ruim virando "achei" é o erro que encerra a sessão cedo e
    devolve o item como pronto sem ele estar."""
    vazio = MasterworkAffix(raw="")
    assert not vazio.readable
    assert not vazio.matches("Strength")
    assert vazio.similarity("Strength") == 0.0


def test_alvo_vazio_nunca_casa(mw_shots, ocr, catalog):
    img = mw_shots["mw_affix"]
    lido = read_masterwork_affix(img, _perfil(img).affix_text, ocr, catalog)
    assert not lido.matches("")
    assert not lido.matches("   ")


def test_afixo_errado_nao_casa_com_o_alvo(mw_shots, ocr, catalog):
    """O print tem Damage with Two-Handed Slashing Weapons; o alvo é Strength."""
    img = mw_shots["mw_affix"]
    lido = read_masterwork_affix(img, _perfil(img).affix_text, ocr, catalog)
    assert lido.readable          # a leitura é boa: o que não bate é o alvo
    assert not lido.matches("Strength")


def test_a_tela_de_passo_tambem_devolve_um_afixo_legivel(mw_shots, ocr, catalog):
    """Armadilha registrada: na tela de NEXT RANK aquela mesma região tem
    "173 All Resist", e isso é lido como um afixo perfeitamente válido.

    Quem impede o ciclo de agir sobre ele NÃO é a leitura — é o estado. O afixo
    só é lido quando "NEXT RANK" sumiu. Se algum dia alguém ler essa região sem
    passar pelo estado, um alvo "All Resist" encerraria a sessão na primeira
    tela, sem nenhum Masterwork ter acontecido.
    """
    img = mw_shots["mw_idle"]
    lido = read_masterwork_affix(img, _perfil(img).affix_text, ocr, catalog)

    assert lido.readable and lido.matches("All Resist")
    # E é por isto que ela nunca é lida ali:
    assert detect_masterwork_state(img, _perfil(img)).state is MasterworkState.STEP
    assert not detect_masterwork_state(img, _perfil(img)).showing_affix
