[CmdletBinding()]
param(
    [string]$HostAddress = "127.0.0.1",
    [ValidateRange(1, 65535)]
    [int]$Port = 3000,
    [string]$ApiBaseUrl = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$FrontendRoot = Join-Path $RepoRoot "frontend"
$NodeModules = Join-Path $FrontendRoot "node_modules"

if (-not (Test-Path -LiteralPath $NodeModules)) {
    throw "Frontend dependencies are missing. Run 'npm install' in frontend first."
}

if ($ApiBaseUrl) {
    $env:NEXT_PUBLIC_API_BASE_URL = $ApiBaseUrl.TrimEnd("/")
}

$EffectiveApiBaseUrl = if ($env:NEXT_PUBLIC_API_BASE_URL) {
    $env:NEXT_PUBLIC_API_BASE_URL
}
else {
    "http://127.0.0.1:8001"
}

Write-Host "Starting dashboard at http://${HostAddress}:$Port"
Write-Host "Research API base URL: $EffectiveApiBaseUrl"
Push-Location $FrontendRoot
try {
    & npm run dev -- --hostname $HostAddress --port $Port
    if ($LASTEXITCODE -ne 0) {
        throw "Dashboard exited with code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
