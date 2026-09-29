"""De onde vem o d4forge — releases do GitHub, sem passar pela API.

`api.github.com` sem autenticação dá **60 requisições por hora por IP**, e num
provedor com NAT esse orçamento é dividido com desconhecidos: o launcher
falharia por culpa de terceiros. O site tem dois caminhos que resolvem a mesma
coisa sem contar nesse limite, e os dois foram medidos contra este repositório:

    GET /ferpgshy/d4forge/releases/latest
        -> 302  .../releases/tag/v1.6.2
    GET /ferpgshy/d4forge/releases/latest/download/<arquivo>
        -> 302  -> release-assets.githubusercontent.com

O segundo responde **206 a um cabeçalho `Range`**, então um download
interrompido continua de onde parou em vez de recomeçar os 141 MB.

HTTPS: medido dentro do executável congelado, `ssl.create_default_context()`
carrega 44 autoridades do próprio Windows — não é preciso empacotar `certifi`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

DONO = "ferpgshy"
REPO = "d4forge"
BASE = f"https://github.com/{DONO}/{REPO}"

# O nome PRECISA ser estável entre releases: é ele que faz `latest/download`
# funcionar. Um nome com a versão dentro quebra no dia seguinte.
MANIFESTO = "manifesto.json"
LAUNCHER = "d4forge-launcher.exe"

# Aponta o launcher para outro lugar — uma pasta servida na própria máquina,
# por exemplo. Existe para conferir um release ANTES de publicá-lo: sem isto,
# o primeiro teste de verdade do fluxo de download seria com usuários dentro.
# Com a variável, os arquivos são buscados direto em `<origem>/<arquivo>`.
VARIAVEL_DE_ORIGEM = "D4FORGE_ORIGEM"

AGENTE = "d4forge-launcher"
TEMPO_LIMITE = 30
PEDACO = 1 << 16          # 64 KiB: progresso fluido sem custo de syscall
TENTATIVAS = 4


class FalhaDeRede(RuntimeError):
    """Não deu para falar com o GitHub — sem internet, DNS, bloqueio."""


class ArquivoCorrompido(RuntimeError):
    """O que chegou não confere com o sha256 anunciado no manifesto."""


def origem() -> str:
    """A origem alternativa, se alguém tiver apontado para uma."""
    return os.environ.get(VARIAVEL_DE_ORIGEM, "").rstrip("/")


def url_do_asset(arquivo: str, tag: str | None = None) -> str:
    """Endereço de um arquivo do release: o mais novo, ou o de uma versão."""
    alternativa = origem()
    if alternativa:
        return f"{alternativa}/{arquivo}"
    if tag:
        return f"{BASE}/releases/download/{tag}/{arquivo}"
    return f"{BASE}/releases/latest/download/{arquivo}"


def _abrir(url: str, cabecalhos: dict[str, str] | None = None,
           metodo: str = "GET"):
    pedido = urllib.request.Request(
        url, method=metodo, headers={"User-Agent": AGENTE, **(cabecalhos or {})}
    )
    return urllib.request.urlopen(
        pedido, timeout=TEMPO_LIMITE, context=ssl.create_default_context()
    )


class _NaoSeguir(urllib.request.HTTPRedirectHandler):
    """Segura o redirecionamento para que dê para ler o destino."""

    def redirect_request(self, *_a, **_k):
        return None


def tag_mais_nova() -> str:
    """A tag do release mais recente, lida do redirecionamento.

    Reserva para quando o manifesto não existe: releases publicados antes do
    launcher não têm o arquivo, e o launcher não pode ficar cego por isso.
    """
    pedido = urllib.request.Request(
        f"{BASE}/releases/latest", method="HEAD", headers={"User-Agent": AGENTE}
    )
    abridor = urllib.request.build_opener(_NaoSeguir)
    try:
        abridor.open(pedido, timeout=TEMPO_LIMITE)
    except urllib.error.HTTPError as erro:
        destino = erro.headers.get("Location") or ""
        if "/tag/" in destino:
            return destino.rsplit("/tag/", 1)[1].strip()
        raise FalhaDeRede(f"resposta inesperada do GitHub: {erro.code}") from erro
    except OSError as erro:
        raise FalhaDeRede(str(erro)) from erro
    raise FalhaDeRede("o GitHub não redirecionou para nenhuma versão")


@dataclass(frozen=True)
class Pacote:
    """Um arquivo baixável e as edições que ele serve.

    Uma edição não é um pacote: `completa` e `forge` são o MESMO download —
    os dois pacotes montados diferem em cinco linhas de 621 arquivos, e a
    diferença que importa é um marcador de dez bytes. Publicar dois zips de
    141 MB idênticos seria cobrar do usuário o preço de um detalhe interno.
    """

    chave: str
    arquivo: str
    bytes: int
    sha256: str
    edicoes: tuple[str, ...]


@dataclass(frozen=True)
class Manifesto:
    """O que o release mais novo oferece."""

    versao: str
    tag: str
    pacotes: dict[str, Pacote]
    launcher_versao: str = ""
    launcher_sha256: str = ""

    def pacote_da_edicao(self, qual: str) -> Pacote | None:
        for pacote in self.pacotes.values():
            if qual in pacote.edicoes:
                return pacote
        return None


def ler_manifesto(bruto: dict) -> Manifesto:
    """Converte o JSON publicado, tolerando campos que ainda não existem."""
    pacotes: dict[str, Pacote] = {}
    for chave, dados in (bruto.get("pacotes") or {}).items():
        pacotes[chave] = Pacote(
            chave=chave,
            arquivo=str(dados.get("arquivo", "")),
            bytes=int(dados.get("bytes", 0)),
            sha256=str(dados.get("sha256", "")),
            edicoes=tuple(dados.get("edicoes") or ()),
        )
    lanc = bruto.get("launcher") or {}
    return Manifesto(
        versao=str(bruto.get("versao", "")),
        tag=str(bruto.get("tag", "")),
        pacotes=pacotes,
        launcher_versao=str(lanc.get("versao", "")),
        launcher_sha256=str(lanc.get("sha256", "")),
    )


def buscar_manifesto(base_url: str | None = None) -> Manifesto:
    """Uma requisição resolve tudo: versão, arquivos, tamanhos e sha256."""
    raiz = base_url or origem()
    url = f"{raiz}/{MANIFESTO}" if raiz else url_do_asset(MANIFESTO)
    try:
        with _abrir(url) as resposta:
            return ler_manifesto(json.loads(resposta.read().decode("utf-8")))
    except urllib.error.HTTPError as erro:
        if erro.code == 404:
            # Release antigo, sem manifesto: ao menos a versão dá para saber.
            tag = tag_mais_nova()
            return Manifesto(versao=tag.lstrip("v"), tag=tag, pacotes={})
        raise FalhaDeRede(f"o GitHub respondeu {erro.code}") from erro
    except (OSError, ValueError) as erro:
        raise FalhaDeRede(str(erro)) from erro


def comparar_versoes(a: str, b: str) -> int:
    """-1, 0 ou 1. Compara número a número; o que não for número vale 0.

    Não é semver completo de propósito: as versões daqui são `1.6.2`, e um
    analisador genérico seria mais código do que o problema pede.
    """

    def partes(v: str) -> list[int]:
        limpo = v.strip().lstrip("vV")
        return [
            int(p) if p.isdigit() else 0
            for p in limpo.replace("-", ".").split(".")
        ]

    pa, pb = partes(a), partes(b)
    tamanho = max(len(pa), len(pb))
    pa += [0] * (tamanho - len(pa))
    pb += [0] * (tamanho - len(pb))
    return (pa > pb) - (pa < pb)


def _digerir(caminho: Path) -> "hashlib._Hash":
    digestor = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        while True:
            bloco = arquivo.read(PEDACO)
            if not bloco:
                break
            digestor.update(bloco)
    return digestor


def sha256_de(caminho: Path) -> str:
    return _digerir(caminho).hexdigest()


def baixar(
    url: str,
    destino: Path,
    *,
    sha256: str = "",
    total_esperado: int = 0,
    progresso: Callable[[int, int], None] | None = None,
    cancelar: Callable[[], bool] | None = None,
) -> Path:
    """Baixa `url` para `destino`, retomando o que já estiver no disco.

    Grava num `.parcial` ao lado e só renomeia no fim: um download
    interrompido nunca vira um zip pela metade com nome de zip inteiro.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")

    for tentativa in range(1, TENTATIVAS + 1):
        ja = parcial.stat().st_size if parcial.exists() else 0
        # O sha256 é do arquivo inteiro: o pedaço já gravado precisa entrar na
        # conta, senão retomar um download significaria não poder conferi-lo.
        digestor = _digerir(parcial) if ja else hashlib.sha256()
        try:
            cabecalhos = {"Range": f"bytes={ja}-"} if ja else {}
            with _abrir(url, cabecalhos) as resposta:
                if ja and resposta.status != 206:
                    # O servidor ignorou o Range: recomeça, senão o arquivo
                    # sairia com o começo duplicado.
                    ja, digestor = 0, hashlib.sha256()
                total = ja + int(resposta.headers.get("Content-Length") or 0)
                total = total or total_esperado
                with parcial.open("ab" if ja else "wb") as saida:
                    baixado = ja
                    if progresso:
                        progresso(baixado, total)
                    while True:
                        if cancelar and cancelar():
                            raise InterruptedError("cancelado")
                        bloco = resposta.read(PEDACO)
                        if not bloco:
                            break
                        saida.write(bloco)
                        digestor.update(bloco)
                        baixado += len(bloco)
                        if progresso:
                            progresso(baixado, total)
            break
        except InterruptedError:
            raise
        except (OSError, urllib.error.HTTPError) as erro:
            log.warning("download falhou (tentativa %d/%d): %s",
                        tentativa, TENTATIVAS, erro)
            if tentativa == TENTATIVAS:
                raise FalhaDeRede(str(erro)) from erro
            # Espera crescente: queda de rede raramente volta no mesmo segundo.
            time.sleep(min(2 ** tentativa, 8))

    if sha256 and digestor.hexdigest().lower() != sha256.lower():
        # Apaga o parcial: insistir num arquivo corrompido só repetiria o erro
        # para sempre, porque retomar continuaria de cima do lixo.
        parcial.unlink(missing_ok=True)
        raise ArquivoCorrompido(f"{destino.name}: sha256 não confere")
    destino.unlink(missing_ok=True)
    parcial.replace(destino)
    return destino
