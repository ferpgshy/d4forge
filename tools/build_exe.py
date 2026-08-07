"""Gera o executável do d4forge.

    .venv\\Scripts\\python.exe tools\\build_exe.py

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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = Path(sys.executable)
NOME = "d4forge"


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


def limpar() -> None:
    for pasta in ("build", "dist"):
        alvo = ROOT / pasta
        if alvo.exists():
            shutil.rmtree(alvo, ignore_errors=True)
    spec = ROOT / f"{NOME}.spec"
    spec.unlink(missing_ok=True)

    # `ignore_errors` acima faz a limpeza passar em silencio quando um arquivo
    # esta' travado - e ai o PyInstaller quebra la' na frente com um traceback
    # de PermissionError em cv2.pyd, que nao diz o que fazer. A causa e' quase
    # sempre uma copia do proprio app ainda aberta.
    restante = ROOT / "dist" / NOME
    if restante.exists():
        raise SystemExit(
            f"nao consegui limpar {restante}.\n"
            f"Feche o {NOME}.exe se ele estiver aberto e rode de novo."
        )


def empacotar(icone: Path) -> None:
    args = [
        str(PY), "-m", "PyInstaller",
        "--name", NOME,
        "--noconfirm",
        "--clean",
        "--windowed",              # sem janela de console atrás da GUI
        "--icon", str(icone),
        # O PyInstaller comprime com UPX sozinho se achar o upx na PATH, e
        # binario comprimido com UPX e' MUITO mais flagado por antivirus - o
        # executavel ja' e' falso positivo de 4 motores heuristicos sem isso.
        # Explicito para que a maquina de quem compilar nao mude o resultado.
        "--noupx",
        # Recursos que o PyInstaller nao descobre sozinho:
        "--collect-all", "rapidocr_onnxruntime",   # modelos .onnx + config.yaml
        "--collect-all", "onnxruntime",            # DLLs do runtime
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
        str(ROOT / "run.py"),
    ]
    executar(*args, descricao="empacotando (pode levar alguns minutos)")


def os_sep() -> str:
    """Separador que o --add-data espera (';' no Windows)."""
    return ";" if sys.platform == "win32" else ":"


def conferir(destino: Path) -> None:
    """O .exe só quebra ao apertar Iniciar se faltar modelo. Conferir agora."""
    exe = destino / f"{NOME}.exe"
    if not exe.exists():
        raise SystemExit(f"executável não foi gerado em {destino}")

    onnx = list(destino.rglob("*.onnx"))
    yaml = list(destino.rglob("config.yaml"))
    afixos = list(destino.rglob("d4lf_affixes_enUS.json"))

    print("\n>> conferindo o pacote")
    print(f"   {NOME}.exe                {exe.stat().st_size / 1024 / 1024:6.1f} MB")
    print(f"   modelos .onnx            {len(onnx)}")
    print(f"   config.yaml do RapidOCR  {len(yaml)}")
    print(f"   lista de afixos          {len(afixos)}")

    problemas = []
    if len(onnx) < 3:
        problemas.append("faltam modelos .onnx (detecção/reconhecimento/classificação)")
    if not yaml:
        problemas.append("falta o config.yaml do RapidOCR")
    if not afixos:
        problemas.append("falta a lista de afixos")
    if problemas:
        raise SystemExit("pacote incompleto:\n  - " + "\n  - ".join(problemas))

    total = sum(p.stat().st_size for p in destino.rglob("*") if p.is_file())
    print(f"   tamanho total            {total / 1024 / 1024:6.0f} MB")


def main() -> int:
    print(f"d4forge — gerando executável com {PY}")
    garantir_dependencias()
    icone = garantir_icone()
    limpar()
    empacotar(icone)

    destino = ROOT / "dist" / NOME
    conferir(destino)

    print(f"\nPronto: {destino / (NOME + '.exe')}")
    print("A pasta dist/d4forge/ inteira é o aplicativo — copie ela, não só o .exe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
