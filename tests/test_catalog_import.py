"""Importador do catálogo completo (lista enUS do d4lf) e modelo de slots."""

import pytest

from d4forge.affixes import AffixCatalog, AffixEntry, Slot, Unit
from d4forge.catalog_import import (
    BUNDLED_PATH,
    display_name,
    guess_entry,
    import_full_catalog,
    load_bundled,
    merge_into,
)


def test_lista_empacotada_existe_e_e_grande():
    assert BUNDLED_PATH.exists()
    entries = load_bundled()
    # A lista do d4lf tem ~870 nomes; se um dia vier truncada, melhor falhar.
    assert len(entries) > 700


def test_importa_no_catalogo_semeado(catalog):
    before = len(catalog)
    added = import_full_catalog(catalog)
    assert added > 700
    assert len(catalog) == before + added


def test_importar_duas_vezes_nao_duplica(catalog):
    import_full_catalog(catalog)
    assert import_full_catalog(catalog) == 0


def test_importacao_preserva_edicao_do_usuario():
    """O usuário preencheu faixa e confirmou unidade; importar não pode desfazer."""
    catalog = AffixCatalog()
    catalog.add(
        AffixEntry("Maximum Life", Unit.FLAT, vmin=800, vmax=1500,
                   slots={Slot.CHEST, Slot.AMULET}, unit_confirmed=True)
    )
    import_full_catalog(catalog)
    kept = catalog.entries["Maximum Life"]
    assert kept.vmin == 800 and kept.vmax == 1500
    assert kept.unit_confirmed
    assert kept.slots == {Slot.CHEST, Slot.AMULET}


def test_cobre_os_afixos_vistos_no_jogo(catalog):
    """Todos os afixos que apareceram nas sessões reais têm de estar na lista."""
    import_full_catalog(catalog)
    vistos = [
        "Maximum Life", "Thorns", "Armor", "Lightning Resistance",
        "Cooldown Reduction", "Lucky Hit Chance", "Imbuement Skills",
        "Impairment Reduction", "Dexterity",
    ]
    for nome in vistos:
        entry, score = catalog.match(nome)
        assert entry is not None and score == 1.0, f"faltou {nome}"


def test_rank_vem_do_prefixo_to():
    entry = guess_entry("to_imbuement_skills", "to imbuement skills")
    assert entry.name == "Imbuement Skills"
    assert entry.unit is Unit.RANK


def test_percentual_e_palpite_nao_confirmado():
    entry = guess_entry("critical_strike_chance", "critical strike chance")
    assert entry.unit is Unit.PERCENT
    assert not entry.unit_confirmed


def test_nome_com_digito_e_descartado():
    assert guess_entry("x", "damage over 4 seconds") is None


@pytest.mark.parametrize(
    "raw, pretty",
    [
        ("maximum life", "Maximum Life"),
        ("life on kill", "Life on Kill"),
        ("damage while in human form", "Damage while in Human Form"),
    ],
)
def test_capitalizacao(raw, pretty):
    assert display_name(raw) == pretty


def test_merge_e_por_igualdade_exata_nao_fuzzy():
    """Nomes parecidos porém distintos são afixos diferentes; fuzzy os fundiria."""
    catalog = AffixCatalog()
    catalog.add(AffixEntry("Maximum Life"))
    added = merge_into(catalog, [AffixEntry("Maximum Life per 5 Seconds")])
    assert added == 1
    assert len(catalog) == 2


# ---------------------------------------------------------------- slots

def test_filtro_por_slot():
    catalog = AffixCatalog()
    catalog.add(AffixEntry("Anel Coisa", slots={Slot.RING}))
    catalog.add(AffixEntry("Coisa Geral"))  # sem slot = aparece em todos
    ring = {e.name for e in catalog.for_slot(Slot.RING)}
    helm = {e.name for e in catalog.for_slot(Slot.HELM)}
    assert ring == {"Anel Coisa", "Coisa Geral"}
    assert helm == {"Coisa Geral"}
    assert len(catalog.for_slot(None)) == 2


def test_slots_sobrevivem_ao_json(tmp_path):
    catalog = AffixCatalog()
    catalog.add(AffixEntry("X", slots={Slot.WEAPON, Slot.OFFHAND}, unit_confirmed=True))
    path = tmp_path / "affixes.json"
    catalog.save(path)
    again = AffixCatalog.load(path)
    assert again.entries["X"].slots == {Slot.WEAPON, Slot.OFFHAND}
    assert again.entries["X"].unit_confirmed


def test_semeados_tem_unidade_confirmada(catalog):
    """As unidades do seed foram conferidas nos prints; palpites do importador não."""
    assert all(e.unit_confirmed for e in catalog)
