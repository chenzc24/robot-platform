param(
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $MyInvocation.MyCommand.Path)).TrimEnd('\')
. (Join-Path $projectRoot "scripts\dev-lifecycle.ps1")
Initialize-DevLifecycle $projectRoot

$state = Read-DevState
$records = @($state.services)
New-Item -ItemType Directory -Force -Path $script:DevStateDir | Out-Null
[System.IO.File]::WriteAllText(
    $script:DevStopRequestPath,
    (Get-Date).ToString("o"),
    [System.Text.UTF8Encoding]::new($false)
)
$ports = @(5173, 8000, 8010)
foreach ($record in $records) {
    if ($record.port) { $ports += [int]$record.port }
}
$ports = @($ports | Select-Object -Unique)
$stoppedAny = $false
$unsafeRecords = @()

# Prefer the recorded launcher PID because stopping its tree also closes helper
# PowerShell, Uvicorn reload workers, Vite and any children spawned beneath it.
foreach ($record in $records) {
    $candidatePids = @()
    if ($record.pid) { $candidatePids += [int]$record.pid }
    if ($record.listener_pid) { $candidatePids += [int]$record.listener_pid }
    foreach ($candidatePid in ($candidatePids | Select-Object -Unique)) {
        $process = Get-DevProcess $candidatePid
        if (-not $process) { continue }
        if (Stop-VerifiedDevProcessTree $candidatePid ([string]$record.name) -Quiet:$Quiet) {
            $stoppedAny = $true
        } else {
            $unsafeRecords += $record
        }
    }
}

# Compatibility path for instances created by older start-dev.ps1 versions or
# orphaned native children whose recorded launcher has already disappeared.
$currentOwners = @(Get-DevPortOwnersForPorts $ports)
foreach ($port in $ports) {
    foreach ($owner in @($currentOwners | Where-Object { $_.port -eq $port })) {
        if (-not $owner.belongs_to_project) {
            if (-not $Quiet) {
                Write-Host "Leaving unrelated process untouched on port $port."
                Write-Host (Format-DevPortOwner $owner "unrelated")
            }
            continue
        }
        if (Stop-VerifiedDevProcessTree ([int]$owner.pid) "project service on port $port" -Quiet:$Quiet) {
            $stoppedAny = $true
        }
    }
}

$deadline = (Get-Date).AddSeconds(8)
do {
    $remainingProjectOwners = @(
        Get-DevPortOwnersForPorts $ports | Where-Object { $_.belongs_to_project }
    )
    if ($remainingProjectOwners.Count -eq 0) { break }
    Start-Sleep -Milliseconds 250
} while ((Get-Date) -lt $deadline)

if ($remainingProjectOwners.Count -gt 0) {
    foreach ($owner in $remainingProjectOwners) {
        Write-Error ("Could not release project service port.`n" + (Format-DevPortOwner $owner "project service"))
    }
    exit 1
}

# The state file is generated runtime metadata. Once no project listener remains,
# old/reused PIDs must not be carried into the next start.
Write-DevState @($unsafeRecords | Where-Object {
    $process = Get-DevProcess ([int]$_.pid)
    $process -and (Test-DevProjectCommandLine ([string]$process.CommandLine))
})

if (-not $Quiet) {
    if ($stoppedAny) {
        Write-Host "Project development services stopped. Ports are released."
    } else {
        Write-Host "No running development services belonging to this project were found."
    }
}
