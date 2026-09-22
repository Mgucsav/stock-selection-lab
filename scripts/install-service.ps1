<#
.SYNOPSIS
  Backend ve frontend'i Windows zamanlanmış görevi olarak kaydeder: oturum açınca
  otomatik başlar, pencereye bağlı değildir, çökerse 1 dakika içinde yeniden başlar.

.DESCRIPTION
  Yönetici hakkı gerekmez (görevler mevcut kullanıcı için kaydedilir).
  Frontend production modunda çalışır (next build + next start). Kodu değiştirdiyseniz
  bu scripti yeniden çalıştırın (yeniden derler ve görevleri yeniden başlatır).

  Kaldırmak için: .\scripts\uninstall-service.ps1
  Durum için:     .\scripts\status.ps1
#>

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path (Join-Path $root ".venv\Scripts\python.exe"))) { throw "Önce .\scripts\setup.ps1 çalıştırın." }

Write-Host "Frontend derleniyor (npm run build)…" -ForegroundColor Cyan
Push-Location (Join-Path $root "apps\web")
try { npm run build | Out-Null; if ($LASTEXITCODE -ne 0) { throw "npm run build başarısız." } } finally { Pop-Location }

$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

foreach ($svc in @(
    @{ Name = "StockSelectionLab-Backend";  Script = "run-backend.ps1" },
    @{ Name = "StockSelectionLab-Frontend"; Script = "run-frontend.ps1" }
)) {
    $scriptPath = Join-Path $PSScriptRoot $svc.Script
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`"" -WorkingDirectory $root
    if (Get-ScheduledTask -TaskName $svc.Name -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $svc.Name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $svc.Name -Confirm:$false
    }
    Register-ScheduledTask -TaskName $svc.Name -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
        -Description "Stock Selection Lab $($svc.Script) — oturum açınca başlar, çökerse yeniden başlar" | Out-Null
    Write-Host "Görev kaydedildi: $($svc.Name)"
}

# Eski elle açılmış sunucuları kapat, görevleri başlat
foreach ($port in 8000, 3000) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}
Start-Sleep 2
Start-ScheduledTask -TaskName "StockSelectionLab-Backend"
Start-ScheduledTask -TaskName "StockSelectionLab-Frontend"

Write-Host "Sunucular başlatılıyor…" -ForegroundColor Cyan
$deadline = (Get-Date).AddSeconds(120)
$ok = $false
while ((Get-Date) -lt $deadline -and -not $ok) {
    Start-Sleep 3
    try {
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 http://localhost:8000/health | Out-Null
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 http://localhost:3000/ | Out-Null
        $ok = $true
    } catch {}
}
if ($ok) {
    Write-Host "Hazır: http://localhost:3000  (API: http://localhost:8000/docs)" -ForegroundColor Green
    Write-Host "Loglar: state\logs\backend.log, state\logs\frontend.log"
} else {
    Write-Host "Sunucular 2 dakika içinde yanıt vermedi; state\logs\ altındaki loglara bakın." -ForegroundColor Yellow
}
