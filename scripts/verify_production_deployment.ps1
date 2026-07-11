[CmdletBinding()]
param(
    [string]$DashboardUrl = "https://dashboard.outlook.xin",
    [string]$ApiUrl = "https://api.outlook.xin",
    [ValidateRange(1, 120)]
    [int]$TimeoutSeconds = 20
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Net.Http
$DashboardUrl = $DashboardUrl.TrimEnd("/")
$ApiUrl = $ApiUrl.TrimEnd("/")
$Results = [System.Collections.Generic.List[object]]::new()
$Client = [System.Net.Http.HttpClient]::new()
$Client.Timeout = [TimeSpan]::FromSeconds($TimeoutSeconds)
$Client.DefaultRequestHeaders.UserAgent.ParseAdd("AutoWealth-Deployment-Verification/1.0")

function Invoke-ReadOnlyCheck {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [int[]]$AllowedStatusCodes = @(200),
        [scriptblock]$ValidateBody
    )

    $StatusCode = 0
    $Body = ""
    $Message = ""
    $Passed = $false
    try {
        $Response = $Client.GetAsync($Url).GetAwaiter().GetResult()
        $StatusCode = [int]$Response.StatusCode
        $Body = $Response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $Passed = $AllowedStatusCodes -contains $StatusCode
        if ($Passed -and $null -ne $ValidateBody) {
            $Passed = [bool](& $ValidateBody $Body $StatusCode)
        }
        $Message = "HTTP $StatusCode"
    }
    catch {
        $Message = $_.Exception.Message
    }

    $Result = [pscustomobject]@{
        Name = $Name
        Url = $Url
        StatusCode = $StatusCode
        Passed = $Passed
        Message = $Message
        Body = $Body
    }
    $Results.Add($Result)
    $Label = if ($Passed) { "PASS" } else { "FAIL" }
    $Color = if ($Passed) { "Green" } else { "Red" }
    Write-Host "[$Label] $Name - $Message" -ForegroundColor $Color
    return $Result
}

try {
    Write-Host "AutoWealth read-only deployment verification" -ForegroundColor Cyan
    Write-Host "Dashboard: $DashboardUrl"
    Write-Host "API:       $ApiUrl"

    $Health = Invoke-ReadOnlyCheck -Name "API health" -Url "$ApiUrl/research/health" -ValidateBody {
        param($Body, $StatusCode)
        if ($StatusCode -ne 200) { return $false }
        try { return (($Body | ConvertFrom-Json).status -eq "ok") } catch { return $false }
    }

    $Runs = Invoke-ReadOnlyCheck -Name "Research run list" -Url "$ApiUrl/research/runs" -ValidateBody {
        param($Body, $StatusCode)
        if ($StatusCode -ne 200) { return $false }
        try { return (($Body | ConvertFrom-Json).data_source -eq "real_artifacts") } catch { return $false }
    }

    $RunCount = 0
    if ($Runs.Passed) {
        try { $RunCount = [int](($Runs.Body | ConvertFrom-Json).count) } catch { $RunCount = 0 }
    }
    $LatestStatuses = if ($RunCount -gt 0) { @(200) } else { @(200, 404) }
    Invoke-ReadOnlyCheck -Name "Latest research run" -Url "$ApiUrl/research/runs/latest" -AllowedStatusCodes $LatestStatuses -ValidateBody {
        param($Body, $StatusCode)
        if ($StatusCode -eq 200) { return $true }
        try { return (($Body | ConvertFrom-Json).code -eq "research_run_not_found") } catch { return $false }
    } | Out-Null

    $Pages = @(
        @{ Name = "Dashboard home"; Path = "/" },
        @{ Name = "Backtest page"; Path = "/backtest" },
        @{ Name = "Portfolio page"; Path = "/portfolio" },
        @{ Name = "Factors page"; Path = "/factors" },
        @{ Name = "Macro page"; Path = "/macro" },
        @{ Name = "Research notes page"; Path = "/research-notes" },
        @{ Name = "System status page"; Path = "/system-status" }
    )
    foreach ($Page in $Pages) {
        Invoke-ReadOnlyCheck -Name $Page.Name -Url "$DashboardUrl$($Page.Path)" | Out-Null
    }

    $PassedCount = @($Results | Where-Object Passed).Count
    $FailedCount = $Results.Count - $PassedCount
    Write-Host ""
    Write-Host "Summary: $PassedCount passed, $FailedCount failed" -ForegroundColor $(if ($FailedCount -eq 0) { "Green" } else { "Red" })
    if ($FailedCount -gt 0) {
        exit 1
    }
}
finally {
    $Client.Dispose()
}
