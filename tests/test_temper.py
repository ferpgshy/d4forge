"""Fundação do Tempering, contra as cinco telas reais do Ferreiro.

O critério de aceite aqui é mais simples que o do encantamento por um motivo
concreto: o jogo mostra o intervalo na própria tela do resultado
(`+8.4% ... [5.0 - 10.0]`), então "isto é um Greater Affix?" sai da linha lida,
sem catálogo e sem faixas cadastradas à mão.
"""

import pytest

from d4forge.geometry import Rect
from d4forge.temper import (
    DEFAULT_TEMPER_PROFILE,
    TemperState,
    button_active,
    detect_temper_state,
    parse_temper_result,
    read_text_lines,
)
from d4forge.temper.result import TemperResult, text_bands


def _perfil(img):
    return DEFAULT_TEMPER_PROFILE.scaled(Rect(0, 0, img.shape[1], img.shape[0]))


# ------------------------------------------------------------- estados

@pytest.mark.parametrize("tela,esperado", [
    ("temper_idle", TemperState.IDLE),
    ("temper_no_recipe", TemperState.IDLE),
    ("temper_recipes", TemperState.RECIPES),
    ("temper_animation", TemperState.ANIMATION),
    ("temper_result", TemperState.RESULT),
])
def test_reconhece_as_cinco_telas(temper_shots, tela, esperado):
    img = temper_shots[tela]
    assert detect_temper_state(img, _perfil(img)).state is esperado


def test_animacao_e_resultado_nao_se_confundem(temper_shots):
    """Skip e Close ocupam o mesmo retângulo e as duas telas têm o mesmo
    cabeçalho, então nem o botão nem o cabeçalho servem de discriminador. Quem
    separa é haver texto de afixo na tela."""
    from d4forge.temper.result import has_text_lines

    anim, res = temper_shots["temper_animation"], temper_shots["temper_result"]

    # o botão é o mesmo pixel nas duas (a menos do arredondamento de escala)
    a, r = _perfil(anim).skip_or_close, _perfil(res).skip_or_close
    assert abs(a.x - r.x) <= 2 and abs(a.y - r.y) <= 2

    assert has_text_lines(res, _perfil(res).result_text)
    assert not has_text_lines(anim, _perfil(anim).result_text)


def test_animacao_nao_e_julgada_pelo_brilho(temper_shots):
    """A animação pulsa: um quadro mais claro não pode virar 'resultado'. A
    checagem é de forma — um brilho de 83x84 nunca vira linha de texto."""
    import numpy as np

    from d4forge.temper.result import has_text_lines

    anim = temper_shots["temper_animation"]
    prof = _perfil(anim)
    for ganho in (1.5, 2.0, 3.0):
        clareado = np.clip(anim.astype(float) * ganho, 0, 255).astype(np.uint8)
        assert not has_text_lines(clareado, prof.result_text), f"ganho {ganho}"


def test_tela_preta_nao_vira_estado_valido(temper_shots):
    """Se o jogo estiver noutra tela, é melhor dizer 'não sei' do que clicar."""
    img = temper_shots["temper_idle"] * 0
    assert detect_temper_state(img, _perfil(img)).state is TemperState.UNKNOWN


# -------------------------------------------------------------- botões

def test_temper_item_aceso_x_cinza(temper_shots):
    """O sinal que conduz o ciclo. Medido: 0.080 de tinta com o botão
    habilitado contra 0.000 quando cinza — o texto apagado nem chega ao limiar
    de brilho, então a separação é total."""
    com = temper_shots["temper_idle"]
    sem = temper_shots["temper_no_recipe"]

    assert button_active(com, _perfil(com).temper_button)
    assert not button_active(sem, _perfil(sem).temper_button)


def test_leitura_do_botao_vem_junto_do_estado(temper_shots):
    img = temper_shots["temper_idle"]
    leitura = detect_temper_state(img, _perfil(img))
    assert leitura.state is TemperState.IDLE
    assert leitura.can_temper

    img = temper_shots["temper_no_recipe"]
    leitura = detect_temper_state(img, _perfil(img))
    assert leitura.state is TemperState.IDLE
    assert not leitura.can_temper


