<#
.SYNOPSIS
    Retire la tache planifiee "PC Lock" et arrete les instances en cours.
.USAGE
    Clic droit > "Executer avec PowerShell" (acceptez l'elevation), ou :
        powershell -ExecutionPolicy Bypass -File .\uninstall-autostart.ps1
#>
$ErrorActionPreference = "SilentlyContinue"
$TaskName = "PC Lock"

# Arrete puis supprime la tache.
Stop-ScheduledTask -TaskName $TaskName | Out-Null
$existed = Get-ScheduledTask -TaskName $TaskName
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false | Out-Null

if ($existed) {
    Write-Host "Tache planifiee '$TaskName' supprimee." -ForegroundColor Green
} else {
    Write-Host "Aucune tache '$TaskName' trouvee."
}

# Tue les instances pythonw qui executent main.py (PC Lock en arriere-plan).
$killed = 0
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | ForEach-Object {
    if ($_.CommandLine -and $_.CommandLine -match "main\.py") {
        Stop-Process -Id $_.ProcessId -Force
        $killed++
    }
}
Write-Host "Instances pythonw/main.py arretees : $killed"
Write-Host "PC Lock ne demarrera plus automatiquement."
