<#
.SYNOPSIS
    Claude Code on DeepSeek V4 Pro with the PC kept awake for long/overnight runs.
    Add -Unattended for true hands-off mode (skips permission prompts).

.DESCRIPTION
    Sets up a long-running Claude Code session on DeepSeek V4 Pro (pay-per-token):
      1. Routes Claude Code to DeepSeek (sets ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN / model),
         reusing the SAME .deepseek-key as deepseek.ps1, so the work does NOT touch your Claude limit.
      2. Blocks Windows sleep for as long as this window is open, then restores normal
         sleep behaviour automatically when the session ends.

    By DEFAULT, Claude Code still asks before edits/commands (safe). Pass -Unattended to add
    --dangerously-skip-permissions so it never stops to ask -- this is what makes a truly
    hands-off overnight run, and you are opting into it explicitly.

    Claude Code runs in the CURRENT directory, so `cd` into the project you want worked on
    first. Any extra arguments (including an initial task prompt) are passed through to claude.

    DeepSeek is an UNOFFICIAL Claude Code route (it works via a translator endpoint), so for
    delicate unattended runs glm-overnight.ps1 is the more reliable fallback.

.PARAMETER Unattended
    Launch with --dangerously-skip-permissions so Claude Code edits/runs WITHOUT asking.
    Use only in a project that is a git repo (so `git diff` lets you review/undo in the morning)
    and only with tasks you are comfortable running unattended.

.NOTES
    If PowerShell refuses to run this script ("running scripts is disabled"), launch it with:
        powershell -ExecutionPolicy Bypass -File .\deepseek-overnight.ps1 -Unattended

    Get a key: https://platform.deepseek.com/api_keys

.EXAMPLE
    cd C:\my\project
    C:\path\to\TokenPricing\deepseek-overnight.ps1
.EXAMPLE
    C:\path\to\TokenPricing\deepseek-overnight.ps1 -Unattended "Work through TODO.md top to bottom, committing after each task."
#>

param(
    [switch]$Unattended,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ClaudeArgs
)

$ErrorActionPreference = 'Stop'
$KeyFile = Join-Path $PSScriptRoot '.deepseek-key'

# --- 1. Resolve the DeepSeek API key -- shared with deepseek.ps1 (.deepseek-key) --
$key = $env:DEEPSEEK_API_KEY
if (-not $key -and (Test-Path $KeyFile)) {
    $key = (Get-Content $KeyFile -Raw).Trim()
}
if (-not $key) {
    Write-Host 'Paste your DeepSeek API key. Get it at https://platform.deepseek.com/api_keys.' -ForegroundColor Cyan
    $secure = Read-Host -AsSecureString 'DeepSeek API key'
    $key = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    if (-not $key) { Write-Error 'No key entered.'; exit 1 }

    $save = Read-Host 'Save this key to .deepseek-key (git-ignored) so you do not re-enter it? (y/N)'
    if ($save -match '^[Yy]') {
        Set-Content -Path $KeyFile -Value $key -Encoding UTF8 -NoNewline
        Write-Host "Saved to $KeyFile (git-ignored)." -ForegroundColor DarkGray
    }
}

# --- 2. Sanity check that Claude Code is installed -----------------------------
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Error "Claude Code ('claude') not found on PATH. Install it first, then re-run."
    exit 1
}

# --- 3. Point Claude Code at DeepSeek for THIS window only ---------------------
$env:ANTHROPIC_BASE_URL            = 'https://api.deepseek.com/anthropic'
$env:ANTHROPIC_AUTH_TOKEN          = $key
$env:ANTHROPIC_MODEL               = 'deepseek-v4-pro'
$env:ANTHROPIC_DEFAULT_HAIKU_MODEL = 'deepseek-v4-flash'

# --- 4. Keep Windows awake while this window is open ---------------------------
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class StayAwake {
    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint esFlags);
}
'@
[uint32]$ES_CONTINUOUS      = 0x80000000L  # L suffix: parse as Int64 first so Windows PowerShell 5.1 doesn't read it as a negative Int32
[uint32]$ES_SYSTEM_REQUIRED = 0x00000001
[StayAwake]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED) | Out-Null

# --- 5. Build the claude argument list -----------------------------------------
$claudeArgsList = @()
if ($Unattended) { $claudeArgsList += '--dangerously-skip-permissions' }
if ($ClaudeArgs) { $claudeArgsList += $ClaudeArgs }

Write-Host ''
if ($Unattended) {
    Write-Host 'OVERNIGHT MODE (UNATTENDED): DeepSeek V4 Pro, permission prompts SKIPPED, PC kept awake.' -ForegroundColor Green
    Write-Host 'Claude Code will edit/run WITHOUT asking. Use only in a git repo (review with `git diff`).' -ForegroundColor Yellow
} else {
    Write-Host 'DeepSeek V4 Pro session, PC kept awake. Permission prompts are ON (safe).' -ForegroundColor Green
    Write-Host 'For true hands-off overnight running, re-run with -Unattended.' -ForegroundColor DarkGray
}
Write-Host 'Runs OFF your Claude weekly limit (pay-per-token on DeepSeek).' -ForegroundColor DarkGray
Write-Host "Working in: $(Get-Location)" -ForegroundColor DarkGray
Write-Host 'DeepSeek is an UNOFFICIAL Claude Code route; if it stalls, glm-overnight.ps1 is more reliable.' -ForegroundColor DarkGray
Write-Host 'Privacy note: hosted DeepSeek stores data in the PRC; use OpenRouter/self-host for sensitive code.' -ForegroundColor DarkGray
Write-Host 'Keep this window open. Closing it ends the run and restores normal sleep.' -ForegroundColor DarkGray
Write-Host ''

# --- 6. Launch Claude Code; restore sleep on exit ------------------------------
try {
    claude @claudeArgsList
}
finally {
    # Clear the keep-awake request so the PC can sleep normally again.
    [StayAwake]::SetThreadExecutionState($ES_CONTINUOUS) | Out-Null
    Write-Host 'Sleep behaviour restored. Session ended.' -ForegroundColor DarkGray
}
