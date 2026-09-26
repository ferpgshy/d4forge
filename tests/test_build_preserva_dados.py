"""O build não pode apagar a configuração de quem usa o .exe.

`config._dirs()` põe a pasta gravável AO LADO do executável quando o app está
congelado, então binds, alvo, ajustes e catálogo do usuário moram dentro de
`dist/d4forge/data/`. E a limpeza do build apaga `dist/` inteiro.

Aconteceu de verdade: recompilar apagou as binds de quem estava testando, mais
de uma vez na mesma sessão.
"""

import json
import shutil
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "tools"))

build_exe = pytest.importorskip("build_exe")


@pytest.fixture
def dist_falsa(tmp_path):
    """Uma `dist/d4forge/` com configuração do usuário dentro."""
    dados = tmp_path / "dist" / build_exe.NOME / "data"
    dados.mkdir(parents=True)
    (dados / "autoskill.json").write_text(
        json.dumps({"cast": {"intervalo_ms": 77}}), encoding="utf-8"
    )
    (dados / "settings.json").write_text('{"language": "en"}', encoding="utf-8")
    return tmp_path


def test_a_config_do_usuario_sobrevive_a_limpeza(dist_falsa):
    guardado = build_exe.guardar_dados(dist_falsa)
    assert guardado is not None

    # É isto que `limpar()` faz, e é o que apagava tudo.
    shutil.rmtree(dist_falsa / "dist")

    build_exe.devolver_dados(guardado, dist_falsa)

    dados = dist_falsa / "dist" / build_exe.NOME / "data"
    blob = json.loads((dados / "autoskill.json").read_text(encoding="utf-8"))
    assert blob["cast"]["intervalo_ms"] == 77
    assert (dados / "settings.json").exists()


def test_a_config_do_usuario_vence_a_que_o_build_criar(dist_falsa):
    """Abrir o app durante o build deixaria um data/ novo no lugar. O que
    vale é o do usuário."""
    guardado = build_exe.guardar_dados(dist_falsa)
    shutil.rmtree(dist_falsa / "dist")

    intruso = dist_falsa / "dist" / build_exe.NOME / "data"
    intruso.mkdir(parents=True)
    (intruso / "autoskill.json").write_text('{"cast": {"intervalo_ms": 120}}',
                                            encoding="utf-8")

    build_exe.devolver_dados(guardado, dist_falsa)

    blob = json.loads((intruso / "autoskill.json").read_text(encoding="utf-8"))
    assert blob["cast"]["intervalo_ms"] == 77, "o data/ novo sobrepôs o do usuário"


def test_sem_data_nao_ha_o_que_guardar(tmp_path):
    """Primeira compilação numa máquina limpa não pode quebrar."""
    assert build_exe.guardar_dados(tmp_path) is None
    build_exe.devolver_dados(None, tmp_path)      # não levanta


def test_devolver_e_seguro_se_o_abrigo_sumir(tmp_path):
    build_exe.devolver_dados(tmp_path / "que-nao-existe", tmp_path)
