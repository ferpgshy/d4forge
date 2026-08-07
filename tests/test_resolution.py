"""Portabilidade entre resoluções.

O perfil é medido em 1920x1080 e convertido em runtime. Antes, a conversão
esticava x por `w/1920` e y por `h/1080` de forma independente: correto por
acidente em 16:9, onde os dois fatores são iguais, e errado em qualquer outra
proporção. Hoje a escala é única (vem da altura) e cada ROI declara se fica
colada na esquerda ou centrada.

Os testes de ponta a ponta usam as telas de referência reescaladas. Isso prova
que a geometria e o OCR sobrevivem à mudança de tamanho; não prova nada sobre o
layout real do jogo numa ultrawide, que ninguém aqui mediu ainda.
"""

import cv2
import pytest

from d4forge.affixes import parse_affix
from d4forge.geometry import Rect
from d4forge.profile import (
    ANCHOR_CENTER,
    ANCHOR_LEFT,
    DEFAULT_PROFILE,
    REFERENCE_HEIGHT,
    REFERENCE_WIDTH,
)
from d4forge.vision.states import ScreenState, detect_state

# As quatro que o usuário pediu.
DEZESSEIS_NOVE = [
    ("Full HD", 1920, 1080),
    ("QHD", 2560, 1440),
    ("4K", 3840, 2160),
]
ULTRAWIDE = ("UltraWide QHD", 3440, 1440)


def _perfil(w, h):
    return DEFAULT_PROFILE.scaled(Rect(0, 0, w, h))


# ------------------------------------------------------- modelo de escala

@pytest.mark.parametrize("nome,w,h", DEZESSEIS_NOVE)
def test_em_16_9_a_ancora_nao_muda_nada(nome, w, h):
    """A garantia que torna a mudança segura: em 16:9 o resultado é idêntico ao
    da conta antiga (`x * w/1920`), tanto para ROI colada à esquerda quanto para
    ROI centrada. Quem já rodava não vê diferença nenhuma."""
    prof = _perfil(w, h)
    sx = w / REFERENCE_WIDTH

    for ref in (DEFAULT_PROFILE.enchant_button, DEFAULT_PROFILE.confirm_accept):
        for anchor in (ANCHOR_LEFT, ANCHOR_CENTER):
            assert prof.rect(ref, anchor).x == round(ref.x * sx)


@pytest.mark.parametrize("nome,w,h", DEZESSEIS_NOVE)
def test_escala_uniforme_preserva_proporcao(nome, w, h):
    """Um quadrado na referência continua quadrado na tela real. Com os dois
    fatores independentes isso valia só em 16:9."""
    prof = _perfil(w, h)
    quadrado = prof.rect(Rect(100, 100, 40, 40))
    assert quadrado.w == quadrado.h


def test_ultrawide_nao_deforma_as_rois():
    """3440x1440 é 21:9. Esticar x por 3440/1920 = 1,79 e y por 1440/1080 = 1,33
    deformaria toda ROI — um orbe de 30x28 viraria 54x37 e o clique cairia fora.
    """
    _, w, h = ULTRAWIDE
    prof = _perfil(w, h)
    escala = h / REFERENCE_HEIGHT

    orbe_ref = DEFAULT_PROFILE.replace_orbs[0]
    orbe = prof.rect(orbe_ref)
    assert orbe.w == round(orbe_ref.w * escala)
    assert orbe.h == round(orbe_ref.h * escala)
    # proporção preservada, que é o que a conta antiga quebrava
    assert orbe.w / orbe.h == pytest.approx(orbe_ref.w / orbe_ref.h, abs=0.05)


def test_ultrawide_centraliza_o_dialogo_de_confirmacao():
    """Accept/Cancel estão centrados na tela (medido: meio em x=959 de 1920).
    Numa tela mais larga eles acompanham o centro, não a borda esquerda."""
    _, w, h = ULTRAWIDE
    prof = _perfil(w, h)

    accept = prof.rect(DEFAULT_PROFILE.confirm_accept, ANCHOR_CENTER)
    cancel = prof.rect(DEFAULT_PROFILE.confirm_cancel, ANCHOR_CENTER)
    meio = (accept.left + cancel.right) / 2
    assert meio == pytest.approx(w / 2, abs=2)


def test_ultrawide_mantem_o_painel_colado_na_esquerda():
    """O painel do Occultist é a âncora oposta: ele não deve escorregar para o
    meio quando a tela alarga."""
    _, w, h = ULTRAWIDE
    prof = _perfil(w, h)
    escala = h / REFERENCE_HEIGHT

    botao = prof.rect(DEFAULT_PROFILE.enchant_button, ANCHOR_LEFT)
    assert botao.x == round(DEFAULT_PROFILE.enchant_button.x * escala)


def test_widescreen_so_marca_fora_de_16_9():
    assert not _perfil(1920, 1080).widescreen
    assert not _perfil(3840, 2160).widescreen
    assert _perfil(3440, 1440).widescreen


