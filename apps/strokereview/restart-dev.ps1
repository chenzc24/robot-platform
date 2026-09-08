param(
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8000,
    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 5173,
    [ValidateRange(1, 65535)]
    [int]$ModelPort = 8010,
    [switch]$SkipModels,
    [switch]$NoBrowser,
    [switch]$Wait,
    [switch]$ReloadBackend,
    [switch]$SmokeTest
)

$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $MyInvocation.MyCommand.Path)).TrimEnd('\')

Write-Host "Stopping previous project development services..."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $projectRoot "stop-dev.ps1")
if ($LASTEXITCODE -ne 0) { throw "stop-dev.ps1 failed with exit code $LASTEXITCODE; restart aborted." }

Write-Host "Starting project development services..."
$arguments = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $projectRoot "start-dev.ps1"),
    "-BackendPort", [string]$BackendPort,
    "-FrontendPort", [string]$FrontendPort,
    "-ModelPort", [string]$ModelPort,
    "-ExistingAction", "Fail"
)
if ($SkipModels) { $arguments += "-SkipModels" }
if ($NoBrowser) { $arguments += "-NoBrowser" }
if ($Wait) { $arguments += "-Wait" }
if ($ReloadBackend) { $arguments += "-ReloadBackend" }
if ($SmokeTest) { $arguments += "-SmokeTest" }

& powershell.exe @arguments
exit $LASTEXITCODE
