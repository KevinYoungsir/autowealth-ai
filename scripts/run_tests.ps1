[CmdletBinding()]
param(
    [string]$TestTarget = "tests/test_research_api.py",
    [string]$BaseTemp = "D:\pytest-tmp-autowealth",
    [string]$PythonCommand = "python"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$FrontendRoot = Join-Path $RepoRoot "frontend"
$NodeModules = Join-Path $FrontendRoot "node_modules"

Push-Location $RepoRoot
try {
    & $PythonCommand -m pytest $TestTarget -v --basetemp $BaseTemp -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) {
        throw "Python tests failed with code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $NodeModules)) {
    throw "Frontend dependencies are missing. Run 'npm install' in frontend first."
}

Push-Location $FrontendRoot
try {
    & npm run typecheck
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend typecheck failed with code $LASTEXITCODE."
    }

    & npm run build
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend build failed with code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
