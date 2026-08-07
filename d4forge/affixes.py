"""Catalogo de afixos, parsing das linhas e correcao de erro de OCR.

O OCR generico erra em texto de 12 px - nos prints de referencia ele leu
"+3,0D0 Shadow Resistance" e "+151Dexterity". Em vez de tentar um modelo melhor,
aproveitamos que a linha tem gramatica rigida e que o nome vem de um conjunto
fechado:

    +151 Dexterity              ->  valor 151, unidade FLAT,    nome Dexterity
    15.0% Resource Generation   ->  valor 15.0, unidade PERCENT
    +2 to Imbuement Skills      ->  valor 2,   unidade RANK

O nome e' casado por similaridade contra o catalogo (conserta letra trocada) e o
valor passa por um mapa de confusao digito<->letra (conserta 0 lido como D). O
que nao passar nessas duas checagens e' marcado como incerto, e o engine trata
incerteza como "nao trocar" - errar para o lado seguro custa uma tentativa, mas
nunca destroi o afixo bom do item.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
from pathlib import Path


class Slot(Enum):
    """Espacos de equipamento que o Occultist encanta.

    Consumiveis, materiais e joias ficam de fora - so' entram aqui os itens que
    tem afixo trocavel.
    """

    HELM = "helm"
    CHEST = "chest"
    GLOVES = "gloves"
    PANTS = "pants"
    BOOTS = "boots"
    AMULET = "amulet"
    RING = "ring"           # Ring 1 e Ring 2 sao o mesmo tipo de item
    WEAPON = "weapon"       # cobre as variacoes de 1M e 2M
    OFFHAND = "offhand"     # foco, totem, escudo

    @property
    def label(self) -> str:
        return {
            "helm": "Elmo",
            "chest": "Peitoral",
            "gloves": "Luvas",
            "pants": "Calças",
            "boots": "Botas",
            "amulet": "Amuleto",
            "ring": "Anel",
            "weapon": "Arma",
            "offhand": "Mão secundária",
        }[self.value]


class Unit(Enum):
    FLAT = "flat"        # +151 Dexterity
    PERCENT = "percent"  # 15.0% Resource Generation
    RANK = "rank"        # +2 to Imbuement Skills

    @property
    def symbol(self) -> str:
        return {"flat": "", "percent": "%", "rank": " (rank)"}[self.value]


# Letras que o OCR troca por digito nesta fonte serif. Aplicado SOMENTE ao token
# numerico da frente, e so' quando ele ja' contem ao menos um digito de verdade.
_DIGIT_CONFUSION = str.maketrans(
    {
        "O": "0", "o": "0", "D": "0", "Q": "0",
        "l": "1", "I": "1", "i": "1", "|": "1",
        "Z": "2", "z": "2",
        "A": "4",
        "S": "5", "s": "5",
        "G": "6",
        "T": "7",
        "B": "8",
        "g": "9", "q": "9",
    }
)

# Numero na frente, unidade opcional, "to" opcional, resto e' o nome.
# `\s*` entre numero e nome porque o OCR as vezes come o espaco.
#
# O numero aceita grupos de digitos separados por espaco - "1 0.0%" - porque o
# OCR frequentemente parte o numero ao meio. Sem isso "1 0.0% Impairment
# Reduction" seria lido como valor 1, um erro que o casamento de nome com o
# catalogo nao pegaria (o nome esta' certo!) e que faria o bot aceitar um roll
# ruim achando que era 1.
_NUMBER = r"[0-9][0-9.,]*(?:[ \t]+[0-9][0-9.,]*)*"

# O sinal aceita "x" alem de +/- porque bonus multiplicativo aparece na tela
# como "x22% Shadow Damage Multiplier" - visto na captura real do jogo.
_SIGN = r"(?:[+-]|[x×])?"

_LINE = re.compile(
    rf"^\s*{_SIGN}\s*"
    rf"(?P<num>{_NUMBER})"
    r"\s*(?P<pct>%?)\s*"
    r"(?P<to>to\s+)?"
    r"(?P<name>.+?)\s*$",
    re.IGNORECASE,
)

# Token numerico ainda sujo, para tentar reparo.
_CONFUSABLE = r"0-9OoDQlIi|ZzASsGTBgq"
_DIRTY = re.compile(
    rf"^\s*{_SIGN}\s*(?P<num>[{_CONFUSABLE}][{_CONFUSABLE}.,]*)\s*(?P<rest>.*)$"
)

_NO_CHANGE = re.compile(r"^\s*no\s*change\b", re.IGNORECASE)

# Numero no MEIO da frase ("Lucky Hit: Up to a 5% Chance...").
#
# Exige pelo menos uma LETRA antes do numero. Sem isso, uma linha cujo digito
# da frente o OCR comeu (".0% Dodge Chance", "431 Maximum Life") caia aqui e
# devolvia o resto como se fosse o valor - 0.0 em vez de 7.0. Como o nome ainda
# casava com o catalogo, a leitura passava por confiavel: exatamente o erro
# silencioso que o parser existe para impedir.
_EMBEDDED = re.compile(r"[A-Za-z].*?(?P<num>[0-9][0-9.,]*)\s*(?P<pct>%?)")

# Similaridade minima para aceitar que o nome lido e' uma entrada do catalogo.
# Medido contra erros reais de OCR: as correcoes legitimas ficam acima de 0.94
# ("Impaiment Reduction" 0.97, "Dodgei Chance" 0.96, "Life on Kil" 0.95). Ja'
# "Life Kil" - que era "+271 Life on Kill" com "71" e "on" comidos - bate 0.82
# em "Life on Kill". Com o limiar antigo isso passava por confiavel valendo 2.
NAME_MATCH_THRESHOLD = 0.86


def _canon(text: str) -> str:
    """Forma canonica para comparar nomes: minusculo, so' letras e digitos."""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def looks_like_affix_name(name: str) -> bool:
    """Filtro para sugerir nomes novos ao catalogo sem sugerir lixo de OCR.

    Nome de afixo do D4 e' texto limpo: sem digito, sem pontuacao solta e com
    pelo menos uma palavra de tamanho decente. Leitura corrompida como
    "+0 +3. Resistance" ou ".0% Healing" cai fora por causa disso.
    """
    name = (name or "").strip()
    if len(name) < 4 or any(c.isdigit() for c in name):
        return False
    if not re.fullmatch(r"[A-Za-z][A-Za-z' -]*", name):
        return False
    return any(len(word) >= 4 for word in name.split())