def test_ponto_de_estacionamento_nao_encosta_no_que_lemos(temper_shots):
    """O cursor do jogo entra na captura. Parado sobre o botão circular, ele
    somava pixels acesos justamente na região que decide "dá para recarregar" —
    o botão apagava ao encher o item e a leitura continuava dizendo "aceso",
    então o ciclo clicava sem parar, gastando um Pergaminho por volta.

    O ponto de descanso tem de ficar fora de TODA região lida."""
    img = temper_shots["temper_idle"]
    prof = _perfil(img)
    parada = prof.cursor_park

    lidas = [
        prof.blacksmith_header, prof.tempering_tab, prof.recharge_button,
        prof.rerolls_remaining, prof.temper_button, prof.recipes_title,
        prof.modal_header, prof.complete_title, prof.result_text,
    ]
    for roi in lidas:
        sobrepoe = not (
            parada.right <= roi.left or parada.left >= roi.right
            or parada.bottom <= roi.top or parada.top >= roi.bottom
        )
        assert not sobrepoe, f"o cursor pousaria dentro de {roi.as_tuple()}"


def test_ponto_de_estacionamento_e_vazio_nas_telas(temper_shots):
    """E tem de ser um lugar morto: se houvesse arte ali, o próprio ponto
    poderia ser confundido com conteúdo em alguma checagem futura."""
    from d4forge.temper.states import ink

    for tela in ("temper_idle", "temper_no_rerolls", "temper_no_recipe",
                 "temper_new_affix", "temper_animation", "temper_result"):
        img = temper_shots[tela]
        assert ink(img, _perfil(img).cursor_park) < 0.01, tela


def test_tabela_de_decisao_completa(temper_shots):
    """Os três sinais que conduzem o ciclo, nas três telas que os produzem.

    Nenhum depende de OCR: são ~0,1 ms cada e não erram dígito. Medido, a
    separação é total — 0,2736 contra 0,0000 no circular, 0,0804 contra 0,0000
    no Temper Item, 0,075 contra 0,000 na linha de rerolls."""
    esperado = {
        # tela                 receita  temperar  recarregar
        "temper_idle":        (True,    True,     False),  # 5 de 5 rerolls
        "temper_no_rerolls":  (True,    False,    True),   # zerou; dá p/ recarregar
        "temper_no_recipe":   (False,   False,    False),  # nem receita há
    }
    for tela, (receita, temperar, recarregar) in esperado.items():
        img = temper_shots[tela]
        r = detect_temper_state(img, _perfil(img))
        assert r.state is TemperState.IDLE, tela
        assert r.has_rerolls is receita, tela
        assert r.can_temper is temperar, tela
        assert r.can_recharge is recarregar, tela


def test_slot_livre_tem_receita_mas_nao_tem_contador(temper_shots):
    """Regressão do jogo real: o ciclo parou dizendo "nenhuma receita escolhida"
    com a receita escolhida.

    Num slot LIVRE o jogo escreve "Adds your selected affix", não mostra
    contador de rerolls, e o botão diz só "Temper Item" — porque ali se ADICIONA
    um afixo em vez de rerrolar. O botão está aceso; era o contador ausente que
    o motor lia como "sem receita"."""
    img = temper_shots["temper_new_affix"]
    r = detect_temper_state(img, _perfil(img))

    assert r.state is TemperState.IDLE
    assert r.can_temper, "o botão está aceso: o jogo diz que dá para temperar"
    assert not r.has_rerolls, "e mesmo assim não há contador de rerolls"


def test_sem_receita_nao_se_confunde_com_rerolls_zerados(temper_shots):
    """As duas telas deixam o Temper Item cinza igual, mas pedem ações opostas:
    uma é 'escolha a receita', a outra é 'recarregue'. Quem separa é a linha
    `Temper Rerolls Remaining`, que só existe depois da receita escolhida."""
    sem_receita = detect_temper_state(
        temper_shots["temper_no_recipe"], _perfil(temper_shots["temper_no_recipe"])
    )
    sem_rolls = detect_temper_state(
        temper_shots["temper_no_rerolls"], _perfil(temper_shots["temper_no_rerolls"])
    )

    assert not sem_receita.can_temper and not sem_rolls.can_temper
    assert not sem_receita.has_rerolls
    assert sem_rolls.has_rerolls


