"""Criterios de aceite: quando parar de rolar.

Uma regra e' "nome do afixo + condicao sobre o valor". Da' para exigir valor
absoluto (>= 3000), percentual do roll maximo (>= 90% do max), ou so' o nome.
Varias regras convivem: basta uma bater para a opcao ser aceitavel.

A decisao final e' conservadora de proposito. Se as duas opcoes servem, pega a
melhor; se nenhuma serve, ou se a leitura nao e' confiavel, mantem No Change -
gastar mais uma tentativa e' barato, trocar o afixo bom por engano nao tem
desfazer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .affixes import ParsedAffix, Unit


class Comparison(Enum):
    ANY = "any"    # qualquer valor serve, basta o nome bater
    GE = "ge"      # >=
    GT = "gt"      # >
    LE = "le"      # <=
    LT = "lt"      # <
    EQ = "eq"      # ==

    @property
    def label(self) -> str:
        return {
            "any": "qualquer valor",
            "ge": ">=",
            "gt": ">",
            "le": "<=",
            "lt": "<",
            "eq": "=",
        }[self.value]

    def test(self, value: float, threshold: float) -> bool:
        if self is Comparison.ANY:
            return True
        if self is Comparison.GE:
            return value >= threshold
        if self is Comparison.GT:
            return value > threshold
        if self is Comparison.LE:
            return value <= threshold
        if self is Comparison.LT:
            return value < threshold
        return abs(value - threshold) < 1e-9


@dataclass(slots=True)
class TargetRule:
    """Um afixo que voce quer, com a condicao que ele precisa cumprir."""

    affix_name: str
    comparison: Comparison = Comparison.GE
    threshold: float = 0.0
    # Exigencia opcional de qualidade do roll (0..1). So' funciona se a entrada
    # do catalogo tiver min/max cadastrados.
    min_quality: float | None = None
    enabled: bool = True
    priority: int = 0  # maior ganha quando as duas opcoes servem
    # Escalada: enquanto o item NAO tem o afixo-alvo, aceita-o com qualquer
    # valor; depois so' troca por valor estritamente maior, ate' a meta acima
    # ser atingida. Cada tentativa custa o mesmo escolhendo ou nao, entao
    # segurar o nome certo cedo nunca sai mais caro - so' converge mais rapido.
    climb: bool = True

    def matches(self, parsed: ParsedAffix) -> bool:
        if not self.enabled or parsed.no_change:
            return False
        if parsed.name.strip().lower() != self.affix_name.strip().lower():
            return False

        if self.min_quality is not None:
            quality = parsed.quality
            if quality is None or quality < self.min_quality:
                return False

        if self.comparison is Comparison.ANY:
            return True
        if parsed.value is None:
            return False
        return self.comparison.test(parsed.value, self.threshold)

    def describe(self) -> str:
        parts = [self.affix_name]
        if self.comparison is not Comparison.ANY:
            parts.append(f"{self.comparison.label} {self.threshold:g}")
        if self.min_quality is not None:
            parts.append(f"e roll >= {self.min_quality * 100:.0f}%")
        return " ".join(parts)

    def same_affix(self, parsed: ParsedAffix) -> bool:
        return parsed.name.strip().lower() == self.affix_name.strip().lower()

    def to_json(self) -> dict:
        return {
            "affix_name": self.affix_name,
            "comparison": self.comparison.value,
            "threshold": self.threshold,
            "min_quality": self.min_quality,
            "enabled": self.enabled,
            "priority": self.priority,
            "climb": self.climb,
        }

    @classmethod
    def from_json(cls, d: dict) -> "TargetRule":
        return cls(
            affix_name=d["affix_name"],
            comparison=Comparison(d.get("comparison", "ge")),
            threshold=float(d.get("threshold", 0.0)),
            min_quality=d.get("min_quality"),
            enabled=bool(d.get("enabled", True)),
            priority=int(d.get("priority", 0)),
            climb=bool(d.get("climb", True)),
        )


class Action(Enum):
    """O que fazer na tela Replace Affix."""

    TAKE_OPTION_1 = 0
    TAKE_OPTION_2 = 1
    NO_CHANGE = 2

    @property
    def orb_index(self) -> int:
        """Indice do orbe correspondente na tela (0, 1 ou 2 = No Change)."""
        return self.value


@dataclass(frozen=True, slots=True)
class Decision:
    action: Action
    rule: TargetRule | None
    # Chave de traducao + argumentos, nao texto pronto: a decisao e' guardada no
    # historico e precisa ser reapresentada no idioma que estiver valendo.
    key: str = ""
    params: dict = field(default_factory=dict)
    # A opcao escolhida ja' cumpre a meta final? Um degrau de escalada e'
    # aceito (accepted=True) mas nao encerra a sessao (goal_reached=False).
    goal_reached: bool = False

    @property
    def reason(self) -> str:
        from .i18n import t

        return t(self.key, **self.params) if self.key else ""

    @property
    def accepted(self) -> bool:
        return self.action is not Action.NO_CHANGE


@dataclass
class RuleSet:
    rules: list[TargetRule] = field(default_factory=list)
    # Recusar leitura duvidosa. Deixe ligado: o custo de errar e' assimetrico.
    require_confident: bool = True

    @property
    def active(self) -> list[TargetRule]:
        return [r for r in self.rules if r.enabled]

    def first_match(self, parsed: ParsedAffix) -> TargetRule | None:
        """Regra de maior prioridade que aceita este afixo (a meta final)."""
        hits = [r for r in self.active if r.matches(parsed)]
        if not hits:
            return None
        return max(hits, key=lambda r: (r.priority, r.threshold))

    def _climb_match(
        self, parsed: ParsedAffix, current: ParsedAffix | None
    ) -> tuple[TargetRule, str] | None:
        """Degrau de escalada: melhora sem ainda cumprir a meta.

        Exige leitura CONFIAVEL do afixo atual do item. Sem saber o que temos,
        trocar seria apostar - e' assim que se rebaixa um 22% para 20% sem
        perceber. Na duvida, so' a regra cheia decide.
        """
        if parsed.no_change or current is None or not current.confident:
            return None
        for rule in sorted(self.active, key=lambda r: -r.priority):
            if not rule.climb or not rule.same_affix(parsed):
                continue
            if not rule.same_affix(current):
                # O item ainda nao tem o afixo-alvo: qualquer valor dele e'
                # melhor do que continuar com o afixo errado.
                return rule, ("decision.climb_first", {"held": current.name})
            if (
                parsed.value is not None
                and current.value is not None
                and parsed.value > current.value
            ):
                # Estritamente maior: valor igual seria troca inutil.
                return rule, (
                    "decision.climb_up",
                    {"value": parsed.value, "current": current.value},
                )
        return None

    def decide(
        self, options: list[ParsedAffix], current: ParsedAffix | None = None
    ) -> Decision:
        """Escolhe entre as opcoes da tela Replace Affix.

        `current` e' o afixo que o item tem agora (lido da propria tela) -
        e' ele que permite a escalada: aceitar o nome certo com qualquer valor
        e depois so' subir, ate' a meta da regra.
        """
        if not self.active:
            return Decision(Action.NO_CHANGE, None, "decision.no_rules")

        # (indice, regra, opcao, cumpre_meta, chave, argumentos)
        candidates: list[tuple[int, TargetRule, ParsedAffix, bool, str, dict]] = []
        for idx, parsed in enumerate(options):
            if idx > 1:
                break
            if self.require_confident and not parsed.confident:
                continue
            rule = self.first_match(parsed)
            if rule is not None:
                candidates.append((
                    idx, rule, parsed, True, "decision.goal",
                    {"index": idx + 1, "rule": rule.describe()},
                ))
                continue
            climb = self._climb_match(parsed, current)
            if climb is not None:
                rule, (chave, args) = climb
                candidates.append((idx, rule, parsed, False, chave, {**args, "index": idx + 1}))

        if not candidates:
            unsure = [
                o for o in options[:2]
                if self.require_confident and not o.confident
            ]
            if unsure:
                return Decision(
                    Action.NO_CHANGE, None, "decision.doubtful", {"count": len(unsure)}
                )
            return Decision(Action.NO_CHANGE, None, "decision.no_match")

        # Meta cumprida ganha de degrau; depois prioridade, qualidade e valor.
        def score(item):
            _idx, rule, parsed, goal, _k, _p = item
            return (goal, rule.priority, parsed.quality or 0.0, parsed.value or 0.0)

        idx, rule, parsed, goal, chave, args = max(candidates, key=score)
        action = Action.TAKE_OPTION_1 if idx == 0 else Action.TAKE_OPTION_2
        return Decision(action, rule, chave, args, goal_reached=goal)

    # -- persistencia -----------------------------------------------------
    def to_json(self) -> dict:
        return {
            "require_confident": self.require_confident,
            "rules": [r.to_json() for r in self.rules],
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_json(), indent=2, ensure_ascii=False), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path) -> "RuleSet":
        if not path.exists():
            return cls()
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        rules = []
        for d in blob.get("rules", []):
            try:
                rules.append(TargetRule.from_json(d))
            except (KeyError, ValueError):
                continue
        return cls(rules=rules, require_confident=bool(blob.get("require_confident", True)))
