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


@pytest.fixture(scope="session")
def profiles(shots):
    """Perfil de ROIs resolvido para o tamanho de cada print."""
    from d4forge.geometry import Rect
    from d4forge.profile import DEFAULT_PROFILE

    return {
        state: DEFAULT_PROFILE.scaled(Rect(0, 0, img.shape[1], img.shape[0]))
        for state, img in shots.items()
    }


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