# ----------------------------------------------------- leitura do texto

def test_le_o_afixo_sorteado_nas_duas_linhas(temper_shots, ocr):
    """A regressão que motivou `read_text_lines`: uma ROI única cobrindo as
    duas linhas volta VAZIA do detector em toda escala de render, enquanto cada
    linha isolada lê perfeito."""
    img = temper_shots["temper_result"]
    texto = read_text_lines(img, _perfil(img).result_text, ocr)

    assert "Lucky Hit" in texto
    assert "8.4%" in texto
    assert "[5.0 - 10.0]" in texto


def test_roi_unica_das_duas_linhas_nao_funciona(temper_shots, ocr):
    """Fixa o motivo de `read_text_lines` existir. Se um dia o detector passar
    a dar conta do bloco inteiro, este teste falha e o código pode simplificar."""
    img = temper_shots["temper_result"]
    direto = ocr.read(_perfil(img).result_text.crop(img)).text

    assert "10.0" not in direto, f"agora funciona: {direto!r}"


def test_ga_e_roll_normal_do_mesmo_afixo(temper_shots, ocr):
    """O teste que vale mais que todos os outros deste arquivo: duas capturas do
    MESMO afixo (Attack Speed), uma normal e uma GA, do jogo real.

    É o que prova o sinal de parada de ponta a ponta — da tela até a decisão —
    em vez de provar só o parser contra texto que eu digitei."""
    casos = {
        "temper_result_normal": ("+4.6% Attack Speed [4.0 - 8.0]%", 4.6, False),
        "temper_result_ga": ("+10.0% Attack Speed", 10.0, True),
    }
    for tela, (texto_esperado, valor, e_ga) in casos.items():
        img = temper_shots[tela]
        prof = _perfil(img)

        assert detect_temper_state(img, prof).state is TemperState.RESULT, tela

        texto = read_text_lines(img, prof.result_text, ocr)
        assert texto == texto_esperado, tela

        r = parse_temper_result(texto)
        assert r.readable, tela
        assert r.value == valor, tela
        assert r.greater is e_ga, tela


def test_linha_curta_de_ga_ainda_conta_como_texto(temper_shots):
    """`+10.0% Attack Speed` é bem mais curta que as outras linhas de resultado.
    Se a checagem de forma exigisse largura demais, a tela do GA seria lida como
    animação — e o ciclo rolaria por cima do GA."""
    from d4forge.temper.result import has_text_lines

    img = temper_shots["temper_result_ga"]
    assert has_text_lines(img, _perfil(img).result_text)


@pytest.mark.parametrize("largura", [201, 150, 120, 90, 60])
def test_ga_curto_nao_e_confundido_com_animacao(temper_shots, largura):
    """A regressão que custou um Greater Affix no jogo real.

    A linha `+10.0% Attack Speed` mede 201 px e o limiar de largura era 150 —
    passava por pouco. Um GA de nome curto (`+3,125 Armor`) fica abaixo, a tela
    virava 'animação', o motor clicava Skip (que ali é o Close) e rolava por
    cima do GA sem nunca tê-lo lido.

    Aqui a linha real é recortada em larguras cada vez menores para provar que
    o comprimento do nome do afixo não decide mais nada.
    """
    import numpy as np

    import numpy as np

    from d4forge.temper.result import has_text_lines
    from d4forge.vision.preprocess import binarize, to_gray

    img = temper_shots["temper_result_ga"].copy()
    prof = _perfil(img)
    roi = prof.result_text

    # A linha vem CENTRADA no modal, não colada na borda da ROI: cortar a
    # partir de `roi.x` apagaria o texto inteiro em vez de encurtá-lo. O corte
    # tem de partir de onde a tinta realmente começa.
    mask = binarize(to_gray(roi.crop(img)), 120)
    inicio = roi.x + int(np.flatnonzero(mask.any(axis=0))[0])
    img[roi.y:roi.y + roi.h, inicio + largura:roi.x + roi.w] = 0

    # A forma sozinha tem de bastar. Sem este assert o teste passaria só pelo
    # título "TEMPER COMPLETE", que fica fora do recorte — e um limiar de
    # largura errado voltaria a passar despercebido.
    assert has_text_lines(img, roi), f"linha de {largura}px deixou de ser texto"
    assert detect_temper_state(img, prof).state is TemperState.RESULT, (
        f"GA de {largura}px virou animação — seria rolado por cima"
    )


