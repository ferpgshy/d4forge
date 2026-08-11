"""Criterio de aceite do Masterworking.

Aqui nao ha' valor a julgar. O Masterwork sorteia QUAL afixo do item recebe o
aumento, entao a meta e' um NOME: "quero que caia no Strength". O criterio
inteiro cabe num campo.
"""

from __future__ import annotations

from dataclasses import dataclass

from .result import MasterworkAffix

# Quanto o nome lido precisa parecer com o alvo para contar como acerto.
# E' a mesma barra que o catalogo usa para aceitar um nome vindo do OCR, e ela
# ja' se provou aqui: no print de referencia, o alvo certo da' 1.000 e o
# vizinho "Damage with Slashing Weapons" - sem o "Two-Handed" - da' 0.847.
DEFAULT_THRESHOLD = 0.86


@dataclass
class MasterworkGoal:
    """Em qual afixo o Masterwork tem de cair para a sessao encerrar."""

    affix: str = ""
    threshold: float = DEFAULT_THRESHOLD

    def describe(self) -> str:
        from ..i18n import t

        return self.affix.strip() or t("mw.goal_any")

    def accepts(self, lido: MasterworkAffix) -> tuple[bool, str, dict]:
        """Este Masterwork encerra a sessao? Devolve (aceita, chave, args).

        A chave e os argumentos, em vez da frase pronta, para o motivo poder ser
        reapresentado no idioma que estiver valendo quando o usuario olhar -
        mesma escolha dos outros dois fluxos.
        """
        if not lido.readable:
            return False, "mw.unreadable", {"raw": lido.raw}

        if not self.affix.strip():
            # Sem alvo nao ha' o que perseguir, e rerrolar as cegas queima ouro
            # sem criterio nenhum. Quem chama e' quem impede isso acontecer; se
            # chegou aqui, a leitura boa ja' basta.
            return True, "mw.got_any", {"affix": lido.describe()}

        if lido.matches(self.affix, self.threshold):
            return True, "mw.got_target", {"affix": lido.describe()}

        return False, "mw.other_affix", {
            "affix": lido.describe(), "want": self.affix.strip(),
        }


@dataclass
class MasterworkLimits:
    """Tetos da sessao.

    Nao ha' teto obrigatorio de gasto, pela mesma razao que o Tempering perdeu o
    dele: as vezes a pessoa quer o afixo e o recurso e' o de menos. Quem decide
    e' quem joga.
    """

    max_attempts: int = 50
    max_minutes: float | None = 30.0
