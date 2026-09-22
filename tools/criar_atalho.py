"""Cria o atalho do d4forge na Área de Trabalho.

    .venv\\Scripts\\python.exe tools\\criar_atalho.py

Aponta para dist/d4forge/d4forge.exe se ele existir; senão, para o modo de
desenvolvimento (o venv rodando run.py). Assim o atalho funciona antes mesmo de
você gerar o executável.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOME = "d4forge"


def alvo() -> tuple[str, str, str]:
    """(executável, argumentos, pasta de trabalho)."""
    exe = ROOT / "dist" / NOME / f"{NOME}.exe"
    if exe.exists():
        return str(exe), "", str(exe.parent)

    pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    if not pythonw.exists():
        raise SystemExit(
            "não achei nem dist/d4forge/d4forge.exe nem o venv.\n"
            "Gere o executável com: .venv\\Scripts\\python.exe tools\\build_exe.py"
        )
    # pythonw em vez de python: sem janela de console atrás da interface.
    return str(pythonw), f'"{ROOT / "run.py"}"', str(ROOT)


def main() -> int:
    destino_exe, args, workdir = alvo()
    icone = ROOT / "d4forge" / "resources" / f"{NOME}.ico"

    # Quem diz onde fica a Área de Trabalho é o WINDOWS, não o palpite de
    # `~/Desktop`. Com o OneDrive ligado ela é REDIRECIONADA para
    # `~/OneDrive/Área de Trabalho`, e o nome ainda muda com o idioma do
    # sistema. Chutar os dois nomes mais prováveis falhava justamente na
    # máquina mais comum — a com OneDrive — e o erro que saía era um
    # DirectoryNotFoundException do PowerShell, que não diz nada disso.
    #
    # O .lnk é um formato COM; o caminho sem dependências extras é o WScript.
    ps = f'''
$desktop = [Environment]::GetFolderPath("Desktop")
$atalho = Join-Path $desktop "{NOME}.lnk"
$s = New-Object -ComObject WScript.Shell
$l = $s.CreateShortcut($atalho)
$l.TargetPath = "{destino_exe}"
$l.Arguments = '{args}'
$l.WorkingDirectory = "{workdir}"
$l.IconLocation = "{icone}"
$l.Description = "d4forge - assistente de encantamento para Diablo IV"
$l.Save()
Write-Output $atalho
'''
    resultado = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, text=True,
    )
    if resultado.returncode != 0:
        print(resultado.stderr)
        raise SystemExit("não consegui criar o atalho")

    print(f"atalho criado: {resultado.stdout.strip()}")
    print(f"  aponta para: {destino_exe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
