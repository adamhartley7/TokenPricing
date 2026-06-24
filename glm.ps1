<#
.SYNOPSIS
    Launch Claude Code routed to GLM 5.2 (Z.ai) instead of Anthropic.

.DESCRIPTION
    Sets the ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN environment variables for
    THIS PowerShell window only, then launches Claude Code. All work done in this
    window runs on your GLM Coding Plan and does NOT consume your Claude weekly
    limit. Close the window (or open a fresh one) to return to normal Claude.

    The model "brain" is swapped to GLM; the Claude Code harness still provides
    your files, local tools, MCP servers and CLAUDE.md. Anthropic-only features
    (ultracode/max-effort, account memory, built-in web search) are NOT available.

.NOTES
    The API key is read from (in order): the GLM_API_KEY env var, a local
    .glm-key file (git-ignored), or an interactive prompt. The key is NEVER
    committed and is NEVER transmitted anywhere except to Z.ai by Claude Code.

    Get a key: https://z.ai/subscribe  ->  account  ->  API Keys.

.EXAMPLE
    ./glm.ps1
.EXAMPLE
    ./glm.ps1 --dangerously-skip-permissions   # extra args pass through to claude
#>

$ErrorActionPreference = 'Stop'
$KeyFile = Join-Path $PSScriptRoot '.glm-key'

# --- 1. Resolve the GLM (Z.ai) API key -----------------------------------------
$key = $env:GLM_API_KEY
if (-not $key -and (Test-Path $KeyFile)) {
    $key = (Get-Content $KeyFile -Raw).Trim()
}
if (-not $key) {
    Write-Host 'Paste your Z.ai (GLM) API key. Get it at https://z.ai > API Keys.' -ForegroundColor Cyan
    $secure = Read-Host -AsSecureString 'GLM API key'
    $key = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    if (-not $key) { Write-Error 'No key entered.'; exit 1 }

    $save = Read-Host 'Save this key to .glm-key (git-ignored) so you do not re-enter it? (y/N)'
    if ($save -match '^[Yy]') {
        Set-Content -Path $KeyFile -Value $key -Encoding UTF8 -NoNewline
        Write-Host "Saved to $KeyFile (git-ignored)." -ForegroundColor DarkGray
    }
}

# --- 2. Point Claude Code at Z.ai for THIS window only -------------------------
$env:ANTHROPIC_BASE_URL   = 'https://api.z.ai/api/anthropic'
$env:ANTHROPIC_AUTH_TOKEN = $key
# Optional: pin specific GLM model ids if Z.ai's default mapping isn't what you want.
# $env:ANTHROPIC_MODEL = 'glm-5.2'

# --- 3. Sanity check that Claude Code is installed -----------------------------
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Error "Claude Code ('claude') not found on PATH. Install it first, then re-run."
    exit 1
}

Write-Host ''
Write-Host 'Routed to GLM 5.2 (Z.ai).' -ForegroundColor Green
Write-Host 'This window does NOT use your Claude weekly limit. Close it to return to normal Claude.' -ForegroundColor DarkGray
Write-Host 'Privacy note: the hosted Z.ai endpoint stores data in the PRC; use OpenRouter/self-host for sensitive code.' -ForegroundColor DarkGray
Write-Host ''

# --- 4. Launch Claude Code (extra args pass through) ---------------------------
claude @args
