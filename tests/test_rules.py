"""Decisao de aceitar ou nao um afixo.

O vies destes testes e' proposital: na duvida, No Change.
"""

from d4forge.affixes import AffixCatalog, AffixEntry, Unit, parse_affix
from d4forge.rules import Action, Comparison, RuleSet, TargetRule


def _options(catalog, *texts):
    return [parse_affix(t, catalog) for t in texts]


def test_aceita_quando_valor_bate(catalog):
    rules = RuleSet([TargetRule("Resource Generation", Comparison.GE, 12)])
    decision = rules.decide(_options(catalog, "15.0% Resource Generation", "+151 Dexterity"))
    assert decision.action is Action.TAKE_OPTION_1
    assert decision.accepted


def test_recusa_quando_valor_nao_bate(catalog):
    rules = RuleSet([TargetRule("Resource Generation", Comparison.GE, 20)])
    decision = rules.decide(_options(catalog, "15.0% Resource Generation", "+151 Dexterity"))
    assert decision.action is Action.NO_CHANGE


def test_pega_a_segunda_opcao(catalog):
    rules = RuleSet([TargetRule("Dexterity", Comparison.GE, 100)])
    decision = rules.decide(_options(catalog, "15.0% Resource Generation", "+151 Dexterity"))
    assert decision.action is Action.TAKE_OPTION_2


def test_prioridade_desempata(catalog):
    rules = RuleSet(
        [
            TargetRule("Resource Generation", Comparison.ANY, priority=1),
            TargetRule("Dexterity", Comparison.ANY, priority=9),
        ]
    )
    decision = rules.decide(_options(catalog, "15.0% Resource Generation", "+151 Dexterity"))
    assert decision.action is Action.TAKE_OPTION_2


def test_leitura_duvidosa_vira_no_change(catalog):
    """O ponto central de seguranca: se o OCR nao foi entendido, nao troca."""
    rules = RuleSet([TargetRule("Maximum Resource", Comparison.ANY)])
    decision = rules.decide(_options(catalog, "+25 axirriurr Resource", "No Change"))
    assert decision.action is Action.NO_CHANGE
    assert "duvidosa" in decision.reason


def test_sem_regras_nao_troca(catalog):
    decision = RuleSet([]).decide(_options(catalog, "+151 Dexterity"))
    assert decision.action is Action.NO_CHANGE


def test_regra_desligada_e_ignorada(catalog):
    rules = RuleSet([TargetRule("Dexterity", Comparison.ANY, enabled=False)])
    assert rules.decide(_options(catalog, "+151 Dexterity")).action is Action.NO_CHANGE


def test_exigencia_de_qualidade_do_roll():
    catalog = AffixCatalog()
    catalog.add(AffixEntry("Shadow Resistance", Unit.FLAT, vmin=1000, vmax=3000))
    rules = RuleSet([TargetRule("Shadow Resistance", Comparison.ANY, min_quality=0.9)])

    bom = rules.decide(_options(catalog, "+2,900 Shadow Resistance"))
    assert bom.action is Action.TAKE_OPTION_1

    ruim = rules.decide(_options(catalog, "+1,500 Shadow Resistance"))
    assert ruim.action is Action.NO_CHANGE


def test_terceira_opcao_nunca_e_escolhida(catalog):
    """A tela tem 3 orbes, mas o terceiro e' No Change - nunca e' um alvo."""
    rules = RuleSet([TargetRule("Dexterity", Comparison.ANY)])
    decision = rules.decide(
        _options(catalog, "15.0% Resource Generation", "10.0% Impairment Reduction", "+151 Dexterity")
    )
    assert decision.action is Action.NO_CHANGE


# ------------------------------------------------------------- escalada
#
# Cenário do usuário: item tem "Shadow Damage Multiplier", alvo é
# "Poison Damage Multiplier >= 24". Sequência esperada:
#   20% Poison  -> SELECIONA (fisga o nome certo, qualquer valor)
#   21% Poison  -> SELECIONA (sobe: 21 > 20)
#   20% Poison  -> NÃO       (20 não é maior que 21)
#   25% Poison  -> SELECIONA e ENCERRA (meta >= 24 atingida)

