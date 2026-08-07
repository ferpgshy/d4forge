"""Higiene do cache de OCR e do catálogo.

Regressão vinda de sessão real: ".7% Dodge Chance" (o "7" da frente comido)
voltava do cache em 0,7 ms muito depois de o parser ter sido corrigido — o
cache guarda o veredito da versão que o gravou, e sobrevive à correção.
"""

import json

import pytest

from d4forge.affixes import AffixCatalog, AffixEntry
from d4forge.catalog_import import find_ocr_garbage, purge_ocr_garbage
from d4forge.vision.ocr import CACHE_VERSION, OcrEngine, plausible_line


@pytest.mark.parametrize("text", ["+395 Resistance to All Elements", "7.7% Dodge Chance",
                                  "No Change", "x22% Shadow Damage Multiplier"])
def test_linha_plausivel(text):
    assert plausible_line(text)


@pytest.mark.parametrize("text", [".7% Dodge Chance", ",425 Thorns", ".0% Healing", "", "   ",
                                  "2970"])
def test_linha_implausivel(text):
    """Dígito da frente comido, ou texto sem letra nenhuma."""
    assert not plausible_line(text)


def test_cache_de_versao_antiga_e_descartado(tmp_path):
    (tmp_path / "ocr_cache.json").write_text(
        json.dumps({"version": CACHE_VERSION - 1, "entries": {"k": "7.7% Dodge Chance"}}),
        encoding="utf-8",
    )
    assert OcrEngine(data_dir=tmp_path).cache == {}


def test_cache_sem_versao_e_descartado(tmp_path):
    """Formato antigo (dict cru) não tem como ser validado; começa do zero."""
    (tmp_path / "ocr_cache.json").write_text(
        json.dumps({"k": "7.7% Dodge Chance"}), encoding="utf-8"
    )
    assert OcrEngine(data_dir=tmp_path).cache == {}


def test_entrada_truncada_e_descartada_na_carga(tmp_path):
    (tmp_path / "ocr_cache.json").write_text(
        json.dumps({
            "version": CACHE_VERSION,
            "entries": {"bom": "7.7% Dodge Chance", "ruim": ".7% Dodge Chance"},
        }),
        encoding="utf-8",
    )
    cache = OcrEngine(data_dir=tmp_path).cache
    assert "bom" in cache and "ruim" not in cache


def test_cache_sobrevive_ida_e_volta(tmp_path):
    engine = OcrEngine(data_dir=tmp_path)
    engine.cache["k"] = "7.7% Dodge Chance"
    engine._dirty = True
    engine.save()
    assert OcrEngine(data_dir=tmp_path).cache == {"k": "7.7% Dodge Chance"}


# ------------------------------------------------------------- catálogo

def test_encontra_lixo_de_ocr_no_catalogo():
    """"Life Kil" entrou pelo aprendizado automático como afixo próprio; depois
    de cadastrado casava exato e fazia a leitura errada parecer confiável."""
    catalog = AffixCatalog()
    catalog.add(AffixEntry("Life on Kill"))
    catalog.add(AffixEntry("Life Kil"))
    catalog.add(AffixEntry("Fire Resistance"))
    catalog.add(AffixEntry("Fire Resistence"))
    assert set(find_ocr_garbage(catalog)) == {"Life Kil", "Fire Resistence"}


def test_palavra_de_uma_letra_e_lixo():
    """"I Fire" sobrou de uma leitura que perdeu o resto da frase; não é
    parecido com nada, mas nenhum afixo do D4 tem palavra de uma letra."""
    catalog = AffixCatalog()
    catalog.add(AffixEntry("I Fire"))
    catalog.add(AffixEntry("Fire Resistance"))
    assert find_ocr_garbage(catalog) == ["I Fire"]


def test_purga_remove_so_o_lixo():
    catalog = AffixCatalog()
    catalog.add(AffixEntry("Life on Kill"))
    catalog.add(AffixEntry("Life Kil"))
    removed = purge_ocr_garbage(catalog)
    assert removed == ["Life Kil"]
    assert "Life on Kill" in catalog.entries


def test_sem_lista_oficial_nao_apaga_nada(monkeypatch):
    """Regressão com perda de dados real: a limpeza roda sozinha ao abrir o app
    e usa a lista empacotada como referência. Um caminho errado apontou para
    uma lista de uma entrada, tudo virou "não-oficial" e o catálogo caiu de 881
    para 466 afixos. Limpeza que depende de referência não roda sem ela."""
    from d4forge import catalog_import
    from d4forge.affixes import Unit

    catalog = AffixCatalog()
    for nome in ("Fire Resistance", "Fire Resistence", "Cold Resistance", "Life on Kill"):
        catalog.add(AffixEntry(nome, Unit.FLAT))

    monkeypatch.setattr(
        catalog_import, "load_bundled", lambda: [AffixEntry("Maximum Life")]
    )
    assert catalog_import.find_ocr_garbage(catalog) == []
    assert catalog_import.purge_ocr_garbage(catalog) == []
    assert len(catalog) == 4


def test_lista_oficial_completa_volta_a_limpar():
    """Com a referência íntegra, a limpeza funciona normalmente."""
    catalog = AffixCatalog()
    catalog.add(AffixEntry("Life on Kill"))
    catalog.add(AffixEntry("Life Kil"))
    assert find_ocr_garbage(catalog) == ["Life Kil"]


def test_afixos_parecidos_porem_reais_sao_preservados():
    """"Core Attack Speed" e "Corpse Attack Speed" são 0.94 parecidos e ambos
    existem no jogo — estar na lista oficial protege os dois."""
    catalog = AffixCatalog()
    from d4forge.catalog_import import import_full_catalog

    import_full_catalog(catalog)
    antes = len(catalog)
    purge_ocr_garbage(catalog)
    assert len(catalog) == antes
