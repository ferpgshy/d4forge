"""Importa o catalogo completo de afixos.

Fonte: a lista enUS do d4lf (github.com/d4lfteam/d4lf), um loot filter que
tambem le' a tela do D4 por OCR - ou seja, os nomes vem exatamente na grafia
que aparece na interface. Uma copia vai empacotada em resources/, entao a
importacao funciona offline; da' para atualizar o arquivo baixando o
assets/lang/enUS/affixes.json mais novo do repo.

O que esta fonte NAO tem, e por que:

* Faixas de roll (min/max). O d4data datminerado ate' as tem, mas escondidas em
  formulas ("FloatRandomRangeWithIntervalUniqueAffixPityBonus(5, 45, 60)") de
  arquivos nomeados por ID interno, sem juncao viavel com o nome de exibicao -
  verificado: nao existe StringList com o mesmo nome do arquivo de afixo. As
  faixas continuam sendo preenchidas a mao na aba Catalogo.
* Mapa afixo -> slot/classe. Mesmo problema de juncao. O modelo do catalogo ja'
  suporta slots, entao a informacao pode ser preenchida aos poucos; afixo sem
  slot cadastrado aparece em todos os filtros.

A unidade de cada afixo e' um PALPITE pelo nome (marcado unit_confirmed=False).
Palpite nao corrige leitura de OCR - so' unidade confirmada faz isso.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .affixes import AffixCatalog, AffixEntry, Unit, _canon

BUNDLED_PATH = Path(__file__).resolve().parent / "resources" / "d4lf_affixes_enUS.json"

# Palavras que, no vocabulario do D4, quase sempre indicam valor percentual.
_PERCENT_HINTS = re.compile(
    r"\b(chance|reduction|generation|speed|multiplier|bonus|rate|received|"
    r"efficiency|damage|healing|critical)\b"
)

# Palavras que ficam minusculas no meio do nome ("Life on Kill").
_SMALL_WORDS = {"of", "on", "per", "to", "the", "a", "and", "with", "while", "for", "in"}


def display_name(raw: str) -> str:
    """"maximum life" -> "Maximum Life"; "life on kill" -> "Life on Kill"."""
    words = raw.strip().split()
    out = []
    for i, w in enumerate(words):
        if i > 0 and w in _SMALL_WORDS:
            out.append(w)
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


def guess_entry(key: str, value: str) -> AffixEntry | None:
    """Converte um par chave/nome do d4lf numa entrada do catalogo."""
    value = value.strip().lower()
    if not value or any(ch.isdigit() for ch in value):
        return None

    if value.startswith("to "):
        # "to imbuement skills" e' rank; o "to" pertence a gramatica da linha,
        # nao ao nome do afixo.
        return AffixEntry(name=display_name(value[3:]), unit=Unit.RANK)

    unit = Unit.PERCENT if _PERCENT_HINTS.search(value) else Unit.FLAT
    return AffixEntry(name=display_name(value), unit=unit)


def parse_d4lf(blob: dict) -> list[AffixEntry]:
    entries: list[AffixEntry] = []
    seen: set[str] = set()
    for key, value in blob.items():
        entry = guess_entry(str(key), str(value))
        if entry is None:
            continue
        canon = _canon(entry.name)
        if canon in seen:
            continue
        seen.add(canon)
        entries.append(entry)
    return entries


def load_bundled() -> list[AffixEntry]:
    blob = json.loads(BUNDLED_PATH.read_text(encoding="utf-8"))
    return parse_d4lf(blob)


def merge_into(catalog: AffixCatalog, entries: list[AffixEntry]) -> int:
    """Acrescenta o que falta, sem tocar no que o usuario ja' tem.

    Entradas existentes carregam faixas, slots e unidades confirmadas - dados
    que o usuario preencheu a mao. Importar de novo nunca pode sobrescreve-los.
    A comparacao e' por igualdade canonica exata, nao fuzzy: o matching fuzzy
    juntaria nomes parecidos porem distintos ("Maximum Life" vs
    "Maximum Life per 5 Seconds").
    """
    existing = {_canon(e.name) for e in catalog.entries.values()}
    added = 0
    for entry in entries:
        if _canon(entry.name) in existing:
            continue
        catalog.add(entry)
        existing.add(_canon(entry.name))
        added += 1
    return added


def import_full_catalog(catalog: AffixCatalog) -> int:
    """Importacao padrao: lista empacotada -> catalogo. Devolve quantos entraram."""
    return merge_into(catalog, load_bundled())
