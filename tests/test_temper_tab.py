"""Aba do Tempering: critério de aceite, política de recarga e o estado na tela.

Recarregar gasta Pergaminhos, então "parar e me avisar" continua sendo o padrão
— mas ligar a recarga não passa por confirmação nem exige teto. Às vezes se
quer o afixo e o Pergaminho é o de menos, e essa escolha é de quem joga.
"""

import pytest

from d4forge.temper.rules import Recharge, TemperGoal


@pytest.fixture
def aba(qt_app):
    from d4forge.gui.temper_tab import TemperTab

    return TemperTab(settings=None)


# ------------------------------------------------------ política de recarga

def test_parar_e_o_padrao(aba):
    """Gastar recurso real não pode ser o comportamento de fábrica — mas quem
    liga a recarga não passa por confirmação nem por teto obrigatório: às vezes
    se quer o afixo e o Pergaminho é o de menos."""
    assert aba.rb_stop.isChecked()
    assert aba.goal().recharge is Recharge.STOP


def test_recarga_liga_direto(aba):
    """Marcar o rádio basta; não há pedágio."""
    aba.rb_one.setChecked(True)
    assert aba.goal().recharge is Recharge.ONE

    aba.rb_full.setChecked(True)
    assert aba.goal().recharge is Recharge.FULL


def test_sem_teto_e_o_padrao(aba):
    """O teto virou opcional. Zero no campo significa "sem limite"."""
    aba.rb_full.setChecked(True)
    assert aba.spin_cap.value() == 0
    assert aba.goal().max_recharges is None


def test_teto_vale_quando_preenchido(aba):
    aba.rb_one.setChecked(True)
    aba.spin_cap.setValue(3)
    assert aba.goal().max_recharges == 3


def test_teto_e_aviso_so_aparecem_quando_gastam(aba):
    for w in (aba.lbl_warn, aba.spin_cap):
        assert not w.isVisibleTo(aba)

    aba.rb_full.setChecked(True)
    for w in (aba.lbl_warn, aba.spin_cap):
        assert w.isVisibleTo(aba)

# ------------------------------------------------------------- critérios

def test_ga_e_o_criterio_padrao(aba):
    goal = aba.goal()
    assert goal.require_greater
    assert goal.min_fraction is None and goal.min_value is None


def test_criterios_sao_exclusivos(aba):
    aba.rb_fraction.setChecked(True)
    aba.spin_fraction.setValue(85)
    goal = aba.goal()

    assert not goal.require_greater
    assert goal.min_fraction == pytest.approx(0.85)
    assert goal.min_value is None


def test_campo_do_criterio_inativo_fica_desabilitado(aba):
    assert not aba.spin_fraction.isEnabled()
    aba.rb_fraction.setChecked(True)
    assert aba.spin_fraction.isEnabled()
    assert not aba.spin_value.isEnabled()


def test_filtro_de_afixo_e_opcional(aba):
    assert aba.goal().affix_contains == ""
    aba.txt_affix.setText("  Attack Speed  ")
    assert aba.goal().affix_contains == "Attack Speed"


# -------------------------------------------------------- ida e volta

def test_load_repoe_a_configuracao(aba):
    aba.load(TemperGoal(
        require_greater=False, min_value=2400, affix_contains="Resistance",
        recharge=Recharge.ONE, max_recharges=4,
    ))

    goal = aba.goal()
    assert goal.min_value == 2400
    assert goal.affix_contains == "Resistance"
    assert goal.recharge is Recharge.ONE
    assert goal.max_recharges == 4


def test_status_mostra_o_motivo_quando_nao_houve_tentativa(qt_app, config_isolada):
    """O defeito que fez o Tempering parecer não funcionar.

    A tabela só ganha linha quando um RESULTADO é lido. Quando o ciclo para
    antes disso — tela não reconhecida, receita não escolhida — não há tentativa
    nenhuma, a tabela fica vazia e a aba fica idêntica a parada. O motivo
    existia, mas só dentro dos detalhes técnicos, que vêm recolhidos.
    """
    from d4forge.gui.app import AppState, MainWindow
    from d4forge.temper.engine import TemperOutcome

    janela = MainWindow(AppState.load())
    try:
        aba = janela.temper_tab
        aba.progress.reset()
        janela._on_temper_finished(
            TemperOutcome(False, "temper.no_recipe", {}, [], 0, 1.0)
        )

        assert aba.progress.tabela.rowCount() == 0, "sem tentativas, como no bug"
        # ...e mesmo assim o usuário fica sabendo o que houve
        assert "receita" in aba.status.text().lower()
        assert aba.status.property("role") == "error"
    finally:
        janela.close()


def test_status_acompanha_o_ciclo(qt_app, config_isolada):
    from d4forge.engine import EngineEvent, EventKind
    from d4forge.gui.app import AppState, MainWindow

    janela = MainWindow(AppState.load())
    try:
        janela._on_temper_event(
            EngineEvent(EventKind.STATE, "eng.screen", {"state": "temper_result"})
        )
        assert "temper_result" in janela.temper_tab.status.text()
    finally:
        janela.close()


@pytest.mark.parametrize("conteudo", [
    # Exatamente o arquivo que impediu o app de abrir: quando `max_recharges`
    # passou a aceitar None, o já salvo trazia `null` e `int(None)` estourou.
    '{"require_greater": true, "min_fraction": null, "min_value": null,'
    ' "affix_contains": "", "max_recharges": null}',
    '{"max_recharges": "abc"}',
    '{"min_value": "nao e numero"}',
    '{"affix_contains": null}',
    '[]',
    'isto nao e json',
    '',
])
def test_arquivo_ruim_nao_impede_o_app_de_abrir(tmp_path, conteudo):
    """A regressão mais grave da noite: o app parou de subir.

    `load_temper_goal` roda na montagem da janela. Um valor inesperado aqui não
    estraga uma preferência — impede de ABRIR. Um arquivo de ajustes jamais
    deveria ter esse poder, então qualquer defeito vira "usa o padrão"."""
    from d4forge import config

    arquivo = tmp_path / "temper.json"
    arquivo.write_text(conteudo, encoding="utf-8")

    goal = config.load_temper_goal(arquivo)
    assert goal.require_greater
    assert goal.max_recharges is None


def test_ida_e_volta_pelo_disco_sobrevive(tmp_path):
    """E o caso normal continua indo e voltando inteiro."""
    from d4forge import config

    arquivo = tmp_path / "temper.json"
    config.save_temper_goal(
        TemperGoal(require_greater=False, min_fraction=0.9,
                   affix_contains="Resistance", max_recharges=4),
        arquivo,
    )
    lido = config.load_temper_goal(arquivo)

    assert not lido.require_greater
    assert lido.min_fraction == pytest.approx(0.9)
    assert lido.affix_contains == "Resistance"
    assert lido.max_recharges == 4


def test_recarga_nunca_volta_ligada_do_disco(tmp_path, monkeypatch):
    """A política é escolhida por sessão. Reabrir o app já gastando Pergaminhos
    seria uma surpresa cara; o teto, que é só preferência, volta salvo."""
    from d4forge import config

    arquivo = tmp_path / "temper.json"
    config.save_temper_goal(TemperGoal(recharge=Recharge.FULL, max_recharges=9), arquivo)

    lido = config.load_temper_goal(arquivo)
    assert lido.recharge is Recharge.STOP
    assert lido.max_recharges == 9, "o teto é preferência; a política é que não volta"
