' ov2n VPN Client Launcher
Option Explicit

Dim oShell, oFSO, sAppDir, sMain
Set oShell = CreateObject("WScript.Shell")
Set oFSO   = CreateObject("Scripting.FileSystemObject")

sAppDir = oFSO.GetParentFolderName(WScript.ScriptFullName)
sMain   = sAppDir & "\main.py"

If Not oFSO.FileExists(sMain) Then
    MsgBox "main.py not found in: " & sAppDir, vbCritical, "ov2n"
    WScript.Quit 1
End If

oShell.CurrentDirectory = sAppDir

Dim sCmd
sCmd = "cmd /c start /b """" pythonw """ & sMain & """"
oShell.Run sCmd, 0, False
