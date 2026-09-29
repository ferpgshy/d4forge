"""O launcher trocando a si mesmo.

No Windows um executável em uso **não pode ser apagado, mas pode ser
renomeado** — é essa assimetria que torna a troca possível sem instalador e
sem pedir administrador. A sequência:

    d4forge-launcher.exe        -> d4forge-launcher.antigo-1234.exe
    (baixado) novo executável   -> d4forge-launcher.exe
    abre o novo, este sai
    na próxima abertura, apaga o que sobrou

O nome do arquivo aposentado leva o PID. Com um nome fixo, uma segunda janela
aberta segurando o `.antigo` travaria toda atualização seguinte — é uma
armadilha conhecida desse padrão, e custa uma interpolação evitá-la.

`MoveFileEx` com `MOVEFILE_DELAY_UNTIL_REBOOT` resolveria o caso de arquivo
travado, mas exige token de administrador e só age no próximo boot. Para um
executável solto isso seria pedir demais e entregar tarde.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from . import __version__
from .fonte import Manifesto, comparar_versoes

log = logging.getLogger(__name__)

APOSENTADO = ".antigo-"


def caminho_do_launcher() -> Path:
    """O executável em execução — ou o script, rodando do código-fonte."""
    return Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve()


def ha_launcher_mais_novo(manifesto: Manifesto) -> bool:
    anunciada = manifesto.launcher_versao
    if not anunciada:
        return False
    return comparar_versoes(anunciada, __version__) > 0


def limpar_aposentados(pasta: Path | None = None) -> int:
    """Apaga os executáveis que já foram substituídos. Nunca levanta."""
    pasta = pasta or caminho_do_launcher().parent
    apagados = 0
    for resto in pasta.glob(f"*{APOSENTADO}*"):
        try:
            resto.unlink()
            apagados += 1
        except OSError:
            # Ainda em uso por outra janela aberta. Não é erro: some depois.
            pass
    return apagados


def trocar(novo: Path, atual: Path | None = None, reiniciar: bool = True) -> Path:
    """Põe `novo` no lugar do launcher atual e devolve o caminho aposentado.

    Não apaga o antigo aqui: apagar um executável em uso falha no Windows.
    Quem apaga é `limpar_aposentados()`, na abertura seguinte.
    """
    atual = (atual or caminho_do_launcher()).resolve()
    aposentado = atual.with_name(f"{atual.stem}{APOSENTADO}{os.getpid()}{atual.suffix}")

    atual.rename(aposentado)
    try:
        novo.replace(atual)
    except OSError:
        # Não conseguiu pôr o novo no lugar: devolve o antigo ao posto, senão
        # o usuário fica sem launcher nenhum.
        aposentado.rename(atual)
        raise

    if reiniciar:
        subprocess.Popen([str(atual)], cwd=str(atual.parent))
    return aposentado
