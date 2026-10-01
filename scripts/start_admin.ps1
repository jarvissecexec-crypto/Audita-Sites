$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (!(Test-Path ".venv\Scripts\python.exe")) {
  & "$Root\scripts\setup.ps1"
}

& ".\.venv\Scripts\python.exe" -m siteaudit admin @args
