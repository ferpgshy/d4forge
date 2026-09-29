"""O que cada edição oferece agora — decidido sem tocar em tela nenhuma.

Esta é a única regra de verdade do launcher: dado o que o release publica e o
que existe no disco, o que aquele cartão deve dizer e o que o botão deve
fazer. Ela fica separada da janela por dois motivos:

1. **Dá para testar.** Criar e destruir vários `tk.Tk()` no mesmo processo
   falha de forma intermitente (medido: 1 em cada 4 no Windows). Uma regra
   que só existe dentro do widget só seria testável junto com essa fragilidade.
2. **Ela é a parte que erra.** "Está instalado?", "é mais novo?", "qual pacote
   serve esta edição?" — é aqui que mora o engano caro, não na cor do botão.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .fonte import Manifesto, comparar_versoes

# Os estados possíveis de um cartão.
NAO_INSTALADO = "nao_instalado"
PRONTO = "pronto"
ATUALIZAVEL = "atualizavel"
INDISPONIVEL = "indisponivel"

# Sem manifesto (offline), é preciso adivinhar qual pacote serve cada edição.
# Só existem dois, e a regra é a mesma que o empacotador aplica.
PADRAO = {"autoskill": ("autoskill",), "completo": ("completa", "forge")}


@dataclass(frozen=True)
class Situacao:
    """O veredito sobre uma edição."""

    edicao: str
    chave: str | None
    estado: str
    versao: str = ""
    bytes: int = 0

    @property
    def precisa_baixar(self) -> bool:
        return self.estado in (NAO_INSTALADO, ATUALIZAVEL)

    @property
    def clicavel(self) -> bool:
        return self.estado != INDISPONIVEL


def pacote_de(qual: str, manifesto: Manifesto | None) -> str | None:
    """Qual download serve esta edição.

    `completa` e `forge` saem do MESMO pacote: os dois montados diferem em um
    marcador de dez bytes. O manifesto manda; na falta dele vale a divisão
    padrão, para que estar offline não impeça de abrir o que já está no disco.
    """
    if manifesto is not None:
        pacote = manifesto.pacote_da_edicao(qual)
        if pacote is not None:
            return pacote.chave
        if manifesto.pacotes:
            # O release conhece pacotes, e nenhum atende esta edição.
            return None
    for chave, edicoes in PADRAO.items():
        if qual in edicoes:
            return chave
    return None


def situacao(
    qual: str,
    manifesto: Manifesto | None,
    instaladas: dict[str, dict],
    esta_instalado: Callable[[str], bool],
) -> Situacao:
    """O estado de uma edição, cruzando o publicado com o que há no disco."""
    chave = pacote_de(qual, manifesto)
    if chave is None:
        return Situacao(qual, None, INDISPONIVEL)

    pacote = manifesto.pacotes.get(chave) if manifesto else None
    no_disco = esta_instalado(chave)
    instalada = str((instaladas.get(chave) or {}).get("versao", ""))
    publicada = manifesto.versao if manifesto else ""

    if not no_disco:
        # Nada no disco e nada publicado: não há o que oferecer.
        if pacote is None:
            return Situacao(qual, chave, INDISPONIVEL)
        return Situacao(qual, chave, NAO_INSTALADO, publicada, pacote.bytes)

    # Instalado sem versão anotada (instalação feita à mão, ou estado perdido):
    # não inventa atualização — o usuário decide quando quiser.
    if publicada and instalada and comparar_versoes(publicada, instalada) > 0:
        return Situacao(qual, chave, ATUALIZAVEL, publicada,
                        pacote.bytes if pacote else 0)
    return Situacao(qual, chave, PRONTO, instalada or publicada)
