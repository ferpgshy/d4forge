"""A janela como JANELA: tamanho, encaixe na tela e o layout que cede.

O que se testa aqui não é o que o app faz, é como ele se comporta na tela. A
versão anterior abria em 1040x840 fixos — mais alto que a área útil de um
monitor 1080p —, exigia 880 pixels de largura e só encolhia até os widgets
começarem a se sobrepor. Cada teste abaixo guarda uma dessas.

O que depende do Windows de verdade (WM_NCHITTEST, Aero Snap, a sombra do DWM)
não cabe aqui: a suíte roda com a plataforma `offscreen`, onde não existe HWND.
Ali o que vale é o caminho reserva, e é ele que estes testes exercitam.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from d4forge.gui.frameless import (  # noqa: E402
    dentro_de_alguma_tela,
    encaixar_na_tela,
    geometria_salva,
    restaurar_geometria,
)
from d4forge.gui.responsive import (  # noqa: E402
    LinhaAdaptavel,
    faixa_central,
    pagina_rolavel,
    trocar_conteudo,
)


def _cartao(largura: int) -> QWidget:
    w = QWidget()
    w.setMinimumWidth(largura)
    return w


def _linha(*larguras: int, pesos=None, espaco: int = 10) -> LinhaAdaptavel:
    """Uma linha JÁ VISÍVEL, que é a condição para o Qt entregar o evento de
    tamanho na hora — escondida ele só o enfileira, e a virada não acontece."""
    linha = LinhaAdaptavel(espaco=espaco)
    for i, largura in enumerate(larguras):
        linha.add(_cartao(largura), pesos[i] if pesos else 1)
    linha.show()
    return linha


def _com_largura(linha: LinhaAdaptavel, largura: int) -> None:
    linha.resize(largura, 300)
    QApplication.processEvents()


# --------------------------------------------------------------- linha/coluna
def test_linha_vira_coluna_quando_a_largura_aperta(qt_app):
    linha = _linha(200, 200)
    limiar = linha.largura_para_caber()
    assert limiar == 2 * (200 + LinhaAdaptavel.CONFORTO) + 10

    _com_largura(linha, limiar + 100)
    assert linha.em_linha()

    _com_largura(linha, limiar - 1)
    assert not linha.em_linha()


def test_a_volta_para_linha_exige_folga(qt_app):
    """Sem histerese o layout pisca entre os dois arranjos durante o arrasto:
    o pixel exato da virada fica alternando a cada evento de tamanho."""
    linha = _linha(200, 200)
    limiar = linha.largura_para_caber()

    _com_largura(linha, limiar - 1)
    assert not linha.em_linha()

    _com_largura(linha, limiar)
    assert not linha.em_linha(), "voltou com um pixel de sobra"

    _com_largura(linha, limiar + LinhaAdaptavel.FOLGA)
    assert linha.em_linha()


def test_minimo_da_linha_e_o_da_coluna(qt_app):
    """Regressão: a linha anunciava a largura dos cartões LADO A LADO como seu
    mínimo, mesmo sabendo virar coluna. Dentro de uma área de rolagem isso
    reservava essa largura para sempre — barra de rolagem horizontal fixa, e a
    virada que existe justamente para evitá-la nunca acontecia."""
    linha = _linha(200, 300)
    _com_largura(linha, linha.largura_para_caber() + 100)

    assert linha.em_linha(), "precondição: o teste é sobre estar EM LINHA"
    assert linha.minimumSizeHint().width() == 300


def test_coluna_nao_estica_os_cartoes(qt_app):
    """Empilhados, os cartões ficam do tamanho do conteúdo. Com peso eles
    dividiriam a altura que sobrasse e um cartão de três linhas viraria um
    retângulo quase vazio."""
    linha = _linha(200, 200, pesos=(3, 1))
    limiar = linha.largura_para_caber()

    _com_largura(linha, limiar + 100)
    assert [linha._caixa.stretch(i) for i in range(2)] == [3, 1]

    _com_largura(linha, limiar - 1)
    assert [linha._caixa.stretch(i) for i in range(2)] == [0, 0]


# ------------------------------------------------------------------- rolagem
def test_pagina_rolavel_nao_herda_o_minimo_do_conteudo(qt_app):
    """É isto que permite a janela encolher: o mínimo de quem rola é o dela
    mesma, não o da página inteira que está lá dentro."""
    conteudo = QWidget()
    conteudo.setMinimumSize(900, 1200)
    area = pagina_rolavel(conteudo)

    assert area.minimumSizeHint().width() < 900
    assert area.minimumSizeHint().height() < 1200
    assert area.widget() is conteudo


def test_trocar_conteudo_descarta_a_pagina_antiga(qt_app):
    antiga = QWidget()
    area = pagina_rolavel(antiga)
    nova = QWidget()

    trocar_conteudo(area, nova)

    assert area.widget() is nova
    assert antiga.parent() is None


def test_faixa_central_para_de_crescer_no_teto(qt_app):
    from PySide6.QtWidgets import QHBoxLayout

    interno = QHBoxLayout()
    interno.addWidget(QWidget())
    fora = faixa_central(interno, 400)
    fora.resize(1600, 80)
    fora.layout().activate()

    miolo = fora.layout().itemAt(1).widget()
    assert miolo.maximumWidth() == 400
    assert miolo.width() <= 400


# ------------------------------------------------------------------ geometria
def test_encaixa_na_tela_em_vez_de_passar_dela(qt_app):
    """Regressão: 1040x840 fixos passavam da área útil de um 1080p, e a janela
    nascia com parte de si — botões de janela inclusive — fora do alcance."""
    janela = QWidget()
    janela.setMinimumSize(200, 150)
    encaixar_na_tela(janela, 5000, 5000)

    livre = QGuiApplication.primaryScreen().availableGeometry()
    assert janela.width() <= livre.width()
    assert janela.height() <= livre.height()
    assert livre.contains(janela.geometry())


def test_encaixa_respeita_o_minimo_da_janela(qt_app):
    janela = QWidget()
    janela.setMinimumSize(300, 200)
    encaixar_na_tela(janela, 100, 100)

    assert janela.width() >= 300
    assert janela.height() >= 200


def test_reconhece_janela_fora_de_todas_as_telas(qt_app):
    """Monitor desligado desde a última sessão, notebook que saiu da dock: a
    geometria salva aponta para uma área que não existe mais."""
    janela = QWidget()
    janela.setGeometry(-9000, -9000, 400, 300)
    assert not dentro_de_alguma_tela(janela)

    encaixar_na_tela(janela, 400, 300)
    assert dentro_de_alguma_tela(janela)


def test_geometria_vai_e_volta(qt_app):
    janela = QWidget()
    encaixar_na_tela(janela, 640, 480)
    blob = geometria_salva(janela)
    assert blob and isinstance(blob, str)

    outra = QWidget()
    assert restaurar_geometria(outra, blob)
    assert outra.size() == janela.size()


@pytest.mark.parametrize("blob", ["", "nao e base64 de nada", "!!!!"])
def test_geometria_estragada_nao_derruba_a_abertura(qt_app, blob):
    """O settings.json é editável à mão e sobrevive a versões. Um valor
    inesperado aqui não pode estragar uma preferência: ele impediria o app de
    ABRIR."""
    assert restaurar_geometria(QWidget(), blob) is False


# ------------------------------------------------------- a janela por inteiro
@pytest.fixture
def janela(qt_app, config_isolada):
    """A janela de verdade, num `data/` descartável.

    Sem `config_isolada`, montar a MainWindow escreve no data/ do usuário:
    `closeEvent` salva catálogo e ajustes e esvazia captures/.
    """
    from d4forge.gui.app import AppState, MainWindow

    w = MainWindow(AppState.load())
    # Mostrada: só então o Qt dá geometria aos filhos, e sem geometria a
    # barra de título não sabe dizer o que há sob um ponto.
    w.show()
    yield w
    w.close()


def test_janela_cabe_numa_tela_pequena(janela):
    """Regressão: 880 de largura mínima. Era o preço de um layout que não
    encolhia — e num notebook 1366x768 com a janela ao lado do jogo, 880 é
    largura demais para pedir."""
    assert janela.minimumWidth() <= 640
    assert janela.minimumHeight() <= 480


# Acima disto um rótulo numa linha só já é mais largo que o resto da aba.
LIMITE_SEM_QUEBRA = 40


@pytest.mark.parametrize("aba", [0, 1, 2, 3])
def test_rotulo_comprido_tem_de_quebrar_linha(janela, aba):
    """Um rótulo longo que não quebra fixa sozinho a largura mínima da aba, e
    com ela a da janela — foi assim que o mínimo chegou a 880.

    O teste é sobre a ESTRUTURA e não sobre pixels de propósito: a suíte roda
    com a plataforma `offscreen`, que cai numa fonte bem mais larga que a
    Segoe UI do Windows, e o mesmo layout mede quase o dobro ali. Um limite em
    pixels só mediria a fonte do ambiente.
    """
    from PySide6.QtWidgets import QCheckBox, QLabel, QRadioButton

    pagina = janela.tabs.widget(aba)
    pagina = getattr(pagina, "widget", lambda: None)() or janela.tabs.widget(aba)

    culpados = [
        f"{type(w).__name__}: {w.text()[:60]}"
        for w in pagina.findChildren(QLabel)
        if len(w.text()) > LIMITE_SEM_QUEBRA and not w.wordWrap()
    ]
    # Caixa de marcar e rádio NUNCA quebram linha, por mais que se peça: o
    # jeito de não travar a largura com elas é o texto ser curto e a
    # explicação morar num rótulo à parte, que quebra.
    culpados += [
        f"{type(w).__name__}: {w.text()[:60]}"
        for w in pagina.findChildren(QCheckBox) + pagina.findChildren(QRadioButton)
        if len(w.text()) > LIMITE_SEM_QUEBRA
    ]
    assert not culpados, culpados


def test_maximizada_nao_usa_o_nome_reservado_do_qt(janela):
    """`maximized` JÁ é uma propriedade do QWidget, e só de leitura:
    `setProperty("maximized", ...)` não cria propriedade dinâmica nenhuma,
    falha calada, e a folha de estilo nunca casa. Vale para `minimized` e
    `fullScreen` também."""
    shell = janela.centralWidget()

    shell.setProperty("maximized", True)
    assert shell.property("maximized") is False, "o Qt aceitou o nome reservado"

    janela.on_maximize_changed(True)
    assert shell.property("maximizada") is True
    janela.on_maximize_changed(False)
    assert shell.property("maximizada") is False


def test_botao_de_maximizar_troca_de_glifo(janela):
    from d4forge.gui.app import _glifo

    botao = janela._botoes_janela["btnMax"]
    janela.on_maximize_changed(True)
    assert botao.text() == _glifo("btnRestore")
    janela.on_maximize_changed(False)
    assert botao.text() == _glifo("btnMax")


def test_barra_de_titulo_sabe_o_que_e_botao(janela):
    """O que a moldura nativa pergunta a cada movimento do mouse: marcar um
    botão como título faria o Windows engolir o clique."""
    from PySide6.QtCore import QPoint

    escala = janela.devicePixelRatioF() or 1.0

    def regiao(widget, dx=None, dy=None):
        ponto = widget.mapTo(
            janela,
            QPoint(
                widget.width() // 2 if dx is None else dx,
                widget.height() // 2 if dy is None else dy,
            ),
        )
        return janela.regiao_da_barra(
            round(ponto.x() * escala), round(ponto.y() * escala)
        )

    assert regiao(janela._botoes_janela["btnMax"]) == "maximizar"
    assert regiao(janela._botoes_janela["btnClose"]) == ""
    assert regiao(janela.btn_lang) == ""
    assert regiao(janela.lbl_subtitle) == "titulo"
    assert regiao(janela.tabs, 10, 10) == ""


def test_troca_de_idioma_preserva_a_sessao(janela):
    """As abas são RENOMEADAS, não removidas e recriadas: o painel de progresso
    guarda a sessão em curso, e refazê-lo perderia as tentativas já feitas."""
    from d4forge.i18n import t

    painel = janela.progress
    painel.note("msg.catalog_loaded", count=7)
    eventos = len(painel._events)

    janela._set_language("en")

    assert janela.progress is painel, "o painel foi refeito"
    assert len(painel._events) >= eventos
    assert janela.tabs.count() == 4
    assert [janela.tabs.tabText(i) for i in range(4)] == [
        t("tab.enchant"), t("tab.temper"), t("tab.mw"), t("tab.catalog")
    ]
    # A página do Enchant é a única refeita, e tem de continuar dentro da área
    # de rolagem — fora dela a aba volta a não encolher.
    assert janela._area_enchant.widget() is not None
    assert janela.status.text() == t("panel.idle")


def test_geometria_e_salva_ao_fechar(qt_app, config_isolada):
    from d4forge import config
    from d4forge.gui.app import AppState, MainWindow

    w = MainWindow(AppState.load())
    w.close()

    assert w.app.settings.window_geometry
    salvo = config.Settings.load(config.SETTINGS_PATH)
    assert salvo.window_geometry == w.app.settings.window_geometry
