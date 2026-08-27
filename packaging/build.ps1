param([switch]$Clean, [string]$PythonExe = "python")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".venv"
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) { & $PythonExe -m venv $venv }
$python = Join-Path $venv "Scripts\python.exe"
& $python -m pip install --upgrade pip
& $python -m pip install -e $root pyinstaller
$localBrowsers = Join-Path $venv "Lib\site-packages\playwright\driver\package\.local-browsers"
$globalBrowsers = Join-Path $env:LOCALAPPDATA "ms-playwright"
$hasChromium = Get-ChildItem -LiteralPath $localBrowsers -Directory -Filter "chromium-*" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $hasChromium) {
    $cachedChromium = Get-ChildItem -LiteralPath $globalBrowsers -Directory -Filter "chromium-*" -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
    if ($cachedChromium) {
        New-Item -ItemType Directory -Force $localBrowsers | Out-Null
        Copy-Item -LiteralPath $cachedChromium.FullName -Destination $localBrowsers -Recurse -Force
    } else {
        $env:PLAYWRIGHT_BROWSERS_PATH = "0"
        & $python -m playwright install chromium
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
}
if (-not (Get-ChildItem -LiteralPath $localBrowsers -Directory -Filter "chromium-*" -ErrorAction SilentlyContinue)) { throw "Playwright 浏览器未安装到本地目录: $localBrowsers" }
if ($Clean) { Remove-Item -Recurse -Force (Join-Path $root "build"), (Join-Path $root "dist") -ErrorAction SilentlyContinue }
Push-Location $root
try { & $python -m PyInstaller --noconfirm (Join-Path $root "packaging\zhihu_crawler.spec") } finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$bundledBrowsers = Join-Path $root "dist\知乎采集器\_internal\playwright\driver\package\.local-browsers"
New-Item -ItemType Directory -Force $bundledBrowsers | Out-Null
Copy-Item -Path (Join-Path $localBrowsers "*") -Destination $bundledBrowsers -Recurse -Force
if (-not (Get-ChildItem -LiteralPath $bundledBrowsers -Recurse -File -ErrorAction SilentlyContinue)) { throw "发布目录缺少 Chromium 浏览器文件" }
$portableDir = Join-Path $root "dist\知乎采集器"
Copy-Item -LiteralPath (Join-Path $root "packaging\PORTABLE_README.txt") -Destination (Join-Path $portableDir "使用说明.txt") -Force
$portableZip = Join-Path $root "dist\知乎采集器-便携版.zip"
if (Test-Path -LiteralPath $portableZip) { Remove-Item -LiteralPath $portableZip -Force }
Compress-Archive -Path (Join-Path $portableDir "*") -DestinationPath $portableZip -CompressionLevel Optimal
Write-Output (Join-Path $root "dist\知乎采集器\知乎采集器.exe")
Write-Output $portableZip
