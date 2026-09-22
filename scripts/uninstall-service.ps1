# Zamanlanmış görevleri durdurur ve kaldırır (install-service.ps1'in tersi).
foreach ($name in "StockSelectionLab-Backend", "StockSelectionLab-Frontend") {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "Kaldırıldı: $name"
    }
}
foreach ($port in 8000, 3000) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}
Write-Host "Sunucular durduruldu."
