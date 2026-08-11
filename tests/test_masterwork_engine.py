"""Ciclo do Masterworking, com a tela trocada por um roteiro falso.

A regra que domina este arquivo: um reroll **substitui** o Masterwork Affix
atual, e custa 10.000.000 por volta. Então, na dúvida, o ciclo para — nunca
continua rerrolando.

O segundo tema é o ESC. Ele é enviado às cegas, e com o painel à mostra fecha o
Masterworking (e o próximo fecha o Ferreiro). Vários testes aqui existem só
para prender essa tecla ao único lugar onde ela é segura.
"""

import time

import pytest

from d4forge.geometry import Point, Rect
from d4forge.masterwork.engine import MasterworkEngine
from d4forge.masterwork.result import MasterworkAffix
from d4forge.masterwork.rules import MasterworkGoal, MasterworkLimits
from d4forge.masterwork.states import MasterworkState
from d4forge.vision.ocr import OcrEngine
from d4forge.window import GameWindow


class TelaRoteirizada:
    """Devolve telas de referência conforme um roteiro.

    Cada clique OU tecla avança um passo — no Masterworking o ESC também muda
    de tela, então ele precisa mover o roteiro igual ao clique.
    """

    def __init__(self, shots, sequencia):
        self.shots = shots
        self.sequencia = list(sequencia)
        self.passo = 0
        self.cliques: list[str] = []
        self.teclas: list[int] = []
        # Quando cada tecla saiu. Carimbado AQUI dentro, e não por um wrapper
        # posto depois: o monkeypatch já capturou este método por referência,
        # e trocá-lo no objeto não muda o que o motor chama.
        self.instantes: list[float] = []

    def grab(self, _region):
        return self.shots[self.sequencia[min(self.passo, len(self.sequencia) - 1)]]

    def close(self):
        pass

    def _avanca(self):
        self.passo = (self.passo + 1) % len(self.sequencia)

    def clica(self, rect, _profile=None):
        self.cliques.append(rect.as_tuple())
        self._avanca()
        return Point(0, 0)

    def tecla(self, scancode):
        self.teclas.append(scancode)
        self.instantes.append(time.monotonic())
        self._avanca()


class JanelaFalsa(GameWindow):
    """Janela de mentira que HERDA da de verdade.

    Não é preciosismo. A primeira versão deste arquivo trazia uma classe solta
    com um atributo `foreground` — o mesmo nome errado que o motor usava. O
    teste concordou com o erro e passou; no jogo, a primeira tentativa morria
    com `'GameWindow' object has no attribute 'foreground'`. Herdando, um nome
    que não existe na janela real não existe aqui também.
    """

    def __init__(self, client: Rect, foreground: bool = True) -> None:
        super().__init__(hwnd=1, title="Diablo IV", client=client, window=client)
        self._foreground = foreground

    @property
    def is_foreground(self) -> bool:
        return self._foreground


@pytest.fixture
def roteiro(monkeypatch, mw_shots, tmp_path):
    def build(sequencia, goal=None, extras=None, foreground=True, **kwargs):
        telas = dict(mw_shots, **(extras or {}))
        img = telas["mw_idle"]
        client = Rect(0, 0, img.shape[1], img.shape[0])
        tela = TelaRoteirizada(telas, sequencia)

        janela = JanelaFalsa(client, foreground)
        monkeypatch.setattr(
            "d4forge.masterwork.engine.find_game_window", lambda: janela
        )
        monkeypatch.setattr("d4forge.masterwork.engine.click_rect", tela.clica)
        monkeypatch.setattr("d4forge.masterwork.engine.press_key", tela.tecla)
        monkeypatch.setattr("d4forge.masterwork.engine.move_to", lambda *a: None)

        engine = MasterworkEngine(
            goal=goal or MasterworkGoal(),
            ocr=OcrEngine(data_dir=tmp_path / "ocr"),
            limits=kwargs.pop(
                "limits", MasterworkLimits(max_attempts=3, max_minutes=None)
            ),
            capture=tela,
            poll_interval=0.001,
            state_timeout=1.0,
            require_foreground=kwargs.pop("require_foreground", False),
            **kwargs,
        )
        engine.AFFIX_SETTLE_S = 0.2
        return engine, tela

    return build


