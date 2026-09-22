<#
.SYNOPSIS
  Backend'i (FastAPI, localhost:8000) ve frontend'i (Next.js, localhost:3000) birlikte başlatır.

.DESCRIPTION
  Backend ayrı bir PowerShell penceresinde uvicorn ile açılır; frontend bu pencerede
  çalışır. Frontend kapatıldığında backend penceresi de kapatılır. Portlar doluysa
  uyarı verir ve devam etmez.

.PARAMETER BackendOnly
  Yalnızca backend'i bu pencerede başlatır.

.PARAMETER FrontendOnly
  Yalnızca frontend'i bu pencerede başlatır.

.PARAMETER AccessLog
  Backend'in her HTTP isteğini loglamasını açar (varsayılan kapalı; yalnızca uyarı/hata görünür).
#>

param(
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [switch]$AccessLog
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Sanal ortam yok. Önce .\scripts\setup.ps1 çalıştırın."
}

function Test-PortFree([int]$port) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    return ($null -eq $listener)
}

$logFlag = if ($AccessLog) { "" } else { "--no-access-log" }
$backendCmd = "& '$venvPython' -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload $logFlag"

if ($BackendOnly) {
    Invoke-Expression $backendCmd
    return
}

$backendProcess = $null
if (-not $FrontendOnly) {
    if (-not (Test-PortFree 8000)) {
        Write-Host "Port 8000 kullanımda; backend zaten çalışıyor olabilir. Yeni backend başlatılmadı." -ForegroundColor Yellow
    } else {
        Write-Host "Backend başlatılıyor: http://localhost:8000 (simge durumunda ayrı pencere; hatalar orada görünür)" -ForegroundColor Cyan
        $backendProcess = Start-Process powershell -WindowStyle Minimized -ArgumentList @(
            "-NoExit", "-ExecutionPolicy", "Bypass", "-Command",
            "Set-Location '$root'; $backendCmd"
        ) -PassThru
    }
}

if (-not (Test-PortFree 3000)) {
    Write-Host "Port 3000 kullanımda; frontend zaten çalışıyor olabilir." -ForegroundColor Yellow
    return
}

Write-Host "Frontend başlatılıyor: http://localhost:3000" -ForegroundColor Cyan
Push-Location (Join-Path $root "apps\web")
try {
    npm run dev
} finally {
    Pop-Location
    if ($backendProcess -and -not $backendProcess.HasExited) {
        Write-Host "Backend penceresi kapatılıyor…"
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
