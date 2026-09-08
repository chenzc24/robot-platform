# Shared, project-scoped process lifecycle helpers for the Windows dev scripts.
# Every stop operation validates the exact process command line against the
# absolute project path before terminating that PID or its descendants.

function Initialize-DevLifecycle([string]$ProjectRoot) {
    $script:DevProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
    $script:DevStateDir = Join-Path $script:DevProjectRoot ".devstate"
    $script:DevStatePath = Join-Path $script:DevStateDir "services.json"
    $script:DevStopRequestPath = Join-Path $script:DevStateDir "stop-requested"
}

function Get-DevProcess([int]$ProcessId) {
    if ($ProcessId -le 0) { return $null }
    return Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
}

function Test-DevProjectCommandLine([string]$CommandLine) {
    if ([string]::IsNullOrWhiteSpace($CommandLine)) { return $false }
    return $CommandLine.IndexOf($script:DevProjectRoot, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
}

function Get-DevPortOwnersForPorts([int[]]$Ports) {
    $owners = @()
    $wantedPorts = @($Ports | Where-Object { $_ -gt 0 } | Select-Object -Unique)
    if ($wantedPorts.Count -eq 0) { return @() }
    # Get-NetTCPConnection is comparatively slow on Windows. Query the system
    # once and filter all project ports in memory instead of invoking it once
    # per port in every lifecycle loop.
    $listeners = @(
        Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
            Where-Object { [int]$_.LocalPort -in $wantedPorts }
    )
    $processCache = @{}
    foreach ($listener in $listeners) {
        $processId = [int]$listener.OwningProcess
        if (-not $processCache.ContainsKey($processId)) {
            $processCache[$processId] = Get-DevProcess $processId
        }
        $process = $processCache[$processId]
        $owners += [pscustomobject]@{
            port = [int]$listener.LocalPort
            pid = $processId
            name = if ($process) { [string]$process.Name } else { "(exited)" }
            command_line = if ($process -and $process.CommandLine) { [string]$process.CommandLine } else { "(command line unavailable)" }
            belongs_to_project = [bool]($process -and (Test-DevProjectCommandLine ([string]$process.CommandLine)))
        }
    }
    return @($owners)
}

function Get-DevPortOwners([int]$Port) {
    return @(Get-DevPortOwnersForPorts @($Port))
}

function Read-DevState {
    if (-not (Test-Path -LiteralPath $script:DevStatePath)) {
        return [pscustomobject]@{ version = 1; project_root = $script:DevProjectRoot; services = @() }
    }
    try {
        $state = Get-Content -LiteralPath $script:DevStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $state.services) { $state | Add-Member -NotePropertyName services -NotePropertyValue @() -Force }
        return $state
    } catch {
        Write-Warning "Ignoring invalid generated dev state file: $script:DevStatePath"
        Remove-Item -LiteralPath $script:DevStatePath -Force -ErrorAction SilentlyContinue
        return [pscustomobject]@{ version = 1; project_root = $script:DevProjectRoot; services = @() }
    }
}

function Write-DevState([object[]]$Services) {
    $records = @($Services | Where-Object { $null -ne $_ })
    if ($records.Count -eq 0) {
        Remove-Item -LiteralPath $script:DevStatePath -Force -ErrorAction SilentlyContinue
        return
    }
    New-Item -ItemType Directory -Force -Path $script:DevStateDir | Out-Null
    $state = [ordered]@{
        version = 1
        project_root = $script:DevProjectRoot
        updated_at = (Get-Date).ToString("o")
        services = $records
    }
    $json = $state | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText($script:DevStatePath, $json, [System.Text.UTF8Encoding]::new($false))
}

function Remove-StaleDevStateRecords {
    $state = Read-DevState
    $live = @()
    foreach ($record in @($state.services)) {
        $candidatePids = @()
        if ($record.pid) { $candidatePids += [int]$record.pid }
        if ($record.listener_pid) { $candidatePids += [int]$record.listener_pid }
        $belongs = $false
        foreach ($candidatePid in ($candidatePids | Select-Object -Unique)) {
            $process = Get-DevProcess $candidatePid
            if ($process -and (Test-DevProjectCommandLine ([string]$process.CommandLine))) {
                $belongs = $true
                break
            }
        }
        if ($belongs) {
            $live += $record
        } else {
            Write-Host "Removed stale state record for service '$($record.name)' (recorded PID $($record.pid))."
        }
    }
    Write-DevState $live
    return @($live)
}

function Get-DevChildProcessIds([int]$ParentProcessId) {
    $result = @()
    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $ParentProcessId" -ErrorAction SilentlyContinue)
    foreach ($child in $children) {
        $result += Get-DevChildProcessIds ([int]$child.ProcessId)
        $result += [int]$child.ProcessId
    }
    return @($result)
}

function Stop-VerifiedDevProcessTree([int]$ProcessId, [string]$ServiceName, [switch]$Quiet) {
    $process = Get-DevProcess $ProcessId
    if (-not $process) { return $true }
    $commandLine = [string]$process.CommandLine
    if (-not (Test-DevProjectCommandLine $commandLine)) {
        if (-not $Quiet) {
            Write-Warning "Skipped PID $ProcessId for '$ServiceName': command line does not contain project path '$script:DevProjectRoot'."
            Write-Warning "Process: $($process.Name) $commandLine"
        }
        return $false
    }
    if (-not $Quiet) {
        Write-Host "Stopping '$ServiceName' process tree: PID $ProcessId ($($process.Name))"
    }
    $descendants = @(Get-DevChildProcessIds $ProcessId)
    foreach ($childId in $descendants) {
        Stop-Process -Id $childId -Force -ErrorAction SilentlyContinue
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    return $true
}

function Format-DevCommandLine([string]$Executable, [string[]]$Arguments) {
    $parts = @('"' + $Executable.Replace('"', '\"') + '"')
    foreach ($argument in $Arguments) {
        $value = [string]$argument
        if ($value -match '[\s"]') {
            $parts += '"' + $value.Replace('"', '\"') + '"'
        } else {
            $parts += $value
        }
    }
    return ($parts -join ' ')
}

function Format-DevPortOwner([object]$Owner, [string]$ServiceName) {
    return @"
Service: $ServiceName
Port: $($Owner.port)
PID: $($Owner.pid)
Process: $($Owner.name)
Command line: $($Owner.command_line)
"@
}
