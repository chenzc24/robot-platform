[CmdletBinding()]
param(
    [string]$OutputDirectory = "",
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$sourceRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $sourceRoot "release"
}
if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = Get-Date -Format "yyyyMMdd-HHmmss"
}

$outputRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
$packageName = "StrokeReview-source-$Version"
$stagingParent = Join-Path $outputRoot $packageName
$stagingRoot = Join-Path $stagingParent "StrokeReview-source"
$archivePath = Join-Path $outputRoot "$packageName.zip"
$hashPath = "$archivePath.sha256"

foreach ($target in @($stagingParent, $archivePath, $hashPath)) {
    if (Test-Path -LiteralPath $target) {
        throw "Refusing to overwrite existing package target: $target"
    }
}

New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null

$rootFiles = @(
    ".env.example",
    ".gitignore",
    "build-desktop.ps1",
    "compose.yaml",
    "Dockerfile",
    "package-source.ps1",
    "restart-dev.ps1",
    "start-dev.ps1",
    "stop-dev.ps1"
)
$sourceDirectories = @(
    "backend",
    "desktop",
    "examples",
    "frontend",
    "model-service",
    "packaging",
    "scripts"
)
$excludedDirectoryNames = @(
    ".cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "dist",
    "node_modules",
    "static"
)
$excludedExtensions = @(
    ".ckpt",
    ".log",
    ".onnx",
    ".pt",
    ".pth",
    ".pyc",
    ".pyo",
    ".safetensors",
    ".tsbuildinfo",
    ".zip"
)
$bundledModelFiles = @(
    "model-service/models/ControlNetHED.pth",
    "model-service/models/table5_pidinet.pth",
    "model-service/models/sk_model.pth",
    "model-service/models/sk_model2.pth"
)

foreach ($relativeFile in $rootFiles) {
    $source = Join-Path $sourceRoot $relativeFile
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required source file is missing: $relativeFile"
    }
    Copy-Item -LiteralPath $source -Destination (Join-Path $stagingRoot $relativeFile)
}

# Windows PowerShell 5 reads UTF-8 scripts without a BOM using the active ANSI
# code page. Discover root Markdown files instead of embedding non-ASCII names.
Get-ChildItem -LiteralPath $sourceRoot -File -Filter "*.md" | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $stagingRoot $_.Name)
}

foreach ($relativeDirectory in $sourceDirectories) {
    $sourceDirectory = Join-Path $sourceRoot $relativeDirectory
    if (-not (Test-Path -LiteralPath $sourceDirectory -PathType Container)) {
        throw "Required source directory is missing: $relativeDirectory"
    }
    Get-ChildItem -LiteralPath $sourceDirectory -Recurse -File | ForEach-Object {
        $relativePath = $_.FullName.Substring($sourceRoot.Length + 1)
        $segments = $relativePath -split '[\\/]'
        $containsExcludedDirectory = $false
        foreach ($segment in $segments[0..([Math]::Max(0, $segments.Length - 2))]) {
            if ($excludedDirectoryNames -contains $segment) {
                $containsExcludedDirectory = $true
                break
            }
        }
        if ($containsExcludedDirectory -or $excludedExtensions -contains $_.Extension.ToLowerInvariant()) {
            return
        }
        if ($_.Name -eq ".env") {
            return
        }
        $destination = Join-Path $stagingRoot $relativePath
        $destinationDirectory = Split-Path -Parent $destination
        New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $destination
    }
}

# A complete source delivery includes the local model weights as ordinary
# runtime assets. Dependencies still come from the locked Python projects, but
# model inference itself does not need to contact Hugging Face after setup.
$weightOutput = Join-Path $stagingRoot "model-service\models"
$weightBundler = Join-Path $sourceRoot "scripts\bundle_model_weights.py"
$modelPython = Join-Path $sourceRoot "model-service\.venv\Scripts\python.exe"
if (Test-Path -LiteralPath $modelPython -PathType Leaf) {
    & $modelPython $weightBundler --output $weightOutput
} else {
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uvCommand) {
        throw "Packaging model weights requires model-service/.venv or uv on PATH."
    }
    & $uvCommand.Source run --project (Join-Path $sourceRoot "model-service") `
        --no-default-groups python $weightBundler --output $weightOutput
}
if ($LASTEXITCODE -ne 0) { throw "Bundling source-package model weights failed." }

$forbiddenFiles = Get-ChildItem -LiteralPath $stagingRoot -Recurse -File | Where-Object {
    $relativePath = $_.FullName.Substring($stagingRoot.Length + 1).Replace('\', '/')
    $isBundledModel = $bundledModelFiles -contains $relativePath
    $_.Name -eq ".env" -or
    (($excludedExtensions -contains $_.Extension.ToLowerInvariant()) -and -not $isBundledModel) -or
    ($_.Length -gt 25MB -and -not $isBundledModel)
}
if ($forbiddenFiles) {
    $names = ($forbiddenFiles.FullName -join [Environment]::NewLine)
    throw "Forbidden or unexpectedly large files entered the source package:$([Environment]::NewLine)$names"
}

$textExtensions = @(".css", ".html", ".iss", ".js", ".json", ".md", ".mjs", ".ps1", ".py", ".toml", ".ts", ".tsx", ".txt", ".yaml", ".yml")
$secretPattern = '(sk-ws[-A-Za-z0-9_.]{20,}|DASHSCOPE_API_KEY\s*=\s*[^\s#]{8,})'
$secretMatches = Get-ChildItem -LiteralPath $stagingRoot -Recurse -File | Where-Object {
    $textExtensions -contains $_.Extension.ToLowerInvariant()
} | Select-String -Pattern $secretPattern
if ($secretMatches) {
    $files = $secretMatches.Path | Sort-Object -Unique
    throw "Possible API credential found in package files: $($files -join ', ')"
}

$manifestLines = Get-ChildItem -LiteralPath $stagingRoot -Recurse -File |
    Sort-Object FullName |
    ForEach-Object {
        $relativePath = $_.FullName.Substring($stagingRoot.Length + 1).Replace('\', '/')
        $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  $relativePath"
    }
$manifestPath = Join-Path $stagingRoot "SOURCE_MANIFEST.sha256"
[System.IO.File]::WriteAllLines($manifestPath, $manifestLines, [System.Text.UTF8Encoding]::new($false))

Compress-Archive -LiteralPath $stagingRoot -DestinationPath $archivePath -CompressionLevel Optimal
$archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
[System.IO.File]::WriteAllText($hashPath, "$archiveHash  $([System.IO.Path]::GetFileName($archivePath))`n", [System.Text.UTF8Encoding]::new($false))

$fileCount = (Get-ChildItem -LiteralPath $stagingRoot -Recurse -File).Count
$archiveSizeMb = [Math]::Round((Get-Item -LiteralPath $archivePath).Length / 1MB, 2)
Write-Output "SOURCE_PACKAGE_DIR=$stagingParent"
Write-Output "SOURCE_ARCHIVE=$archivePath"
Write-Output "SOURCE_ARCHIVE_SHA256=$archiveHash"
Write-Output "SOURCE_FILE_COUNT=$fileCount"
Write-Output "SOURCE_ARCHIVE_MB=$archiveSizeMb"
Write-Output "SOURCE_MODEL_WEIGHTS=$($bundledModelFiles.Count)"
