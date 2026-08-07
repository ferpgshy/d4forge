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
import logging
import re
from difflib import SequenceMatcher
from pathlib import Path

from .affixes import AffixCatalog, AffixEntry, Unit, _canon

def _bundled_path() -> Path:
    """Onde esta' a lista de afixos empacotada.

    No .exe os recursos vao para sys._MEIPASS, nao para o lado do modulo -
    entao quando congelado o bundle tem prioridade. Fora dele, vale a copia do
    repositorio.
    """
    import sys

    from .config import RESOURCE_DIR

    do_bundle = [
        RESOURCE_DIR / "d4forge" / "resources" / "d4lf_affixes_enUS.json",
        RESOURCE_DIR / "resources" / "d4lf_affixes_enUS.json",
    ]
    do_repo = [Path(__file__).resolve().parent / "resources" / "d4lf_affixes_enUS.json"]

    candidatos = do_bundle + do_repo if getattr(sys, "frozen", False) else do_repo + do_bundle
    for caminho in candidatos:
        if caminho.exists():
            return caminho
    return candidatos[0]


BUNDLED_PATH = _bundled_path()

log = logging.getLogger(__name__)

# A lista do d4lf tem ~877 nomes. Bem abaixo disso significa que ela nao
# carregou direito, e nao que o jogo encolheu.
MIN_OFFICIAL_AFFIXES = 500

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


def find_ocr_garbage(catalog: AffixCatalog) -> list[str]:
    """Entradas que nao existem na lista oficial e sao quase-copias de outra.

    O aprendizado automatico ja' deixou entrar "Life Kil", "Fire Resistence",
    "I Fire" e "Resistance" - leituras estropiadas que viraram afixo proprio.
    O estrago e' silencioso: depois de cadastradas elas casam EXATAMENTE, e a
    leitura errada passa a se apresentar como confiavel.
    """
    official = {_canon(e.name) for e in load_bundled()}

    # Sem uma lista oficial crivel, NAO apagamos nada.
    #
    # Esta funcao roda sozinha ao abrir o app e decide o que e' lixo comparando
    # com a lista empacotada. Se essa lista falhar em carregar - arquivo
    # ausente, empacotamento incompleto, caminho errado no .exe -, todo afixo
    # legitimo vira "nao-oficial" e e' apagado em silencio. Aconteceu: um teste
    # apontou o caminho para uma lista de uma entrada e o catalogo caiu de 881
    # para 466 afixos. Limpeza que depende de referencia nao pode rodar sem ela.
    if len(official) < MIN_OFFICIAL_AFFIXES:
        log.warning(
            "lista oficial com apenas %d afixos (esperado >= %d); "
            "limpeza do catalogo cancelada por seguranca",
            len(official), MIN_OFFICIAL_AFFIXES,
        )
        return []

    suspects: list[str] = []
    for name in list(catalog.entries):
        if _canon(name) in official:
            continue

        # Palavra de uma letra so'. Nenhum afixo do D4 tem - "I Fire" e' o
        # residuo de uma leitura que perdeu o resto da frase.
        if any(len(w) == 1 and w.isalpha() for w in name.split()):
            suspects.append(name)
            continue

        # Limiar proprio, mais frouxo que o do parser de propósito: aqui a
        # pergunta e' "isto e' quase-copia de um afixo que ja' existe?", e a
        # resposta certa para "Life Kil" vs "Life on Kill" (0.82) e' sim -
        # mesmo que o parser, por seguranca, se recuse a casar os dois.
        key = _canon(name)
        for other in catalog.entries:
            if other == name:
                continue
            if SequenceMatcher(None, key, _canon(other)).ratio() >= 0.80:
                suspects.append(name)
                break
    return sorted(suspects)


def purge_ocr_garbage(catalog: AffixCatalog) -> list[str]:
    """Remove as entradas acima. Devolve os nomes retirados."""
    removed = find_ocr_garbage(catalog)
    for name in removed:
        catalog.remove(name)
    return removed


def import_full_catalog(catalog: AffixCatalog) -> int:
    """Importacao padrao: lista empacotada -> catalogo. Devolve quantos entraram."""
    return merge_into(catalog, load_bundled())
