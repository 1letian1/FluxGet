param(
    [string]$DataRoot
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$releaseRoot = Join-Path $repoRoot "dist\release"
$oneFileExe = Join-Path $releaseRoot "onefile\URLDownloader.exe"
$portableExe = Join-Path $releaseRoot "URLDownloader-portable\URLDownloader.exe"
foreach ($path in @($oneFileExe, $portableExe)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Release executable is missing: $path" }
}

if (-not $DataRoot) {
    $DataRoot = Join-Path $env:TEMP ("URLDownloader-smoke-" + [guid]::NewGuid().ToString("N"))
}
$DataRoot = [System.IO.Path]::GetFullPath($DataRoot)
New-Item -ItemType Directory -Path $DataRoot -Force | Out-Null
$previousLocalAppData = $env:LOCALAPPDATA
$results = [System.Collections.Generic.List[string]]::new()
$results.Add("System: $([Environment]::OSVersion.VersionString) / $([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture)")
$results.Add("Test data: $DataRoot")
$env:LOCALAPPDATA = $DataRoot

try {
    foreach ($case in @(@{ Name = "single-file"; Path = $oneFileExe }, @{ Name = "portable"; Path = $portableExe })) {
        for ($launch = 1; $launch -le 2; $launch++) {
            Start-Process -FilePath $case.Path | Out-Null
            $appWindow = $null
            for ($second = 0; $second -lt 30; $second++) {
                Start-Sleep -Seconds 1
                $appWindow = Get-Process | Where-Object { $_.Path -eq $case.Path -and $_.MainWindowHandle -ne 0 } | Select-Object -First 1
                if ($appWindow) { break }
            }
            if (-not $appWindow) { throw "$($case.Name) launch $launch did not create a desktop window." }

            $pattern = "127\.0\.0\.1:(\d+)\s+0\.0\.0\.0:0\s+LISTENING\s+$($appWindow.Id)$"
            $listener = netstat -ano | Select-String $pattern | Select-Object -First 1
            if (-not $listener) { throw "$($case.Name) launch $launch did not expose its loopback API listener." }
            $port = [regex]::Match($listener.Line, "127\.0\.0\.1:(\d+)").Groups[1].Value
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/v1/health" -TimeoutSec 5
            if ($health.status -ne "ok") { throw "$($case.Name) launch $launch returned an unhealthy API response." }

            $database = Join-Path $DataRoot "UniversalDownloader\downloader.db"
            if (-not (Test-Path -LiteralPath $database -PathType Leaf)) { throw "$($case.Name) launch $launch did not initialize its database." }
            if (-not $appWindow.CloseMainWindow()) { throw "$($case.Name) launch $launch did not accept a normal close request." }
            $closed = $false
            for ($second = 0; $second -lt 30; $second++) {
                Start-Sleep -Seconds 1
                if (-not (Get-Process -Id $appWindow.Id -ErrorAction SilentlyContinue)) { $closed = $true; break }
            }
            if (-not $closed) { throw "$($case.Name) launch $launch did not shut down cleanly." }
            $results.Add("$($case.Name) launch $launch`: window, API health, database, normal close passed")
        }
        $results.Add("$($case.Name) restart persistence: database present")
    }
} finally {
    $env:LOCALAPPDATA = $previousLocalAppData
}

$results.Add("Manual acceptance still required: clean Windows 10/11 systems, no Python/Node/npm, and a real UI download to completion.")
$results | Set-Content -LiteralPath (Join-Path $releaseRoot "SMOKE-RESULTS.txt") -Encoding UTF8
$results | ForEach-Object { Write-Host $_ }
Write-Host "Smoke record: $(Join-Path $releaseRoot 'SMOKE-RESULTS.txt')"
