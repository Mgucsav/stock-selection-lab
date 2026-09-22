# Backend'i (FastAPI/uvicorn) günlük dosyaya loglayarak çalıştırır. Zamanlanmış görev tarafından kullanılır.
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$logDir = Join-Path $root "state\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = Join-Path $logDir "backend.log"
$python = Join-Path $root ".venv\Scripts\python.exe"
# Süreç çökerse 5 sn sonra yeniden başlatılır (Görev Zamanlayıcı yalnızca başlatma hatasında yeniden dener).
while ($true) {
    "[$(Get-Date -Format s)] backend başlatılıyor" | Add-Content $log
    & $python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --no-access-log 2>&1 | ForEach-Object { "$_" | Add-Content $log }
    "[$(Get-Date -Format s)] backend durdu (kod $LASTEXITCODE); 5 sn sonra yeniden başlatılacak" | Add-Content $log
    Start-Sleep -Seconds 5
}
