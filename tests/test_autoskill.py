"""AutoSkill: leitura do HUD, binds e configuração.

As telas daqui são RECORTES do HUD — barra de habilidades, orbes e contador de
poção. O resto do quadro (nome do personagem, mapa, ouro) ficou de fora pelo
mesmo motivo das outras fixtures: este repositório é público.
"""

import numpy as np
import pytest

from d4forge.automation import binds
from d4forge.autoskill.profile import DEFAULT_AUTOSKILL_PROFILE, SLOTS
from d4forge.autoskill.rules import (
    AutoSkillConfig,
    Controle,
    ModoDeAtivacao,
    ModoDoSlot,
    SlotConfig,
)
from d4forge.autoskill.vision import LeitorDeCooldown, ler_vida
from d4forge.geometry import Rect
from d4forge.profile import ANCHOR_CENTER, ResolvedProfile

# Onde o recorte do HUD foi tirado do quadro de 1919x1079. Repor o recorte
# nessa posição devolve a geometria real, e é ela que o app vê.
HUD_X, HUD_Y = 430, 860
QUADRO_W, QUADRO_H = 1919, 1079

TELAS_HUD = {
    "pronto": "autoskill_pronto.png",
    "cd1": "autoskill_cd1.png",
    "cd2": "autoskill_cd2.png",
}

# Geometria do orbe dentro de cada recorte de vida, medida uma vez por
# HoughCircles. São arquivos fixos, então isto é dado de teste, não cálculo.
ORBES = {
    "autoskill_vida_cheia.png": (Rect(8, 14, 136, 136), 99),
    "autoskill_vida_alta.png": (Rect(34, 42, 156, 156), 61),
    "autoskill_vida_baixa.png": (Rect(4, 24, 168, 168), 44),
}


def _carrega(nome):
    from pathlib import Path

    from d4forge.imageio import imread

    caminho = Path(__file__).parent / "fixtures" / "telas" / nome
    if not caminho.exists():
        pytest.skip(f"fixture ausente: {nome}")
    img = imread(caminho)
    if img is None:
        pytest.skip(f"nao consegui ler {nome}")
    return img


@pytest.fixture(scope="module")
def huds():
    """Os recortes repostos num quadro do tamanho real."""
    telas = {}
    for chave, nome in TELAS_HUD.items():
        recorte = _carrega(nome)
        quadro = np.zeros((QUADRO_H, QUADRO_W, 3), dtype=np.uint8)
        alt, larg = recorte.shape[:2]
        quadro[HUD_Y:HUD_Y + alt, HUD_X:HUD_X + larg] = recorte
        telas[chave] = quadro
    return telas


@pytest.fixture
def perfil():
    return ResolvedProfile(
        DEFAULT_AUTOSKILL_PROFILE, Rect(0, 0, QUADRO_W, QUADRO_H)
    )


# ------------------------------------------------------------------ cooldown
@pytest.mark.parametrize(
    "tela, esperado",
    [
        ("pronto", [False] * 6),
        ("cd1", [True] + [False] * 5),
        ("cd2", [True, True] + [False] * 4),
    ],
)
def test_reconhece_quais_slots_estao_em_cooldown(huds, perfil, tela, esperado):
    """O ícone em cooldown fica escurecido. Medido nestes mesmos recortes: o
    brilho do decil mais claro cai de 226..234 para 89..94 — 130 pontos de
    margem, sem uma sobreposição."""
    leitor = LeitorDeCooldown(SLOTS)
    # O "pronto" primeiro para o leitor aprender o brilho normal de cada slot,
    # que é como o app roda: o primeiro quadro de jogo ensina a referência.
    leitor.ler(huds["pronto"], perfil.skill_slots)

    estados = leitor.ler(huds[tela], perfil.skill_slots)
    assert [e.em_cooldown for e in estados] == esperado


def test_a_referencia_de_brilho_so_sobe(huds, perfil):
    """Se ela acompanhasse a queda, o ícone escurecido viraria o novo "normal"
    em dois quadros e o cooldown nunca mais seria detectado."""
    leitor = LeitorDeCooldown(SLOTS)
    leitor.ler(huds["pronto"], perfil.skill_slots)
    antes = leitor.ler(huds["cd2"], perfil.skill_slots)[0].referencia

    for _ in range(5):
        estados = leitor.ler(huds["cd2"], perfil.skill_slots)

    assert estados[0].referencia == antes
    assert estados[0].em_cooldown, "cooldown sumiu depois de alguns quadros"


