@echo off
REM ============================================================
REM  PC Lock - demarrage auto SIMPLE (dossier Demarrage)
REM  Depose un raccourci vers run-hidden.vbs dans shell:startup.
REM  NON eleve : les hooks bas niveau peuvent exiger l'admin.
REM  Pour un demarrage eleve + cache, preferez install-autostart.ps1
REM  (Tache planifiee, RunLevel Highest).
REM ============================================================
setlocal
set "HERE=%~dp0"
set "VBS=%HERE%run-hidden.vbs"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LNK=%STARTUP%\PC Lock.lnk"

if not exist "%VBS%" (
    echo run-hidden.vbs introuvable dans %HERE%
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=New-Object -ComObject WScript.Shell;" ^
  "$l=$s.CreateShortcut('%LNK%');" ^
  "$l.TargetPath='wscript.exe';" ^
  "$l.Arguments='\"%VBS%\"';" ^
  "$l.WorkingDirectory='%HERE%';" ^
  "$l.WindowStyle=7;" ^
  "$l.Description='PC Lock (arriere-plan, cache)';" ^
  "$l.Save()"

if exist "%LNK%" (
    echo Raccourci cree : %LNK%
    echo PC Lock se lancera a chaque ouverture de session ^(sans console^).
    echo Pour le retirer : supprimez ce raccourci du dossier Demarrage ^(shell:startup^).
) else (
    echo Echec de creation du raccourci.
)
pause