# ------------------------------------------------ ponta a ponta reescalado

@pytest.fixture(scope="module")
def escaladas(shots):
    """Telas de referência redimensionadas para cada resolução 16:9."""
    saida = {}
    for nome, w, h in DEZESSEIS_NOVE:
        saida[(w, h)] = {
            estado: cv2.resize(img, (w, h), interpolation=cv2.INTER_LANCZOS4)
            for estado, img in shots.items()
        }
    return saida


@pytest.mark.parametrize("nome,w,h", DEZESSEIS_NOVE)
def test_detecta_todos_os_estados_em_qualquer_16_9(nome, w, h, escaladas):
    prof = _perfil(w, h)
    for esperado, img in escaladas[(w, h)].items():
        assert detect_state(img, prof).state.value == esperado, f"{nome}: {esperado}"


@pytest.mark.parametrize("nome,w,h", DEZESSEIS_NOVE)
def test_le_os_afixos_em_qualquer_16_9(nome, w, h, escaladas, ocr, catalog):
    """O que o usuário sente: os mesmos afixos, lidos igual, em 1080p ou 4K."""
    prof = _perfil(w, h)
    img = escaladas[(w, h)]["replace"]

    lidos = []
    for roi in prof.replace_options:
        res = ocr.read(roi.crop(img), ui_scale=prof.scale)
        lidos.append(parse_affix(res.text, catalog))

    assert [p.name for p in lidos] == ["Resource Generation", "Impairment Reduction"]
    assert all(p.confident for p in lidos), [p.raw for p in lidos]


@pytest.mark.parametrize("nome,w,h", DEZESSEIS_NOVE)
def test_afixo_travado_e_lido_em_qualquer_16_9(nome, w, h, escaladas, ocr, catalog):
    prof = _perfil(w, h)
    img = escaladas[(w, h)]["enchant_locked"]
    res = ocr.read(prof.locked_affix.crop(img), ui_scale=prof.scale)
    parsed = parse_affix(res.text, catalog)

    assert parsed.name == "Shadow Resistance"
    assert parsed.value == 3000


@pytest.mark.parametrize("nome,w,h", DEZESSEIS_NOVE)
def test_le_o_orbe_marcado_em_qualquer_16_9(nome, w, h, escaladas):
    """A leitura mais cara de errar: é ela que confirma qual opção foi marcada
    antes de apertar Replace Affix, e trocar o afixo errado não tem desfazer.
    Na tela de referência o No Change (índice 2) está marcado."""
    from d4forge.vision.states import selected_orb

    prof = _perfil(w, h)
    assert selected_orb(escaladas[(w, h)]["replace"], prof.replace_orbs) == 2


@pytest.mark.parametrize("nome,w,h", DEZESSEIS_NOVE[1:])
def test_orbe_lido_igual_ao_de_1080p(nome, w, h, escaladas):
    """Qual orbe está aceso não pode depender da resolução. Aqui a referência é
    o que 1080p lê — a única leitura conferida contra o jogo de verdade — e não
    um valor escrito no teste."""
    from d4forge.vision.states import selected_orb

    base = _perfil(1920, 1080)
    prof = _perfil(w, h)
    for tela, orbes in (("replace", "replace_orbs"), ("enchant_select", "affix_orbs")):
        esperado = selected_orb(escaladas[(1920, 1080)][tela], getattr(base, orbes))
        assert selected_orb(escaladas[(w, h)][tela], getattr(prof, orbes)) == esperado, tela


def test_densidade_de_tinta_e_medida_na_escala_de_referencia(escaladas, ocr, catalog):
    """Regressão de desempenho: `MAX_INK_PER_CHAR` conta pixels da tela de
    referência. Sem converter, a mesma frase em 4K tem o dobro da tinta para o
    mesmo número de letras, `density_ok` reprova SEMPRE e a escada percorre os
    três degraus em toda linha — medido, 3,00 degraus por linha contra 2,05.
    """
    from d4forge.vision.ocr import OcrEngine

    verify = lambda texto: parse_affix(texto, catalog).confident  # noqa: E731

    def degraus_por_linha(w, h, converter):
        motor = OcrEngine(data_dir=ocr.data_dir / f"esc{w}{converter}")
        prof = _perfil(w, h)
        img = escaladas[(w, h)]["replace"]
        for roi in prof.replace_options:
            motor.read(roi.crop(img), verify, ui_scale=prof.scale if converter else 1.0)
        return 1 + motor.stats.retries / max(1, motor.stats.backend_calls)

    assert degraus_por_linha(3840, 2160, True) < degraus_por_linha(3840, 2160, False)
    # Em 1080p a conversão é identidade: não pode mexer em nada.
    assert degraus_por_linha(1920, 1080, True) == degraus_por_linha(1920, 1080, False)
