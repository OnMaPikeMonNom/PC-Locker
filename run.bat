@echo off
cd /d "%~dp0"
echo PC Lock - demarrage...
python --version >nul 2>&1
if errorlevel 1 (
    echo Python n'est pas installe ou pas dans le PATH.
    echo Installez Python 3 depuis https://www.python.org/downloads/
    echo Cochez "Add python.exe to PATH" pendant l'installation.
    pause
    exit /b 1
)
if not exist ".deps_ok" (
    echo Installation des dependances (une seule fois)...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Echec de pip install.
        pause
        exit /b 1
    )
    echo. > .deps_ok
)
python main.py
if errorlevel 1 pause
