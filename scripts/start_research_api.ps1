[CmdletBinding()]
param(
    [string]$HostAddress = "127.0.0.1",
    [ValidateRange(1, 65535)]
    [int]$Port = 8001,
    [string]$CorsOrigins = "",
    [string]$PythonCommand = "python"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $RepoRoot ".env"

if ($CorsOrigins) {
    $env:RESEARCH_API_CORS_ORIGINS = $CorsOrigins
}

$UvicornArgs = @(
    "-m", "uvicorn",
    "autowealth.api.research_server:app",
    "--reload",
    "--host", $HostAddress,
    "--port", $Port
)

if (Test-Path -LiteralPath $EnvFile) {
    $UvicornArgs += @("--env-file", $EnvFile)
}

Write-Host "Starting research API at http://${HostAddress}:$Port"
Push-Location $RepoRoot
try {
    & $PythonCommand @UvicornArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Research API exited with code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
