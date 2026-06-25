<#
.SYNOPSIS
    Make the 7CE's gateway start automatically (hidden) every time you log in.

.DESCRIPTION
    Registers a Windows Scheduled Task "7CEs-Gateway" that runs the gateway with no window at logon,
    and restarts it if it ever crashes. After this you never have to babysit a terminal window — the
    gateway (and therefore LibreChat + the phone app) is always available once you're logged in.

    Run from the 7ces folder (approve the UAC prompt if asked):
        powershell -ExecutionPolicy Bypass -File .\install-autostart.ps1

    Start it immediately without logging off:
        Start-ScheduledTask -TaskName '7CEs-Gateway'
    Remove it later with uninstall-autostart.ps1.
#>
$ErrorActionPreference = 'Stop'
$vbs = Join-Path $PSScriptRoot 'gateway\run-hidden.vbs'
if (-not (Test-Path $vbs)) { Write-Error "run-hidden.vbs not found at $vbs"; exit 1 }

$action  = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument ('"{0}"' -f $vbs)
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName '7CEs-Gateway' -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force `
    -Description "Runs the 7CE's spend-guard gateway hidden at logon." | Out-Null

Write-Host "Registered '7CEs-Gateway' — the gateway will start hidden at every logon." -ForegroundColor Green
Write-Host "Start it now:  Start-ScheduledTask -TaskName '7CEs-Gateway'" -ForegroundColor DarkGray
