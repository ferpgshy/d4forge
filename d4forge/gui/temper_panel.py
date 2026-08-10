"""Painel de progresso do Tempering.

O Tempering sorteia UM afixo por tentativa, e nao duas opcoes como o
encantamento. Entao a tabela tem tres colunas em vez de quatro, e o veredito
diz se aquele roll encerrou a sessao.

Todo o resto - metricas, relogio, detalhes tecnicos, troca de idioma - vem do
painel do encantamento sem alteracao.
"""

from __future__ import annotations

from ..i18n import t
from .progress import ProgressPanel


class TemperProgressPanel(ProgressPanel):
    COLUNAS = ("progress.col_n", "temper.col_affix", "progress.col_result")

    def _celulas(self, tentativa) -> list[str]:
        # A linha CRUA, como o jogo escreveu, e nao o resumo numerico: e' ela
        # que diz qual afixo saiu, e o afixo importa tanto quanto o valor
        # quando a receita sorteia entre varios.
        return [
            str(tentativa.index),
            tentativa.result.raw or tentativa.result.describe(),
            self._resultado(tentativa),
        ]

    def _add_row(self, tentativa) -> None:
        super()._add_row(tentativa)
        # A métrica "Afixo atual" mostra o último roll: no Tempering não há
        # evento de leitura separado como no encantamento.
        self._current = tentativa.result.raw or tentativa.result.describe()

    def _destaques(self, tentativa) -> tuple[int, ...]:
        # A rodada que encerrou a sessao e' a unica que interessa achar de
        # relance numa tabela de 100 linhas.
        return (1, 2) if tentativa.accepted else ()

    def _dica(self, tentativa) -> str:
        return tentativa.reason

    def _resultado(self, tentativa) -> str:
        if tentativa.accepted:
            return t("temper.col_done")
        if tentativa.result.greater:
            return t("temper.col_ga")
        return t("temper.col_rolled")