def test_sem_referencia_ainda_decide_pelo_limiar_de_partida(huds, perfil):
    """Primeiro quadro da sessão: o slot em cooldown tem de ser reconhecido
    mesmo antes de alguém revelar o brilho normal dele."""
    leitor = LeitorDeCooldown(SLOTS)
    estados = leitor.ler(huds["cd2"], perfil.skill_slots)
    assert [e.em_cooldown for e in estados] == [True, True] + [False] * 4


def test_cooldown_nao_olha_a_cor(huds, perfil):
    """São mais de cem habilidades, cada uma com a sua paleta. Trocar o matiz
    do ícone inteiro não pode mudar o veredito — só o brilho importa."""
    import cv2

    leitor = LeitorDeCooldown(SLOTS)
    leitor.ler(huds["pronto"], perfil.skill_slots)
    original = [e.em_cooldown for e in leitor.ler(huds["cd2"], perfil.skill_slots)]

    hsv = cv2.cvtColor(huds["cd2"], cv2.COLOR_BGR2HSV)
    hsv[..., 0] = (hsv[..., 0].astype(int) + 90) % 180
    girado = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

    outro = LeitorDeCooldown(SLOTS)
    outro.ler(huds["pronto"], perfil.skill_slots)
    assert [e.em_cooldown for e in outro.ler(girado, perfil.skill_slots)] == original


# ---------------------------------------------------------------------- vida
@pytest.mark.parametrize("nome, esperado", [(n, v) for n, (_, v) in ORBES.items()])
def test_le_a_vida_pela_borda_do_liquido(nome, esperado):
    rect, _ = ORBES[nome]
    leitura = ler_vida(_carrega(nome), rect)
    assert leitura.confiavel
    assert abs(leitura.porcentagem() - esperado) <= 3, leitura.descreve()


def test_com_escudo_a_leitura_e_conservadora(huds, perfil):
    """A regressão que MATAVA o personagem.

    O critério "o vazio é preto" é exato sem escudo, mas a barreira é azul —
    ou seja, não é preta. Com o orbe coberto, ele lia 99% com a vida no fim, a
    poção nunca saía, e o personagem morria de vida cheia no indicador.

    A vida por baixo do escudo não está na tela para ninguém. Então a leitura
    passa a ser a MENOR entre o preenchimento total e o nível do vermelho —
    errar para baixo custa uma carga de poção, errar para cima custa a vida.
    """
    for tela in ("cd1", "cd2"):          # os dois quadros têm barreira ativa
        leitura = ler_vida(huds[tela], perfil.health_orb)
        assert leitura.confiavel
        assert leitura.com_escudo, f"{tela}: deveria acusar escudo"
        assert leitura.barreira > 0.1
        # Conservadora: abaixo do que o critério otimista devolvia (99%).
        assert leitura.porcentagem() < 95, f"{tela}: {leitura.descreve()}"
        # E não pode desabar a ponto de beber poção à toa com a vida cheia.
        assert leitura.porcentagem() > 70, f"{tela}: {leitura.descreve()}"


def test_sem_escudo_a_leitura_nao_muda(huds, perfil):
    """A ressalva acima só vale quando há escudo: sem ele, o critério exato
    continua valendo inteiro."""
    leitura = ler_vida(huds["pronto"], perfil.health_orb)
    assert not leitura.com_escudo
    assert leitura.porcentagem() >= 95, leitura.descreve()


def test_orbe_todo_escuro_e_vida_no_fim():
    preto = np.zeros((300, 300, 3), dtype=np.uint8)
    leitura = ler_vida(preto, Rect(50, 50, 200, 200))
    assert leitura.confiavel
    assert leitura.porcentagem() == 0


# ------------------------------------------------------------------ geometria
def test_o_hud_e_ancorado_no_centro(perfil):
    """O bloco do HUD vai de x 454 a 1488 num quadro de 1919: meio em 971
    contra centro de tela 959. Preso à esquerda, ele sairia do lugar em
    ultrawide."""
    assert DEFAULT_AUTOSKILL_PROFILE.ANCORA_PADRAO == ANCHOR_CENTER
    assert perfil._anchor_for("skill_slots") == ANCHOR_CENTER
    assert perfil._anchor_for("health_orb") == ANCHOR_CENTER


