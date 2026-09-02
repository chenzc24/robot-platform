param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("start", "stop", "status")]
    [string]$Action,

    [string]$MaixCamHost = "maixcam-6c7d.local"
)

$ErrorActionPreference = "Stop"
$workspace = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$mediaMtxDir = Join-Path $workspace ".tools\mediamtx-v1.20.0"
$mediaMtxExecutable = Join-Path $mediaMtxDir "mediamtx.exe"
$ffmpegRoot = Join-Path $workspace ".tools\ffmpeg-9.0.1"
$config = Join-Path $workspace "config\mediamtx.local.yml"
$stateDir = Join-Path $workspace ".device-cache\mediamtx"
$mediaMtxPidFile = Join-Path $stateDir "mediamtx.pid"
$ffmpegPidFile = Join-Path $stateDir "ffmpeg.pid"
$logDir = Join-Path $workspace "logs\mediamtx"
$mediaMtxStdoutLog = Join-Path $logDir "stdout.log"
$mediaMtxStderrLog = Join-Path $logDir "stderr.log"
$ffmpegStdoutLog = Join-Path $logDir "ffmpeg-stdout.log"
$ffmpegStderrLog = Join-Path $logDir "ffmpeg-stderr.log"

function Find-FfmpegExecutable {
    if (-not (Test-Path -LiteralPath $ffmpegRoot)) {
        return $null
    }
    return Get-ChildItem -LiteralPath $ffmpegRoot -Filter "ffmpeg.exe" -File -Recurse |
        Select-Object -ExpandProperty FullName -First 1
}

