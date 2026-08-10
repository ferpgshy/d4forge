"""Ciclo do Tempering, com a tela trocada por um roteiro falso.

A regra que domina este arquivo: o Tempering **substitui** o afixo que já está
no item. Então, na dúvida, o ciclo para — nunca continua rolando. Parar sem
necessidade custa tempo; continuar sem necessidade rola por cima do resultado
que o usuário queria.
"""

import pytest

from d4forge.geometry import Point, Rect
from d4forge.temper.engine import TemperEngine
from d4forge.temper.result import TemperResult
from d4forge.temper.rules import Recharge, TemperGoal, TemperLimits
from d4forge.temper.states import TemperState
from d4forge.vision.ocr import OcrEngine


class TelaRoteirizada:
    """Devolve telas de referência conforme um roteiro; cada clique avança."""

    def __init__(self, shots, sequencia):
        self.shots = shots
        self.sequencia = list(sequencia)
        self.passo = 0
        self.cliques: list[str] = []

    def grab(self, _region):
        return self.shots[self.sequencia[min(self.passo, len(self.sequencia) - 1)]]

    def close(self):
        pass

    def avanca(self, rect, _profile=None):
        """Substitui click_rect: registra onde clicou e avança o roteiro."""
        self.cliques.append(rect.as_tuple())
        self.passo = (self.passo + 1) % len(self.sequencia)
        return Point(0, 0)


@pytest.fixture
def parcialmente_cheio(temper_shots):
    """Estado real que não tenho capturado: rerolls acima de zero, abaixo do
    máximo — Temper Item aceso E botão circular aceso ao mesmo tempo.

    Composto do `temper_idle` (botão aceso, circular apagado por estar cheio)
    com o circular aceso recortado do `temper_no_rerolls`. É o estado em que o
    ciclo se encontra logo depois da primeira recarga, e é onde o modo "encher
    até o máximo" se distingue do "1 por vez"."""
    from d4forge.temper import DEFAULT_TEMPER_PROFILE

    img = temper_shots["temper_idle"].copy()
    aceso = temper_shots["temper_no_rerolls"]
    r = DEFAULT_TEMPER_PROFILE.scaled(
        Rect(0, 0, img.shape[1], img.shape[0])
    ).recharge_button
    img[r.y:r.y + r.h, r.x:r.x + r.w] = aceso[r.y:r.y + r.h, r.x:r.x + r.w]
    return img


@pytest.fixture
def roteiro(monkeypatch, temper_shots, tmp_path):
    def build(sequencia, goal=None, extras=None, **kwargs):
        telas = dict(temper_shots, **(extras or {}))
        img = telas["temper_idle"]
        client = Rect(0, 0, img.shape[1], img.shape[0])
        tela = TelaRoteirizada(telas, sequencia)

        class Janela:
            def __init__(self):
                self.client = client
                self.is_foreground = True

        monkeypatch.setattr("d4forge.temper.engine.find_game_window", lambda: Janela())
        monkeypatch.setattr("d4forge.temper.engine.click_rect", tela.avanca)

        engine = TemperEngine(
            goal=goal or TemperGoal(),
            ocr=OcrEngine(data_dir=tmp_path / "ocr"),
            limits=kwargs.pop("limits", TemperLimits(max_attempts=3, max_minutes=None)),
            capture=tela,
            poll_interval=0.001,
            state_timeout=1.0,
            require_foreground=False,
            **kwargs,
        )
        return engine, tela

    return build


# ------------------------------------------------------- caminho feliz

def test_para_no_greater_affix(roteiro):
    """O ciclo completo: temperar, pular a animação, ler, e encerrar no GA."""
    engine, tela = roteiro(
        ["temper_idle", "temper_animation", "temper_result_ga"],
        TemperGoal(require_greater=True),
    )

    resultado = engine.run()

    assert resultado.found, resultado.reason
    assert resultado.reason_key == "temper.got_ga"
    assert resultado.count == 1
    assert resultado.attempts[0].result.value == 10.0


