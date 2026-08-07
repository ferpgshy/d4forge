"""Parsing de linha de afixo e correcao de erro de OCR.

As entradas "sujas" nao sao inventadas: sao exatamente o que o RapidOCR devolveu
ao ler os prints de referencia.
"""

import pytest

from d4forge.affixes import (
    AffixCatalog,
    AffixEntry,
    Unit,
    looks_like_affix_name,
    parse_affix,
)


@pytest.mark.parametrize(
    "text, value, name, unit",
    [
        # leituras limpas
        ("+151 Dexterity", 151, "Dexterity", Unit.FLAT),
        ("+3,000 Shadow Resistance", 3000, "Shadow Resistance", Unit.FLAT),
        ("15.0% Resource Generation", 15.0, "Resource Generation", Unit.PERCENT),
        ("+2 to Imbuement Skills", 2, "Imbuement Skills", Unit.RANK),
        ("+2,714 Poison Resistance", 2714, "Poison Resistance", Unit.FLAT),
        ("9.4% Impairment Reduction", 9.4, "Impairment Reduction", Unit.PERCENT),
        # erros reais do OCR que precisam ser consertados
        ("+151Dexterity", 151, "Dexterity", Unit.FLAT),                      # espaco comido
        ("+3,0D0 Shadow Resistance", 3000, "Shadow Resistance", Unit.FLAT),  # 0 lido como D
        ("1s.% Resource Generation", 15.0, "Resource Generation", Unit.PERCENT),  # 5 como s
        ("1 0.0% Impairment Reduction", 10.0, "Impairment Reduction", Unit.PERCENT),  # numero partido
        ("10.0% Impaiment Reduction", 10.0, "Impairment Reduction", Unit.PERCENT),   # letra faltando
        ("+2 to Ibuerent skills", 2, "Imbuement Skills", Unit.RANK),         # bem corrompido
        # multiplicativo: a tela usa prefixo "x" em vez de "+"
        ("x22% Shadow Damage Multiplier", 22.0, "Shadow Damage Multiplier", Unit.PERCENT),
        ("x20% Poison Damage Multiplier", 20.0, "Poison Damage Multiplier", Unit.PERCENT),
    ],
)
def test_parse_conserta_leitura(catalog, text, value, name, unit):
    parsed = parse_affix(text, catalog)
    assert parsed.value == value
    assert parsed.name == name
    assert parsed.unit is unit
    assert parsed.confident


def test_numero_partido_nao_vira_valor_truncado(catalog):
    """Regressao: "1 0.0%" ja' foi lido como valor 1.

    O nome casava com o catalogo, entao a checagem de nome sozinha nao pegava o
    erro - o bot aceitaria um roll de 10% achando que era 1%.
    """
    assert parse_affix("1 0.0% Impairment Reduction", catalog).value == 10.0


def test_digito_corrompido_nao_vira_nome(catalog):
    """Regressao: "+3,0D0 Shadow Resistance" casava como valor 3,0 e nome
    "D0 Shadow Resistance" - erro silencioso."""
    parsed = parse_affix("+3,0D0 Shadow Resistance", catalog)
    assert parsed.value == 3000
    assert parsed.name == "Shadow Resistance"
    assert parsed.repaired


def test_nome_irreconhecivel_nao_e_confiavel(catalog):
    """Lixo do OCR precisa ser recusado, nao chutado."""
    parsed = parse_affix("+25 axirriurr Resource", catalog)
    assert parsed.entry is None
    assert not parsed.confident


