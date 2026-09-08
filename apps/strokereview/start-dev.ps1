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
    [switch]$SmokeTest,
    [ValidateSet("Auto", "Prompt", "Use", "Restart", "Fail")]
    [string]$ExistingAction = "Auto"
)

$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $MyInvocation.MyCommand.Path)).TrimEnd('\')
$backendDir = Join-Path $projectRoot "backend"
$frontendDir = Join-Path $projectRoot "frontend"
$modelDir = Join-Path $projectRoot "model-service"
$logDir = Join-Path $projectRoot ".devlogs"
$serviceRunner = Join-Path $projectRoot "scripts\run-dev-service.ps1"
$stopScript = Join-Path $projectRoot "stop-dev.ps1"
. (Join-Path $projectRoot "scripts\dev-lifecycle.ps1")
Initialize-DevLifecycle $projectRoot
Remove-Item -LiteralPath $script:DevStopRequestPath -Force -ErrorAction SilentlyContinue
$script:stopRequestBaselineUtc = [DateTime]::UtcNow

function Get-StopRequestTimeUtc {
    if (-not (Test-Path -LiteralPath $script:DevStopRequestPath)) { return $null }
    try {
        $raw = (Get-Content -LiteralPath $script:DevStopRequestPath -Raw -Encoding UTF8).Trim()
        return [DateTimeOffset]::Parse(
            $raw,
            [System.Globalization.CultureInfo]::InvariantCulture,
            [System.Globalization.DateTimeStyles]::RoundtripKind
        ).UtcDateTime
    } catch {
        # Compatibility with an incomplete/older marker: its file timestamp is
        # still sufficient to decide whether it targets this run.
        return (Get-Item -LiteralPath $script:DevStopRequestPath).LastWriteTimeUtc
    }
}

function Test-CurrentRunStopRequested {
    $requestedAtUtc = Get-StopRequestTimeUtc
    return $null -ne $requestedAtUtc -and $requestedAtUtc -gt $script:stopRequestBaselineUtc
}

if (-not (Get-Command node.exe -ErrorAction SilentlyContinue) -and (Test-Path "C:\Program Files\nodejs\node.exe")) {
    $env:Path = "C:\Program Files\nodejs;" + $env:Path
}

function Get-ErrorLogTail([string]$ErrorLog, [int]$LineCount = 40) {
    if (-not (Test-Path -LiteralPath $ErrorLog)) { return "(error log does not exist)" }
    $lines = @(Get-Content -LiteralPath $ErrorLog -Tail $LineCount -ErrorAction SilentlyContinue)
    if ($lines.Count -eq 0) { return "(error log is empty)" }
    return ($lines -join [Environment]::NewLine)
}

function Throw-ServiceFailure(
    [string]$ServiceName,
    [int]$Port,
    [System.Diagnostics.Process]$Process,
    [string]$ErrorLog,
    [string]$ExitCodeFile,
    [string]$Reason
) {
    $exitCode = "not available"
    if (Test-Path -LiteralPath $ExitCodeFile) {
        $recorded = (Get-Content -LiteralPath $ExitCodeFile -Raw -ErrorAction SilentlyContinue).Trim()
        if (-not [string]::IsNullOrWhiteSpace($recorded)) { $exitCode = $recorded }
    } elseif ($Process) {
        try {
            $Process.Refresh()
            if ($Process.HasExited) { $exitCode = [string]$Process.ExitCode }
        } catch { $exitCode = "unknown" }
    }
    $processId = if ($Process) { $Process.Id } else { "not started" }
    $tail = Get-ErrorLogTail $ErrorLog
    throw @"
Service '$ServiceName' failed.
Reason: $Reason
Port: $Port
Launcher PID: $processId
Exit code: $exitCode
Error log: $ErrorLog
--- error log tail ---
$tail
--- end error log tail ---
"@
}

function Test-UrlReady([string]$Url, [int]$TimeoutSeconds = 4) {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec $TimeoutSeconds | Out-Null
        return $true
    } catch { return $false }
}

function Wait-ForUrl(
    [string]$ServiceName,
    [int]$Port,
    [string]$Url,
    [System.Diagnostics.Process]$Process,
    [string]$ErrorLog,
    [string]$ExitCodeFile,
    [int]$TimeoutSeconds = 60
) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $Process.Refresh()
        if ($Process.HasExited) {
            Throw-ServiceFailure $ServiceName $Port $Process $ErrorLog $ExitCodeFile "exited before $Url became ready"
        }
        if (Test-UrlReady $Url 2) { return }
        Start-Sleep -Milliseconds 500
    }
    Throw-ServiceFailure $ServiceName $Port $Process $ErrorLog $ExitCodeFile "timed out after $TimeoutSeconds seconds waiting for $Url"
}