def test_titulo_lido_separa_resultado_de_animacao(temper_shots, ocr):
    """A autoridade passou a ser LER o título, não medir tinta.

    "TEMPER COMPLETE" é texto fixo: comparar texto não tem limiar para calibrar,
    e foi um limiar — a largura mínima de linha — que deixou passar um GA."""
    from d4forge.temper.states import _reads_complete

    for tela in ("temper_result", "temper_result_normal", "temper_result_ga"):
        img = temper_shots[tela]
        assert _reads_complete(img, _perfil(img), ocr), tela

    anim = temper_shots["temper_animation"]
    assert not _reads_complete(anim, _perfil(anim), ocr)


def test_titulo_resiste_ao_pulsar_da_animacao(temper_shots, ocr):
    """A animação é um brilho que muda de quadro a quadro. Medir tinta obriga a
    escolher um corte entre 0,053 e 0,169; ler o texto não."""
    import numpy as np

    from d4forge.temper.states import _reads_complete

    anim = temper_shots["temper_animation"]
    prof = _perfil(anim)
    for ganho in (1.5, 2.5, 4.0):
        claro = np.clip(anim.astype(float) * ganho, 0, 255).astype(np.uint8)
        assert not _reads_complete(claro, prof, ocr), f"ganho {ganho}"


def test_sem_ocr_a_forma_ainda_decide(temper_shots):
    """A leitura é a autoridade, mas não pode ser um requisito: sem OCR o
    detector continua funcionando pela forma."""
    for tela, esperado in (
        ("temper_result_ga", TemperState.RESULT),
        ("temper_animation", TemperState.ANIMATION),
    ):
        img = temper_shots[tela]
        assert detect_temper_state(img, _perfil(img), ocr=None).state is esperado


def test_animacao_lida_como_resultado_e_o_erro_barato(temper_shots, ocr):
    """A troca oposta não é simétrica, e é por isso que o viés é este.

    Se a animação for tomada por resultado, o motor lê lixo, `readable` falha e
    o ciclo PARA — chato e reversível. Se o resultado for tomado por animação,
    um GA vai embora e o Tempering substitui o afixo: não tem desfazer.
    """
    from d4forge.temper.result import parse_temper_result

    img = temper_shots["temper_animation"]
    texto = read_text_lines(img, _perfil(img).result_text, ocr)

    assert not parse_temper_result(texto).readable


def test_le_quantos_rerolls_restam(temper_shots, ocr):
    img = temper_shots["temper_idle"]
    texto = read_text_lines(img, _perfil(img).rerolls_remaining, ocr)
    assert "Temper Rerolls Remaining" in texto
    assert texto.rstrip().endswith("5")


def test_bandas_separam_as_linhas(temper_shots):
    import numpy as np

    from d4forge.vision.preprocess import binarize, to_gray

    img = temper_shots["temper_result"]
    crop = _perfil(img).result_text.crop(img)
    assert len(text_bands(binarize(to_gray(crop), 120))) == 2


# ------------------------------------------------------------- decisão

def test_extrai_valor_e_intervalo_da_linha_real():
    """Resultado de duas linhas, colhido do jogo."""
    texto = (
        "Lucky Hit: Up to a +8.4% Chance to Make Enemies Vulnerable for "
        "2 Seconds [5.0 - 10.0]%[2]"
    )
    r = parse_temper_result(texto)

    assert r.value == 8.4
    assert (r.low, r.high) == (5.0, 10.0)
    assert r.readable
    assert not r.greater
    assert r.fraction == pytest.approx(0.68)