ALVO = "Damage with Two-Handed Slashing Weapons"


# ------------------------------------------------------- caminho feliz

def test_para_quando_o_masterwork_cai_no_alvo(roteiro):
    """A tela já mostra o afixo alvo: encerra sem gastar um único reroll."""
    engine, tela = roteiro(["mw_affix"], MasterworkGoal(affix=ALVO))

    resultado = engine.run()

    assert resultado.found, resultado.reason
    assert resultado.reason_key == "mw.got_target"
    assert resultado.count == 1
    assert tela.cliques == []          # nada foi gasto
    assert tela.teclas == []           # e nenhum ESC foi enviado


def test_rerrola_quando_o_afixo_nao_e_o_alvo(roteiro):
    """Afixo errado: clica em Upgrade, pula a animação com ESC, lê de novo."""
    engine, tela = roteiro(
        ["mw_affix", "mw_animation", "mw_affix"],
        MasterworkGoal(affix="Strength"),
        limits=MasterworkLimits(max_attempts=2, max_minutes=None),
    )

    resultado = engine.run()

    prof = engine._resolved
    assert not resultado.found
    assert resultado.reason_key == "stop.max_attempts"
    # Clicou no Upgrade, e não em outra coisa.
    assert tela.cliques == [prof.upgrade_button.as_tuple()]
    # E pulou a animação com ESC, sem tocar no botão Skip.
    assert tela.teclas and prof.skip_button.as_tuple() not in tela.cliques
    assert resultado.count == 2


def test_o_teto_nao_gasta_um_reroll_que_ninguem_vai_ler(roteiro):
    """Com o teto batido, o ciclo encerra DEPOIS de ler — sem rerrolar de novo.

    Antes ele checava o teto só no topo do laço: lia a última tentativa, clicava
    em Upgrade e só então parava. Eram 10.000.000 gastos num resultado que o
    relatório nem mostra, e o item ficava com um afixo desconhecido.
    """
    engine, tela = roteiro(
        ["mw_affix", "mw_animation", "mw_affix"],
        MasterworkGoal(affix="Strength"),
        limits=MasterworkLimits(max_attempts=1, max_minutes=None),
    )
    resultado = engine.run()

    assert resultado.reason_key == "stop.max_attempts"
    assert resultado.count == 1
    assert tela.cliques == [], "leu uma vez, bateu o teto, e não gastou nada"


# ------------------------------------------------------- a trava do ESC

def test_esc_nunca_e_enviado_com_o_painel_a_mostra(roteiro):
    """Com o painel visível, ESC fecha o Masterworking — e o próximo fecha o
    Ferreiro. O ciclo terminaria cego, fora de qualquer tela conhecida."""
    engine, tela = roteiro(["mw_affix"], MasterworkGoal(affix=ALVO))
    engine.run()
    assert tela.teclas == []

    engine, tela = roteiro(
        ["mw_idle", "mw_affix"], MasterworkGoal(affix=ALVO),
        limits=MasterworkLimits(max_attempts=1, max_minutes=None),
    )
    engine.run()
    assert tela.teclas == [], "painel de NEXT RANK também não pode levar ESC"


def test_desiste_se_o_esc_nao_devolve_o_painel(roteiro):
    """Modal que não fecha: parar é melhor que metralhar tecla às cegas."""
    engine, tela = roteiro(["mw_animation"], MasterworkGoal(affix=ALVO))
    engine.ESCAPE_BEAT_S = 0.01
    engine.ESCAPE_SETTLE_S = 0.05

    resultado = engine.run()

    assert not resultado.found
    assert resultado.reason_key == "mw.stuck_modal"
    assert len(tela.teclas) == engine.MAX_ESCAPES


