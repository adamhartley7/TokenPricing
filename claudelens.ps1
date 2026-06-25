<#
.SYNOPSIS
    Launch ClaudeLens (desktop session/memory browser) routed to GLM 5.2 (Z.ai).

.DESCRIPTION
    Sets the ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN environment variables for THIS
    PowerShell window only, then opens the ClaudeLens desktop app. Because ClaudeLens is
    launched as a child of this window, its embedded terminal AND its in-app chat
    (Claude Agent SDK) inherit these variables and run on your GLM Coding Plan instead of
    Anthropic -- so browsing and continuing sessions does NOT consume your Claude weekly
    limit. The GLM key is the SAME one used by glm.ps1 (.glm-key), so you only manage one.

    ClaudeLens itself is read from (in order): the CLAUDELENS_EXE env var, a local
    .claudelens-path file (git-ignored), common Windows install locations, or the PATH.

    IMPORTANT: ClaudeLens is single-instance. If it is already open, fully QUIT it first
    (it would otherwise just refocus the existing window and ignore this routing).

.NOTES
    The API key is read from (in order): the GLM_API_KEY env var, a local .glm-key file
    (git-ignored), or an interactive prompt. The key is NEVER committed and is NEVER
    transmitted anywhere except to Z.ai by ClaudeLens.

    Get a key: https://z.ai/subscribe  ->  account  ->  API Keys.
    Get ClaudeLens: https://github.com/giulio333/ClaudeLens/releases

.EXAMPLE
    ./claudelens.ps1
#>

$ErrorActionPreference = 'Stop'
$KeyFile  = Join-Path $PSScriptRoot '.glm-key'
$PathFile = Join-Path $PSScriptRoot '.claudelens-path'

# --- 1. Resolve the GLM (Z.ai) API key -- shared with glm.ps1 (.glm-key) -------
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

# --- 2. Locate the ClaudeLens executable ---------------------------------------
$exe = $null
$candidates = @()
if ($env:CLAUDELENS_EXE)        { $candidates += $env:CLAUDELENS_EXE }
if (Test-Path $PathFile)        { $candidates += (Get-Content $PathFile -Raw).Trim() }
$candidates += @(
    (Join-Path $env:LOCALAPPDATA 'Programs\claudelens\ClaudeLens.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\ClaudeLens\ClaudeLens.exe'),
    (Join-Path $env:ProgramFiles 'ClaudeLens\ClaudeLens.exe')
)
foreach ($c in $candidates) {
    if ($c -and (Test-Path $c)) { $exe = $c; break }
}
if (-not $exe) {
    $cmd = Get-Command claudelens -ErrorAction SilentlyContinue
    if ($cmd) { $exe = $cmd.Source }
}

if (-not $exe) {
    Write-Host ''
    Write-Host 'ClaudeLens was not found.' -ForegroundColor Yellow
    Write-Host '  1. Download the Windows .exe from https://github.com/giulio333/ClaudeLens/releases'
    Write-Host '     (Windows support is experimental; SmartScreen -> More info -> Run anyway.)'
    Write-Host '  2. Run the installer, then re-run ./claudelens.ps1'
    Write-Host ''
    $typed = Read-Host 'Or paste the full path to ClaudeLens.exe now (blank to exit)'
    if ($typed -and (Test-Path $typed)) {
        $exe = $typed
        $save = Read-Host 'Save this path to .claudelens-path (git-ignored)? (y/N)'
        if ($save -match '^[Yy]') {
            Set-Content -Path $PathFile -Value $exe -Encoding UTF8 -NoNewline
            Write-Host "Saved to $PathFile (git-ignored)." -ForegroundColor DarkGray
        }
    } else {
        Write-Error 'ClaudeLens executable not found.'; exit 1
    }
}

# --- 3. Point ClaudeLens at Z.ai for THIS window only --------------------------
$env:ANTHROPIC_BASE_URL   = 'https://api.z.ai/api/anthropic'
$env:ANTHROPIC_AUTH_TOKEN = $key
# Optional: pin a specific GLM model id if Z.ai's default mapping isn't what you want.
# $env:ANTHROPIC_MODEL = 'glm-5.2'

Write-Host ''
Write-Host 'Launching ClaudeLens routed to GLM 5.2 (Z.ai).' -ForegroundColor Green
Write-Host 'Its terminal + in-app chat run on GLM, NOT your Claude weekly limit.' -ForegroundColor DarkGray
Write-Host 'If ClaudeLens is already open, QUIT it first or it will ignore this routing.' -ForegroundColor DarkGray
Write-Host 'Privacy note: the hosted Z.ai endpoint stores data in the PRC; use a local/Western model for sensitive code.' -ForegroundColor DarkGray
Write-Host ''

# --- 4. Launch ClaudeLens (inherits the env vars set above) --------------------
Start-Process -FilePath $exe
