"""Onde o aplicativo fica, como ele é trocado e como ele é aberto.

Duas regras mandam aqui, e as duas vêm de erro já cometido neste projeto:

1. **A pasta `data/` é do usuário.** Atualizar já apagou as binds de quem usa
   isto — o build fazia `rmtree` na pasta inteira. Aqui a troca é feita numa
   pasta ao lado e `data/` é transplantada antes de qualquer coisa virar
   definitiva.
2. **Nada é trocado enquanto o aplicativo está aberto.** No Windows a pasta de
   um processo vivo não se renomeia, e é bom que não se renomeie: a tentativa
   falha inteira em vez de deixar meia instalação no disco.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

ESTADO = "d4forge-launcher.json"
SUFIXO_NOVO = ".novo"
SUFIXO_ANTIGO = ".antigo"

# Onde o marcador de edição mora dentro de um pacote do PyInstaller.
MARCADOR = Path("_internal") / "d4forge" / "resources" / "edicao.txt"


class InstalacaoOcupada(RuntimeError):
    """O aplicativo está aberto — fechar é condição para trocar arquivos."""


def congelado() -> bool:
    return bool(getattr(sys, "frozen", False))


def _escrevivel(pasta: Path) -> bool:
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        teste = pasta / ".teste-de-escrita"
        teste.write_bytes(b"")
        teste.unlink()
        return True
    except OSError:
        return False


def raiz() -> Path:
    """A pasta onde as edições são instaladas.

    Ao lado do launcher, para que o conjunto continue portátil — copiar a
    pasta leva tudo, que é como este projeto sempre foi distribuído. Se esse
    lugar não aceitar escrita (Arquivos de Programas, pendrive travado,
    pasta de Downloads sob política), cai em `%LOCALAPPDATA%\\d4forge`.
    """
    if congelado():
        vizinha = Path(sys.executable).resolve().parent
    else:
        vizinha = Path(__file__).resolve().parent.parent
    if _escrevivel(vizinha):
        return vizinha
    reserva = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "d4forge"
    reserva.mkdir(parents=True, exist_ok=True)
    return reserva


@dataclass
class Estado:
    """O que o launcher lembra entre uma abertura e outra."""

    instalados: dict[str, dict] = field(default_factory=dict)
    edicao: str = ""
    idioma: str = "pt-BR"

    @classmethod
    def carregar(cls, pasta: Path | None = None) -> "Estado":
        arquivo = (pasta or raiz()) / ESTADO
        try:
            bruto = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        return cls(
            instalados=dict(bruto.get("instalados") or {}),
            edicao=str(bruto.get("edicao", "")),
            idioma=str(bruto.get("idioma", "pt-BR")),
        )

    def salvar(self, pasta: Path | None = None) -> None:
        arquivo = (pasta or raiz()) / ESTADO
        try:
            arquivo.write_text(
                json.dumps(
                    {
                        "instalados": self.instalados,
                        "edicao": self.edicao,
                        "idioma": self.idioma,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError as erro:  # disco cheio, pasta somente-leitura
            log.warning("não deu para gravar %s: %s", arquivo, erro)

    def versao_de(self, chave: str) -> str:
        return str((self.instalados.get(chave) or {}).get("versao", ""))


def pasta_do_pacote(chave: str, base: Path | None = None) -> Path:
    return (base or raiz()) / f"d4forge-{chave}"


def executavel_em(pasta: Path) -> Path | None:
    """O .exe do aplicativo dentro de uma instalação, se ela existir."""
    if not pasta.is_dir():
        return None
    candidatos = sorted(pasta.glob("d4forge*.exe"))
    return candidatos[0] if candidatos else None


def instalado(chave: str, base: Path | None = None) -> bool:
    return executavel_em(pasta_do_pacote(chave, base)) is not None


def _raiz_do_zip(extraido: Path) -> Path:
    """O conteúdo do zip, pulando a pasta única que ele costuma ter dentro."""
    filhos = [c for c in extraido.iterdir() if not c.name.startswith(".")]
    if len(filhos) == 1 and filhos[0].is_dir():
        return filhos[0]
    return extraido


def extrair(
    zip_path: Path,
    chave: str,
    base: Path | None = None,
    progresso: Callable[[int, int], None] | None = None,
) -> Path:
    """Instala (ou atualiza) um pacote, preservando a `data/` que existir.

    A ordem existe para que uma falha no meio não deixe o usuário sem nada:
    extrai ao lado, transplanta a `data/`, e só então troca as pastas de
    lugar. Se a troca falhar, a instalação antiga continua íntegra.
    """
    base = base or raiz()
    destino = pasta_do_pacote(chave, base)
    novo = base / f"d4forge-{chave}{SUFIXO_NOVO}"
    antigo = base / f"d4forge-{chave}{SUFIXO_ANTIGO}"

    for resto in (novo, antigo):
        if resto.exists():
            shutil.rmtree(resto, ignore_errors=True)

    with zipfile.ZipFile(zip_path) as zf:
        itens = zf.infolist()
        for i, item in enumerate(itens, 1):
            zf.extract(item, novo)
            if progresso:
                progresso(i, len(itens))

    conteudo = _raiz_do_zip(novo)

    # A `data/` do usuário vale mais que a do pacote: binds, catálogo editado,
    # geometria da janela. Ela entra por cima do que veio no zip.
    dados_atuais = destino / "data"
    if dados_atuais.is_dir():
        dados_novos = conteudo / "data"
        if dados_novos.is_dir():
            shutil.rmtree(dados_novos, ignore_errors=True)
        shutil.copytree(dados_atuais, dados_novos)

    if destino.exists():
        try:
            destino.rename(antigo)
        except OSError as erro:
            shutil.rmtree(novo, ignore_errors=True)
            raise InstalacaoOcupada(
                "feche o d4forge antes de atualizar"
            ) from erro
    try:
        conteudo.rename(destino)
    except OSError:
        # `conteudo` pode estar dentro de `novo`: copiar resolve o caso raro
        # em que renomear atravessa volumes ou esbarra em antivírus.
        shutil.copytree(conteudo, destino)
    shutil.rmtree(novo, ignore_errors=True)
    shutil.rmtree(antigo, ignore_errors=True)
    return destino


def marcar_edicao(pasta: Path, qual: str) -> None:
    """Grava a edição dentro do pacote instalado.

    O launcher já passa `D4FORGE_EDICAO` ao abrir, mas quem cria um atalho
    para o `.exe` — e alguém sempre cria — não passa variável nenhuma. O
    marcador faz o clique direto abrir a mesma edição que foi escolhida aqui.
    """
    alvo = pasta / MARCADOR
    if not alvo.parent.is_dir():
        return
    try:
        alvo.write_text(qual, encoding="utf-8")
    except OSError as erro:
        log.warning("não deu para marcar a edição em %s: %s", alvo, erro)


def abrir(chave: str, qual: str, base: Path | None = None) -> subprocess.Popen:
    """Abre a edição escolhida e devolve o processo."""
    pasta = pasta_do_pacote(chave, base)
    exe = executavel_em(pasta)
    if exe is None:
        raise FileNotFoundError(f"não achei o d4forge em {pasta}")
    marcar_edicao(pasta, qual)
    ambiente = dict(os.environ, D4FORGE_EDICAO=qual)
    return subprocess.Popen([str(exe)], cwd=str(pasta), env=ambiente)


def limpar_restos(base: Path | None = None) -> int:
    """Remove sobras de uma atualização interrompida. Nunca levanta."""
    base = base or raiz()
    removidos = 0
    for molde in (f"*{SUFIXO_NOVO}", f"*{SUFIXO_ANTIGO}", "*.parcial"):
        for resto in base.glob(molde):
            try:
                if resto.is_dir():
                    shutil.rmtree(resto)
                else:
                    resto.unlink()
                removidos += 1
            except OSError:
                pass
    return removidos
