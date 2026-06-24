<#
.SYNOPSIS
    Generate a local usage.json from ccusage for the cost calculator page.

.DESCRIPTION
    Runs `npx ccusage@latest monthly --json`, parses the most recent month's
    token counts and reported cost, and writes them to ./usage.json next to this
    script in a simple, stable schema:

        {
          "month":            "YYYY-MM",
          "inputTokens":      <int>,
          "outputTokens":     <int>,
          "cacheWriteTokens": <int>,
          "cacheReadTokens":  <int>,
          "totalTokens":      <int>,
          "reportedCostUSD":  <number>
        }

    index.html optionally fetches ./usage.json at runtime to personalize the
    page. If usage.json is absent the page falls back to neutral defaults.

.NOTES
    PRIVACY / LOCAL-ONLY:
    usage.json is git-ignored (see .gitignore) and is NEVER published. It can
    contain your personal usage figures, so it stays on your machine only.

    This script does NOT transmit anything anywhere. It only:
      1. runs ccusage locally (which reads your local Claude Code logs), and
      2. writes a file to disk in this directory.
    No network upload, no telemetry, no API calls of its own.

    Requirements: Node.js / npm on PATH (so `npx` works). ccusage is fetched on
    demand by npx; no global install needed.

    Fallback: if `--json` is unavailable in your ccusage version, run
    `npx ccusage@latest monthly` (no flag) to read the plain table by eye, or
    upgrade ccusage. This script requires the --json output to parse reliably.
#>

[CmdletBinding()]
param(
    # Where to write the output file. Defaults to usage.json beside this script.
    [string]$OutFile = (Join-Path $PSScriptRoot 'usage.json')
)

$ErrorActionPreference = 'Stop'

Write-Host 'Running ccusage (monthly, JSON)...' -ForegroundColor Cyan

# --- Run ccusage and capture stdout -----------------------------------------
try {
    # Capture raw JSON text. npx will download ccusage on first run.
    $raw = & npx ccusage@latest monthly --json 2>$null
}
catch {
    Write-Error "Failed to run 'npx ccusage@latest monthly --json'. Is Node.js/npm installed and on PATH? Underlying error: $($_.Exception.Message)"
    exit 1
}

if (-not $raw) {
    Write-Error "ccusage returned no output. If your ccusage version lacks --json, run 'npx ccusage@latest monthly' and read the table manually, or upgrade ccusage."
    exit 1
}

# --- Parse JSON --------------------------------------------------------------
try {
    # $raw may be an array of lines; join before parsing.
    $json = ($raw -join "`n") | ConvertFrom-Json
}
catch {
    Write-Error "Could not parse ccusage JSON output. Raw output begins: $(( $raw -join ' ' ).Substring(0, [Math]::Min(200, ($raw -join ' ').Length)))"
    exit 1
}

# ccusage shapes vary by version. The monthly report is typically an array of
# month objects under .monthly (newer) or the top-level value itself (older).
$months = $null
if ($json.PSObject.Properties.Name -contains 'monthly') {
    $months = $json.monthly
}
elseif ($json -is [System.Array]) {
    $months = $json
}
else {
    # Single object — wrap it.
    $months = @($json)
}

if (-not $months -or $months.Count -eq 0) {
    Write-Error 'ccusage JSON contained no monthly rows.'
    exit 1
}

# --- Pick the latest month ---------------------------------------------------
# Each row usually has a 'month' field like "2026-06". Sort lexically (YYYY-MM
# sorts chronologically) and take the last; fall back to the last array element.
$latest = $months |
    Where-Object { $_.month } |
    Sort-Object month |
    Select-Object -Last 1
if (-not $latest) { $latest = $months[-1] }

# --- Helper: read the first field that exists, else 0 ------------------------
function Get-Field {
    param([object]$Obj, [string[]]$Names)
    foreach ($n in $Names) {
        if ($Obj.PSObject.Properties.Name -contains $n -and $null -ne $Obj.$n) {
            return $Obj.$n
        }
    }
    return 0
}

# Field names differ across ccusage versions; try the common variants.
$inputTokens      = [int64](Get-Field $latest @('inputTokens', 'input_tokens', 'input'))
$outputTokens     = [int64](Get-Field $latest @('outputTokens', 'output_tokens', 'output'))
$cacheWriteTokens = [int64](Get-Field $latest @('cacheCreationTokens', 'cacheCreateTokens', 'cache_creation_tokens', 'cacheCreate'))
$cacheReadTokens  = [int64](Get-Field $latest @('cacheReadTokens', 'cache_read_tokens', 'cacheRead'))
$reportedCost     = [double](Get-Field $latest @('totalCost', 'cost', 'costUSD', 'totalCostUsd'))
$monthLabel       = [string](Get-Field $latest @('month'))

# Prefer an explicit total if present; otherwise sum the components.
$totalTokens = [int64](Get-Field $latest @('totalTokens', 'total_tokens'))
if ($totalTokens -le 0) {
    $totalTokens = $inputTokens + $outputTokens + $cacheWriteTokens + $cacheReadTokens
}

# --- Build the output object (ordered for stable, readable JSON) -------------
$out = [ordered]@{
    month            = $monthLabel
    inputTokens      = $inputTokens
    outputTokens     = $outputTokens
    cacheWriteTokens = $cacheWriteTokens
    cacheReadTokens  = $cacheReadTokens
    totalTokens      = $totalTokens
    reportedCostUSD  = $reportedCost
}

# --- Write usage.json (local only; never transmitted) ------------------------
$out | ConvertTo-Json -Depth 4 | Set-Content -Path $OutFile -Encoding UTF8

Write-Host ''
Write-Host "Wrote $OutFile" -ForegroundColor Green
Write-Host "  month            : $monthLabel"
Write-Host "  inputTokens      : $inputTokens"
Write-Host "  outputTokens     : $outputTokens"
Write-Host "  cacheWriteTokens : $cacheWriteTokens"
Write-Host "  cacheReadTokens  : $cacheReadTokens"
Write-Host "  totalTokens      : $totalTokens"
Write-Host "  reportedCostUSD  : $reportedCost"
Write-Host ''
Write-Host 'This file is local-only and git-ignored. Nothing was transmitted.' -ForegroundColor DarkGray
