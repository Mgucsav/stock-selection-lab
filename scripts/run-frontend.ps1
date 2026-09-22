# Frontend'i production modunda (next start) çalıştırır; .next derlemesi yoksa önce derler.
$root = Split-Path -Parent $PSScriptRoot
$web = Join-Path $root "apps\web"
Set-Location $web
$logDir = Join-Path $root "state\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = Join-Path $logDir "frontend.log"
if (-not (Test-Path (Join-Path $web ".next\BUILD_ID"))) {
    "[$(Get-Date -Format s)] derleme yok, npm run build çalışıyor" | Add-Content $log
    & npm run build 2>&1 | ForEach-Object { "$_" | Add-Content $log }
}
# Süreç çökerse 5 sn sonra yeniden başlatılır.
while ($true) {
    "[$(Get-Date -Format s)] frontend başlatılıyor" | Add-Content $log
    & npx next start -p 3000 2>&1 | ForEach-Object { "$_" | Add-Content $log }
    "[$(Get-Date -Format s)] frontend durdu (kod $LASTEXITCODE); 5 sn sonra yeniden başlatılacak" | Add-Content $log
    Start-Sleep -Seconds 5
}
