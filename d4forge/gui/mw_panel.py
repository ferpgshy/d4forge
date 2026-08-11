"""Painel de progresso do Masterworking.

Cada tentativa e' um Masterwork Affix lido: o afixo que o jogo sorteou e se ele
encerrou a sessao. Nao ha' valor a julgar, entao a coluna do meio e' o nome.

Todo o resto - metricas, relogio, detalhes tecnicos, troca de idioma - vem do
painel do encantamento sem alteracao.
"""

from __future__ import annotations

from ..i18n import t
from .progress import ProgressPanel


class MasterworkProgressPanel(ProgressPanel):
    COLUNAS = ("progress.col_n", "mw.col_affix", "progress.col_result")

    def _celulas(self, tentativa) -> list[str]:
        return [
            str(tentativa.index),
            tentativa.affix.raw or tentativa.affix.describe(),
            self._resultado(tentativa),
        ]

    def _add_row(self, tentativa) -> None:
        super()._add_row(tentativa)
        self._current = tentativa.affix.raw or tentativa.affix.describe()

    def _destaques(self, tentativa) -> tuple[int, ...]:
        return (1, 2) if tentativa.accepted else ()

    def _dica(self, tentativa) -> str:
        return tentativa.reason

    def _resultado(self, tentativa) -> str:
        if tentativa.accepted:
            return t("mw.col_done")
        if not tentativa.affix.readable:
            return t("mw.col_unreadable")
        return t("mw.col_rolled")