def test_o_intervalo_entre_os_esc_e_fixo(roteiro):
    """250 ms, ESC, 250 ms, ESC — e não "o tempo que a tela levar".

    O intervalo era o tempo até a tela sair do estado anterior, o que dava de
    ~100 ms a 1 s conforme a rodada. O segundo ESC caía em cima da troca de
    tela, onde o jogo o ignora, e o ciclo se perdia.
    """
    engine, tela = roteiro(["mw_animation"], MasterworkGoal(affix=ALVO))
    engine.ESCAPE_SETTLE_S = 0.01
    assert engine.ESCAPE_BEAT_S == pytest.approx(0.25)

    engine.run()

    assert len(tela.instantes) >= 2
    for antes, depois in zip(tela.instantes, tela.instantes[1:]):
        # A pausa é a peça fixa; a observação no meio custa alguns ms a mais.
        assert 0.24 <= depois - antes <= 0.55, tela.instantes


def test_a_pausa_vem_antes_do_esc_e_nao_depois(roteiro):
    """Se a pausa viesse depois, o PRIMEIRO ESC sairia colado na troca de tela
    que acabou de acontecer — que é exatamente onde o jogo o ignora."""
    engine, tela = roteiro(["mw_animation"], MasterworkGoal(affix=ALVO))
    engine.ESCAPE_SETTLE_S = 0.01

    começo = time.monotonic()
    engine.run()

    assert tela.instantes, "nenhum ESC foi enviado"
    assert tela.instantes[0] - começo >= 0.24, "o primeiro ESC saiu sem a pausa"


def test_o_teto_de_esc_nao_da_para_desligar(roteiro):
    """Não é preferência do usuário: é o que impede tecla às cegas em laço."""
    engine, _ = roteiro(["mw_animation"])
    assert engine.MAX_ESCAPES <= 6
    assert "MAX_ESCAPES" in type(engine).__dict__


# --------------------------------------------------- na dúvida, parar

def test_para_quando_nao_consegue_ler_o_afixo(roteiro, mw_shots):
    """Sem saber qual afixo está no item, rerrolar pode passar por cima do
    certo — e são 10.000.000 para descobrir que era ele."""
    import numpy as np

    from d4forge.masterwork.profile import DEFAULT_MW_PROFILE

    img = mw_shots["mw_affix"].copy()
    prof = DEFAULT_MW_PROFILE.scaled(Rect(0, 0, img.shape[1], img.shape[0]))
    r = prof.affix_text
    img[r.y:r.y + r.h, r.x:r.x + r.w] = 0     # apaga só a caixa do afixo

    engine, tela = roteiro(
        ["mw_ilegivel"], MasterworkGoal(affix=ALVO),
        extras={"mw_ilegivel": img},
    )
    resultado = engine.run()

    assert not resultado.found
    assert resultado.reason_key == "mw.unreadable_stop"
    assert tela.cliques == [], "não pode ter gasto um reroll sem saber o que tinha"


def _sem_botao(mw_shots):
    """A tela do afixo com o interior do Upgrade apagado."""
    from d4forge.masterwork.profile import DEFAULT_MW_PROFILE

    img = mw_shots["mw_affix"].copy()
    prof = DEFAULT_MW_PROFILE.scaled(Rect(0, 0, img.shape[1], img.shape[0]))
    r = prof.upgrade_button
    img[r.y:r.y + r.h, r.x:r.x + r.w] = 0
    return img


def test_para_quando_o_upgrade_esta_cinza(roteiro, mw_shots):
    """Sem ouro, sem material, ou item no teto: o botão fica apagado e FICA."""
    engine, tela = roteiro(
        ["mw_sem_recurso"], MasterworkGoal(affix="Strength"),
        extras={"mw_sem_recurso": _sem_botao(mw_shots)},
    )
    engine.UPGRADE_CONFIRM_S = 0.2
    resultado = engine.run()

    assert not resultado.found
    assert resultado.reason_key == "mw.cannot_upgrade"
    assert tela.cliques == []