def test_resultado_de_uma_linha_so():
    """Colhido do jogo: nem todo resultado quebra em duas linhas."""
    r = parse_temper_result("+68.0% Damage while Berserking [40.0 - 80.0]%")

    assert r.value == 68.0
    assert (r.low, r.high) == (40.0, 80.0)
    assert not r.greater
    assert r.fraction == pytest.approx(0.7)


def test_ga_e_a_ausencia_do_intervalo():
    """O sinal de GA é estrutural, não numérico: num roll normal o jogo escreve
    o intervalo junto do valor; num GA ele mostra só o valor.

    Isso é melhor do que comparar números — um dígito lido errado não inverte a
    decisão."""
    normal = parse_temper_result("+1,738 Physical Resistance [1,500 - 2,500]")
    ga = parse_temper_result("+3,125 Physical Resistance")

    assert normal.readable and not normal.greater
    assert ga.readable and ga.greater
    assert ga.value == 3125
    assert not ga.has_range


@pytest.mark.parametrize("texto", [
    "+2,404 Poison Resistance [1,500 - 2,500]",       # como o jogo escreve
    "+2,404 Poison Resistance [1,500 – 2,500]",       # traço EN
    "+2,404 Poison Resistance [1,500 — 2,500]",       # travessão
    "+2,404 Poison Resistance (1,500 - 2,500)",       # parênteses
    "+2,404 Poison Resistance [1,500 - 2,500)",       # um colchete só
    "+2,404 Poison Resistance 1,500 - 2,500",         # sem colchete nenhum
    "+2,404 Poison Resi nce [1,500 ~ 2,500]",         # nome e traço truncados
])
def test_intervalo_sobrevive_a_grafia_que_o_ocr_escolher(texto):
    """A regressão que encerrou uma sessão no jogo real.

    Com `[1,500 - 2,500]` na tela, bastava o OCR ler travessão no lugar do
    hífen, ou perder um colchete, para o intervalo "sumir" — e sumir é
    exatamente o que este código entende por Greater Affix. Um roll comum de
    2.404 virava GA e parava tudo.

    A pontuação é o que o reconhecedor menos acerta; os dígitos são o que ele
    mais acerta. O padrão passou a olhar os números."""
    r = parse_temper_result(texto)

    assert (r.low, r.high) == (1500, 2500), texto
    assert r.value == 2404
    assert not r.greater, "roll de 2.404 dentro de 1.500–2.500 não é GA"


def test_intervalo_com_digito_comido_ainda_conta_como_intervalo():
    """Regressão de uma sessão real: a tela dizia `[2.5 - 5.0]` e o OCR leu
    `. 5 - 5.0`. O par virou (5, 5.0), `low < high` reprovou, o intervalo
    "sumiu" — e sumir é o que este código chama de Greater Affix.

    Um intervalo de verdade sempre tem low menor que high, então `low == high`
    só aparece quando um dígito se perdeu. Aceitar mesmo assim é o lado seguro:
    significa "havia um intervalo aqui", que é o oposto de GA."""
    texto = (
        "Lucky Hit: Up to a +5.0% Chanet : to Make Enermies Vulnerable for "
        "2 Seconds: . 5 - 5.0]%[2]"
    )
    from d4forge.temper.rules import TemperGoal

    r = parse_temper_result(texto)

    assert r.has_range, "o intervalo estava na tela; não pode virar GA"
    assert not r.greater
    assert r.value == 5.0
    # E não pode parar a sessão por "leitura duvidosa" tampouco: a pergunta que
    # importa — havia intervalo? — foi respondida.
    assert r.readable
    assert TemperGoal(require_greater=True).accepts(r)[1] == "temper.keep_rolling"


