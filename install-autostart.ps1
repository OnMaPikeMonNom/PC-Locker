<#
.SYNOPSIS
    Installe PC Lock au demarrage de session Windows via une Tache planifiee
    (eleve + cachee), pour que les hooks bas niveau s'installent sans console.

.DESCRIPTION
    Cree une tache "PC Lock" qui :
      - se declenche a l'ouverture de session de l'utilisateur courant,
      - lance pythonw.exe (pas de fenetre console) avec le chemin complet de main.py,
      - utilise le dossier du script comme repertoire de travail,
      - s'execute avec les privileges les plus eleves (-RunLevel Highest),
      - tourne cachee.

.USAGE
    Clic droit sur ce fichier > "Executer avec PowerShell"
    (acceptez l'elevation UAC), ou dans une PowerShell admin :
        powershell -ExecutionPolicy Bypass -File .\install-autostart.ps1
#>

$ErrorActionPreference = "Stop"
$TaskName = "PC Lock"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$MainPy = Join-Path $ScriptDir "main.py"

if (-not (Test-Path $MainPy)) {
    Write-Error "main.py introuvable dans $ScriptDir"
    exit 1
}

# --- Resolution robuste de pythonw.exe ---
function Resolve-Pythonw {
    # 1) where.exe pythonw
    $w = (& where.exe pythonw.exe 2>$null | Select-Object -First 1)
    if ($w -and (Test-Path $w)) { return $w }
    # 2) a cote de python.exe trouve par where.exe
    $p = (& where.exe python.exe 2>$null | Select-Object -First 1)
    if ($p -and (Test-Path $p)) {
        $cand = Join-Path (Split-Path -Parent $p) "pythonw.exe"
        if (Test-Path $cand) { return $cand }
    }
    # 3) py launcher -> prefixe d'installation
    try {
        $pref = (& py -c "import sys,os;print(os.path.dirname(sys.executable))" 2>$null)
        if ($pref) {
            $cand = Join-Path $pref "pythonw.exe"
            if (Test-Path $cand) { return $cand }
        }
    } catch {}
    return $null
}

$Pythonw = Resolve-Pythonw
if (-not $Pythonw) {
    Write-Error "pythonw.exe introuvable. Installez Python 3 (cochez 'Add to PATH')."
    exit 1
}
Write-Host "pythonw : $Pythonw"
Write-Host "main.py : $MainPy"

$Action = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$MainPy`"" -WorkingDirectory $ScriptDir
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERDOMAIN\$env:USERNAME -LogonType Interactive -RunLevel Highest
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -Hidden -ExecutionTimeLimit ([TimeSpan]::Zero)

# Supprime une eventuelle ancienne tache du meme nom.
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description "PC Lock : verrou clavier/souris au demarrage (cache, eleve)." | Out-Null

Write-Host ""
Write-Host "Tache planifiee '$TaskName' installee." -ForegroundColor Green
Write-Host "Elle se lancera a la prochaine ouverture de session (cachee, elevee)."
Write-Host "Pour la demarrer tout de suite :"
Write-Host "    Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Pour la retirer : .\uninstall-autostart.ps1"