def _climb_rules(catalog):
    catalog.add(AffixEntry("Poison Damage Multiplier", Unit.PERCENT, unit_confirmed=True))
    catalog.add(AffixEntry("Shadow Damage Multiplier", Unit.PERCENT, unit_confirmed=True))
    return RuleSet([TargetRule("Poison Damage Multiplier", Comparison.GE, 24, climb=True)])


def test_escalada_fisga_o_nome_certo_com_qualquer_valor(catalog):
    rules = _climb_rules(catalog)
    current = parse_affix("x22% Shadow Damage Multiplier", catalog)
    decision = rules.decide(
        _options(catalog, "x20% Poison Damage Multiplier", "+151 Dexterity"), current
    )
    assert decision.action is Action.TAKE_OPTION_1
    assert not decision.goal_reached  # degrau, não meta


def test_escalada_so_sobe(catalog):
    rules = _climb_rules(catalog)
    current = parse_affix("x20% Poison Damage Multiplier", catalog)
    decision = rules.decide(
        _options(catalog, "x21% Poison Damage Multiplier", "+151 Dexterity"), current
    )
    assert decision.action is Action.TAKE_OPTION_1
    assert not decision.goal_reached


def test_escalada_nao_desce_nem_empata(catalog):
    rules = _climb_rules(catalog)
    current = parse_affix("x21% Poison Damage Multiplier", catalog)
    for oferta in ("x20% Poison Damage Multiplier", "x21% Poison Damage Multiplier"):
        decision = rules.decide(_options(catalog, oferta, "+151 Dexterity"), current)
        assert decision.action is Action.NO_CHANGE, oferta


def test_escalada_encerra_na_meta(catalog):
    rules = _climb_rules(catalog)
    current = parse_affix("x21% Poison Damage Multiplier", catalog)
    decision = rules.decide(
        _options(catalog, "x25% Poison Damage Multiplier", "+151 Dexterity"), current
    )
    assert decision.action is Action.TAKE_OPTION_1
    assert decision.goal_reached


def test_meta_direta_ganha_do_degrau(catalog):
    """Se uma opção já cumpre a meta e a outra é só degrau, pega a meta."""
    rules = _climb_rules(catalog)
    current = parse_affix("x20% Poison Damage Multiplier", catalog)
    decision = rules.decide(
        _options(
            catalog,
            "x22% Poison Damage Multiplier",
            "x30% Poison Damage Multiplier",
        ),
        current,
    )
    assert decision.action is Action.TAKE_OPTION_2
    assert decision.goal_reached


def test_sem_leitura_do_atual_nao_ha_escalada(catalog):
    """Sem saber o que o item tem, trocar às cegas poderia rebaixar um roll
    bom — só a regra cheia decide."""
    rules = _climb_rules(catalog)
    decision = rules.decide(
        _options(catalog, "x20% Poison Damage Multiplier", "+151 Dexterity"), None
    )
    assert decision.action is Action.NO_CHANGE


def test_escalada_desligada_volta_ao_comportamento_antigo(catalog):
    catalog.add(AffixEntry("Poison Damage Multiplier", Unit.PERCENT, unit_confirmed=True))
    catalog.add(AffixEntry("Shadow Damage Multiplier", Unit.PERCENT, unit_confirmed=True))
    rules = RuleSet([TargetRule("Poison Damage Multiplier", Comparison.GE, 24, climb=False)])
    current = parse_affix("x22% Shadow Damage Multiplier", catalog)
    decision = rules.decide(
        _options(catalog, "x20% Poison Damage Multiplier", "+151 Dexterity"), current
    )
    assert decision.action is Action.NO_CHANGE


def test_climb_persiste(tmp_path):
    path = tmp_path / "rules.json"
    RuleSet([TargetRule("X", climb=False)]).save(path)
    assert RuleSet.load(path).rules[0].climb is False
    RuleSet([TargetRule("X", climb=True)]).save(path)
    assert RuleSet.load(path).rules[0].climb is True


def test_persistencia(tmp_path):
    path = tmp_path / "rules.json"
    original = RuleSet([TargetRule("Dexterity", Comparison.GT, 140, min_quality=0.8, priority=3)])
    original.save(path)
    again = RuleSet.load(path)
    assert again.rules[0].affix_name == "Dexterity"
    assert again.rules[0].comparison is Comparison.GT
    assert again.rules[0].min_quality == 0.8
