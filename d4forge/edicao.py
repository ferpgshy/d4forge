"""Qual recorte do app este executavel e'.

Sao tres, e a diferenca nao e' so' cosmetica:

    completa   tudo - as tres bancadas de crafting mais o AutoSkill
    forge      so' Enchant, Tempering, Masterworking e o Catalogo
    autoskill  so' o AutoSkill

O AutoSkill **nao usa OCR**. Ele le' o HUD por estatistica de brilho, nao por
texto. Entao a edicao dele dispensa o rapidocr e o onnxruntime - 57 MB do
pacote - e nao paga o segundo de partida que importar os ~880 afixos custa.
Nao e' apenas um filtro de abas: e' menos coisa dentro do executavel.

COMO A EDICAO E' DECIDIDA, em ordem:

1. A variavel de ambiente `D4FORGE_EDICAO`. Existe para desenvolvimento e
   testes: da' para rodar as tres edicoes do mesmo codigo sem recompilar.
2. Um arquivo `edicao.txt` nos recursos, que o build grava. E' o que vale no
   executavel.
3. Na falta dos dois, `completa` - rodar do codigo-fonte mostra tudo.

Valor desconhecido cai em `completa` e registra aviso, NUNCA levanta: isto e'
lido na abertura da janela, e um arquivo estragado nao pode impedir o app de
abrir.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

COMPLETA = "completa"
FORGE = "forge"
AUTOSKILL = "autoskill"

TODAS = (COMPLETA, FORGE, AUTOSKILL)

VARIAVEL = "D4FORGE_EDICAO"
ARQUIVO = "edicao.txt"

# Quais abas cada edicao mostra, na ordem em que aparecem.
ABAS: dict[str, tuple[str, ...]] = {
    COMPLETA: ("enchant", "temper", "mw", "autoskill", "catalog"),
    FORGE: ("enchant", "temper", "mw", "catalog"),
    AUTOSKILL: ("autoskill",),
}

# As bancadas de crafting: sao elas que leem texto da tela.
ABAS_DE_OCR = frozenset({"enchant", "temper", "mw", "catalog"})

NOMES = {
    COMPLETA: "d4forge",
    FORGE: "d4forge Forge",
    AUTOSKILL: "d4forge AutoSkill",
}

_cache: str | None = None


def _do_arquivo() -> str | None:
    from . import config

    for pasta in (config.RESOURCE_DIR, Path(__file__).resolve().parent):
        caminho = Path(pasta) / "d4forge" / "resources" / ARQUIVO
        alternativa = Path(pasta) / "resources" / ARQUIVO
        for alvo in (caminho, alternativa):
            try:
                if alvo.is_file():
                    return alvo.read_text(encoding="utf-8").strip().lower()
            except OSError:
                continue
    return None


def atual() -> str:
    """A edicao deste executavel. Resolvida uma vez e guardada."""
    global _cache
    if _cache is not None:
        return _cache

    bruto = os.environ.get(VARIAVEL) or _do_arquivo()
    if bruto:
        bruto = bruto.strip().lower()
        if bruto in TODAS:
            _cache = bruto
            return _cache
        log.warning("edicao desconhecida %r; usando %s", bruto, COMPLETA)
    _cache = COMPLETA
    return _cache


def esquecer() -> None:
    """Zera o cache. Existe para os testes trocarem de edicao."""
    global _cache
    _cache = None


def abas() -> tuple[str, ...]:
    return ABAS[atual()]


def tem(aba: str) -> bool:
    return aba in ABAS[atual()]


def precisa_de_ocr() -> bool:
    """Alguma aba desta edicao le' texto da tela?

    Quando nao, a partida pula o catalogo e o leitor - e o build pode deixar
    o onnxruntime inteiro de fora.
    """
    return bool(ABAS_DE_OCR & set(ABAS[atual()]))


def nome() -> str:
    return NOMES.get(atual(), NOMES[COMPLETA])


__all__ = [
    "ABAS",
    "AUTOSKILL",
    "COMPLETA",
    "FORGE",
    "TODAS",
    "abas",
    "atual",
    "esquecer",
    "nome",
    "precisa_de_ocr",
    "tem",
]
