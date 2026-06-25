<# Remove the 7CE's gateway auto-start task. Run:  powershell -ExecutionPolicy Bypass -File .\uninstall-autostart.ps1 #>
$ErrorActionPreference = 'SilentlyContinue'
Unregister-ScheduledTask -TaskName '7CEs-Gateway' -Confirm:$false
Write-Host "Removed the '7CEs-Gateway' auto-start task (if it existed)." -ForegroundColor Yellow
