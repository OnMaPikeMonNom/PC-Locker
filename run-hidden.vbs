' PC Lock — lance l'app SANS fenetre console (pythonw).
' Double-clic : demarre PC Lock en arriere-plan (icone systray seulement).
' NOTE : les hooks bas niveau peuvent exiger les droits admin. Pour un
' demarrage automatique eleve et cache, utilisez install-autostart.ps1
' (Tache planifiee, RunLevel Highest). Ce script ne demande PAS l'elevation.
Option Explicit
Dim shell, fso, here, pyw, target, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)

' Recherche pythonw.exe : d'abord dans le PATH, sinon a cote de python.exe.
pyw = "pythonw.exe"
On Error Resume Next
Dim exec, line, found
found = ""
' Essaye "where pythonw"
Set exec = shell.Exec("cmd /c where pythonw.exe")
If Err.Number = 0 Then
  Do While Not exec.StdOut.AtEndOfStream
    line = Trim(exec.StdOut.ReadLine())
    If found = "" And line <> "" Then found = line
  Loop
End If
On Error Goto 0
If found <> "" Then pyw = found

target = fso.BuildPath(here, "main.py")
' Chdir vers le dossier puis lance pythonw main.py, fenetre cachee (0), sans attendre.
cmd = "cmd /c cd /d """ & here & """ && """ & pyw & """ """ & target & """"
shell.Run cmd, 0, False