@pytest.mark.parametrize(
    "text, value",
    [
        # Separador seguido de 3 dígitos é milhar, mesmo lido como ponto.
        ("+3,000 Fire Resistance", 3000),
        ("+3. 000 Fire Resistance", 3000),
        ("+1,431 Maximum Life", 1431),
        ("+1.431 Maximum Life", 1431),
        # Seguido de 1 ou 2 dígitos é decimal de verdade.
        ("14.5% Barrier Generation", 14.5),
        ("9.4% Impairment Reduction", 9.4),
    ],
)
def test_milhar_x_decimal(catalog, text, value):
    """Regressão: "+3,000 Fire Resistance" veio do OCR como "+3. 000 ire
    Resistance" e virava 3.0 — mil vezes menos — passando por confiável porque
    o nome casava. Quem decide o papel do separador é a contagem de dígitos."""
    from d4forge.affixes import AffixEntry

    catalog.add(AffixEntry("Fire Resistance"))
    catalog.add(AffixEntry("Maximum Life"))
    catalog.add(AffixEntry("Barrier Generation", Unit.PERCENT))
    assert parse_affix(text, catalog).value == value


def test_nome_muito_corrompido_nao_casa(catalog):
    """"Life Kil" (era "+271 Life on Kill", com "71" e "on" comidos) bate 0.82
    em "Life on Kill" — abaixo do limiar, então não pode virar leitura
    confiável valendo 2."""
    from d4forge.affixes import AffixEntry

    catalog.add(AffixEntry("Life on Kill"))
    assert not parse_affix("+2 Life Kil", catalog).confident
    # a correção legítima continua passando
    assert parse_affix("+291 Life on Kil", catalog).confident


def test_lucky_hit_valor_no_meio_da_frase(catalog):
    """"Lucky Hit: Up to a 5% Chance..." não começa com número — o valor está
    no meio. Só é aceito quando o texto casa com o catálogo."""
    catalog.add(
        AffixEntry(
            "Lucky Hit: Up to a Chance to Restore Primary Resource",
            Unit.PERCENT, unit_confirmed=True,
        )
    )
    parsed = parse_affix(
        "Lucky Hit: Up to a 5% Chance to Restore Primary Resource", catalog
    )
    assert parsed.confident
    assert parsed.value == 5.0
    assert parsed.unit is Unit.PERCENT


def test_lucky_hit_corrompido_continua_duvidoso(catalog):
    """Lixo de OCR com número no meio não pode virar leitura confiável."""
    parsed = parse_affix("Lutky Hibiupiva 13% tne lU Keslule f4", catalog)
    assert not parsed.confident


def test_no_change(catalog):
    parsed = parse_affix("No Change", catalog)
    assert parsed.no_change
    assert parsed.confident


def test_qualidade_do_roll():
    catalog = AffixCatalog()
    catalog.add(AffixEntry("Shadow Resistance", Unit.FLAT, vmin=1000, vmax=3000))
    assert parse_affix("+3,000 Shadow Resistance", catalog).quality == pytest.approx(1.0)
    assert parse_affix("+2,000 Shadow Resistance", catalog).quality == pytest.approx(0.5)


def test_sem_faixa_cadastrada_qualidade_e_desconhecida(catalog):
    assert parse_affix("+151 Dexterity", catalog).quality is None


@pytest.mark.parametrize(
    "name",
    # Nomes reais colhidos do jogo durante uma sessão.
    ["Thorns", "Armor", "Lightning Resistance", "Healing Received", "Energy"],
)
def test_aceita_nome_de_afixo_plausivel(name):
    assert looks_like_affix_name(name)


@pytest.mark.parametrize(
    "garbage",
    # Leituras corrompidas reais: não podem virar sugestão de catálogo.
    ["+0 +3. Resistance", ".0% Healing Received 5.", "D0 Shadow Resistance", "ext", ""],
)
def test_recusa_lixo_de_ocr_como_nome(garbage):
    assert not looks_like_affix_name(garbage)


def test_catalogo_persiste(tmp_path, catalog):
    path = tmp_path / "affixes.json"
    catalog.add(AffixEntry("Teste", Unit.PERCENT, 1, 9))
    catalog.save(path)
    again = AffixCatalog.load(path)
    assert again.entries["Teste"].vmax == 9
    assert len(again) == len(catalog)
