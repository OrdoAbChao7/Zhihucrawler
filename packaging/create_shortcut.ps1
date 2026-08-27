param([string]$ExePath = "", [string]$ShortcutPath = "")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $ExePath) { $ExePath = Join-Path $root "dist\知乎采集器\知乎采集器.exe" }
$ExePath = [IO.Path]::GetFullPath($ExePath)
if (-not (Test-Path -LiteralPath $ExePath)) { throw "找不到 exe: $ExePath" }
if (-not $ShortcutPath) { $ShortcutPath = Join-Path ([Environment]::GetFolderPath("DesktopDirectory")) "知乎采集器.lnk" }
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut([IO.Path]::GetFullPath($ShortcutPath))
$shortcut.TargetPath = $ExePath
$shortcut.WorkingDirectory = Split-Path $ExePath
$shortcut.Description = "知乎采集器"
$shortcut.Save()
Write-Output ([IO.Path]::GetFullPath($ShortcutPath))