function Assert-PortFree([string]$ServiceName, [int]$Port) {
    $owners = @(Get-DevPortOwners $Port)
    if ($owners.Count -eq 0) { return }
    $details = ($owners | ForEach-Object { Format-DevPortOwner $_ $ServiceName }) -join [Environment]::NewLine
    throw "Service '$ServiceName' cannot start because port $Port is still occupied.`n$details"
}

function Start-DevService(
    [string]$ServiceName,
    [int]$Port,
    [string]$Executable,
    [string[]]$Arguments,
    [string]$WorkingDirectory,
    [string]$StandardOutputLog,
    [string]$StandardErrorLog,
    [string]$ExitCodeFile
) {
    $specPath = Join-Path $logDir "$ServiceName.service.json"
    foreach ($generatedFile in @($StandardOutputLog, $StandardErrorLog, $ExitCodeFile, $specPath)) {
        if (Test-Path -LiteralPath $generatedFile) { Remove-Item -LiteralPath $generatedFile -Force }
    }
    $spec = [ordered]@{
        executable = $Executable
        arguments = $Arguments
        working_directory = $WorkingDirectory
        stdout_log = $StandardOutputLog
        stderr_log = $StandardErrorLog
        exit_code_file = $ExitCodeFile
    }
    $specJson = $spec | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($specPath, $specJson, [System.Text.UTF8Encoding]::new($false))

    $launcher = Start-Process -FilePath "powershell.exe" `
        -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", "`"$serviceRunner`"",
            "-SpecPath", "`"$specPath`""
        ) `
        -WorkingDirectory $projectRoot -PassThru -WindowStyle Hidden

    $launcherInfo = Get-DevProcess $launcher.Id
    $record = [pscustomobject][ordered]@{
        name = $ServiceName
        port = $Port
        pid = $launcher.Id
        listener_pid = 0
        process_name = if ($launcherInfo) { [string]$launcherInfo.Name } else { "powershell.exe" }
        command_line = Format-DevCommandLine $Executable $Arguments
        launcher_command_line = if ($launcherInfo) { [string]$launcherInfo.CommandLine } else { "(unavailable)" }
        executable = $Executable
        arguments = $Arguments
        working_directory = $WorkingDirectory
        stdout_log = $StandardOutputLog
        stderr_log = $StandardErrorLog
        started_at = (Get-Date).ToString("o")
    }
    $script:serviceRecords += $record
    Write-DevState $script:serviceRecords
    return $launcher
}

function Update-ServiceListener([string]$ServiceName, [int]$Port) {
    $owner = @(Get-DevPortOwners $Port | Where-Object { $_.belongs_to_project } | Select-Object -First 1)
    if ($owner.Count -eq 0) { return }
    foreach ($record in $script:serviceRecords) {
        if ($record.name -eq $ServiceName) {
            $record.listener_pid = [int]$owner[0].pid
        }
    }
    Write-DevState $script:serviceRecords
}

$requestedServices = @(
    [pscustomobject]@{ name = "frontend"; port = $FrontendPort; health = "http://127.0.0.1:$FrontendPort" },
    [pscustomobject]@{ name = "backend"; port = $BackendPort; health = "http://127.0.0.1:$BackendPort/api/health" }
)
if (-not $SkipModels) {
    $requestedServices += [pscustomobject]@{ name = "model-service"; port = $ModelPort; health = "http://127.0.0.1:$ModelPort/api/health" }
}

# Drop dead/reused PID records before interpreting port ownership.
Write-Host "Checking project runtime state and ports..."
Remove-StaleDevStateRecords | Out-Null
$projectConflicts = @()
$foreignConflicts = @()
$requestedPorts = @($requestedServices | ForEach-Object { [int]$_.port })
$currentPortOwners = @(Get-DevPortOwnersForPorts $requestedPorts)
foreach ($service in $requestedServices) {
    foreach ($owner in @($currentPortOwners | Where-Object { $_.port -eq [int]$service.port })) {
        $conflict = [pscustomobject]@{ service = $service; owner = $owner }
        if ($owner.belongs_to_project) { $projectConflicts += $conflict } else { $foreignConflicts += $conflict }
    }
}

if ($foreignConflicts.Count -gt 0) {
    $messages = @()
    foreach ($conflict in $foreignConflicts) {
        $messages += Format-DevPortOwner $conflict.owner $conflict.service.name
    }
    throw @"
Development environment was not started because a required port belongs to another program.
No process was terminated.
$($messages -join [Environment]::NewLine)
"@
}