def test_ultrawide_desloca_o_hud_junto_com_o_centro():
    largo = ResolvedProfile(DEFAULT_AUTOSKILL_PROFILE, Rect(0, 0, 3440, 1440))
    normal = ResolvedProfile(DEFAULT_AUTOSKILL_PROFILE, Rect(0, 0, 1920, 1080))
    assert largo.widescreen and not normal.widescreen

    # O centro do orbe tem de continuar à mesma distância do centro da tela.
    def desvio(p, tela_w):
        orbe = p.health_orb
        return (orbe.x + orbe.w / 2) - tela_w / 2

    assert abs(desvio(largo, 3440) / largo.scale
               - desvio(normal, 1920) / normal.scale) < 2


def test_o_perfil_do_enchant_nao_mudou_de_ancora():
    """A extensão que deixou o perfil declarar a própria âncora não podia
    mexer no que já existia."""
    from d4forge.profile import DEFAULT_PROFILE

    p = ResolvedProfile(DEFAULT_PROFILE, Rect(0, 0, 1920, 1080))
    assert p._anchor_for("affix_rows") != ANCHOR_CENTER
    assert p._anchor_for("confirm_accept") == ANCHOR_CENTER


# ----------------------------------------------------------------- binds
def test_bind_vai_e_volta_do_json():
    original = binds.tecla(0x51, "Q")
    assert binds.Bind.from_json(original.to_json()) == original
    assert binds.Bind.from_json(binds.botao_mouse(binds.VK_XBUTTON2).to_json()).codigo \
        == binds.VK_XBUTTON2


@pytest.mark.parametrize("lixo", [None, "", 42, {"tipo": "???"}, {"tipo": "key", "codigo": "x"}])
def test_bind_estragada_vira_vazia_e_nao_excecao(lixo):
    """O autoskill.json é editável à mão e guarda BINDS. Um valor inesperado
    não pode impedir o app de ABRIR."""
    assert not binds.Bind.from_json(lixo)


def test_tecla_estendida_ganha_o_prefixo():
    """O scancode da seta colide com o do teclado numérico; só o 0xE0 separa
    os dois. Sem isso, Seta-Direita chega ao jogo como "6"."""
    assert binds.scancode_de(0x27) & 0xE000      # seta direita
    assert not binds.scancode_de(0x51) & 0xE000  # Q


def test_roda_nao_serve_de_hotkey():
    """Ela não tem estado de "pressionada", só eventos — então não dá para
    perguntar se está segurada."""
    assert not binds.esta_pressionada(binds.roda(1))
    assert not binds.foi_pressionada(binds.roda(-1))


# ---------------------------------------------------------------- configuração
def test_config_vai_e_volta():
    cfg = AutoSkillConfig()
    cfg.cast.slots[0] = SlotConfig(binds.tecla(0x31, "1"), ModoDoSlot.COOLDOWN, 2)
    cfg.cast.extras = [SlotConfig(binds.botao_mouse(binds.VK_XBUTTON1), ModoDoSlot.SPAM)]
    cfg.potion.limiar_pct = 55
    cfg.repetidores[0].controle = Controle(binds.tecla(0x70, "F1"), ModoDeAtivacao.SEGURAR)

    volta = AutoSkillConfig.from_json(cfg.to_json())
    assert volta.cast.slots[0].modo is ModoDoSlot.COOLDOWN
    assert volta.cast.slots[0].prioridade == 2
    assert volta.cast.extras[0].bind.codigo == binds.VK_XBUTTON1
    assert volta.potion.limiar_pct == 55
    assert volta.repetidores[0].controle.ativacao is ModoDeAtivacao.SEGURAR


@pytest.mark.parametrize("lixo", [None, "", [], {"cast": "x", "potion": 9}])
def test_config_estragada_vira_padrao(lixo):
    cfg = AutoSkillConfig.from_json(lixo)
    assert len(cfg.cast.slots) == SLOTS
    assert cfg.potion.bind, "a poção perdeu o padrão"
    assert cfg.repetidor("dodge") is not None


def test_prioridade_manda_na_ordem_e_o_slot_desempata():
    cfg = AutoSkillConfig()
    for i in range(4):
        cfg.cast.slots[i] = SlotConfig(
            binds.tecla(0x31 + i, str(i + 1)), ModoDoSlot.COOLDOWN, 0
        )
    cfg.cast.slots[2].prioridade = -1     # o slot 3 passa na frente
    assert [i for i, _ in cfg.cast.ordem_de_cast()] == [2, 0, 1, 3]


