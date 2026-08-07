"""Deteccao de estado e OCR, verificados contra os prints reais do jogo."""

import pytest

from d4forge.affixes import parse_affix
from d4forge.vision.states import ScreenState, detect_state, selected_orb

# Texto exato que aparece em cada print.
EXPECTED_TEXT = {
    "enchant_select": [
        "+2 to Imbuement Skills",
        "+151 Dexterity",
        "+25 Maximum Resource",
        "+3,000 Shadow Resistance",
    ],
    "replace": [
        "15.0% Resource Generation",
        "10.0% Impairment Reduction",
    ],
}


@pytest.mark.parametrize("state_name", list(ScreenState.__members__))
def test_enum_tem_valor(state_name):
    assert ScreenState[state_name].value


@pytest.mark.parametrize(
    "state_name",
    ["enchant_select", "confirm", "replace", "result", "enchant_locked"],
)
def test_classifica_tela_certa(shots, profiles, state_name):
    reading = detect_state(shots[state_name], profiles[state_name])
    assert reading.state is ScreenState(state_name), reading.describe()


def test_orbe_marcado_na_tela_de_selecao(shots, profiles):
    """No print de referencia o primeiro afixo esta' marcado."""
    idx = selected_orb(shots["enchant_select"], profiles["enchant_select"].affix_orbs)
    assert idx == 0


def test_no_change_vem_marcado_por_padrao(shots, profiles):
    """A tela Replace Affix abre com No Change (indice 2) selecionado - e' isso
    que faz "nao escolher nada" ser seguro."""
    idx = selected_orb(shots["replace"], profiles["replace"].replace_orbs)
    assert idx == 2


def test_le_os_afixos_da_tela_de_selecao(shots, profiles, ocr, catalog):
    img, prof = shots["enchant_select"], profiles["enchant_select"]
    got = [ocr.read(roi.crop(img)).text for roi in prof.affix_rows]
    assert got == EXPECTED_TEXT["enchant_select"]


def test_le_as_opcoes_da_tela_replace(shots, profiles, ocr, catalog):
    img, prof = shots["replace"], profiles["replace"]
    got = [ocr.read(roi.crop(img)).text for roi in prof.replace_options]
    assert got == EXPECTED_TEXT["replace"]

    for text in got:
        assert parse_affix(text, catalog).confident


def test_le_o_afixo_atual_nas_duas_telas(shots, profiles, ocr):
    assert ocr.read(profiles["replace"].replace_current.crop(shots["replace"])).text == (
        "+3,000 Shadow Resistance"
    )
    assert ocr.read(
        profiles["enchant_locked"].locked_affix.crop(shots["enchant_locked"])
    ).text == "+3,000 Shadow Resistance"


@pytest.mark.parametrize(
    "state_name",
    ["enchant_select", "confirm", "replace", "result", "enchant_locked"],
)
def test_ponto_de_parada_do_cursor_esta_vazio(shots, profiles, state_name):
    """O cursor do jogo é desenhado dentro do quadro capturado.

    Regressão: com ele parado sobre a lista de afixos, a tela "enchant_locked"
    era classificada como "enchant_select" — o cursor acendia a ROI da 4ª linha.
    O ponto onde o estacionamos precisa ser vazio em toda tela, senão trocamos
    um falso positivo por outro.
    """
    from d4forge.vision.states import ink

    assert ink(shots[state_name], profiles[state_name].cursor_park) < 0.005


def test_ponto_de_parada_nao_encosta_em_roi_usada(profiles):
    """Estacionar o cursor não pode cair sobre nada que o app leia ou clique."""
    prof = profiles["replace"]
    park = prof.cursor_park
    usadas = [
        prof.replace_current, prof.replace_button, prof.locked_affix,
        prof.enchant_button, prof.enchant_cost, prof.result_close,
        prof.confirm_accept, prof.confirm_cancel, prof.occultist_title,
        *prof.replace_options, *prof.replace_orbs,
        *prof.affix_rows, *prof.affix_orbs,
    ]
    for roi in usadas:
        assert park.clip_to(roi).area == 0, f"ponto de parada colide com {roi}"


