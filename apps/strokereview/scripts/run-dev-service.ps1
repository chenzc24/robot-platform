param(
    [Parameter(Mandatory = $true)]
    [string]$SpecPath
)

$ErrorActionPreference = "Stop"
# The project path contains Chinese characters. Windows PowerShell 5 otherwise
# reads UTF-8-without-BOM as the active ANSI code page and corrupts these paths.
$spec = Get-Content -LiteralPath $SpecPath -Raw -Encoding UTF8 | ConvertFrom-Json
$exitCode = 1

try {
    Set-Location -LiteralPath $spec.working_directory
    $arguments = @($spec.arguments)
    # Windows PowerShell 5 wraps any native stderr output as NativeCommandError.
    # Uvicorn writes normal INFO logs to stderr, so do not treat that stream as
    # a terminating PowerShell exception while the native service is running.
    $ErrorActionPreference = "Continue"
    & $spec.executable @arguments 1> $spec.stdout_log 2> $spec.stderr_log
    $ErrorActionPreference = "Stop"
    if ($null -ne $LASTEXITCODE) {
        $exitCode = [int]$LASTEXITCODE
    }
} catch {
    ($_ | Out-String) | Add-Content -LiteralPath $spec.stderr_log
    $exitCode = 1
} finally {
    [System.IO.File]::WriteAllText($spec.exit_code_file, [string]$exitCode)
}

exit $exitCode