def test_slot_manual_ou_sem_bind_fica_de_fora():
    """O exemplo do usuário: 1 e 2 em cooldown, 3 e 4 em spam, o resto manual."""
    cfg = AutoSkillConfig()
    cfg.cast.slots[0] = SlotConfig(binds.tecla(0x31, "1"), ModoDoSlot.COOLDOWN)
    cfg.cast.slots[1] = SlotConfig(binds.tecla(0x32, "2"), ModoDoSlot.SPAM)
    cfg.cast.slots[2] = SlotConfig(binds.Bind(), ModoDoSlot.SPAM)      # sem tecla
    cfg.cast.slots[3] = SlotConfig(binds.tecla(0x34, "4"), ModoDoSlot.MANUAL)
    assert [i for i, _ in cfg.cast.ordem_de_cast()] == [0, 1]


# ---------------------------------------------------------------- gatilhos
def _gatilho(monkeypatch, ativacao, pressionada=False, tocada=False):
    from d4forge.autoskill import engine as motor

    monkeypatch.setattr(motor.binds, "descarta_toque_pendente", lambda _b: None)
    monkeypatch.setattr(motor.binds, "esta_pressionada", lambda _b: pressionada)
    monkeypatch.setattr(motor.binds, "foi_pressionada", lambda _b: tocada)
    return motor._Gatilho(Controle(binds.tecla(0x70, "F1"), ativacao))


def test_toggle_liga_e_desliga_a_cada_toque(monkeypatch):
    g = _gatilho(monkeypatch, ModoDeAtivacao.TOGGLE, tocada=True)
    assert g.atualizar() is True
    assert g.atualizar() is False
    assert g.atualizar() is True


def test_segurar_acompanha_a_tecla(monkeypatch):
    g = _gatilho(monkeypatch, ModoDeAtivacao.SEGURAR, pressionada=True)
    assert g.atualizar() is True

    from d4forge.autoskill import engine as motor

    monkeypatch.setattr(motor.binds, "esta_pressionada", lambda _b: False)
    assert g.atualizar() is False


def test_hotkey_vazia_nunca_liga_sozinha(monkeypatch):
    from d4forge.autoskill import engine as motor

    monkeypatch.setattr(motor.binds, "descarta_toque_pendente", lambda _b: None)
    monkeypatch.setattr(motor.binds, "foi_pressionada", lambda _b: True)
    g = motor._Gatilho(Controle(binds.Bind(), ModoDeAtivacao.TOGGLE))
    assert g.atualizar() is False


def test_so_o_modo_cooldown_pede_captura():
    """Uma configuração só de spam não deve custar um único quadro — é o caso
    de quem só quer trocar a macro do LGHUB."""
    from d4forge.autoskill.engine import AutoSkillEngine

    cfg = AutoSkillConfig()
    cfg.cast.slots[0] = SlotConfig(binds.tecla(0x31, "1"), ModoDoSlot.SPAM)
    assert not AutoSkillEngine(cfg)._algum_slot_le_tela()

    cfg.cast.slots[1] = SlotConfig(binds.tecla(0x32, "2"), ModoDoSlot.COOLDOWN)
    assert AutoSkillEngine(cfg)._algum_slot_le_tela()


# -------------------------------------------------- o laço sobe com o app
def test_o_laco_sobe_junto_com_a_janela(qt_app, config_isolada):
    """Não há botão de ligar, e isso é o ponto: as hotkeys só podem ser
    ouvidas por um laço que já esteja rodando. Exigir um clique antes delas
    obrigaria a voltar ao app toda vez, que era o passo inútil."""
    from d4forge.gui.app import AppState, MainWindow

    janela = MainWindow(AppState.load())
    try:
        assert janela.autoskill_worker is not None
        assert janela.autoskill_worker.isRunning()
        assert not hasattr(janela, "btn_autoskill"), "o botão de ligar voltou"
    finally:
        janela.close()
        janela.autoskill_worker.wait(3000)
    assert not janela.autoskill_worker.isRunning(), "o laço sobreviveu ao fechar"