def test_a_animacao_e_pulada_e_nao_esperada(roteiro):
    """A animação não é esperada até acabar: o ciclo clica em Skip.

    Os dois cliques do caminho feliz são, em ordem, o botão Temper Item e o
    Skip — e é justamente por isso que o ciclo não fica parado assistindo."""
    engine, tela = roteiro(
        ["temper_idle", "temper_animation", "temper_result_ga"],
        TemperGoal(require_greater=True),
    )
    engine.run()

    prof = engine._resolved

    assert tela.cliques == [
        prof.temper_button.as_tuple(),
        prof.skip_or_close.as_tuple(),
    ]


def test_roll_normal_nao_encerra_e_fecha_a_tela(roteiro):
    """Resultado com intervalo na linha não é GA: o ciclo clica Close e segue."""
    engine, tela = roteiro(
        ["temper_idle", "temper_animation", "temper_result_normal"],
        TemperGoal(require_greater=True),
        limits=TemperLimits(max_attempts=2, max_minutes=None),
    )

    resultado = engine.run()

    assert not resultado.found
    assert resultado.reason_key == "stop.max_attempts"
    assert all(not a.accepted for a in resultado.attempts)
    assert all(a.result.value == 4.6 for a in resultado.attempts)


# --------------------------------------------------- travas de segurança

def test_tempera_num_slot_livre_mesmo_sem_contador(roteiro):
    """A regressão que o usuário viu: parou dizendo "nenhuma receita escolhida"
    com a receita escolhida.

    Perguntar "tem contador de rerolls?" antes de "o botão está aceso?" invertia
    a autoridade. O botão aceso é o próprio jogo dizendo que dá para agir."""
    engine, tela = roteiro(
        ["temper_new_affix", "temper_animation", "temper_result_ga"],
        TemperGoal(require_greater=True),
    )

    resultado = engine.run()

    assert resultado.found, resultado.reason
    assert resultado.reason_key == "temper.got_ga"


def test_para_quando_nao_ha_receita_escolhida(roteiro):
    """Sem receita, `Temper Item` fica cinza — mas por um motivo diferente de
    'os rerolls acabaram', e a ação é outra."""
    engine, _ = roteiro(["temper_no_recipe"])

    resultado = engine.run()

    assert not resultado.found
    assert resultado.reason_key == "temper.no_recipe"


def test_nao_recarrega_sem_ser_mandado(roteiro):
    """Recarregar consome Pergaminhos. O padrão é parar e avisar — gastar
    recurso real sozinho, em laço, não pode ser o comportamento padrão."""
    engine, tela = roteiro(["temper_no_rerolls"], TemperGoal(recharge=Recharge.STOP))

    resultado = engine.run()

    assert not resultado.found
    assert resultado.reason_key == "temper.out_of_rerolls"
    assert resultado.recharges == 0
    assert tela.passo == 0, "não podia ter clicado em nada"


def test_encher_ate_o_maximo_nao_para_no_primeiro_reroll(roteiro, parcialmente_cheio):
    """O que o usuário viu: "encher até o máximo" enchia de um em um.

    Depois da primeira recarga o item tem 1 reroll, e aí o Temper Item ACENDE —
    com o circular ainda aceso, porque cheio não está. Como o ciclo pergunta
    "dá para temperar?" antes de tudo, ele temperava e nunca enchia.

    Encher é clicar ENQUANTO o circular seguir aceso; é ele que apaga ao bater
    o limite do item, e é esse apagar que define "cheio"."""
    engine, tela = roteiro(
        ["temper_no_rerolls", "parcial", "parcial", "temper_idle",
         "temper_animation", "temper_result_ga"],
        TemperGoal(require_greater=True, recharge=Recharge.FULL, max_recharges=9),
        extras={"parcial": parcialmente_cheio},
    )
    engine.RECHARGE_SETTLE_S = 0.0

    resultado = engine.run()

    assert resultado.found, resultado.reason
    assert resultado.recharges == 3, (
        "devia clicar nos três quadros com o circular aceso, e só parar quando "
        "ele apagou"
    )


