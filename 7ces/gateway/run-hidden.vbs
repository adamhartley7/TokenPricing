' 7C's — launch the spend-guard gateway with NO visible window.
' Used by the "7Cs-Gateway" logon Scheduled Task (see ../install-autostart.ps1). Self-locating:
' it finds the gateway folder as its own directory, so it works wherever the repo lives.
Set fso = CreateObject("Scripting.FileSystemObject")
gatewayDir = fso.GetParentFolderName(WScript.ScriptFullName)
pyw = gatewayDir & "\.venv\Scripts\pythonw.exe"
q = Chr(34)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = gatewayDir
sh.Run q & pyw & q & " -m uvicorn app:app --host 0.0.0.0 --port 8787", 0, False