@pytest.mark.parametrize("texto,valor", [
    # Sem sinal nenhum — o caso que parou uma sessão com o texto lido certo.
    ("4.1% Cooldown Reduction [3.0 - 6.0]%", 4.1),
    ("6.0% Cooldown Reduction", 6.0),
    # Multiplicador: começa com "x".
    ("x25% Critical Strike Damage Multiplier [13 - 25]%", 25),
    # E os que já levam "+" continuam valendo.
    ("+2,404 Poison Resistance [1,500 - 2,500]", 2404),
    ("+1 to Brawling Skills [1 - 2]", 1),
])
def test_valor_nao_depende_de_sinal_na_frente(texto, valor):
    """Nem todo afixo escreve "+" antes do número.

    Exigir o sinal fazia o valor sair como None, a leitura ser dada como
    duvidosa e o ciclo parar — com a linha lida corretamente na tela, o que
    torna o defeito especialmente confuso de diagnosticar."""
    r = parse_temper_result(texto)
    assert r.value == valor
    assert r.readable


def test_valor_e_o_primeiro_numero_e_nao_o_do_intervalo():
    """Se o valor fosse buscado na frase inteira, um afixo sem sinal pegaria o
    limite inferior do intervalo em vez do roll."""
    r = parse_temper_result("4.1% Cooldown Reduction [3.0 - 6.0]%")
    assert r.value == 4.1
    assert (r.low, r.high) == (3.0, 6.0)


def test_intervalo_e_o_ultimo_par_da_linha():
    """O meio da frase também tem números. Em "…for 2 Seconds [5.0 - 10.0]%[2]",
    o par (2, 5.0) casa com o padrão tão bem quanto o verdadeiro — e o sufixo
    `%[2]` ainda forma (10.0, 2), que `low < high` descarta."""
    r = parse_temper_result(
        "Lucky Hit: Up to a +8.4% Chance to Make Enemies Vulnerable for "
        "2 Seconds [5.0 - 10.0]%[2]"
    )
    assert (r.low, r.high) == (5.0, 10.0)
    assert r.value == 8.4


def test_o_colchete_decide_e_nao_o_numero():
    """O veredito de Greater Affix não pode depender de acertar dígito.

    Comparar o valor com o teto da receita já esteve aqui e teve de sair: o
    teto é justamente o que o OCR erra. `[20.0 - 40.0]%` saía como
    `[20.0 - 401%` — o `]` virando `1` — rodada após rodada, até virar
    maioria. Com o teto em 401, um `+50.0%` legítimo foi julgado dentro da
    faixa e o ciclo ia rolar por cima dele.

    Colchete é presença, e presença não depende de dígito."""
    for faixa in (None, (20.0, 401.0), (20.0, 40.0), (1500.0, 2500.0)):
        ga = parse_temper_result(
            "+50.0% Damage with Tw : Handed Slashing Weapons"
        ).corroborated(faixa)
        assert ga.greater, f"faixa conhecida {faixa} não pode suprimir um GA"

        comum = parse_temper_result(
            "+23.0% Damage with Two-H Jed Slashing Weapons [20.0 - 4%"
        ).corroborated(faixa)
        assert not comum.greater, f"há colchete: não é GA, faixa {faixa}"


def test_sem_intervalo_conhecido_a_leitura_vale_como_esta():
    """Na primeira tentativa da sessão não há com o que corroborar."""
    r = parse_temper_result("+3,125 Poison Resistance").corroborated(None)
    assert r.greater


def test_colchete_sem_intervalo_montado_nao_e_ga():
    """A primeira rodada da sessão é a única desprotegida: não há intervalo
    anterior com que comparar. E foi lá que o erro apareceu no jogo.

    A tela mostrava `[5 - 12]` numa linha separada e o OCR devolveu `[52]` —
    o traço sumiu e os números colaram. Sem traço não há intervalo, e ausência
    de intervalo é o que este código chama de GA.

    O colchete é evidência de que o jogo mostrou uma faixa. Quando ele aparece
    e mesmo assim não montamos o intervalo, houve falha de leitura — não
    ausência de faixa."""
    lido = ("Lucky Hit: Up to a 15% Chance :: Restore +5 Primary Resource [52]")
    r = parse_temper_result(lido).corroborated(None)

    assert not r.greater, "colchete na linha: havia faixa, a leitura é que falhou"
    assert r.range_hidden
    assert r.readable, "o valor foi lido; dá para seguir rolando"
    assert r.value == 15


