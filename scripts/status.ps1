# Sunucuların ve zamanlanmış görevlerin durumunu gösterir.
foreach ($name in "StockSelectionLab-Backend", "StockSelectionLab-Frontend") {
    $t = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($t) { $i = Get-ScheduledTaskInfo -TaskName $name; "$name : $($t.State) (son çalışma $($i.LastRunTime), sonuç $($i.LastTaskResult))" } else { "$name : kayıtlı değil" }
}
foreach ($port in 8000, 3000) {
    $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($c) { "port $port : AÇIK" } else { "port $port : KAPALI" }
}
try { $h = Invoke-RestMethod -TimeoutSec 5 http://localhost:8000/health; "backend: $($h.status) · kaynak $($h.data_source) · demo=$($h.is_demo)" } catch { "backend: yanıt yok" }
try { $s = Invoke-RestMethod -TimeoutSec 5 http://localhost:8000/api/v1/data/status; "veri: $($s.date_range.start)..$($s.date_range.end) · son başarılı $($s.last_success_at) · otomatik: $($s.auto_refresh.last_result)" } catch {}