def test_um_por_vez_volta_a_temperar_no_primeiro_reroll(roteiro, parcialmente_cheio):
    """O contraste: aqui a ideia é gastar o mínimo de Pergaminhos, então basta
    um reroll para voltar a temperar — mesmo com o circular ainda aceso."""
    engine, tela = roteiro(
        ["temper_no_rerolls", "parcial", "temper_animation", "temper_result_ga"],
        TemperGoal(require_greater=True, recharge=Recharge.ONE, max_recharges=9),
        extras={"parcial": parcialmente_cheio},
    )
    engine.RECHARGE_SETTLE_S = 0.0

    resultado = engine.run()

    assert resultado.found, resultado.reason
    assert resultado.recharges == 1


def test_recarga_nao_clica_infinito(roteiro):
    """O bug: com "sem limite" e o item nunca enchendo, o ciclo clicava para
    sempre — e cada clique gasta um Pergaminho.

    Tirar o teto obrigatório tirou junto a única saída do laço: sobrou "clicar
    até o botão circular apagar". Se o clique não pega, ou o botão não apaga,
    não havia mais nada segurando. A trava contra descontrole não é preferência
    do usuário e não pode ser desligada por ele."""
    engine, tela = roteiro(
        # a tela NUNCA sai de "sem rerolls": o circular fica aceso para sempre
        ["temper_no_rerolls"],
        TemperGoal(require_greater=True, recharge=Recharge.FULL,
                   max_recharges=None),
    )
    engine.RECHARGE_SETTLE_S = 0.0

    resultado = engine.run()

    assert not resultado.found
    assert resultado.reason_key == "temper.recharge_runaway"
    # Para no 3º clique sem efeito, não no teto de 12: uma recarga que funciona
    # acende o Temper Item, então três cliques que não acendem já provam o
    # problema. São 3 Pergaminhos perdidos em vez de 12.
    assert resultado.recharges == engine.MAX_DEAD_CLICKS


def test_temperar_zera_o_contador_de_descontrole(roteiro, parcialmente_cheio):
    """A trava não pode atrapalhar o uso normal: encher, temperar, encher de
    novo é o ciclo esperado numa sessão longa."""
    engine, tela = roteiro(
        ["temper_no_rerolls", "parcial", "temper_idle",
         "temper_animation", "temper_result_ga"],
        TemperGoal(require_greater=True, recharge=Recharge.FULL,
                   max_recharges=None),
        extras={"parcial": parcialmente_cheio},
    )
    engine.RECHARGE_SETTLE_S = 0.0

    resultado = engine.run()

    assert resultado.found, resultado.reason
    assert engine._burst == 0, "temperou, então o contador voltou a zero"


def test_so_recarrega_com_o_temper_item_cinza(roteiro):
    """Recarregar gasta Pergaminho, então só acontece quando não dá para
    temperar. Com o botão aceso, o ciclo tempera e não encosta no circular."""
    engine, tela = roteiro(
        ["temper_idle", "temper_animation", "temper_result_ga"],
        TemperGoal(require_greater=True, recharge=Recharge.FULL, max_recharges=9),
    )

    resultado = engine.run()

    assert resultado.found
    assert resultado.recharges == 0


def test_recarrega_quando_autorizado_e_respeita_o_teto(roteiro):
    """Com a recarga ligada, o teto de Pergaminhos da sessão é obedecido."""
    engine, _ = roteiro(
        ["temper_no_rerolls"],
        TemperGoal(recharge=Recharge.ONE, max_recharges=2),
    )

    resultado = engine.run()

    assert not resultado.found
    assert resultado.reason_key == "temper.recharge_limit"
    assert resultado.recharges == 2


def test_para_com_a_lista_de_receitas_aberta(roteiro):
    """Escolher receita é do usuário: clicar sozinho ali gastaria rerolls num
    afixo que ele não pediu."""
    engine, tela = roteiro(["temper_recipes"])

    resultado = engine.run()

    assert resultado.reason_key == "temper.recipes_open"
    assert tela.passo == 0


def test_tela_desconhecida_para_em_vez_de_clicar(roteiro, temper_shots):
    engine, tela = roteiro(["temper_idle"])
    tela.grab = lambda _r: temper_shots["temper_idle"] * 0

    resultado = engine.run()
    assert resultado.reason_key == "temper.unknown_screen"


