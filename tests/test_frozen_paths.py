"""Caminhos quando o app roda como .exe do PyInstaller.

Congelado, `__file__` aponta para dentro do pacote (somente leitura, recriado a
cada execução) e os recursos vão para `sys._MEIPASS`. Gravar catálogo e
configurações no lugar errado significa perdê-los ao fechar — e o .exe só
denuncia isso em uso, nunca nos testes normais.
"""

import importlib
import sys

import pytest


@pytest.fixture
def congelado(tmp_path, monkeypatch):
    """Simula o layout que o PyInstaller produz."""
    exe_dir = tmp_path / "dist" / "d4forge"
    meipass = exe_dir / "_internal"
    (meipass / "d4forge" / "resources").mkdir(parents=True)
    exe_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "d4forge.exe"))

    from d4forge import catalog_import, config

    importlib.reload(config)
    importlib.reload(catalog_import)
    yield config, exe_dir, meipass

    # Desfaz ANTES de recarregar: os módulos guardam os caminhos em constantes
    # de import, então recarregar com sys.frozen ainda ligado deixaria
    # BUNDLED_PATH apontando para o bundle de mentira e quebraria os testes
    # seguintes com um catálogo de uma entrada só.
    monkeypatch.undo()
    importlib.reload(config)
    importlib.reload(catalog_import)


def test_dados_ficam_ao_lado_do_executavel(congelado):
    config, exe_dir, meipass = congelado
    assert config.PROJECT_DIR == exe_dir
    assert config.DATA_DIR == exe_dir / "data"
    assert config.CAPTURES_DIR == exe_dir / "captures"
    # O que o usuário edita nunca pode cair no diretório temporário.
    assert meipass not in config.DATA_DIR.parents


def test_recursos_vem_do_bundle(congelado):
    config, _exe_dir, meipass = congelado
    assert config.RESOURCE_DIR == meipass


def test_lista_de_afixos_e_encontrada_no_bundle(congelado):
    config, _exe_dir, meipass = congelado
    empacotada = meipass / "d4forge" / "resources" / "d4lf_affixes_enUS.json"
    empacotada.write_text('{"maximum_life": "maximum life"}', encoding="utf-8")

    from d4forge import catalog_import

    importlib.reload(catalog_import)
    assert catalog_import._bundled_path() == empacotada
    assert [e.name for e in catalog_import.load_bundled()] == ["Maximum Life"]


def test_em_desenvolvimento_usa_a_raiz_do_projeto():
    """Sem congelar, tudo continua na pasta do projeto."""
    from d4forge import config

    assert config.PROJECT_DIR == config.RESOURCE_DIR
    assert (config.PROJECT_DIR / "d4forge").is_dir()
