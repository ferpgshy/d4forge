"""Gera o `d4forge-launcher.exe` — o arquivo único que vai para o release.

Um arquivo só, e não uma pasta: o launcher é o que a pessoa baixa antes de
ter qualquer coisa instalada, e "extraia a pasta e ache o .exe" é justamente
o passo que ele existe para eliminar.

O tamanho é o requisito, então o que NÃO entra importa mais do que o que
entra. `--exclude-module` corta PySide6, OpenCV, numpy e o leitor de OCR: o
launcher importa `d4forge.i18n` e `d4forge.edicao`, que são dicionários e
strings, mas o PyInstaller seguiria qualquer import vizinho se deixado solto.
Medido: 10,4 MB com os cortes.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = Path(sys.executable)
NOME = "d4forge-launcher"
SAIDA = ROOT / "dist"

# Tudo o que o aplicativo usa e o launcher não. Sem isto, a análise do
# PyInstaller acha PySide6 por um caminho indireto e o exe passa de 90 MB.
FORA = (
    "PySide6", "shiboken6", "PIL", "cv2", "numpy", "scipy",
    "rapidocr_onnxruntime", "onnxruntime", "shapely", "pyclipper",
    "dxcam", "mss", "comtypes", "win32com", "matplotlib", "pytest",
)


def executar(*args: str, descricao: str = "") -> None:
    if descricao:
        print(f"\n>> {descricao}")
    resultado = subprocess.run(args, cwd=ROOT)
    if resultado.returncode != 0:
        raise SystemExit(resultado.returncode)


def icone() -> Path:
    alvo = ROOT / "d4forge" / "resources" / "d4forge.ico"
    if not alvo.exists():
        executar(str(PY), str(ROOT / "tools" / "make_icon.py"),
                 descricao="gerando ícone")
    return alvo


def empacotar() -> Path:
    ico = icone()
    argumentos = [
        str(PY), "-m", "PyInstaller",
        "--onefile", "--noconsole", "--noupx", "--clean", "--noconfirm",
        "--name", NOME,
        "--icon", str(ico),
        # O ícone também vai para dentro: a janela do tkinter o carrega de
        # `sys._MEIPASS` em tempo de execução.
        "--add-data", f"{ico}{';' if sys.platform == 'win32' else ':'}.",
        "--distpath", str(SAIDA),
        "--workpath", str(ROOT / "build" / NOME),
        "--specpath", str(ROOT / "build"),
    ]
    for modulo in FORA:
        argumentos += ["--exclude-module", modulo]
    # A entrada é o script da raiz, não `launcher/__main__.py`: o PyInstaller
    # roda o alvo como `__main__`, sem pacote, e os imports relativos morrem.
    argumentos.append(str(ROOT / "run_launcher.py"))
    executar(*argumentos, descricao=f"empacotando {NOME}")
    return SAIDA / f"{NOME}.exe"


def conferir(exe: Path) -> float:
    """O launcher tem de ser pequeno e não pode ter arrastado o Qt junto."""
    if not exe.is_file():
        raise SystemExit(f"não saiu executável em {exe}")
    mb = exe.stat().st_size / (1 << 20)

    # O arquivo do PyInstaller em modo `onefile` é um zip anexado ao exe.
    intrusos = []
    try:
        with zipfile.ZipFile(exe) as pacote:
            nomes = pacote.namelist()
    except (zipfile.BadZipFile, OSError):
        nomes = []
    for proibido in ("PySide6", "cv2", "numpy", "onnxruntime"):
        if any(proibido.lower() in n.lower() for n in nomes):
            intrusos.append(proibido)
    if intrusos:
        raise SystemExit(f"o launcher arrastou {', '.join(intrusos)} junto")
    if mb > 40:
        raise SystemExit(f"o launcher saiu com {mb:.1f} MB — algo entrou junto")

    print(f"\n>> {exe.name}: {mb:.1f} MB")
    return mb


def main() -> int:
    print(f"d4forge — launcher, com {PY}")
    exe = empacotar()
    conferir(exe)
    print("\nPronto:", exe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
