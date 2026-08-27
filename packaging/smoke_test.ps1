param([string]$ExePath = "")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $ExePath) { $ExePath = Join-Path $root "dist\知乎采集器\知乎采集器.exe" }
$process = Start-Process -FilePath ([IO.Path]::GetFullPath($ExePath)) -PassThru
try {
    Start-Sleep -Seconds 3
    if ($process.HasExited) { throw "GUI 进程提前退出，退出码 $($process.ExitCode)" }
    Write-Output "GUI process started: $($process.Id)"
} finally {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
}

