<#
.SYNOPSIS
  Yerel geliştirme ortamını hazırlar (Windows / PowerShell). Tekrar çalıştırmak güvenlidir.

.DESCRIPTION
  1. .venv yoksa Python sanal ortamı oluşturur.
  2. Backend bağımlılıklarını (requirements.txt) kurar.
  3. apps/web için npm bağımlılıklarını kurar (node_modules yoksa veya package-lock değiştiyse).
  4. .env dosyaları yoksa .env.example'dan kopyalar.
  5. data/cache ve state dizinlerini oluşturur.
#>

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== Stock Selection Lab kurulumu ==" -ForegroundColor Cyan

# --- Python sanal ortamı ---------------------------------------------------
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Python sanal ortamı oluşturuluyor (.venv)…"
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { throw "python bulunamadı. Python 3.11+ kurun ve PATH'e ekleyin." }
    & python -m venv .venv
} else {
    Write-Host ".venv mevcut, atlanıyor."
}

Write-Host "Backend bağımlılıkları kuruluyor…"
& $venvPython -m pip install --upgrade pip --quiet
& $venvPython -m pip install -r requirements.txt --quiet

# --- Frontend ----------------------------------------------------------------
$web = Join-Path $root "apps\web"
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm bulunamadı. Node.js 20+ kurun."
}
Push-Location $web
try {
    if (-not (Test-Path "node_modules")) {
        Write-Host "Frontend bağımlılıkları kuruluyor (npm install)…"
        npm install
    } else {
        Write-Host "node_modules mevcut; npm install atlanıyor (gerekirse elle çalıştırın)."
    }
} finally {
    Pop-Location
}

# --- Ortam dosyaları ---------------------------------------------------------
if (-not (Test-Path (Join-Path $root ".env"))) {
    Copy-Item (Join-Path $root ".env.example") (Join-Path $root ".env")
    Write-Host ".env oluşturuldu (.env.example kopyası)."
}
if (-not (Test-Path (Join-Path $web ".env.local"))) {
    Copy-Item (Join-Path $web ".env.example") (Join-Path $web ".env.local")
    Write-Host "apps/web/.env.local oluşturuldu."
}

# --- Dizinler ----------------------------------------------------------------
foreach ($dir in @("data\cache", "state")) {
    $path = Join-Path $root $dir
    if (-not (Test-Path $path)) { New-Item -ItemType Directory -Path $path | Out-Null }
}

Write-Host ""
Write-Host "Kurulum tamam. Çalıştırmak için: .\scripts\dev.ps1" -ForegroundColor Green