def test_um_quadro_rasgado_nao_conta_como_botao_cinza(roteiro, mw_shots):
    """O bug que parou a sessão do usuário.

    Num quadro salvo pelo próprio ciclo, o painel inteiro havia desenhado — o
    "Current Masterwork Affix" lia-se sem esforço — e só o interior do botão
    veio preto, com a moldura vermelha intacta. Uma volta depois ele media
    0.0461 outra vez. "Cinza" é uma AUSÊNCIA de tinta, e ausência é o sinal
    frágil: um quadro só não pode encerrar a sessão.
    """
    img = mw_shots["mw_affix"]
    rasgado = _sem_botao(mw_shots)

    engine, tela = roteiro(
        ["mw_affix"], MasterworkGoal(affix="Strength"),
        limits=MasterworkLimits(max_attempts=1, max_minutes=None),
    )
    engine.UPGRADE_CONFIRM_S = 1.0
    # Primeiro quadro rasgado, os seguintes bons — como no jogo.
    quadros = [rasgado, rasgado, img]
    engine.capture.grab = lambda _r: quadros.pop(0) if quadros else img

    resultado = engine.run()

    # Chegou ao teto de tentativas, e NÃO parou dizendo que o botão está cinza.
    assert resultado.reason_key == "stop.max_attempts", resultado.reason
    assert resultado.reason_key != "mw.cannot_upgrade"


def test_alvo_vazio_aceita_a_primeira_leitura_boa(roteiro):
    """Sem alvo não há o que perseguir, e rerrolar às cegas queima ouro sem
    critério nenhum. Quem impede a sessão de começar assim é a GUI."""
    engine, _ = roteiro(["mw_affix"], MasterworkGoal(affix=""))
    resultado = engine.run()

    assert resultado.found
    assert resultado.reason_key == "mw.got_any"


# ------------------------------------------------------------- a meta

def test_afixo_parecido_nao_encerra_a_sessao():
    """"Damage with Slashing Weapons" não é "Damage with Two-Handed Slashing
    Weapons" — dá 0.847 de similaridade, abaixo da barra."""
    from d4forge.affixes import parse_affix

    lido = MasterworkAffix(
        raw="+80.0% Damage with Two-Handed Slashing Weapons",
        parsed=parse_affix("+80.0% Damage with Two-Handed Slashing Weapons"),
    )
    aceita, chave, _ = MasterworkGoal(affix="Damage with Slashing Weapons").accepts(lido)
    assert not aceita and chave == "mw.other_affix"

    aceita, chave, _ = MasterworkGoal(affix=ALVO).accepts(lido)
    assert aceita and chave == "mw.got_target"


def test_leitura_ruim_nunca_vira_acerto():
    aceita, chave, _ = MasterworkGoal(affix=ALVO).accepts(MasterworkAffix(raw="???"))
    assert not aceita and chave == "mw.unreadable"


# ------------------------------------------- confirmação da leitura

def test_a_confirmacao_compara_o_afixo_e_nao_o_texto_cru():
    """Exigir o texto cru igual é exigir que o OCR erre igual duas vezes.

    Foi o que travou uma sessão real: um glifo de borda aparecia numa leitura e
    sumia na outra, a confirmação nunca fechava, e depois de 3 s o ciclo parava
    dizendo que não conseguiu ler um "+242 Strength" que estava na tela.
    """
    from d4forge.affixes import parse_affix
    from d4forge.masterwork.engine import MasterworkEngine as ME

    com_lixo = MasterworkAffix(raw="+242 Strength", parsed=parse_affix("+242 Strength"))
    limpo = MasterworkAffix(raw="+242  Strength", parsed=parse_affix("+242 Strength"))
    outro = MasterworkAffix(raw="+242 Armor", parsed=parse_affix("+242 Armor"))
    ilegivel = MasterworkAffix(raw="???")

    assert com_lixo.raw != limpo.raw          # o texto cru difere...
    assert ME._mesma_leitura(com_lixo, limpo)  # ...e mesmo assim concordam

    assert not ME._mesma_leitura(com_lixo, outro)
    assert not ME._mesma_leitura(com_lixo, ilegivel)
    assert not ME._mesma_leitura(ilegivel, ilegivel), "duas ilegíveis não confirmam nada"
    assert not ME._mesma_leitura(com_lixo, None)


