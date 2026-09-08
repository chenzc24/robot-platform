param(
    [switch]$SkipModels,
    [switch]$SkipInstaller,
    [switch]$NoZip
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $projectRoot "backend"
$frontendDir = Join-Path $projectRoot "frontend"
$modelDir = Join-Path $projectRoot "model-service"
$staticDir = Join-Path $backendDir "static"
$buildDir = Join-Path $projectRoot ".desktop-build"
$releaseDir = Join-Path $projectRoot "release"
$portableDir = Join-Path $releaseDir "StrokeReviewDesktop"

function Assert-ChildPath([string]$Candidate, [string]$Parent) {
    $resolvedCandidate = [System.IO.Path]::GetFullPath($Candidate)
    $resolvedParent = [System.IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    if (-not $resolvedCandidate.StartsWith($resolvedParent, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe generated path outside project: $resolvedCandidate"
    }
}

$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $uvCommand) { throw "uv was not found on PATH." }
if (-not $npmCommand) { throw "npm was not found. Install Node.js LTS and reopen PowerShell." }

Assert-ChildPath $staticDir $projectRoot
Assert-ChildPath $buildDir $projectRoot
Assert-ChildPath $releaseDir $projectRoot

if (Test-Path $buildDir) { Remove-Item -LiteralPath $buildDir -Recurse -Force }
if (Test-Path $portableDir) { Remove-Item -LiteralPath $portableDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $buildDir, $releaseDir | Out-Null

Write-Host "[1/6] Building the React frontend..."
$frontendDistDir = Join-Path $frontendDir "dist"
$viteScript = Join-Path $frontendDir "node_modules\vite\bin\vite.js"
$frontendBuildDir = $frontendDir
if (-not (Test-Path $viteScript)) {
    $frontendBuildDir = Join-Path $buildDir "frontend-source"
    New-Item -ItemType Directory -Force -Path $frontendBuildDir | Out-Null
    Get-ChildItem -LiteralPath $frontendDir -Force |
        Where-Object { $_.Name -notin @("node_modules", "dist") } |
        Copy-Item -Destination $frontendBuildDir -Recurse -Force
    $frontendDistDir = Join-Path $frontendBuildDir "dist"
}
Push-Location $frontendBuildDir
try {
    if (-not (Test-Path (Join-Path $frontendBuildDir "node_modules\vite\bin\vite.js"))) {
        Write-Host "Installing frontend dependencies in an isolated build folder..."
        & $npmCommand.Source ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
    } else {
        Write-Host "Reusing the existing frontend dependencies."
    }
    & $npmCommand.Source run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
} finally {
    Pop-Location
}

Write-Host "[2/6] Preparing frontend static files..."
if (Test-Path $staticDir) { Remove-Item -LiteralPath $staticDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $staticDir | Out-Null
Copy-Item -Path (Join-Path $frontendDistDir "*") -Destination $staticDir -Recurse -Force

Write-Host "[3/6] Building the desktop application..."
$previousUvEnvironment = $env:UV_PROJECT_ENVIRONMENT
$env:UV_PROJECT_ENVIRONMENT = Join-Path $buildDir "backend-venv"
try {
    & $uvCommand.Source sync --project $backendDir --python 3.12 --no-default-groups --group desktop
    if ($LASTEXITCODE -ne 0) { throw "Backend desktop dependencies failed to install." }
    & $uvCommand.Source run --project $backendDir --no-default-groups --group desktop pyinstaller `
        --noconfirm --clean `
        --distpath (Join-Path $buildDir "desktop-dist") `
        --workpath (Join-Path $buildDir "desktop-work") `
        (Join-Path $projectRoot "packaging\windows\desktop.spec")
    if ($LASTEXITCODE -ne 0) { throw "Desktop application build failed." }
} finally {
    $env:UV_PROJECT_ENVIRONMENT = $previousUvEnvironment
}
Copy-Item -LiteralPath (Join-Path $buildDir "desktop-dist\StrokeReview") -Destination $portableDir -Recurse -Force

if (-not $SkipModels) {
    Write-Host "[4/6] Building the optional CPU model companion (this can take a long time)..."
    $previousUvEnvironment = $env:UV_PROJECT_ENVIRONMENT
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $buildDir "model-venv"
    $bundledWeightsDir = Join-Path $buildDir "model-weights"
    $modelRepository = if ([string]::IsNullOrWhiteSpace($env:LINEART_MODEL_REPOSITORY)) {
        "lllyasviel/Annotators"
    } else {
        $env:LINEART_MODEL_REPOSITORY
    }
    try {
        & $uvCommand.Source sync --project $modelDir --python 3.12 --no-default-groups --group desktop
        if ($LASTEXITCODE -ne 0) { throw "Model desktop dependencies failed to install." }
        & $uvCommand.Source run --project $modelDir --no-default-groups --group desktop pyinstaller `
            --noconfirm --clean `
            --distpath (Join-Path $buildDir "model-dist") `
            --workpath (Join-Path $buildDir "model-work") `
            (Join-Path $projectRoot "packaging\windows\model-service.spec")
        if ($LASTEXITCODE -ne 0) { throw "Model companion build failed." }
        & $uvCommand.Source run --project $modelDir --no-default-groups --group desktop python `
            (Join-Path $projectRoot "scripts\bundle_model_weights.py") `
            --repository $modelRepository `
            --output $bundledWeightsDir
        if ($LASTEXITCODE -ne 0) { throw "Bundling offline model weights failed." }
    } finally {
        $env:UV_PROJECT_ENVIRONMENT = $previousUvEnvironment
    }
    $portableModelDir = Join-Path $portableDir "model-service"
    New-Item -ItemType Directory -Force -Path $portableModelDir | Out-Null
    Copy-Item -Path (Join-Path $buildDir "model-dist\StrokeModelService\*") -Destination $portableModelDir -Recurse -Force
    Copy-Item -LiteralPath $bundledWeightsDir -Destination (Join-Path $portableModelDir "models") -Recurse -Force
} else {
    Write-Host "[4/6] Skipping the CPU model companion. Classic and SVG remain available."
}

Write-Host "[5/6] Running packaged startup smoke test..."
$smokeArguments = @("--smoke-test")
if ($SkipModels) { $smokeArguments += "--no-model" }
$smoke = Start-Process -FilePath (Join-Path $portableDir "StrokeReview.exe") `
    -ArgumentList $smokeArguments -PassThru -Wait -WindowStyle Hidden
if ($smoke.ExitCode -ne 0) { throw "Packaged application smoke test failed with exit code $($smoke.ExitCode)." }

Write-Host "[6/6] Creating delivery artifacts..."
if (-not $NoZip) {
    $zipPath = Join-Path $releaseDir "StrokeReviewDesktop-portable.zip"
    if (Test-Path $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    Compress-Archive -Path $portableDir -DestinationPath $zipPath -CompressionLevel Optimal
    Write-Host "Portable ZIP: $zipPath"
}

if (-not $SkipInstaller) {
    $iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if (-not $iscc) {
        $defaultIscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
        if (Test-Path $defaultIscc) { $iscc = Get-Item $defaultIscc }
    }
    if ($iscc) {
        & $iscc.Source (Join-Path $projectRoot "packaging\windows\StrokeReview.iss")
        if ($LASTEXITCODE -ne 0) { throw "Installer build failed." }
    } else {
        Write-Warning "Inno Setup 6 was not found. Portable version was built; installer was skipped."
    }
}

Write-Host "Desktop delivery ready: $portableDir\StrokeReview.exe"