if ($projectConflicts.Count -gt 0) {
    $occupiedProjectPorts = @($projectConflicts | ForEach-Object { [int]$_.service.port } | Select-Object -Unique)
    $allServicesPresent = $occupiedProjectPorts.Count -eq $requestedServices.Count
    Write-Host "Found an older development instance belonging to this project:"
    foreach ($conflict in $projectConflicts) {
        Write-Host (Format-DevPortOwner $conflict.owner $conflict.service.name)
    }

    $action = $ExistingAction
    if ($action -eq "Auto") {
        $allExistingHealthy = $allServicesPresent
        if ($allExistingHealthy) {
            foreach ($service in $requestedServices) {
                if (-not (Test-UrlReady $service.health 5)) {
                    $allExistingHealthy = $false
                    break
                }
            }
        }
        $action = if ($allExistingHealthy) { "Use" } else { "Restart" }
        if ($action -eq "Use") {
            Write-Host "All existing project services are healthy; reusing them."
        } else {
            Write-Host "The existing project environment is incomplete or unhealthy; restarting it safely."
        }
    }
    if ($action -eq "Prompt") {
        if ($allServicesPresent) {
            $answer = Read-Host "Choose [U] use existing services, [R] safely restart, or [C] cancel"
        } else {
            $answer = Read-Host "Only part of the environment is running. Choose [R] safely restart or [C] cancel"
        }
        if ($answer -match '^[Uu]' -and $allServicesPresent) { $action = "Use" }
        elseif ($answer -match '^[Rr]') { $action = "Restart" }
        else { $action = "Fail" }
    }

    if ($action -eq "Use") {
        if (-not $allServicesPresent) {
            throw "Cannot use the existing instance because only some required project services are running. Run .\restart-dev.ps1."
        }
        foreach ($service in $requestedServices) {
            if (-not (Test-UrlReady $service.health 5)) {
                throw "Existing service '$($service.name)' on port $($service.port) belongs to this project but failed its health check. Run .\restart-dev.ps1."
            }
        }
        $frontendUrl = "http://127.0.0.1:$FrontendPort"
        Write-Host "Using existing project services: $frontendUrl"
        if (-not $NoBrowser) { Start-Process $frontendUrl }
        return
    }

    if ($action -eq "Restart") {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $stopScript
        if ($LASTEXITCODE -ne 0) { throw "Safe restart failed because stop-dev.ps1 returned exit code $LASTEXITCODE." }
        # stop-dev.ps1 writes a marker so an older start-dev.ps1 controller can
        # leave its monitoring loop. Keep that marker for the old controller,
        # but make this new run ignore it. A later stop-dev.ps1 call overwrites
        # the marker with a newer timestamp and will stop this run normally.
        $script:stopRequestBaselineUtc = [DateTime]::UtcNow
    } else {
        throw "Existing project services were left untouched. Run .\restart-dev.ps1 or rerun with -ExistingAction Use."
    }
}

foreach ($service in $requestedServices) { Assert-PortFree $service.name ([int]$service.port) }

$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
$nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
if (-not $uvCommand) { throw "uv was not found on PATH." }
if (-not $npmCommand) { throw "npm was not found. Install Node.js LTS and reopen the terminal." }
if (-not $nodeCommand) { throw "node was not found. Install Node.js LTS and reopen the terminal." }

