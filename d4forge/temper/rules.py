"""Criterio de aceite do Tempering e politica de recarga.

O criterio padrao e' Greater Affix, que aqui e' um sinal ESTRUTURAL: o jogo
mostra o intervalo num roll normal e o omite num GA. Nao ha' catalogo de faixas
para cadastrar, ao contrario do encantamento.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .result import TemperResult


class Recharge(Enum):
    """O que fazer quando os Temper Rerolls zeram.

    Recarregar consome Pergaminhos, que e' recurso real. Por isso o padrao e'
    parar e avisar: gastar sozinho, em laco, enquanto o usuario nao esta'
    olhando e' o tipo de coisa que so' se descobre depois do estoque acabar.
    """

    STOP = "stop"    # para e avisa
    ONE = "one"      # adiciona 1 reroll e continua
    FULL = "full"    # enche ate' o botao circular apagar (maximo do item)


@dataclass
class TemperGoal:
    """Quando parar de temperar.

    `require_greater` ligado e' o modo do documento: so' o GA encerra. Os outros
    dois criterios existem porque GA e' raro e nem sempre vale a espera.
    """

    require_greater: bool = True
    # Fracao minima do intervalo (0 a 1). Num intervalo [1.500-2.500], 0.9
    # aceita 2.400 ou mais. Ignorado quando o resultado e' GA (nao ha' faixa).
    min_fraction: float | None = None
    # Valor absoluto minimo, para quem sabe o numero que quer.
    min_value: float | None = None
    # O afixo tem de conter este trecho. Serve para receitas que sorteiam entre
    # varios afixos: sem isso, o ciclo pararia num GA do afixo errado.
    affix_contains: str = ""

    # -- politica de recarga ----------------------------------------------
    recharge: Recharge = Recharge.STOP
    # Teto de recargas na sessao, ou None para nao ter teto. Sem limite e' uma
    # escolha legitima: as vezes se quer o afixo e o Pergaminho e' o de menos.
    max_recharges: int | None = None

    def describe(self) -> str:
        from ..i18n import t

        partes = []
        if self.require_greater:
            partes.append(t("temper.goal_ga"))
        if self.min_fraction is not None:
            partes.append(t("temper.goal_fraction", pct=self.min_fraction * 100))
        if self.min_value is not None:
            partes.append(t("temper.goal_value", value=self.min_value))
        if self.affix_contains:
            partes.append(f"'{self.affix_contains}'")
        return " / ".join(partes) or t("temper.goal_any")

    def matches_affix(self, result: TemperResult) -> bool:
        if not self.affix_contains:
            return True
        return self.affix_contains.strip().lower() in result.raw.lower()

    def accepts(self, result: TemperResult) -> tuple[bool, str, dict]:
        """Este resultado encerra a sessao? Devolve (aceita, chave, args).

        A chave e os argumentos, em vez da frase pronta, para o motivo poder ser
        reapresentado no idioma que estiver valendo quando o usuario olhar -
        mesma escolha do encantamento.
        """
        if not result.readable:
            return False, "temper.unreadable", {}

        if not self.matches_affix(result):
            return False, "temper.other_affix", {"want": self.affix_contains}

        if self.require_greater and result.greater:
            return True, "temper.got_ga", {"value": result.value}

        if self.min_value is not None and result.value >= self.min_value:
            return True, "temper.got_value", {"value": result.value}

        if self.min_fraction is not None:
            fracao = result.fraction
            # Um GA nao tem faixa, entao nao ha' fracao para comparar - mas ele
            # e' por definicao melhor que qualquer roll dentro do intervalo.
            if result.greater:
                return True, "temper.got_ga", {"value": result.value}
            if fracao is not None and fracao >= self.min_fraction:
                return True, "temper.got_fraction", {
                    "value": result.value, "pct": fracao * 100,
                }

        # Nenhum criterio definido: qualquer leitura boa serve.
        if not (self.require_greater or self.min_value or self.min_fraction):
            return True, "temper.got_any", {"value": result.value}

        return False, "temper.keep_rolling", {"affix": result.describe()}


@dataclass
class TemperLimits:
    """Tetos da sessao."""

    max_attempts: int = 100
    max_minutes: float | None = 30.0
    scrolls_spent: int = field(default=0, repr=False)