def test_le_o_afixo_mesmo_com_a_caixa_em_branco_no_primeiro_quadro(roteiro, mw_shots):
    """Logo depois do reroll o jogo apaga a caixa antes de repintá-la — num
    quadro de depuração real a região do afixo saiu preta. Guardar esse branco
    como "leitura anterior" reiniciaria a confirmação a cada volta."""
    from d4forge.masterwork.profile import DEFAULT_MW_PROFILE

    img = mw_shots["mw_affix"]
    prof = DEFAULT_MW_PROFILE.scaled(Rect(0, 0, img.shape[1], img.shape[0]))
    branco = img.copy()
    r = prof.affix_text
    branco[r.y:r.y + r.h, r.x:r.x + r.w] = 0

    # A tela alterna entre a caixa em branco e a caixa pintada, sem clique
    # nenhum no meio — é o que a repintura faz.
    engine, tela = roteiro(
        ["mw_repintando", "mw_affix"], MasterworkGoal(affix=ALVO),
        extras={"mw_repintando": branco},
    )
    engine.capture.grab = lambda _r, _c=[0]: (
        _c.__setitem__(0, _c[0] + 1) or (branco if _c[0] % 2 else img)
    )

    resultado = engine.run()
    assert resultado.found, resultado.reason
    assert resultado.reason_key == "mw.got_target"


# ------------------------------------------------------ jogo em foco

def test_roda_com_o_jogo_em_foco(roteiro):
    """Este caminho não era exercitado por nenhum teste: todos rodavam com
    `require_foreground=False`, então a linha que consulta a janela nunca era
    executada. Ela tinha o nome do atributo errado, e a primeira tentativa de
    verdade morria em `'GameWindow' object has no attribute 'foreground'`.
    """
    engine, _ = roteiro(
        ["mw_affix"], MasterworkGoal(affix=ALVO),
        require_foreground=True, foreground=True,
    )
    resultado = engine.run()
    assert resultado.found, resultado.reason


def test_para_se_o_jogo_nao_esta_em_primeiro_plano(roteiro):
    engine, tela = roteiro(
        ["mw_affix"], MasterworkGoal(affix=ALVO),
        require_foreground=True, foreground=False,
    )
    resultado = engine.run()

    assert not resultado.found
    # Chave genérica: a `stop.not_foreground` manda apertar F9, que é a tecla
    # do encantamento e não a deste fluxo.
    assert resultado.reason_key == "stop.lost_focus"
    assert tela.cliques == [] and tela.teclas == []


def test_a_janela_falsa_nao_inventa_atributo(roteiro):
    """Se a janela de mentira aceitar um nome que a de verdade não tem, ela para
    de servir para testar — foi assim que o bug do `foreground` passou."""
    engine, _ = roteiro(["mw_affix"])
    janela = engine._frame.__globals__["find_game_window"]()
    assert isinstance(janela, GameWindow)
    assert not hasattr(janela, "foreground")
    assert hasattr(janela, "is_foreground")


def test_estados_do_painel_sao_os_dois_com_ferreiro_aberto():
    from d4forge.masterwork.engine import PANEL_STATES

    assert set(PANEL_STATES) == {MasterworkState.STEP, MasterworkState.AFFIX}
    assert MasterworkState.ANIMATION not in PANEL_STATES
    assert MasterworkState.UNKNOWN not in PANEL_STATES
