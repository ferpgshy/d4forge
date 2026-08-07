@echo off
REM Atalho para abrir o d4forge com duplo clique.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [!] Ambiente virtual nao encontrado.
    echo     Rode uma vez:
    echo.
    echo     py -3.13 -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" run.py
if errorlevel 1 pause