# Separador seguido de exatamente TRES digitos e' milhar; de um ou dois, decimal.
# O jogo nunca mostra tres casas decimais, entao a contagem decide sozinha.
_THOUSANDS = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")


def _parse_number(token: str) -> float | None:
    """Converte o token numerico, decidindo o papel de cada separador.

    O OCR troca virgula por ponto com frequencia: "+3,000 Fire Resistance" veio
    como "+3. 000 ire Resistance". Tratar o ponto sempre como decimal fazia isso
    virar 3.0 - e, como o NOME casava com o catalogo, a leitura passava por
    confiavel valendo mil vezes menos. Quem desfaz a ambiguidade e' a contagem
    de digitos depois do separador, nao o simbolo lido.
    """
    # O OCR tambem parte o numero ao meio ("1 0.0%", "3. 000").
    compact = re.sub(r"\s+", "", token)
    if _THOUSANDS.match(compact):
        return float(re.sub(r"[.,]", "", compact))

    cleaned = compact.replace(",", "").rstrip(".")
    if not cleaned or not any(c.isdigit() for c in cleaned):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


@dataclass(slots=True)
class AffixEntry:
    """Uma entrada do catalogo. min/max sao opcionais e servem para calcular
    a qualidade do roll; sem eles o app so' compara valor absoluto."""

    name: str
    unit: Unit = Unit.FLAT
    vmin: float | None = None
    vmax: float | None = None
    note: str = ""
    # Em quais espacos este afixo pode sair. Vazio = ainda nao sabemos, e o
    # afixo aparece em qualquer filtro (melhor mostrar demais que esconder algo
    # que existe).
    slots: set[Slot] = field(default_factory=set)
    # A unidade veio de palpite do importador ou foi confirmada por alguem?
    # So' confiamos na unidade do catalogo para corrigir o OCR quando ela foi
    # confirmada - senao um palpite errado estragaria uma leitura boa.
    unit_confirmed: bool = False

    def fits(self, slot: Slot | None) -> bool:
        return slot is None or not self.slots or slot in self.slots

    def roll_quality(self, value: float) -> float | None:
        """0..1 dentro da faixa conhecida, ou None se a faixa nao foi informada."""
        if self.vmin is None or self.vmax is None or self.vmax <= self.vmin:
            return None
        return max(0.0, min(1.0, (value - self.vmin) / (self.vmax - self.vmin)))

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "unit": self.unit.value,
            "vmin": self.vmin,
            "vmax": self.vmax,
            "note": self.note,
            "slots": sorted(s.value for s in self.slots),
            "unit_confirmed": self.unit_confirmed,
        }

    @classmethod
    def from_json(cls, d: dict) -> "AffixEntry":
        slots = set()
        for value in d.get("slots", []):
            try:
                slots.add(Slot(value))
            except ValueError:
                continue
        return cls(
            name=d["name"],
            unit=Unit(d.get("unit", "flat")),
            vmin=d.get("vmin"),
            vmax=d.get("vmax"),
            note=d.get("note", ""),
            slots=slots,
            unit_confirmed=bool(d.get("unit_confirmed", False)),
        )