@pytest.mark.parametrize(
    "fixture_name",
    ["locked_x22_shadow_multiplier.jpg", "locked_1431_maximum_life.jpg"],
)
def test_tela_travada_nao_vira_lista_de_selecao(fixture_name):
    """Regressão dupla, vinda de frames reais que pararam o bot com "nenhum
    afixo está marcado":

    * "x22% Shadow Damage Multiplier" é centralizado e começa em x=219,
      invadindo a coluna dos orbes que servia de discriminador;
    * o cursor do jogo parado sobre a 4ª linha acendia o outro discriminador.

    O sinal correto é a 2ª linha de afixo: com texto = lista de seleção; vazia
    = tela travada (é o vão entre a caixa do afixo e o texto de explicação).
    """
    from pathlib import Path

    from d4forge.geometry import Rect
    from d4forge.imageio import imread
    from d4forge.profile import DEFAULT_PROFILE

    fixture = Path(__file__).parent / "fixtures" / fixture_name
    if not fixture.exists():
        pytest.skip("fixture ausente")
    frame = imread(fixture)
    prof = DEFAULT_PROFILE.scaled(Rect(0, 0, frame.shape[1], frame.shape[0]))
    assert detect_state(frame, prof).state is ScreenState.ENCHANT_LOCKED


def test_le_valor_de_milhar_sem_perder_digito(ocr):
    """Regressão vinda do jogo: '+1,431 Maximum Life' saía como '431 Maximum . Life'.

    O detector partia a linha em 3 caixas e descartava o '+1,'. Pior, o
    resultado truncado ainda casava com o catálogo ('Maximum Life') e passava
    como confiável — o bot aceitaria 431 achando que era 1431.
    """
    from pathlib import Path

    from d4forge.imageio import imread

    fixture = Path(__file__).parent / "fixtures" / "linha_1431_maximum_life.png"
    if not fixture.exists():
        pytest.skip("fixture ausente")
    assert ocr.read(imread(fixture)).text == "+1,431 Maximum Life"


def test_repescagem_so_dispara_quando_precisa(shots, profiles, ocr):
    """A segunda passada custa ~2x; não pode virar rotina."""
    ocr.stats.retries = 0
    ocr.cache.clear()
    img, prof = shots["replace"], profiles["replace"]
    for roi in (*prof.replace_options, prof.replace_current):
        ocr.read(roi.crop(img))
    assert ocr.stats.retries == 0


def test_caixas_de_duas_linhas_saem_em_ordem_de_leitura():
    """Regressão de sessão real: afixo longo quebra em 2 linhas e ordenar as
    caixas só por X intercalava as linhas — "Lucky Hit: Up to a 13%..." virou
    "Lutky ... 13% tne lU ..."."""
    from d4forge.vision.ocr import order_boxes

    # (esq, dir, topo, base, texto, score) — duas linhas, embaralhadas
    boxes = [
        (200.0, 380.0, 40.0, 64.0, "Chance to Restore", 0.9),   # linha 2, meio
        (16.0, 190.0, 10.0, 34.0, "Lucky Hit: Up", 0.9),        # linha 1, início
        (16.0, 190.0, 40.0, 64.0, "13% tne", 0.9),              # linha 2, início
        (200.0, 380.0, 10.0, 34.0, "to a", 0.9),                # linha 1, meio
    ]
    ordered = [t for _l, _r, _t, _b, t, _s in order_boxes(boxes)]
    assert ordered == ["Lucky Hit: Up", "to a", "13% tne", "Chance to Restore"]


def test_roi_alta_nao_muda_leitura_de_linha_unica(shots, profiles, ocr):
    """As ROIs das opções ganharam altura para 2 linhas; afixo de 1 linha tem
    de continuar lendo idêntico (o aparo por bbox descarta a folga)."""
    img, prof = shots["replace"], profiles["replace"]
    got = [ocr.read(roi.crop(img)).text for roi in prof.replace_options]
    assert got == EXPECTED_TEXT["replace"]


def test_rois_das_opcoes_nao_se_tocam(profiles):
    """Se as ROIs se sobrepuserem, a opção 2 leria a 2ª linha da opção 1."""
    a, b = profiles["replace"].replace_options
    assert a.bottom < b.top


def test_cache_evita_o_backend(shots, profiles, ocr):
    """Segunda leitura da mesma linha tem que sair do cache, nao do modelo."""
    roi = profiles["replace"].replace_options[0]
    crop = roi.crop(shots["replace"])
    ocr.read(crop)
    second = ocr.read(crop)
    assert second.source == "cache"
    assert second.elapsed_ms < 5.0