if (-not (Test-Path (Join-Path $backendDir ".venv"))) {
    Write-Host "Installing backend dependencies..."
    & $uvCommand.Source sync --locked --project $backendDir --group dev
    if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed." }
}
if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Write-Host "Installing frontend dependencies..."
    Push-Location $frontendDir
    try { & $npmCommand.Source ci } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
}
if (-not $SkipModels -and -not (Test-Path (Join-Path $modelDir ".venv"))) {
    Write-Host "Installing local CPU model dependencies..."
    & $uvCommand.Source sync --locked --project $modelDir --python 3.12 --group dev
    if ($LASTEXITCODE -ne 0) { throw "Model dependency installation failed." }
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$backendOut = Join-Path $logDir "backend.out.log"
$backendErr = Join-Path $logDir "backend.err.log"
$frontendOut = Join-Path $logDir "frontend.out.log"
$frontendErr = Join-Path $logDir "frontend.err.log"
$modelOut = Join-Path $logDir "model.out.log"
$modelErr = Join-Path $logDir "model.err.log"
$backendExitCode = Join-Path $logDir "backend.exitcode"
$frontendExitCode = Join-Path $logDir "frontend.exitcode"
$modelExitCode = Join-Path $logDir "model.exitcode"

$script:serviceRecords = @()
$modelProcess = $null
$backendProcess = $null
$frontendProcess = $null
$startedAny = $false
$leaveServicesRunning = $false

try {
    if (-not $SkipModels) {
        Write-Host "Starting model service on port $ModelPort..."
        $env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
        $modelExecutable = Join-Path $modelDir ".venv\Scripts\uvicorn.exe"
        $modelProcess = Start-DevService "model-service" $ModelPort $modelExecutable `
            @("app.main:app", "--host", "127.0.0.1", "--port", [string]$ModelPort) `
            $modelDir $modelOut $modelErr $modelExitCode
        $startedAny = $true
    }

    Write-Host "Starting backend on port $BackendPort..."
    $env:LINEART_LOCAL_SERVICE_URL = "http://127.0.0.1:$ModelPort"
    $backendExecutable = Join-Path $backendDir ".venv\Scripts\uvicorn.exe"
    $backendArguments = @("app.main:app", "--host", "127.0.0.1", "--port", [string]$BackendPort)
    if ($ReloadBackend) { $backendArguments = @("app.main:app", "--reload", "--host", "127.0.0.1", "--port", [string]$BackendPort) }
    $backendProcess = Start-DevService "backend" $BackendPort $backendExecutable `
        $backendArguments `
        $backendDir $backendOut $backendErr $backendExitCode
    $startedAny = $true

    Write-Host "Starting frontend on port $FrontendPort..."
    $env:STROKE_REVIEW_API_URL = "http://127.0.0.1:$BackendPort"
    $viteScript = Join-Path $frontendDir "node_modules\vite\bin\vite.js"
    $frontendProcess = Start-DevService "frontend" $FrontendPort $nodeCommand.Source `
        @($viteScript, "--host", "127.0.0.1", "--port", [string]$FrontendPort) `
        $frontendDir $frontendOut $frontendErr $frontendExitCode
    $startedAny = $true

    if ($modelProcess) {
        Wait-ForUrl "model-service" $ModelPort "http://127.0.0.1:$ModelPort/api/health" $modelProcess $modelErr $modelExitCode
        Update-ServiceListener "model-service" $ModelPort
        Write-Host "Model service is ready."
    }
    Wait-ForUrl "backend" $BackendPort "http://127.0.0.1:$BackendPort/api/health" $backendProcess $backendErr $backendExitCode
    Update-ServiceListener "backend" $BackendPort
    Write-Host "Backend is ready."
    Wait-ForUrl "frontend" $FrontendPort "http://127.0.0.1:$FrontendPort" $frontendProcess $frontendErr $frontendExitCode
    Update-ServiceListener "frontend" $FrontendPort
    Write-Host "Frontend is ready."

    $frontendUrl = "http://127.0.0.1:$FrontendPort"
    Write-Host "Development environment started: $frontendUrl"
    Write-Host "Runtime state: $script:DevStatePath"
    Write-Host "Logs: $logDir"
    if ($SmokeTest) {
        Write-Host "Startup smoke test passed. Stopping services."
        return
    }
    if (-not $NoBrowser) { Start-Process $frontendUrl }

    if (-not $Wait) {
        $leaveServicesRunning = $true
        Write-Host "Services are running in the background; this terminal is ready to use or close."
        Write-Host "Stop:    powershell -ExecutionPolicy Bypass -File .\stop-dev.ps1"
        Write-Host "Restart: powershell -ExecutionPolicy Bypass -File .\restart-dev.ps1"
        return
    }

    Write-Host "Foreground monitoring is enabled. Press Ctrl+C to stop all project services."

    while ($true) {
        if (Test-CurrentRunStopRequested) {
            Write-Host "A stop-dev.ps1 request was received. Exiting normally."
            break
        }
        $backendProcess.Refresh()
        $frontendProcess.Refresh()
        if ($backendProcess.HasExited) {
            Throw-ServiceFailure "backend" $BackendPort $backendProcess $backendErr $backendExitCode "exited while the environment was running"
        }
        if ($frontendProcess.HasExited) {
            Throw-ServiceFailure "frontend" $FrontendPort $frontendProcess $frontendErr $frontendExitCode "exited while the environment was running"
        }
        if ($modelProcess) {
            $modelProcess.Refresh()
            if ($modelProcess.HasExited) {
                Throw-ServiceFailure "model-service" $ModelPort $modelProcess $modelErr $modelExitCode "exited while the environment was running"
            }
        }
        Start-Sleep -Seconds 1
    }
} finally {
    $externalStopRequested = Test-CurrentRunStopRequested
    if ($startedAny -and -not $externalStopRequested -and -not $leaveServicesRunning) {
        # A generated state record plus project-path validation allows this cleanup
        # to work on normal exit, startup failure and most Ctrl+C paths.
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $stopScript -Quiet
    }
}
