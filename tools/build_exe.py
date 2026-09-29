"""Gera os executáveis do d4forge.

    .venv\\Scripts\\python.exe tools\\build_exe.py              as tres
    .venv\\Scripts\\python.exe tools\\build_exe.py autoskill    so' uma

Sao TRES edicoes, para quem baixa pegar so' o que vai usar:

    completa    d4forge              tudo
    forge       d4forge-forge        Enchant, Tempering, Masterworking
    autoskill   d4forge-autoskill    so' o AutoSkill

A diferenca nao e' so' quais abas aparecem. O AutoSkill nao le' texto da tela
- ele mede brilho -, entao a edicao dele deixa o rapidocr e o onnxruntime de
fora, o que tira ~60 MB do pacote. Ver `d4forge/edicao.py`.

Instala o que faltar (PyInstaller e as dependências do projeto) e empacota tudo
em dist/d4forge/. Não precisa de Python na máquina que for rodar o resultado.

Duas decisões que valem explicação:

* **Pasta, não arquivo único.** O `--onefile` produz um .exe só, mas ele
  descompacta ~500 MB num diretório temporário a cada execução — 20 s ou mais
  de espera antes da janela aparecer. Em pasta, o start é imediato.
* **Os modelos do RapidOCR precisam ser coletados à mão.** São .onnx e um
  config.yaml carregados por caminho em tempo de execução; o PyInstaller não
  enxerga isso analisando os imports, e o .exe só falha quando você aperta
  Iniciar. Por isso a checagem explícita mais abaixo.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = Path(sys.executable)
NOME = "d4forge"

sys.path.insert(0, str(ROOT))
from d4forge import edicao  # noqa: E402

# Nome do executavel de cada edicao, e o que cada uma deixa de fora.
#
# So' a `autoskill` exclui: as outras duas leem texto e precisam do leitor
# inteiro. Excluir por engano nao daria erro de compilacao - o import do
# rapidocr e' TARDIO, dentro da funcao -, daria erro so' quando o usuario
# apertasse Iniciar. Por isso `conferir` cobra os modelos das edicoes que os
# usam.
EDICOES = {
    edicao.COMPLETA: ("d4forge", ()),
    edicao.FORGE: ("d4forge-forge", ()),
    edicao.AUTOSKILL: (
        "d4forge-autoskill",
        ("rapidocr_onnxruntime", "onnxruntime", "shapely", "pyclipper", "PIL"),
    ),
}

MARCADOR = ROOT / "d4forge" / "resources" / edicao.ARQUIVO


def executar(*args: str, descricao: str = "") -> None:
    if descricao:
        print(f"\n>> {descricao}")
    resultado = subprocess.run(args, cwd=ROOT)
    if resultado.returncode != 0:
        raise SystemExit(f"falhou: {' '.join(args)}")


def garantir_dependencias() -> None:
    faltando = []
    for modulo, pacote in [
        ("PyInstaller", "pyinstaller"),
        ("PySide6", "PySide6"),
        ("rapidocr_onnxruntime", "rapidocr-onnxruntime"),
        ("cv2", "opencv-python-headless"),
        ("dxcam", "dxcam"),
        ("PIL", "pillow"),
    ]:
        try:
            __import__(modulo)
        except ImportError:
            faltando.append(pacote)

    if faltando:
        executar(str(PY), "-m", "pip", "install", *faltando,
                 descricao=f"instalando {', '.join(faltando)}")
    else:
        print(">> dependências ok")


def garantir_icone() -> Path:
    icone = ROOT / "d4forge" / "resources" / f"{NOME}.ico"
    if not icone.exists():
        executar(str(PY), str(ROOT / "tools" / "make_icon.py"),
                 descricao="gerando ícone")
    return icone


def guardar_dados(raiz: Path | None = None, nome: str = NOME) -> Path | None:
    """Tira o `data/` do usuario de dentro de `dist/` antes da limpeza.

    `config._dirs()` poe a pasta gravavel AO LADO do executavel quando o app
    esta' congelado - entao binds, alvo, ajustes e catalogo de quem usa o .exe
    moram em `dist/d4forge/data/`. E `limpar()` apaga `dist/` inteiro.

    O resultado e' que recompilar apagava a configuracao do usuario. Nao e'
    hipotese: aconteceu, e mais de uma vez na mesma sessao - quem estava
    testando perdeu as binds a cada build.
    """
    origem = (raiz or ROOT) / "dist" / nome / "data"
    if not origem.is_dir():
        return None
    abrigo = Path(tempfile.mkdtemp(prefix=f"{nome}-data-"))
    destino = abrigo / "data"
    shutil.move(str(origem), str(destino))
    print(f">> guardei {origem} durante o build")
    return destino


def devolver_dados(guardado: Path | None, raiz: Path | None = None,
                   nome: str = NOME) -> None:
    """Repoe o `data/` do usuario depois do build. Idempotente."""
    if guardado is None or not Path(guardado).is_dir():
        return
    guardado = Path(guardado)
    destino = (raiz or ROOT) / "dist" / nome / "data"
    destino.parent.mkdir(parents=True, exist_ok=True)
    # O build novo pode ter criado um data/ proprio; o do usuario e' que vale.
    if destino.exists():
        shutil.rmtree(destino, ignore_errors=True)
    shutil.move(str(guardado), str(destino))
    shutil.rmtree(guardado.parent, ignore_errors=True)
    print(f">> devolvi {destino}")


def limpar(nome: str) -> None:
    """Apaga o que sobrou do build ANTERIOR desta edicao.

    Por edicao, e nao `dist/` inteiro: com tres executaveis, limpar tudo faria
    o segundo build apagar o primeiro.
    """
    for alvo in (ROOT / "build" / nome, ROOT / "dist" / nome):
        if alvo.exists():
            shutil.rmtree(alvo, ignore_errors=True)
    (ROOT / f"{nome}.spec").unlink(missing_ok=True)

    # `ignore_errors` acima faz a limpeza passar em silencio quando um arquivo
    # esta' travado - e ai o PyInstaller quebra la' na frente com um traceback
    # de PermissionError em cv2.pyd, que nao diz o que fazer. A causa e' quase
    # sempre uma copia do proprio app ainda aberta.
    restante = ROOT / "dist" / nome
    if restante.exists():
        raise SystemExit(
            f"nao consegui limpar {restante}.\n"
            f"Feche o {nome}.exe se ele estiver aberto e rode de novo."
        )


def empacotar(qual: str, icone: Path) -> None:
    nome, excluir = EDICOES[qual]
    # O marcador viaja dentro do pacote, junto dos outros recursos: e' por ele
    # que o executavel sabe qual edicao e' (ver `edicao._do_arquivo`).
    MARCADOR.write_text(qual + "\n", encoding="utf-8")

    coleta: list[str] = []
    if qual != edicao.AUTOSKILL:
        coleta = [
            "--collect-all", "rapidocr_onnxruntime",  # modelos .onnx + config
            "--collect-all", "onnxruntime",           # DLLs do runtime
        ]

    args = [
        str(PY), "-m", "PyInstaller",
        "--name", nome,
        "--noconfirm",
        "--clean",
        "--windowed",              # sem janela de console atrás da GUI
        "--icon", str(icone),
        # O PyInstaller comprime com UPX sozinho se achar o upx na PATH, e
        # binario comprimido com UPX e' MUITO mais flagado por antivirus - o
        # executavel ja' e' falso positivo de 4 motores heuristicos sem isso.
        # Explicito para que a maquina de quem compilar nao mude o resultado.
        "--noupx",
        *coleta,
        "--add-data", f"{ROOT / 'd4forge' / 'resources'}{os_sep()}d4forge/resources",
        # Modulos carregados por nome, invisiveis para a analise estatica:
        "--hidden-import", "dxcam",
        "--hidden-import", "mss",
        # Peso morto: puxados por dependencia mas nunca usados aqui.
        "--exclude-module", "matplotlib",
        "--exclude-module", "scipy",
        "--exclude-module", "pandas",
        "--exclude-module", "tkinter",
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.Qt3DCore",
        "--exclude-module", "PySide6.QtMultimedia",
    ]
    for modulo in excluir:
        args += ["--exclude-module", modulo]
    args.append(str(ROOT / "run.py"))
    executar(*args, descricao=f"empacotando {nome} (pode levar alguns minutos)")


def os_sep() -> str:
    """Separador que o --add-data espera (';' no Windows)."""
    return ";" if sys.platform == "win32" else ":"


def conferir(qual: str) -> float:
    """O .exe só quebra ao apertar Iniciar se faltar modelo. Conferir agora."""
    nome, _ = EDICOES[qual]
    destino = ROOT / "dist" / nome
    exe = destino / f"{nome}.exe"
    if not exe.exists():
        raise SystemExit(f"executável não foi gerado em {destino}")

    marcador = list(destino.rglob(edicao.ARQUIVO))
    onnx = list(destino.rglob("*.onnx"))
    yaml = list(destino.rglob("config.yaml"))
    afixos = list(destino.rglob("d4lf_affixes_enUS.json"))
    total = sum(p.stat().st_size for p in destino.rglob("*") if p.is_file())

    print(f"\n>> conferindo {nome}")
    print(f"   {nome}.exe{' ' * max(1, 24 - len(nome))}{exe.stat().st_size / 1024 / 1024:6.1f} MB")
    print(f"   marcador de edição       {len(marcador)}")
    print(f"   modelos .onnx            {len(onnx)}")
    print(f"   lista de afixos          {len(afixos)}")
    print(f"   tamanho total            {total / 1024 / 1024:6.0f} MB")

    problemas = []
    if not marcador:
        problemas.append(f"falta o {edicao.ARQUIVO} - o exe nao saberia a edicao")
    else:
        lido = marcador[0].read_text(encoding="utf-8").strip()
        if lido != qual:
            problemas.append(f"o marcador diz {lido!r} e deveria dizer {qual!r}")
    if qual == edicao.AUTOSKILL:
        # O contrario das outras: aqui a presenca e' que seria defeito.
        if onnx:
            problemas.append(f"{len(onnx)} modelo(s) .onnx numa edição sem OCR")
    else:
        if len(onnx) < 3:
            problemas.append("faltam modelos .onnx (detecção/reconhecimento/classificação)")
        if not yaml:
            problemas.append("falta o config.yaml do RapidOCR")
        if not afixos:
            problemas.append("falta a lista de afixos")
    if problemas:
        raise SystemExit("pacote incompleto:\n  - " + "\n  - ".join(problemas))
    return total / 1024 / 1024


def main(argv: list[str] | None = None) -> int:
    pedidas = [a.lower() for a in (argv if argv is not None else sys.argv[1:])]
    for a in pedidas:
        if a not in EDICOES:
            raise SystemExit(
                f"edição desconhecida: {a!r}. Escolha entre {', '.join(EDICOES)}."
            )
    alvos = pedidas or list(EDICOES)

    print(f"d4forge — gerando {len(alvos)} executável(is) com {PY}")
    garantir_dependencias()
    icone = garantir_icone()

    tamanhos: dict[str, float] = {}
    for qual in alvos:
        nome, _ = EDICOES[qual]
        # O `finally` nao e' zelo excessivo: `limpar()` ABORTA quando o .exe
        # esta' aberto, e sem isto a configuracao do usuario ficaria largada
        # no temporario.
        guardado = guardar_dados(nome=nome)
        try:
            limpar(nome)
            empacotar(qual, icone)
        finally:
            devolver_dados(guardado, nome=nome)
            # O marcador nao pode sobrar na arvore: rodar do codigo-fonte
            # depois de compilar a edicao `autoskill` mostraria uma aba so'.
            MARCADOR.unlink(missing_ok=True)
        tamanhos[qual] = conferir(qual)

    print("\nPronto:")
    for qual in alvos:
        nome, _ = EDICOES[qual]
        print(f"  {qual:10} dist/{nome}/{nome}.exe   {tamanhos[qual]:5.0f} MB")
    print("A pasta de cada um é o aplicativo — copie ela, não só o .exe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