def test_espera_a_tela_de_resultado_acabar_de_aparecer(roteiro, monkeypatch):
    """Regressão do jogo real: o ciclo parava em 0,6 s dizendo que não conseguiu
    ler o resultado.

    O TEMPER COMPLETE não surge inteiro de uma vez — o título aparece antes da
    linha do afixo. Lendo no primeiro quadro em que o título já está legível, a
    região do afixo ainda está vazia."""
    engine, _ = roteiro(
        ["temper_idle", "temper_animation", "temper_result_ga"],
        TemperGoal(require_greater=True),
    )
    engine.RESULT_SETTLE_S = 2.0

    # Os dois primeiros quadros da tela de resultado ainda não têm o afixo.
    leituras = iter([TemperResult(raw=""), TemperResult(raw="")])
    real = engine._read_result
    monkeypatch.setattr(
        engine, "_read_result",
        lambda f, p: next(leituras, None) or real(f, p),
    )

    resultado = engine.run()

    assert resultado.found, resultado.reason
    assert resultado.attempts[0].result.value == 10.0


def test_desiste_se_o_afixo_nunca_aparece(roteiro, monkeypatch):
    """A paciência é limitada: esperar para sempre travaria a sessão."""
    engine, _ = roteiro(
        ["temper_idle", "temper_animation", "temper_result_ga"],
        TemperGoal(require_greater=True),
    )
    engine.RESULT_SETTLE_S = 0.2
    monkeypatch.setattr(engine, "_read_result", lambda f, p: TemperResult(raw=""))

    resultado = engine.run()

    assert not resultado.found
    assert resultado.reason_key == "temper.unreadable_stop"


def test_resultado_ilegivel_para_o_ciclo(roteiro, monkeypatch, temper_shots):
    """A trava mais importante daqui. Se não dá para ler o que saiu, continuar
    rolaria por cima de um resultado que pode ser justamente o GA."""
    engine, _ = roteiro(
        ["temper_idle", "temper_animation", "temper_result_ga"],
        TemperGoal(require_greater=True),
    )
    monkeypatch.setattr(
        engine, "_read_result", lambda *a: TemperResult(raw="?!@ ilegivel")
    )

    resultado = engine.run()

    assert not resultado.found
    assert resultado.reason_key == "temper.unreadable_stop"
    assert resultado.count == 1


# --------------------------------------------------------- critérios

def test_criterio_por_fracao_do_intervalo():
    """GA é raro; quem só quer um roll alto usa o percentual do intervalo."""
    goal = TemperGoal(require_greater=False, min_fraction=0.9)

    baixo = TemperResult("x", 2000, 1500, 2500)     # 50%
    alto = TemperResult("x", 2400, 1500, 2500)      # 90%

    assert not goal.accepts(baixo)[0]
    assert goal.accepts(alto)[0]


def test_ga_satisfaz_o_criterio_de_fracao():
    """Um GA não tem intervalo, então não tem fração — mas é por definição
    melhor que qualquer roll de dentro da faixa."""
    goal = TemperGoal(require_greater=False, min_fraction=0.9)
    assert goal.accepts(TemperResult("x", 3125))[0]


def test_criterio_de_afixo_evita_parar_no_errado():
    """Algumas receitas sorteiam entre vários afixos. Sem este filtro, o ciclo
    pararia num GA do afixo que o usuário não queria."""
    goal = TemperGoal(require_greater=True, affix_contains="Attack Speed")

    certo = TemperResult("+10.0% Attack Speed", 10.0)
    errado = TemperResult("+12.0% Critical Strike Chance", 12.0)

    assert goal.accepts(certo)[0]
    aceita, chave, _ = goal.accepts(errado)
    assert not aceita and chave == "temper.other_affix"


def test_leitura_duvidosa_nunca_e_aceita():
    goal = TemperGoal(require_greater=True)
    aceita, chave, _ = goal.accepts(TemperResult(raw="lixo"))
    assert not aceita and chave == "temper.unreadable"
