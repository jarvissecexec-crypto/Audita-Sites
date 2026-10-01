$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (!(Test-Path ".venv\Scripts\python.exe")) {
  Write-Host "==> Criando ambiente virtual local"
  py -3 -m venv .venv
}

Write-Host "==> Atualizando pip"
.\.venv\Scripts\python.exe -m pip install --upgrade pip

Write-Host "==> Instalando dependências"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest

Write-Host "==> Pronto"
Write-Host "Para abrir painel: .\scripts\start_admin.ps1"
