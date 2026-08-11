import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Telas de referencia, uma por estado do fluxo do Occultist.
#
# Sao versoes higienizadas das capturas originais: so' as regioes que o app le'
# (painel do Occultist e dialogo central) foram preservadas, o resto e' preto.
# As originais mostravam nome de conta, personagem, ouro e o nome de outros
# jogadores no mundo - nada disso e' usado, e o repositorio e' publico.
# Regeradas por tools/sanitize_shots.py.
SHOTS = ROOT / "tests" / "fixtures" / "telas"

REFERENCE_SHOTS = {
    "enchant_select": "enchant_select.jpg",
    "confirm": "confirm.jpg",
    "replace": "replace.jpg",
    "result": "result.jpg",
    "enchant_locked": "enchant_locked.jpg",
}


@pytest.fixture(scope="session")
def shots():
    """Carrega as telas de referencia; pula os testes se nao existirem."""
    from d4forge.imageio import imread

    if not SHOTS.is_dir():
        pytest.skip(f"telas de referencia nao encontradas em {SHOTS}")
    loaded = {}
    for state, name in REFERENCE_SHOTS.items():
        img = imread(SHOTS / name)
        if img is None:
            pytest.skip(f"nao consegui ler {name}")
        loaded[state] = img
    return loaded


TELAS_TEMPER = {
    "temper_idle": "temper_idle.jpg",
    "temper_recipes": "temper_recipes.jpg",
    "temper_no_recipe": "temper_no_recipe.jpg",
    "temper_result": "temper_result.jpg",
    "temper_animation": "temper_animation.jpg",
    # Par casado do mesmo afixo: com e sem intervalo na linha.
    "temper_result_normal": "temper_result_normal.jpg",
    "temper_result_ga": "temper_result_ga.jpg",
    "temper_no_rerolls": "temper_no_rerolls.jpg",
    "temper_new_affix": "temper_new_affix.jpg",
    # Preview do item pelo tooltip, durante a animação.
    "preview_lucky_hit": "preview_lucky_hit.jpg",
    "preview_lucky_hit_2": "preview_lucky_hit_2.jpg",
    "preview_lucky_hit_daze": "preview_lucky_hit_daze.jpg",
    "preview_movement_ga": "preview_movement_ga.jpg",
}


@pytest.fixture(scope="session")
def temper_shots():
    """Telas do Ferreiro, tambem higienizadas: so' o painel esquerdo sobrou."""
    from d4forge.imageio import imread

    loaded = {}
    for state, name in TELAS_TEMPER.items():
        img = imread(SHOTS / name)
        if img is None:
            pytest.skip(f"nao consegui ler {name}")
        loaded[state] = img
    return loaded


@pytest.fixture(scope="session")
def profiles(shots):
    """Perfil de ROIs resolvido para o tamanho de cada print."""
    from d4forge.geometry import Rect
    from d4forge.profile import DEFAULT_PROFILE

    return {
        state: DEFAULT_PROFILE.scaled(Rect(0, 0, img.shape[1], img.shape[0]))
        for state, img in shots.items()
    }


TELAS_MW = {
    "mw_idle": "mw_idle.jpg",        # NEXT RANK / QUALITY 0/25
    "mw_affix": "mw_affix.jpg",      # Current Masterwork Affix
    "mw_animation": "mw_animation.jpg",
}


@pytest.fixture(scope="session")
def mw_shots():
    """Telas do Masterworking, higienizadas como as outras."""
    from d4forge.imageio import imread

    loaded = {}
    for state, name in TELAS_MW.items():
        img = imread(SHOTS / name)
        if img is None:
            pytest.skip(f"nao consegui ler {name}")
        loaded[state] = img
    return loaded


@pytest.fixture(scope="session")
def ocr(tmp_path_factory):
    from d4forge.vision.ocr import OcrEngine

    return OcrEngine(data_dir=tmp_path_factory.mktemp("ocr"))


@pytest.fixture
def catalog():
    from d4forge.affixes import AffixCatalog

    return AffixCatalog.seeded()


@pytest.fixture(scope="session")
def qt_app():
    """QApplication unica da sessao; o Qt nao aceita duas."""
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def config_isolada(tmp_path, monkeypatch):
    """Aponta o config para um diretorio descartavel.

    Sem isto, qualquer teste que monta a MainWindow escreve no `data/` de
    verdade: `closeEvent` salva catalogo e ajustes e esvazia `captures/`. Ja'
    aconteceu de uma rodada de testes destruir o catalogo do usuario, e de
    deixar o app aberto em ingles porque um teste trocou o idioma e salvou.

    O catalogo continua vindo cheio: `import_full_catalog` o preenche a partir
    da lista embutida, nao do arquivo do usuario.
    """
    from d4forge import config

    dados = tmp_path / "data"
    dados.mkdir()
    monkeypatch.setattr(config, "DATA_DIR", dados)
    monkeypatch.setattr(config, "CAPTURES_DIR", tmp_path / "captures")
    monkeypatch.setattr(config, "SETTINGS_PATH", dados / "settings.json")
    monkeypatch.setattr(config, "CATALOG_PATH", dados / "affixes.json")
    monkeypatch.setattr(config, "RULES_PATH", dados / "rules.json")
    monkeypatch.setattr(config, "TIMINGS_PATH", dados / "timings.json")
    monkeypatch.setattr(config, "TEMPER_PATH", dados / "temper.json")
    monkeypatch.setattr(config, "MW_PATH", dados / "masterwork.json")
    return dados


@pytest.fixture(autouse=True)
def idioma_padrao():
    """Idioma de volta ao padrao antes de cada teste.

    O i18n guarda o idioma corrente num global, entao um teste que troca para
    ingles contaminava todos os que rodassem depois - e o efeito aparecia longe
    dali, em asserts sobre mensagens do engine. Restaurar aqui e' de graca e
    corta a classe de problema inteira.
    """
    from d4forge import i18n

    i18n.set_language(i18n.DEFAULT)
    yield
    i18n.set_language(i18n.DEFAULT)