@dataclass(slots=True)
class ParsedAffix:
    """Resultado de ler uma linha de afixo."""

    raw: str
    name: str
    value: float | None
    unit: Unit
    entry: AffixEntry | None = None
    similarity: float = 0.0
    repaired: bool = False
    no_change: bool = False

    @property
    def confident(self) -> bool:
        """So' e' confiavel se o nome casou com o catalogo e o valor saiu limpo."""
        if self.no_change:
            return True
        return self.entry is not None and self.value is not None

    @property
    def quality(self) -> float | None:
        if self.entry is None or self.value is None:
            return None
        return self.entry.roll_quality(self.value)

    def describe(self) -> str:
        if self.no_change:
            return "No Change"
        if self.value is None:
            return self.raw
        num = f"{self.value:g}"
        q = self.quality
        tail = f"  [{q * 100:.0f}% do max]" if q is not None else ""
        if self.unit is Unit.PERCENT:
            return f"{num}% {self.name}{tail}"
        if self.unit is Unit.RANK:
            return f"+{num} to {self.name}{tail}"
        return f"+{num} {self.name}{tail}"


# Nomes efetivamente observados nos prints de referencia. O catalogo cresce
# sozinho conforme o app le' afixos novos, e da' para editar tudo pela GUI.
SEED_AFFIXES: tuple[tuple[str, Unit], ...] = (
    ("Dexterity", Unit.FLAT),
    ("Maximum Resource", Unit.FLAT),
    ("Shadow Resistance", Unit.FLAT),
    ("Poison Resistance", Unit.FLAT),
    ("Resource Generation", Unit.PERCENT),
    ("Impairment Reduction", Unit.PERCENT),
    ("Imbuement Skills", Unit.RANK),
    ("Trap Skills", Unit.RANK),
    ("Poison Trap", Unit.RANK),
    # Multiplicativos, exibidos com prefixo "x" ("x22% ..."). Vistos ao vivo.
    ("Shadow Damage Multiplier", Unit.PERCENT),
    ("Poison Damage Multiplier", Unit.PERCENT),
)


