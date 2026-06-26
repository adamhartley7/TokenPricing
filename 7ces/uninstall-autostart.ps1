<# Remove the 7C's gateway auto-start task. Run:  powershell -ExecutionPolicy Bypass -File .\uninstall-autostart.ps1 #>
$ErrorActionPreference = 'SilentlyContinue'
Unregister-ScheduledTask -TaskName '7Cs-Gateway' -Confirm:$false
Write-Host "Removed the '7Cs-Gateway' auto-start task (if it existed)." -ForegroundColor Yellow
