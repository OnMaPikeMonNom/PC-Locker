@echo off
REM Relance PC Lock EN ADMINISTRATEUR (hooks bas niveau plus fiables).
cd /d "%~dp0"
echo PC Lock - relancement en administrateur...
powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath 'cmd.exe' -ArgumentList '/k','cd /d \"%~dp0\" ^&^& python main.py'"
if errorlevel 1 (
    echo Echec du relancement en administrateur.
    echo Faites un clic droit sur run-admin.bat puis "Executer en tant qu'administrateur".
    pause
)
