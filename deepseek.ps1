<#
.SYNOPSIS
    Launch Claude Code routed to DeepSeek V4 Pro instead of Anthropic.

.DESCRIPTION
    Sets ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN for THIS PowerShell window only, then launches Claude
    Code. Work done here runs on DeepSeek (pay-per-token) and does NOT consume your Claude weekly limit.
    Close the window to return to normal Claude.

    The harness (Claude Code) still provides your files, local tools, MCP servers and CLAUDE.md. Anthropic-only
    features (ultracode/max-effort, account memory, built-in web search) are NOT available — add a search MCP
    server if you need web search (see ADVANCED-SETUP.md).

.NOTES
    Key resolved from: DEEPSEEK_API_KEY env var, a local .deepseek-key file (git-ignored), or a secure prompt.
    Get a key: https://platform.deepseek.com/api_keys
    Privacy: the hosted DeepSeek endpoint stores data in the PRC; use a Western host or self-host for sensitive code.

.EXAMPLE
    ./deepseek.ps1
.EXAMPLE
    ./deepseek.ps1 --dangerously-skip-permissions
#>

$ErrorActionPreference = 'Stop'
$KeyFile = Join-Path $PSScriptRoot '.deepseek-key'

# --- 1. Resolve the DeepSeek API key -------------------------------------------
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

# --- 2. Point Claude Code at DeepSeek for THIS window only ---------------------
$env:ANTHROPIC_BASE_URL          = 'https://api.deepseek.com/anthropic'
$env:ANTHROPIC_AUTH_TOKEN        = $key
$env:ANTHROPIC_MODEL             = 'deepseek-v4-pro'
$env:ANTHROPIC_DEFAULT_HAIKU_MODEL = 'deepseek-v4-flash'

# --- 3. Sanity check ------------------------------------------------------------
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Error "Claude Code ('claude') not found on PATH. Install it first, then re-run."
    exit 1
}

Write-Host ''
Write-Host 'Routed to DeepSeek V4 Pro.' -ForegroundColor Green
Write-Host 'This window does NOT use your Claude weekly limit. Close it to return to normal Claude.' -ForegroundColor DarkGray
Write-Host 'Privacy note: hosted DeepSeek stores data in the PRC; use OpenRouter/self-host for sensitive code.' -ForegroundColor DarkGray
Write-Host ''

# --- 4. Launch Claude Code (extra args pass through) ---------------------------
claude @args
