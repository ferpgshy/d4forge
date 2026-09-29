"""As três edições: completa, só-Forge e só-AutoSkill.

O mesmo código com recortes diferentes. O que importa travar aqui não é a
lista de abas — é que cada edição só mexa no que é dela, porque as três
podem acabar rodando na MESMA pasta de dados.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from d4forge import edicao  # noqa: E402
from d4forge.gui.app import (  # noqa: E402
    esvaziar_saidas,
    nomear_aplicativo,
)


@pytest.fixture
def qual(monkeypatch):
    """Troca a edição corrente e devolve o cache ao normal no fim."""

    def usar(nome):
        monkeypatch.setenv(edicao.VARIAVEL, nome)
        edicao.esquecer()
        return nome

    yield usar
    monkeypatch.delenv(edicao.VARIAVEL, raising=False)
    edicao.esquecer()


# ------------------------------------------------------------- a edição
def test_sem_marcador_e_sem_variavel_mostra_tudo(monkeypatch):
    """Rodar do código-fonte tem de mostrar o app inteiro."""
    monkeypatch.delenv(edicao.VARIAVEL, raising=False)
    monkeypatch.setattr(edicao, "_do_arquivo", lambda: None)
    edicao.esquecer()
    assert edicao.atual() == edicao.COMPLETA


@pytest.mark.parametrize("nome", list(edicao.TODAS))
def test_a_variavel_manda(qual, nome):
    qual(nome)
    assert edicao.atual() == nome
    assert edicao.abas() == edicao.ABAS[nome]


def test_valor_estragado_cai_na_completa_sem_levantar(qual):
    """Isto é lido na abertura da janela: um valor inesperado não pode
    impedir o app de ABRIR."""
    qual("nao-existe")
    assert edicao.atual() == edicao.COMPLETA


def test_o_arquivo_vale_quando_nao_ha_variavel(monkeypatch):
    monkeypatch.delenv(edicao.VARIAVEL, raising=False)
    monkeypatch.setattr(edicao, "_do_arquivo", lambda: "  AutoSkill \n")
    edicao.esquecer()
    assert edicao.atual() == edicao.AUTOSKILL


def test_so_o_autoskill_dispensa_o_leitor(qual):
    """É disto que sai a economia de ~60 MB no pacote dele."""
    qual(edicao.AUTOSKILL)
    assert not edicao.precisa_de_ocr()
    for nome in (edicao.COMPLETA, edicao.FORGE):
        qual(nome)
        assert edicao.precisa_de_ocr()


# ------------------------------------------------------------- a janela
def _janela(config_isolada):
    from d4forge.gui.app import AppState, MainWindow

    return MainWindow(AppState.load())


@pytest.mark.parametrize(
    "nome, esperadas",
    [
        (edicao.COMPLETA, 5),
        (edicao.FORGE, 4),
        (edicao.AUTOSKILL, 1),
    ],
)
def test_cada_edicao_monta_so_as_abas_dela(qt_app, config_isolada, qual,
                                           nome, esperadas):
    qual(nome)
    janela = _janela(config_isolada)
    try:
        assert janela.tabs.count() == esperadas
        assert janela.windowTitle() == edicao.nome()
    finally:
        janela.close()


@pytest.mark.parametrize("nome", list(edicao.TODAS))
def test_abrir_e_fechar_nao_quebra_em_nenhuma_edicao(qt_app, config_isolada,
                                                     qual, nome):
    """Regressão: metade do código assumia que todas as abas existiam, e
    fechar a janela estourava em `_salvar_tudo` e em `_collect_settings`."""
    qual(nome)
    janela = _janela(config_isolada)
    janela.close()
    assert (config_isolada / "settings.json").exists()


@pytest.mark.parametrize("nome", list(edicao.TODAS))
def test_o_windows_nao_cola_nada_no_titulo(qt_app, config_isolada, qual, nome):
    """Regressão: a janela da edição Forge abria "d4forge Forge - d4forge".

    O plugin do Windows acrescenta `" - <nome de exibição>"` a todo título que
    ainda não termine nesse nome. O nome de exibição era fixo, o título não —
    e as duas edições novas ganhavam um sufixo. O que trava o conserto é esta
    relação entre os dois, não o texto de nenhum deles.
    """
    qual(nome)
    nomear_aplicativo(qt_app)
    janela = _janela(config_isolada)
    try:
        assert janela.windowTitle().endswith(qt_app.applicationDisplayName())
    finally:
        janela.close()


def test_a_saida_aguenta_nao_ter_console(monkeypatch):
    """Regressão: no exe sem console, `sys.stdout` e `sys.stderr` são None.

    O caminho de saída chamava `.flush()` nos dois. O app já tinha gravado
    tudo, mas fechava com a caixa de erro do PyInstaller na cara do usuário.
    """
    monkeypatch.setattr("sys.stdout", None)
    monkeypatch.setattr("sys.stderr", None)
    esvaziar_saidas()  # não pode levantar


def test_o_autoskill_nao_sobe_onde_nao_existe(qt_app, config_isolada, qual):
    qual(edicao.FORGE)
    janela = _janela(config_isolada)
    try:
        assert janela.autoskill_worker is None
        assert not hasattr(janela, "autoskill_tab")
    finally:
        janela.close()


def test_a_edicao_autoskill_nao_apaga_o_catalogo(qt_app, config_isolada, qual):
    """O estrago silencioso que isto evita: a edição só-AutoSkill carrega um
    catálogo VAZIO, porque não lê texto. Sem a guarda, abrir esse executável
    na mesma pasta da edição completa sobrescrevia com nada o affixes.json de
    quem tinha editado o catálogo à mão."""
    import json

    from d4forge import config

    alvo = config.CATALOG_PATH
    alvo.write_text(json.dumps({"Dexterity": {"unit": "flat"}}), encoding="utf-8")
    antes = alvo.read_text(encoding="utf-8")

    qual(edicao.AUTOSKILL)
    janela = _janela(config_isolada)
    janela.close()

    assert alvo.read_text(encoding="utf-8") == antes, "o catálogo foi sobrescrito"


def test_a_edicao_forge_nao_mexe_na_config_do_autoskill(qt_app, config_isolada,
                                                        qual):
    from d4forge import config

    assert not config.AUTOSKILL_PATH.exists()
    qual(edicao.FORGE)
    janela = _janela(config_isolada)
    janela.close()
    assert not config.AUTOSKILL_PATH.exists(), "a Forge criou autoskill.json"


# --------------------------------------------------------------- o build
def test_o_build_conhece_as_tres_e_recusa_o_resto():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    build_exe = pytest.importorskip("build_exe")

    assert set(build_exe.EDICOES) == set(edicao.TODAS)
    nomes = [n for n, _ in build_exe.EDICOES.values()]
    assert len(set(nomes)) == 3, "duas edições com o mesmo nome de executável"

    # Só a do AutoSkill exclui o leitor.
    assert build_exe.EDICOES[edicao.AUTOSKILL][1]
    assert not build_exe.EDICOES[edicao.COMPLETA][1]

    with pytest.raises(SystemExit):
        build_exe.main(["nao-existe"])