@pytest.mark.parametrize("texto", [
    "7.5% Cooldown Reduction",
    "+10.0% Attack Speed",
    "+3,125 Lightning Resistance",
])
def test_ga_de_verdade_nao_tem_colchete_nenhum(texto):
    """A contrapartida: é assim que o jogo escreve um Greater Affix. Sem
    colchete na linha, a ausência de intervalo é real."""
    r = parse_temper_result(texto).corroborated(None)
    assert r.greater
    assert not r.bracketed


def test_nome_ilegivel_sem_colchete_ainda_conta_como_ga():
    """`3.4% Cooldr*.. n Reduction` tem o nome destruído mas nenhum colchete.

    Antes o valor era comparado com a faixa da receita e isso o rebaixava a
    roll comum. Hoje não: a decisão é estrutural, então uma linha sem colchete
    encerra a sessão e você confere o item — o erro barato. O caro seria o
    contrário."""
    r = parse_temper_result("3.4% Cooldr*.. n Reduction").corroborated((3.0, 6.0))
    assert r.greater


def test_sufixo_de_colchete_unico_nao_e_intervalo():
    """A linha do Lucky Hit termina em `%[2]`. Um colchete com um número só não
    é intervalo — se fosse confundido, um GA viraria roll normal e o ciclo
    rolaria por cima dele."""
    r = parse_temper_result("+3.5% alguma coisa [2]")
    assert not r.has_range


def test_intervalo_invertido_nao_e_intervalo():
    """`[10.0 - 2.0]` não descreve faixa nenhuma; recusar é o certo. O que
    protege o veredito de GA daí em diante é a corroboração com o intervalo já
    visto na sessão, não este par."""
    r = parse_temper_result("+5 x [10.0 - 2.0]")
    assert not r.has_range
    assert not r.corroborated((1.0, 20.0)).greater


def test_numero_com_separador_nao_vira_intervalo():
    """`+3,125` é um número só. Se fosse partido em "3 a 125", um GA legítimo
    viraria roll comum — e o ciclo rolaria por cima dele."""
    for texto in ("+3,125 Poison Resistance", "+3.5% Dodge Chance",
                  "+1,450 Maximum Life"):
        assert not parse_temper_result(texto).has_range, texto


def test_separador_de_milhar_nao_vira_decimal():
    """`+3,000` é três mil, `+3.0` é três — e o OCR troca vírgula por ponto o
    tempo todo. A regra é a contagem de dígitos, não o caractere."""
    assert parse_temper_result("+3,000 x [1 - 2]").value == 3000
    assert parse_temper_result("+3.000 x [1 - 2]").value == 3000
    assert parse_temper_result("+3.0 x [1 - 2]").value == 3.0
    assert parse_temper_result("+8.4% x [5.0 - 10.0]").value == 8.4


def test_valor_vem_de_antes_do_intervalo():
    """O intervalo também tem números; capturar o primeiro da frase inteira
    pegaria o limite inferior em vez do roll."""
    r = parse_temper_result("Something [1,500 - 2,500]")
    assert r.value is None
    assert (r.low, r.high) == (1500, 2500)


def test_linha_sem_valor_nao_e_julgada():
    """Sem valor não há o que decidir. E aqui chutar é caro: o Tempering
    substitui o afixo que já está no item, então seguir rolando por engano
    passa por cima de um resultado que podia ser o bom."""
    r = parse_temper_result("Lucky Hit: alguma coisa ilegivel")
    assert not r.readable
    assert not r.greater
    assert r.fraction is None


def test_descricao_marca_o_ga():
    assert "GA" in TemperResult("x", 3125).describe()
    assert "GA" not in TemperResult("x", 1738, 1500, 2500).describe()
