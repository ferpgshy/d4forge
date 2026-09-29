"""Monta o que vai para o release: o launcher, os zips e o manifesto.

    .venv\\Scripts\\python.exe tools/empacotar_release.py
    .venv\\Scripts\\python.exe tools/empacotar_release.py --pular-build

**Dois zips para três edições, e isso é de propósito.** Os pacotes montados
das edições `completa` e `forge` diferem em cinco linhas de 621 arquivos — a
diferença real é o marcador de dez bytes que diz qual delas é. Publicar dois
arquivos de ~141 MB idênticos cobraria do usuário o preço de um detalhe
interno; o launcher baixa um e escolhe a edição na hora de abrir.

A pasta `data/` fica de fora dos zips. Ela é do usuário: binds, catálogo
editado, geometria da janela. Empacotá-la significaria distribuir a
configuração de quem gerou o release e, pior, sobrescrever a de quem
atualiza.
"""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from d4forge import __version__, edicao  # noqa: E402
from launcher import __version__ as versao_do_launcher  # noqa: E402

DIST = ROOT / "dist"
SAIDA = DIST / "release"

# chave do pacote -> (pasta gerada pelo build, edições que ele atende)
PACOTES: dict[str, tuple[str, tuple[str, ...]]] = {
    "completo": ("d4forge", (edicao.COMPLETA, edicao.FORGE)),
    "autoskill": ("d4forge-autoskill", (edicao.AUTOSKILL,)),
}

LAUNCHER = "d4forge-launcher.exe"
MANIFESTO = "manifesto.json"

# O que nunca entra num zip de distribuição.
FORA = ("data", "captures", "__pycache__")


def sha256_de(caminho: Path) -> str:
    digestor = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        while True:
            bloco = arquivo.read(1 << 20)
            if not bloco:
                break
            digestor.update(bloco)
    return digestor.hexdigest()


def compactar(pasta: Path, destino: Path) -> Path:
    """Zipa uma instalação inteira, com a pasta no topo do arquivo."""
    if not pasta.is_dir():
        raise SystemExit(f"não achei {pasta} — rode o build antes")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.unlink(missing_ok=True)

    arquivos = [
        c for c in sorted(pasta.rglob("*"))
        if c.is_file() and not any(p in FORA for p in c.relative_to(pasta).parts)
    ]
    print(f">> compactando {destino.name} ({len(arquivos)} arquivos)")
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for arquivo in arquivos:
            zf.write(arquivo, Path(pasta.name) / arquivo.relative_to(pasta))
    return destino


def montar_manifesto(assets: dict[str, Path]) -> dict:
    """O arquivo que o launcher lê primeiro — uma requisição resolve tudo."""
    pacotes = {}
    for chave, (_, edicoes) in PACOTES.items():
        arquivo = assets[chave]
        pacotes[chave] = {
            "arquivo": arquivo.name,
            "bytes": arquivo.stat().st_size,
            "sha256": sha256_de(arquivo),
            "edicoes": list(edicoes),
        }
    manifesto: dict = {
        "versao": __version__,
        "tag": f"v{__version__}",
        "pacotes": pacotes,
    }
    exe = assets.get("launcher")
    if exe and exe.is_file():
        manifesto["launcher"] = {
            "versao": versao_do_launcher,
            "arquivo": exe.name,
            "bytes": exe.stat().st_size,
            "sha256": sha256_de(exe),
        }
    return manifesto


def main(argv: list[str] | None = None) -> int:
    argumentos = list(sys.argv[1:] if argv is None else argv)
    pular = "--pular-build" in argumentos

    print(f"d4forge {__version__} — montando o release")
    if not pular:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import build_exe
        import build_launcher

        # Só as duas edições que viram download. A `forge` sai do mesmo zip
        # que a completa, decidida pelo marcador na hora de abrir.
        if build_exe.main([edicao.COMPLETA, edicao.AUTOSKILL]) != 0:
            return 1
        build_launcher.main()

    SAIDA.mkdir(parents=True, exist_ok=True)
    assets: dict[str, Path] = {}
    for chave, (pasta, _) in PACOTES.items():
        assets[chave] = compactar(DIST / pasta, SAIDA / f"d4forge-{chave}.zip")

    exe = DIST / LAUNCHER
    if exe.is_file():
        destino = SAIDA / LAUNCHER
        destino.write_bytes(exe.read_bytes())
        assets["launcher"] = destino

    manifesto = montar_manifesto(assets)
    (SAIDA / MANIFESTO).write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"\nPronto em {SAIDA}:")
    for arquivo in sorted(SAIDA.iterdir()):
        print(f"   {arquivo.name:28} {arquivo.stat().st_size / (1 << 20):7.1f} MB")
    print(
        "\nPara publicar:\n"
        f'   gh release create v{__version__} "{SAIDA}"/* '
        f'--title "d4forge v{__version__}" --notes-file <notas.md>'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
