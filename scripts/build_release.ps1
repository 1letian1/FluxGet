param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$cachePath = Join-Path $repoRoot ".uv-cache"
$releaseRoot = Join-Path $repoRoot "dist\release"
$workRoot = Join-Path $repoRoot "build\pyinstaller"
$smokeResults = Join-Path $releaseRoot "SMOKE-RESULTS.txt"

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw "Project .venv is missing. Run uv sync --locked --group dev first."
}
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot "frontend\node_modules") -PathType Container)) {
    throw "frontend/node_modules is missing. Run npm ci in frontend first."
}

# Keep uv's cache inside the writable project workspace for reproducible local builds.
$env:UV_CACHE_DIR = $cachePath

Push-Location (Join-Path $repoRoot "frontend")
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed (exit $LASTEXITCODE)." }
} finally {
    Pop-Location
}

if (-not $SkipTests) {
    Push-Location $repoRoot
    try {
        uv run --locked -- python -m pytest -q -p no:cacheprovider
        if ($LASTEXITCODE -ne 0) { throw "Python test suite failed (exit $LASTEXITCODE)." }
    } finally {
        Pop-Location
    }
}

New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
New-Item -ItemType Directory -Path $workRoot -Force | Out-Null
if (Test-Path -LiteralPath $smokeResults) {
    $resolvedSmokeResults = [System.IO.Path]::GetFullPath($smokeResults)
    if (-not $resolvedSmokeResults.StartsWith($releaseRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a smoke record outside the release directory: $resolvedSmokeResults"
    }
    Remove-Item -LiteralPath $resolvedSmokeResults -Force
}
$oneFileDist = Join-Path $releaseRoot "onefile"
$portableDist = Join-Path $releaseRoot "portable-build"
$oneFileWork = Join-Path $workRoot "onefile"
$portableWork = Join-Path $workRoot "portable"

foreach ($path in @($oneFileDist, $portableDist, $oneFileWork, $portableWork)) {
    $fullPath = [System.IO.Path]::GetFullPath($path)
    if (-not $fullPath.StartsWith($repoRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean a path outside the repository: $fullPath"
    }
    if (Test-Path -LiteralPath $fullPath) {
        Remove-Item -LiteralPath $fullPath -Recurse -Force
    }
}

Push-Location $repoRoot
try {
    uv run --locked -- python -m PyInstaller --noconfirm --clean --distpath $oneFileDist --workpath $oneFileWork URLDownloader.spec
    if ($LASTEXITCODE -ne 0) { throw "Single-file PyInstaller build failed (exit $LASTEXITCODE)." }

    uv run --locked -- python -m PyInstaller --noconfirm --clean --distpath $portableDist --workpath $portableWork URLDownloader-portable.spec
    if ($LASTEXITCODE -ne 0) { throw "Portable PyInstaller build failed (exit $LASTEXITCODE)." }
} finally {
    Pop-Location
}

$portableSource = Join-Path $portableDist "URLDownloader-portable"
$portableTarget = Join-Path $releaseRoot "URLDownloader-portable"
$legacyPortableTarget = Join-Path $releaseRoot "UniversalDownloader-portable"
$legacyPortableZip = Join-Path $releaseRoot "UniversalDownloader-portable.zip"
if (-not (Test-Path -LiteralPath (Join-Path $oneFileDist "URLDownloader.exe") -PathType Leaf)) {
    throw "Single-file executable was not produced."
}
if (-not (Test-Path -LiteralPath (Join-Path $portableSource "URLDownloader.exe") -PathType Leaf)) {
    throw "Portable executable was not produced."
}

Copy-Item -LiteralPath (Join-Path $repoRoot "packaging\PORTABLE-README.txt") -Destination (Join-Path $portableSource "README.txt")
$portableZip = Join-Path $releaseRoot "URLDownloader-portable.zip"
foreach ($legacyPath in @($legacyPortableTarget, $legacyPortableZip)) {
    if (Test-Path -LiteralPath $legacyPath) {
        $resolvedLegacyPath = [System.IO.Path]::GetFullPath($legacyPath)
        if (-not $resolvedLegacyPath.StartsWith($releaseRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to clean a legacy artifact outside the release directory: $resolvedLegacyPath"
        }
        Remove-Item -LiteralPath $resolvedLegacyPath -Recurse -Force
    }
}
if (Test-Path -LiteralPath $portableTarget) {
    $resolvedTarget = [System.IO.Path]::GetFullPath($portableTarget)
    if (-not $resolvedTarget.StartsWith($repoRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean a path outside the repository: $resolvedTarget"
    }
    Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
}
if (Test-Path -LiteralPath $portableZip) { Remove-Item -LiteralPath $portableZip -Force }
Move-Item -LiteralPath $portableSource -Destination $portableTarget
Compress-Archive -Path $portableTarget -DestinationPath $portableZip -CompressionLevel Optimal

$python = $venvPython
& $python (Join-Path $repoRoot "scripts\verify_release.py") --release-root $releaseRoot
if ($LASTEXITCODE -ne 0) { throw "Release artifact verification failed (exit $LASTEXITCODE)." }

$gitCommit = (git -C $repoRoot rev-parse HEAD).Trim()
$workingTree = if ((git -C $repoRoot status --porcelain).Length -eq 0) { "clean" } else { "modified" }
$pythonVersion = (& $venvPython --version 2>&1 | Out-String).Trim()
$pyinstallerVersion = (& $venvPython -m PyInstaller --version 2>&1 | Out-String).Trim()
$nodeVersion = (node --version | Out-String).Trim()
$npmVersion = (npm --version | Out-String).Trim()
$pythonTestResult = if ($SkipTests) { "skipped via -SkipTests" } else { "passed (full pytest suite)" }
$releaseInfo = @(
    "Build system: $([Environment]::OSVersion.VersionString)"
    "Architecture: $([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture)"
    "Git commit: $gitCommit ($workingTree working tree)"
    "$pythonVersion"
    "PyInstaller $pyinstallerVersion"
    "Node.js $nodeVersion"
    "npm $npmVersion"
    "Python tests: $pythonTestResult"
    "Artifact structure and SHA-256 generation: passed"
    "Clean Windows 10/11 VM and application download-flow acceptance: pending"
    "WebView2 Evergreen runtime must be available on target Windows systems."
)
$releaseInfo | Set-Content -LiteralPath (Join-Path $releaseRoot "RELEASE-INFO.txt") -Encoding UTF8

Write-Host "Release artifacts are ready in $releaseRoot"