@dataclass
class AffixCatalog:
    """Dicionario de nomes conhecidos. Serve para dois fins: corrigir o OCR e
    guardar as faixas de roll que o usuario cadastrar."""

    entries: dict[str, AffixEntry] = field(default_factory=dict)
    _index: dict[str, str] = field(default_factory=dict, repr=False)

    # -- construcao -------------------------------------------------------
    @classmethod
    def seeded(cls) -> "AffixCatalog":
        cat = cls()
        for name, unit in SEED_AFFIXES:
            # Unidades conferidas nos prints de referencia.
            cat.add(AffixEntry(name=name, unit=unit, unit_confirmed=True))
        return cat

    def for_slot(self, slot: Slot | None) -> list[AffixEntry]:
        """Afixos que podem sair neste espaco de equipamento."""
        return [e for e in self if e.fits(slot)]

    def add(self, entry: AffixEntry) -> None:
        self.entries[entry.name] = entry
        self._index[_canon(entry.name)] = entry.name

    def remove(self, name: str) -> bool:
        entry = self.entries.pop(name, None)
        if entry is None:
            return False
        self._index.pop(_canon(name), None)
        return True

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        return iter(sorted(self.entries.values(), key=lambda e: e.name))

    # -- casamento --------------------------------------------------------
    def match(self, name: str) -> tuple[AffixEntry | None, float]:
        """Melhor entrada para um nome possivelmente com erro de OCR."""
        if not name:
            return None, 0.0
        key = _canon(name)
        exact = self._index.get(key)
        if exact is not None:
            return self.entries[exact], 1.0

        best: AffixEntry | None = None
        best_score = 0.0
        for canon_key, real in self._index.items():
            score = SequenceMatcher(None, key, canon_key).ratio()
            if score > best_score:
                best, best_score = self.entries[real], score
        if best_score >= NAME_MATCH_THRESHOLD:
            return best, best_score
        return None, best_score

    # -- persistencia -----------------------------------------------------
    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = {"affixes": [e.to_json() for e in self]}
        path.write_text(json.dumps(blob, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "AffixCatalog":
        if not path.exists():
            return cls.seeded()
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls.seeded()
        cat = cls()
        for d in blob.get("affixes", []):
            try:
                cat.add(AffixEntry.from_json(d))
            except (KeyError, ValueError):
                continue
        return cat if cat.entries else cls.seeded()


def _candidates(raw: str):
    """Variacoes da linha para tentar interpretar, da mais fiel a mais reparada.

    A segunda candidata troca letras por digitos no bloco numerico da frente.
    Isso e' necessario porque "+3,0D0 Shadow Resistance" casa com a gramatica
    ingenuamente como valor 3,0 e nome "D0 Shadow Resistance" - um erro
    silencioso, que e' pior do que nao ler nada.
    """
    yield raw, False
    m = _DIRTY.match(raw)
    if m and any(c.isdigit() for c in m.group("num")):
        fixed = m.group("num").translate(_DIGIT_CONFUSION)
        if fixed != m.group("num"):
            yield f"{fixed} {m.group('rest')}", True


def _interpret(text: str, catalog: AffixCatalog | None) -> tuple[ParsedAffix, float] | None:
    """Aplica a gramatica a uma candidata. Devolve (resultado, pontuacao)."""
    m = _LINE.match(text)
    if m is None:
        return None

    value = _parse_number(m.group("num"))
    if m.group("pct"):
        unit = Unit.PERCENT
    elif m.group("to"):
        unit = Unit.RANK
    else:
        unit = Unit.FLAT

    name_raw = m.group("name").strip(" .:-")
    entry, score = catalog.match(name_raw) if catalog else (None, 0.0)
    name = entry.name if entry else name_raw
    if (
        entry is not None
        and entry.unit_confirmed
        and entry.unit is not unit
        and unit is Unit.FLAT
    ):
        # O catalogo sabe a unidade certa; o OCR as vezes come o "%". So' vale
        # para entrada confirmada: o importador chuta a unidade pelo nome, e um
        # palpite errado aqui estragaria uma leitura que estava boa.
        unit = entry.unit

    parsed = ParsedAffix(
        raw=text, name=name, value=value, unit=unit, entry=entry, similarity=score
    )
    # Prioriza casar com o catalogo; empate desempata pela similaridade.
    return parsed, (1.0 if entry is not None else 0.0) + score


def parse_affix(text: str, catalog: AffixCatalog | None = None) -> ParsedAffix:
    """Le uma linha de afixo, corrigindo o que der para corrigir."""
    raw = (text or "").strip()
    if not raw:
        return ParsedAffix(raw="", name="", value=None, unit=Unit.FLAT)

    if _NO_CHANGE.match(raw):
        return ParsedAffix(raw=raw, name="No Change", value=None, unit=Unit.FLAT, no_change=True)

    best: ParsedAffix | None = None
    best_score = -1.0
    best_repaired = False
    for candidate, repaired in _candidates(raw):
        result = _interpret(candidate, catalog)
        if result is None:
            continue
        parsed, score = result
        if score > best_score:
            best, best_score, best_repaired = parsed, score, repaired

    if best is None:
        # A linha nao comeca com numero. Familia "Lucky Hit: Up to a 5%
        # Chance..." traz o valor no MEIO da frase; se o texto casar com o
        # catalogo, extraimos o primeiro numero como valor. A exigencia de
        # casamento vem antes: em texto corrompido o numero solto nao
        # significa nada, e a leitura fica (corretamente) duvidosa.
        entry, score = catalog.match(raw) if catalog else (None, 0.0)
        value = None
        unit = Unit.FLAT
        if entry is not None:
            m = _EMBEDDED.search(raw)
            if m:
                value = _parse_number(m.group("num"))
                unit = Unit.PERCENT if m.group("pct") else entry.unit
        return ParsedAffix(
            raw=raw, name=entry.name if entry else raw, value=value,
            unit=unit, entry=entry, similarity=score,
        )

    best.raw = raw
    best.repaired = best_repaired
    return best
