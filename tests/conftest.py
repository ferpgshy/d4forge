import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SHOTS = ROOT / "PRINTS SEM CORTE (DIMENSAO)"

# Cada print de referencia e' um estado do fluxo do Occultist.
REFERENCE_SHOTS = {
    "enchant_select": "image 5.png",
    "confirm": "image 6.png",
    "replace": "image 7.png",
    "result": "image 8.png",
    "enchant_locked": "image 9.png",
}


@pytest.fixture(scope="session")
def shots():
    """Carrega os prints de referencia; pula os testes se nao existirem."""
    from d4forge.imageio import imread

    if not SHOTS.is_dir():
        pytest.skip(f"prints de referencia nao encontrados em {SHOTS}")
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
