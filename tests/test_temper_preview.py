"""Leitura do item pelo tooltip — o que já funciona e o que ainda não.

Este módulo NÃO está ligado ao ciclo. Os testes existem para registrar
exatamente onde ele para de funcionar, para quem retomar não precisar
redescobrir; e para falhar no dia em que a leitura melhorar, avisando que dá
para ligar.
"""

import pytest

from d4forge.geometry import Rect
from d4forge.temper.preview import read_preview, tempered_affix

TOOLTIP = Rect(676, 60, 400, 820)


def _linhas(shots, tela, ocr):
    return read_preview(shots[tela], TOOLTIP, ocr)


def test_acha_o_afixo_temperado_pela_coluna(temper_shots, ocr):
    """O identificador que sobrou depois de nome, estrela e ícone falharem.

    O glifo do afixo temperado é mais largo que o losango dos comuns, então a
    linha dele começa mais à esquerda — x=35 contra x=58. Isso vale
    independente de qual glifo a categoria usa."""
    linhas = _linhas(temper_shots, "preview_movement_ga", ocr)

    temperadas = [linha for linha in linhas if linha.tempered]
    assert temperadas, "nenhuma linha na coluna do glifo largo"
    assert "Movement Speed" in temperadas[-1].text


def test_le_o_ga_de_uma_linha_so(temper_shots, ocr):
    """`+31% Movement Speed` cabe numa linha, e aí a leitura fecha: estrela,
    sem intervalo, GA. Note que o item TAMBÉM tem um `+24% Movement Speed`
    comum — o mesmo nome duas vezes, que é o caso que derruba casar por nome."""
    r = tempered_affix(_linhas(temper_shots, "preview_movement_ga", ocr))

    assert r is not None
    assert r.value == 31
    assert r.greater


def test_cabecalho_do_item_nao_e_confundido_com_afixo(temper_shots, ocr):
    """"1,899 Damage Per Second" também começa na coluna do glifo largo. Pegar
    a ÚLTIMA linha daquela coluna descarta o cabeçalho sem precisar saber o que
    ele é."""
    linhas = _linhas(temper_shots, "preview_lucky_hit", ocr)
    temperadas = [linha for linha in linhas if linha.tempered]

    # O nome do item e outras linhas de cabeçalho caem na mesma coluna.
    assert len(temperadas) > 1, "há cabeçalho junto na coluna"
    assert any("Damage Per Second" in linha.text for linha in temperadas[:-1])
    assert "Lucky Hit" in temperadas[-1].text


@pytest.mark.xfail(
    reason="afixo que quebra em várias linhas é lido só na primeira, e o "
           "intervalo fica na continuação — vira falso GA. É o que impede "
           "ligar o preview no ciclo.",
    strict=True,
)
def test_afixo_que_quebra_em_varias_linhas(temper_shots, ocr):
    """O bloqueio, registrado como teste.

    O `[2.5 - 5.0]` do Lucky Hit está na linha de baixo. Sem ele, o afixo é
    julgado Greater Affix sem ser — e o erro caro é justamente esse: quem para
    achando que ganhou perde tempo, quem continua rola por cima do bom.

    Quando a leitura passar a juntar as continuações, este teste passa e o
    `strict=True` avisa que dá para ligar o preview."""
    r = tempered_affix(_linhas(temper_shots, "preview_lucky_hit", ocr))

    assert r is not None
    assert (r.low, r.high) == (2.5, 5.0)
    assert not r.greater