def test_a_aba_edita_a_mesma_config_que_o_motor_segura(qt_app, config_isolada):
    """É isto que faz uma bind nova valer sem reiniciar nada."""
    from d4forge.gui.app import AppState, MainWindow

    janela = MainWindow(AppState.load())
    try:
        do_motor = janela.autoskill_worker._engine.config
        assert janela.autoskill_tab.goal() is do_motor
    finally:
        janela.close()
        janela.autoskill_worker.wait(3000)


def test_trocar_a_hotkey_vale_no_laco_em_andamento(monkeypatch):
    """O gatilho aponta para o controle novo em vez de guardar uma cópia."""
    from d4forge.autoskill import engine as motor

    monkeypatch.setattr(motor.binds, "descarta_toque_pendente", lambda _b: None)
    monkeypatch.setattr(motor.binds, "foi_pressionada", lambda _b: False)
    g = motor._Gatilho(Controle(binds.tecla(0x70, "F1"), ModoDeAtivacao.TOGGLE))

    novo = Controle(binds.tecla(0x71, "F2"), ModoDeAtivacao.SEGURAR)
    g.apontar_para(novo)
    assert g.controle.hotkey.codigo == 0x71
    assert g.controle.ativacao is ModoDeAtivacao.SEGURAR


def test_hotkey_nova_nao_liga_sozinha_com_o_toque_que_a_gravou(monkeypatch):
    """`foi_pressionada` devolve True uma vez por aperto. Sem descartar o
    pendente, a tecla que o usuário apertou PARA GRAVAR a bind seria lida em
    seguida como o toque que liga o recurso."""
    from d4forge.autoskill import engine as motor

    descartadas = []
    monkeypatch.setattr(motor.binds, "descarta_toque_pendente", descartadas.append)
    g = motor._Gatilho(Controle(binds.tecla(0x70, "F1")))
    descartadas.clear()

    g.apontar_para(Controle(binds.tecla(0x71, "F2")))
    assert [b.codigo for b in descartadas] == [0x71]

    # Mesma hotkey de novo não precisa descartar nada.
    descartadas.clear()
    g.apontar_para(Controle(binds.tecla(0x71, "F2")))
    assert descartadas == []


def test_a_captura_so_nasce_quando_alguem_precisa_de_quadro(qt_app, config_isolada):
    """O laço fica no ar a sessão inteira. Abrir o dxcam ali tomaria um
    dispositivo de vídeo de quem talvez nunca ligue o AutoSkill — e de quem
    configurou só spam, que nunca precisa de quadro nenhum."""
    import time

    from d4forge.gui.app import AppState, MainWindow

    janela = MainWindow(AppState.load())
    try:
        time.sleep(0.3)      # alguns tiques do laço
        assert janela.autoskill_worker._engine._captura is None
    finally:
        janela.close()
        janela.autoskill_worker.wait(3000)


# ------------------------------------------------------- rodízio entre slots
class _Espiao:
    """Conta quem foi apertado, sem tocar no teclado de verdade."""

    def __init__(self):
        self.apertados = []

    def __call__(self, bind, hold=None):
        self.apertados.append(bind.rotulo)
        return True


def _motor_com_dois_slots(monkeypatch, espiao, prontos=(True, True)):
    from d4forge.autoskill import engine as motor

    cfg = AutoSkillConfig()
    cfg.cast.slots[0] = SlotConfig(binds.tecla(0x31, "1"), ModoDoSlot.COOLDOWN, 1)
    cfg.cast.slots[1] = SlotConfig(binds.tecla(0x32, "2"), ModoDoSlot.COOLDOWN, 2)
    monkeypatch.setattr(motor.binds, "disparar", espiao)

    engine = motor.AutoSkillEngine(cfg)

    class LeitorFalso:
        def ler(self, _quadro, rois):
            from d4forge.autoskill.vision import EstadoDoSlot

            return [
                EstadoDoSlot(i, 200.0, 200.0, not (prontos[i] if i < len(prontos) else False))
                for i in range(len(rois))
            ]

    engine._leitor = LeitorFalso()
    return engine, cfg


def test_dois_slots_prontos_se_revezam(monkeypatch, perfil):
    """O bug que o usuário achou: com 1 e 2 em "manter em cooldown", só o 1
    disparava. A varredura reiniciava sempre na maior prioridade e saía no
    primeiro que disparasse, então o slot 2 nunca chegava a vez."""
    import numpy as np

    espiao = _Espiao()
    engine, _cfg = _motor_com_dois_slots(monkeypatch, espiao)
    quadro = np.zeros((10, 10, 3), dtype=np.uint8)
    estado = type("E", (), {"slots_prontos": [], "ultima_acao": ""})()

    # Seis tiques, com folga entre eles para a carência não mascarar o rodízio.
    for tique in range(6):
        engine._talvez_castar(quadro, perfil, estado, tique * 1.0)

    assert espiao.apertados == ["1", "2", "1", "2", "1", "2"], espiao.apertados