function Get-ManagedProcess {
    param(
        [string]$PidFile,
        [string]$ExpectedExecutable
    )

    if (-not (Test-Path -LiteralPath $PidFile)) {
        return $null
    }
    $managedProcessId = 0
    if (-not [int]::TryParse((Get-Content -Raw -LiteralPath $PidFile).Trim(), [ref]$managedProcessId)) {
        Remove-Item -LiteralPath $PidFile -Force
        return $null
    }
    $process = Get-Process -Id $managedProcessId -ErrorAction SilentlyContinue
    if (-not $process) {
        Remove-Item -LiteralPath $PidFile -Force
        return $null
    }
    try {
        $actualExecutable = $process.Path
    }
    catch {
        return $null
    }
    if (-not $actualExecutable -or
        -not [string]::Equals(
            [System.IO.Path]::GetFullPath($actualExecutable),
            [System.IO.Path]::GetFullPath($ExpectedExecutable),
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        Write-Warning "Ignoring stale PID file $PidFile; PID $managedProcessId belongs to another executable"
        Remove-Item -LiteralPath $PidFile -Force
        return $null
    }
    return $process
}

function Stop-ManagedProcess {
    param(
        [string]$Name,
        [string]$PidFile,
        [string]$ExpectedExecutable
    )

    $process = Get-ManagedProcess -PidFile $PidFile -ExpectedExecutable $ExpectedExecutable
    if (-not $process) {
        Write-Output "${Name}_NOT_RUNNING"
        return
    }
    Stop-Process -Id $process.Id
    Wait-Process -Id $process.Id -Timeout 10 -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    Write-Output "${Name}_STOPPED pid=$($process.Id)"
}

function Test-RelayReady {
    try {
        $response = Invoke-RestMethod `
            -Uri "http://127.0.0.1:9997/v3/paths/list" `
            -Method Get `
            -TimeoutSec 2
    }
    catch {
        return $false
    }

    $path = $response.items |
        Where-Object { $_.name -eq "maixcam" } |
        Select-Object -First 1
    return [bool]($path -and $path.ready -and $path.online)
}

function Wait-RelayReady {
    param(
        [System.Diagnostics.Process]$MediaMtxProcess,
        [System.Diagnostics.Process]$FfmpegProcess,
        [int]$TimeoutSeconds = 20
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($MediaMtxProcess.HasExited) {
            throw "MediaMTX exited before the relay path became ready"
        }
        if ($FfmpegProcess.HasExited) {
            throw "FFmpeg exited before the relay path became ready"
        }
        if (Test-RelayReady) {
            return
        }
        Start-Sleep -Milliseconds 250
    }
    throw "Video relay processes started, but path maixcam did not become ready within ${TimeoutSeconds}s"
}

$ffmpegExecutable = Find-FfmpegExecutable

switch ($Action) {
    "start" {
        if (-not (Test-Path -LiteralPath $mediaMtxExecutable)) {
            throw "MediaMTX executable missing: $mediaMtxExecutable"
        }
        if (-not $ffmpegExecutable) {
            throw "FFmpeg executable missing below: $ffmpegRoot"
        }
        if (-not (Test-Path -LiteralPath $config)) {
            throw "Local config missing: copy config/mediamtx.example.yml to config/mediamtx.local.yml"
        }

        $mediaMtxProcess = Get-ManagedProcess `
            -PidFile $mediaMtxPidFile `
            -ExpectedExecutable $mediaMtxExecutable
        $ffmpegProcess = Get-ManagedProcess `
            -PidFile $ffmpegPidFile `
            -ExpectedExecutable $ffmpegExecutable
        if ($mediaMtxProcess -and $ffmpegProcess) {
            Wait-RelayReady `
                -MediaMtxProcess $mediaMtxProcess `
                -FfmpegProcess $ffmpegProcess
            Write-Output "VIDEO_RELAY_ALREADY_RUNNING mediamtx_pid=$($mediaMtxProcess.Id) ffmpeg_pid=$($ffmpegProcess.Id)"
            exit 0
        }
        if ($mediaMtxProcess -or $ffmpegProcess) {
            throw "Video relay is only partially running; run -Action stop before starting it again"
        }

        $cameraAddress = Resolve-DnsName $MaixCamHost -Type A -ErrorAction Stop |
            Select-Object -ExpandProperty IPAddress -First 1
        if (-not $cameraAddress) {
            throw "No IPv4 address found for $MaixCamHost"
        }

        New-Item -ItemType Directory -Force -Path $stateDir, $logDir | Out-Null
        try {
            $mediaMtxProcess = Start-Process `
                -FilePath $mediaMtxExecutable `
                -ArgumentList ('"{0}"' -f $config) `
                -WorkingDirectory $mediaMtxDir `
                -WindowStyle Hidden `
                -RedirectStandardOutput $mediaMtxStdoutLog `
                -RedirectStandardError $mediaMtxStderrLog `
                -PassThru
            Set-Content -LiteralPath $mediaMtxPidFile -Value $mediaMtxProcess.Id
            Start-Sleep -Seconds 2
            if ($mediaMtxProcess.HasExited) {
                Get-Content -LiteralPath $mediaMtxStdoutLog, $mediaMtxStderrLog -ErrorAction SilentlyContinue
                throw "MediaMTX exited during startup"
            }

            $sourceUrl = "rtsp://${cameraAddress}:8554/live"
            $publishUrl = "rtsp://127.0.0.1:8555/maixcam"
            $ffmpegArguments = @(
                "-hide_banner",
                "-loglevel", "info",
                "-nostdin",
                "-rtsp_transport", "tcp",
                "-i", $sourceUrl,
                "-map", "0:v:0",
                "-an",
                "-c:v", "copy",
                "-f", "rtsp",
                "-rtsp_transport", "tcp",
                "-muxdelay", "0",
                $publishUrl
            )
            $ffmpegProcess = Start-Process `
                -FilePath $ffmpegExecutable `
                -ArgumentList $ffmpegArguments `
                -WorkingDirectory (Split-Path -Parent $ffmpegExecutable) `
                -WindowStyle Hidden `
                -RedirectStandardOutput $ffmpegStdoutLog `
                -RedirectStandardError $ffmpegStderrLog `
                -PassThru
            Set-Content -LiteralPath $ffmpegPidFile -Value $ffmpegProcess.Id
            Wait-RelayReady `
                -MediaMtxProcess $mediaMtxProcess `
                -FfmpegProcess $ffmpegProcess
            Write-Output "VIDEO_RELAY_STARTED mediamtx_pid=$($mediaMtxProcess.Id) ffmpeg_pid=$($ffmpegProcess.Id) source=$cameraAddress"
        }
        catch {
            if ($ffmpegProcess -and -not $ffmpegProcess.HasExited) {
                Stop-Process -Id $ffmpegProcess.Id -ErrorAction SilentlyContinue
            }
            if ($mediaMtxProcess -and -not $mediaMtxProcess.HasExited) {
                Stop-Process -Id $mediaMtxProcess.Id -ErrorAction SilentlyContinue
            }
            Remove-Item -LiteralPath $ffmpegPidFile, $mediaMtxPidFile -Force -ErrorAction SilentlyContinue
            throw
        }
    }
    "stop" {
        if ($ffmpegExecutable) {
            Stop-ManagedProcess -Name "FFMPEG" -PidFile $ffmpegPidFile -ExpectedExecutable $ffmpegExecutable
        }
        else {
            Write-Output "FFMPEG_NOT_RUNNING"
        }
        Stop-ManagedProcess -Name "MEDIAMTX" -PidFile $mediaMtxPidFile -ExpectedExecutable $mediaMtxExecutable
    }
    "status" {
        $mediaMtxProcess = Get-ManagedProcess `
            -PidFile $mediaMtxPidFile `
            -ExpectedExecutable $mediaMtxExecutable
        if ($ffmpegExecutable) {
            $ffmpegProcess = Get-ManagedProcess `
                -PidFile $ffmpegPidFile `
                -ExpectedExecutable $ffmpegExecutable
        }
        else {
            $ffmpegProcess = $null
        }
        if ($mediaMtxProcess -and $ffmpegProcess -and (Test-RelayReady)) {
            Write-Output "VIDEO_RELAY_RUNNING mediamtx_pid=$($mediaMtxProcess.Id) ffmpeg_pid=$($ffmpegProcess.Id)"
            exit 0
        }
        if ($mediaMtxProcess -and $ffmpegProcess) {
            Write-Output "VIDEO_RELAY_NOT_READY mediamtx_pid=$($mediaMtxProcess.Id) ffmpeg_pid=$($ffmpegProcess.Id)"
            exit 1
        }
        Write-Output "VIDEO_RELAY_NOT_RUNNING mediamtx=$([bool]$mediaMtxProcess) ffmpeg=$([bool]$ffmpegProcess)"
        exit 1
    }
}
