"""Limpeza da pasta captures/.

A pasta guarda material descartável de depuração (recortes do OCR e quadros de
erro). Ela é esvaziada ao iniciar uma sessão e ao fechar a janela normalmente —
mas *não* num crash, que é justamente quando a evidência importa.
"""

import pytest

from d4forge import config


@pytest.fixture
def captures(tmp_path, monkeypatch):
    pasta = tmp_path / "captures"
    pasta.mkdir()
    monkeypatch.setattr(config, "CAPTURES_DIR", pasta)
    return pasta


def test_leva_tudo(captures):
    (captures / "ocr_001_opcao1_ok.png").write_bytes(b"x")
    (captures / "debug_tela_desconhecida.png").write_bytes(b"x")
    (captures / "snap_01.png").write_bytes(b"x")
    (captures / "anotacao.txt").write_text("nota")

    assert config.clear_captures() == 4
    assert list(captures.iterdir()) == []


def test_remove_subpastas(captures):
    """A rotação antiga deixava captures/sessao_anterior/; ela também sai."""
    antiga = captures / config.PREVIOUS_SESSION_DIR
    antiga.mkdir()
    (antiga / "ocr_007_opcao2_ok.png").write_bytes(b"x")
    (captures / "ocr_001_opcao1_ok.png").write_bytes(b"x")

    assert config.clear_captures() == 2
    assert not antiga.exists()
    assert list(captures.iterdir()) == []


def test_pasta_vazia_nao_e_problema(captures):
    assert config.clear_captures() == 0
    assert captures.is_dir()


def test_pasta_inexistente_nao_e_problema(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CAPTURES_DIR", tmp_path / "nao_existe")
    assert config.clear_captures() == 0


def test_fechamento_normal_limpa(tmp_path, monkeypatch):
    """closeEvent limpa; um crash não passa por lá e preserva tudo."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QApplication

    from d4forge.gui.app import AppState, MainWindow

    pasta = tmp_path / "captures"
    pasta.mkdir()
    (pasta / "ocr_001_opcao1_ok.png").write_bytes(b"x")
    (pasta / "debug_algo.png").write_bytes(b"x")
    monkeypatch.setattr(config, "CAPTURES_DIR", pasta)

    QApplication.instance() or QApplication([])
    janela = MainWindow(AppState.load())
    janela.closeEvent(QCloseEvent())

    assert list(pasta.iterdir()) == []