def test_a_prioridade_manda_em_quem_comeca(monkeypatch, perfil):
    """Prioridade continua sendo ordem — o de menor número abre o rodízio."""
    import numpy as np

    espiao = _Espiao()
    engine, cfg = _motor_com_dois_slots(monkeypatch, espiao)
    cfg.cast.slots[0].prioridade = 5      # o slot 2 passa na frente
    quadro = np.zeros((10, 10, 3), dtype=np.uint8)
    estado = type("E", (), {"slots_prontos": [], "ultima_acao": ""})()

    for tique in range(4):
        engine._talvez_castar(quadro, perfil, estado, tique * 1.0)

    assert espiao.apertados == ["2", "1", "2", "1"], espiao.apertados


def test_carencia_impede_repetir_antes_de_o_jogo_mostrar_o_cooldown(
    monkeypatch, perfil
):
    """O jogo leva um ou dois quadros para escurecer o ícone. Sem carência, o
    tique seguinte lê "pronta" de novo e aperta a mesma tecla."""
    import numpy as np

    from d4forge.autoskill.engine import GRACA_APOS_DISPARO_S

    espiao = _Espiao()
    # So' o slot 1 configurado: sem rodizio para mascarar a carencia.
    engine, cfg = _motor_com_dois_slots(monkeypatch, espiao)
    cfg.cast.slots[1] = SlotConfig()
    quadro = np.zeros((10, 10, 3), dtype=np.uint8)
    estado = type("E", (), {"slots_prontos": [], "ultima_acao": ""})()

    engine._talvez_castar(quadro, perfil, estado, 100.0)
    assert espiao.apertados == ["1"]

    # Dentro da carência: não repete.
    engine._talvez_castar(quadro, perfil, estado, 100.0 + GRACA_APOS_DISPARO_S / 2)
    assert espiao.apertados == ["1"], "apertou de novo cedo demais"

    # Passada a carência, volta a valer.
    engine._talvez_castar(quadro, perfil, estado, 100.0 + GRACA_APOS_DISPARO_S * 2)
    assert espiao.apertados == ["1", "1"]


def test_slot_em_cooldown_cede_a_vez_em_vez_de_travar_a_fila(monkeypatch, perfil):
    """Se o de maior prioridade está em cooldown, o seguinte dispara — e o
    rodízio não pode deixar o ciclo parado esperando por ele."""
    import numpy as np

    espiao = _Espiao()
    engine, _cfg = _motor_com_dois_slots(monkeypatch, espiao, prontos=(False, True))
    quadro = np.zeros((10, 10, 3), dtype=np.uint8)
    estado = type("E", (), {"slots_prontos": [], "ultima_acao": ""})()

    for tique in range(3):
        engine._talvez_castar(quadro, perfil, estado, tique * 1.0)

    assert espiao.apertados == ["2", "2", "2"], espiao.apertados


def test_extras_entram_no_mesmo_rodizio(monkeypatch, perfil):
    """Dois botões de mouse em spam também se revezam — antes só o primeiro
    da lista era apertado, pelo mesmo motivo."""
    from d4forge.autoskill import engine as motor

    espiao = _Espiao()
    cfg = AutoSkillConfig()
    cfg.cast.extras = [
        SlotConfig(binds.botao_mouse(binds.VK_XBUTTON1), ModoDoSlot.SPAM),
        SlotConfig(binds.botao_mouse(binds.VK_XBUTTON2), ModoDoSlot.SPAM),
    ]
    monkeypatch.setattr(motor.binds, "disparar", espiao)
    engine = motor.AutoSkillEngine(cfg)
    estado = type("E", (), {"slots_prontos": [], "ultima_acao": ""})()

    for tique in range(4):
        engine._talvez_castar(None, None, estado, tique * 1.0)

    assert espiao.apertados == [
        "Mouse lateral 1", "Mouse lateral 2",
        "Mouse lateral 1", "Mouse lateral 2",
    ], espiao.apertados
