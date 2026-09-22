# Stock Selection Lab

Bu depo, hisse seçimi problemini küçük ve denetlenebilir adımlarla öğrenmek için
hazırlanmış bir Python çalışmasıdır. 1. ve 2. Gün modülleri sentetik veriyle
temel yapı taşlarını kurar; bunların üzerine **BIST 100 için fpfs (bulanık
parametreli bulanık esnek küme) tabanlı hisse sıralaması ve model portföy takibi**
yapan yerel bir web uygulaması eklenmiştir.

**Eğitim ve araştırma amaçlıdır; yatırım tavsiyesi değildir.** Uygulama gerçek
emir göndermez, aracı kurum hesabına bağlanmaz, fiyat tahmini veya garantili
getiri sunmaz. Bütün çıktılar model portföy simülasyonudur.

## Hızlı başlangıç (Windows / PowerShell)

```powershell
.\scripts\setup.ps1   # .venv, pip, npm, .env dosyaları (tekrar çalıştırmak güvenlidir)
.\scripts\dev.ps1     # backend http://localhost:8000 + frontend http://localhost:3000
```

İlk açılışta cache boştur; uygulama **deterministik demo verisiyle** (açıkça
“DEMO MODU” etiketli) açılır. Canlı veri için **Veri Sağlığı → Canlı veriyi
yenile (yfinance)** düğmesini kullanın (~1 dk, 100 sembol + XU100).

Elle çalıştırma:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --port 8000 --reload
cd apps\web; npm run dev
```

Testler:

```powershell
.\.venv\Scripts\python.exe -m pytest -q          # backend (mevcut 48 + yeni 72 test)
cd apps\web; npm run typecheck; npm test; npm run lint
```

> Not: Bu makinede depodaki `.pytest-tmp` klasörü erişim izni nedeniyle
> silinemiyorsa `--basetemp` ile başka bir geçici dizin verin:
> `python -m pytest -q --basetemp=$env:TEMP\ssl-pytest`.

## Mimari

```text
apps/web/                 Next.js (App Router, TypeScript strict, Tailwind, Recharts, Vitest)
api/                      FastAPI uygulama katmanı (main.py, schemas.py)
src/
  day01_baseline.py       1. Gün: getiri, drawdown, min-max normalizasyon (yeniden kullanılır)
  day02_data_pipeline.py  2. Gün: OHLCV sözleşmesi, clean_prices, kalite raporu (yeniden kullanılır)
  stock_selection/
    settings.py           ortam değişkenleri (SSL_*), .env
    universe.py           config/bist100_symbols.csv okuma/doğrulama
    demo.py               deterministik sentetik demo verisi (source="demo")
    application.py        servisler: MarketDataService, RankingService, PortfolioService
    data/
      providers/base.py   MarketDataProvider protokolü, FetchOutcome (ok / no_data / provider_error)
      providers/yahoo.py  YahooFinanceProvider: batch, retry + üstel geri çekilme, actions=True
      providers/fake.py   ağ kullanmayan test/demo sağlayıcısı
      cleaning.py         day02.clean_prices + temettü bağlama + stale/eksik gün kontrolü
      cache.py            PriceStore arayüzü + ParquetPriceCache (ham/temiz/benchmark)
    features/criteria.py  getiri, aşağı yönlü risk, temettü verimi, likidite proxy
    fuzzy/membership.py   üyelik dönüşümleri, sabit sütun politikası, fail-fast doğrulama
    fuzzy/fpfs.py         fpfs matrisi (sıfırıncı satır = μ), CCE10, FSS, DRF, DMF
    fuzzy/profiles.py     yatırımcı profilleri (config/profiles.json ile ezilebilir)
    portfolio/builder.py  üç model portföy, tavan ve yeniden dağıtım
    portfolio/stats.py    tarihsel volatilite / maksimum düşüş (day01 fonksiyonlarıyla)
    tracking/snapshot.py  giriş fiyatı (bir sonraki işlem günü), tam lot, nakit
    tracking/valuation.py günlük değer serisi, metrikler, BIST 100 karşılaştırması
    repositories/base.py  repository Protocol'leri (veritabanından bağımsız)
    repositories/sqlite.py SQLAlchemy uygulaması (SQLite MVP; JSON sütunlar PostgreSQL uyumlu)
config/
  bist100_symbols.csv     evren: symbol,name,sector,effective_from,effective_to,source
  profiles.json           profil ağırlıkları, hisse sayısı, tavan, ağırlık şeması
data/cache/  data/demo/  Parquet cache'ler (Git'e eklenmez)
state/                    SQLite veritabanı (Git'e eklenmez)
scripts/setup.ps1, dev.ps1
tests/                    pytest (fixtures/seminar_example.py: seminerin 7 hisselik örneği)
```

Veri akışı:

```text
provider.fetch_daily → ham parquet → day02.clean_prices (+temettü, stale) → temiz parquet
→ compute_criteria(as_of) → build_memberships → evaluate_fpfs(μ) → ScoreRun (SQLite)
→ build_candidate (ağırlıklar) → select → snapshot (lot, nakit) → valuation_series
```

fpfs **seçer ve sıralar**; portföy ağırlıklandırma **ayrı bir uygulama
katmanıdır**. Bu ayrım kodda (`fuzzy/` vs `portfolio/`) ve arayüzde korunur.

## Akademik model

Kriterler ve sütun sırası sözleşmesi: `return, dividend, liquidity, risk`.

```text
r_it            = adj_close_t / adj_close_{t-1} - 1
mean_return_i   = mean(r_it)                              (dönemsel; üyelikte kullanılır)
downside_risk_i = mean(max(0, mean_return_i - r_it))      (yarı-mutlak sapma, cost)
dividend_yield  = son 12 ay nakit temettü / referans kapanış
liquidity_proxy = median(close * volume)                  (TL hacim; gerçek turnover değil)

benefit_membership = (x - min_x) / (max_x - min_x)        → return
cost_membership    = 1 - (x - min_x) / (max_x - min_x)    → risk
max_division       = x / max_x                            → dividend, liquidity

fpfs matrisi: a_0j = mu_j, a_ij = üyelik
CCE10:  score_i = (1/n) Σ_j mu_j a_ij      (ana sonuç)
FSS:    fss_i   = (1/n) Σ_j a_ij           (ağırlıksız baseline)
DRF:    drf_i   = Σ_j mu_j a_ij
DMF:    C_ik = Σ_j mu_j (a_ij - a_kj),  D_i = Σ_k C_ik
```

Sabit sütunda sessiz bölme yapılmaz (`neutral` = 0.5 / `zero` / `raise`
politikası + uyarı). NaN, sonsuz ve `[0,1]` dışı üyelikte hata fırlatılır.
Kullanılan normalizasyon yöntemi ve politika her `score_run` kaydında saklanır.

Seminer örneği (`tests/fixtures/seminar_example.py`) Dengeli profil ile FSS
sırasını `C29 > C21 > C9 > C4 > C7 > C16 > C14`, fpfs sırasını
`C29 > C21 > C9 > C7 > C4 > C16 > C14` ve skorları (±0.001) yeniden üretir.
Seminer sunumunda ham üyelik matrisi verilmediği için fixture'daki değerler bu
sonuçları üreten bir **yeniden yapılandırmadır**; seminerin orijinal verisi değildir.

### Yatırımcı profilleri (başlangıç/demo parametreleri)

| Profil | return | dividend | liquidity | risk | Portföy | Tavan | Ağırlık şeması |
|---|---:|---:|---:|---:|---:|---:|---|
| Muhafazakâr | 0.55 | 0.75 | 0.80 | 1.00 | ilk 15 | %10 | 1 / downside_risk |
| Dengeli (seminer) | 0.80 | 0.60 | 0.60 | 0.80 | ilk 10 | %15 | %50 skor payı + %50 ters risk payı |
| Agresif | 1.00 | 0.35 | 0.55 | 0.55 | ilk 7 | %20 | fpfs skoruyla orantılı |

Bunlar akademik olarak doğrulanmış evrensel profiller değildir;
`config/profiles.json` ile düzenlenebilir, arayüzde slider ile değiştirilebilir.

### Portföy takibi

```text
quantity_i        = floor(capital * w_i / entry_price_i)   (BIST tam lot; artan tutar nakit)
portfolio_value_t = cash + Σ quantity_i * price_it
total_return_t    = portfolio_value_t / capital - 1
```

Look-ahead engeli: karar tarihindeki sıralama yalnızca o tarihe kadar olan veriyi
kullanır; giriş fiyatı **bir sonraki işlem gününün açılışı**dır (yoksa kapanış).
O gün henüz oluşmamışsa portföy `pending` kalır ve arayüzde açıkça gösterilir.
Seçim anında `score_run_id`, karar/veri tarihi, profil, model sürümü, hisseler,
hedef ağırlıklar, giriş fiyatları, lotlar ve nakit değiştirilemez snapshot olarak
SQLite'a yazılır.

## Gün içi takip ve hisse paneli (gecikmeli fiyat)

Yahoo Finance BIST kotasyonlarını **≈15 dakika gecikmeli** verir; tick akışı yoktur.
Uygulama bunu şöyle kullanır:

- **Piyasa** (`/market`): 100 hissenin son fiyatı, günlük değişim, açılış/yüksek/düşük, hacim; 60 sn'de bir yenilenir.
- **Hisse paneli** (`/stocks/THYAO.IS`): 1 dk (7 gün), 5 dk / 15 dk (60 gün), 1 saat (730 gün) ve günlük (3 yıl) grafik;
  temettü listesi, 52 hafta aralığı, fpfs üyelikleri.
- **Gün içi takip** (Panel ve portföy detayı): pozisyonlar × son fiyat + nakit → anlık değer, bugünkü değişim
  (önceki kapanışa göre), girişten bu yana K/Z. Resmî gün sonu değerleme ayrı tutulur.
- Son fiyatlar 60 sn, gün içi barlar 5 dk TTL ile cache'lenir (oran sınırı için).
- **Günlük veri otomatik yenilenir:** backend açılışta ve her saat başı kontrol eder; veri demo ise veya son başarılı
  güncelleme `SSL_AUTO_REFRESH_HOURS` (varsayılan 20) saatten eskiyse arka planda `refresh` çalıştırır. Durum Veri Sağlığı'nda görünür; `0` ile kapatılır.
- Yahoo günlük seride son günleri eksik/NaN verirse `data/refresh` bu günleri **saatlik barlardan günlük OHLCV** olarak türetir ve uyarı yazar.
- Demo modunda canlı fiyat devre dışıdır; demo veriyle kurulan portföy canlı veriyle aktive edilmez/değerlenmez (kaynak karışmaz).

Endpointler: `GET /api/v1/quotes?symbols=`, `GET /api/v1/stocks/{symbol}`, `GET /api/v1/stocks/{symbol}/history?interval=1d|1h|15m|5m|1m`,
`GET /api/v1/portfolios/{id}/live`.

## API

```text
GET  /health
GET  /api/v1/universe             POST /api/v1/universe (CSV metniyle evreni güncelle)
GET  /api/v1/profiles
GET  /api/v1/data/status          POST /api/v1/data/refresh
POST /api/v1/rankings/run         GET  /api/v1/rankings/latest?profile_id=
GET  /api/v1/rankings/{score_run_id}
POST /api/v1/portfolios/generate  {capital, decision_date?}
POST /api/v1/portfolios/{candidate_id}/select  {initial_capital?, name?}
GET  /api/v1/portfolios           GET /api/v1/portfolios/{portfolio_id}
POST /api/v1/portfolios/{portfolio_id}/revalue
```

`rankings/run` gövdesinde `weights` verilirse özel ağırlıklar kullanılır;
`persist=false` ile önizleme (kayıtsız) alınır. Hatalar `{"detail": "..."}`
biçiminde Türkçe döner (400 doğrulama, 404 bulunamadı, 503 veri alınamadı).

## BIST 100 evreni

`config/bist100_symbols.csv` 19.09.2026 tarihinde **KAP** (kap.org.tr/tr/Endeksler,
XU100 bileşenleri; sektörler kap.org.tr/tr/Sektorler) üzerinden doğrulanmış 100
sembol içerir (`.IS` uzantılı). Bileşenler değiştikçe `effective_from` /
`effective_to` ile kayıt tutulur; Veri Sağlığı sayfasından CSV yükleyerek veya
dosyayı düzenleyerek evren güncellenebilir. 100 sembol doğrulanamazsa uygulama
çalışmaya devam eder ve arayüzde “universe incomplete” uyarısı gösterir.

## Bilinen veri kısıtları

- Yahoo Finance verisi gecikmelidir (gün içi ≈15 dk); gerçek zamanlı BIST verisi lisanslı
  yayıncılardan ücretli alınır. Günlük seride son günler eksik/NaN gelebilir; bu günler
  saatlik barlardan türetilir, türetilemeyen satırlar `invalid_price` ile reddedilir ve
  Veri Sağlığı'nda gösterilir. 1 dk veri yalnızca son 30 gün için (istek başına 8 gün) alınabilir.
- Temettü verisi sağlayıcıya bağlıdır; `no_dividend_observed` ile `unavailable`
  ayrı işaretlenir. Devir hızı yerine TL hacim proxy'si kullanılır.
- “Eksik gün” oranı Pazartesi–Cuma takvimine göre hesaplanır; BIST tatilleri
  eksik gün gibi görünür (bilgi amaçlıdır, reddetmez).
- Komisyon, vergi, kayma, emir derinliği ve tarihsel endeks bileşen değişimleri
  (survivorship) modellenmez. Tarihsel volatilite/maks. düşüş geçmiş gözlemdir.
- Demo verisi sentetiktir; canlı yenileme başarısız olursa demo veri sessizce
  canlı veri yerine **kullanılmaz**, hata Veri Sağlığı'nda gösterilir.

## Yerelde kesintisiz çalıştırma (zamanlanmış görev)

`dev.ps1` sunucuları açık bir pencereye bağlar; pencere kapanınca dururlar. Kalıcı çalışma için:

```powershell
.\scripts\install-service.ps1   # frontend'i derler, iki Windows görevi kaydeder ve başlatır
.\scripts\status.ps1            # durum
.\scripts\uninstall-service.ps1 # kaldır
```

Görevler oturum açınca otomatik başlar, çökerse 1 dk içinde yeniden başlar, loglar
`state/logs/` altındadır. Kodu değiştirdiyseniz `install-service.ps1`'i yeniden çalıştırın.

> `pyarrow` (Parquet) bu makinede Windows Uygulama Denetimi tarafından engellenebiliyor;
> bu durumda uygulama fiyatları otomatik olarak SQLite tablolarında tutar (`SSL_PRICE_STORE=auto`).

## Buluta taşıma: Vercel (frontend) + PostgreSQL (Neon/Supabase) + konteyner (backend)

Backend, Vercel'in sunucusuz fonksiyonlarına uygun değildir (60 sn'lik veri indirme, arka
plan yenileme, Yahoo'nun veri merkezi IP'lerini engellemesi). Hedef mimari:

```text
Tarayıcı ──► Vercel (apps/web, Next.js) ──HTTPS──► Backend konteyneri (Render/Railway/Fly, Dockerfile)
                                                        │
                                                        └──► PostgreSQL: Neon / Supabase / Railway (durum + fiyat tabloları)
```

Adımlar:

1. **PostgreSQL** (herhangi biri): Neon (Vercel panelinden Marketplace → Neon; ücretsiz), Supabase,
   Railway veya Render Postgres. Bağlantı adresini olduğu gibi `SSL_DATABASE_URL` olarak verin
   (`postgresql://…` ve `postgres://…` adresleri psycopg sürücüsüne otomatik bağlanır).
   Tablolar ilk açılışta otomatik oluşur (`score_runs`, `portfolios`, `prices_clean`, …). Veri ~20 MB.
2. **Backend**: depoyu GitHub'a itin; Render'da "New → Blueprint" ile `render.yaml`'ı seçin
   (veya Railway/Fly'da Dockerfile ile). Ortam değişkenleri: `SSL_DATABASE_URL`,
   `SSL_CORS_ORIGINS=https://<proje>.vercel.app`, `SSL_PRICE_STORE=sql`, `SSL_AUTO_REFRESH_HOURS=20`.
   Açılışta veri otomatik indirilir. `https://<api>/health` ile doğrulayın.
3. **Vercel**: "Add New Project" → GitHub deposu → **Root Directory: `apps/web`** → Environment
   Variable `NEXT_PUBLIC_API_BASE_URL=https://<api-adresi>` → Deploy.
4. Yahoo bulut IP'lerini engellerse (`429`) Veri Sağlığı'nda görünür; o durumda backend'i başka
   bölgeye taşımak ya da lisanslı bir veri sağlayıcı adaptörü eklemek gerekir.

Sonraki adımlar: Supabase Auth ile kullanıcı bazlı portföyler (`user_id`), zamanlanmış
yenileme için dış cron (backend zaten saat başı kontrol eder), gerçek zamanlı veri için lisanslı sağlayıcı.

## 1. ve 2. Gün (mevcut temel)

- 1. Gün: basit getiri, oynaklık, aşağı yönlü oynaklık, maksimum düşüş,
  min-max normalizasyonu ve ağırlıklı sıralama (`src/day01_baseline.py`).
- 2. Gün: veri sözleşmesi, tür dönüşümü, doğrulama, ret nedenleri, yinelenen
  kayıtlar ve kalite raporu (`src/day02_data_pipeline.py`). İzinli kaynak kümesine
  `yahoo` ve `fake` eklenmiştir.

```powershell
.\.venv\Scripts\python.exe src/day01_baseline.py
.\.venv\Scripts\python.exe src/day02_data_pipeline.py
```

Beklenen 1. Gün sıralaması `GAMA` (≈0,600), `BETA` (≈0,520), `ALFA` (≈0,359);
2. Gün örneği yedi ham satırdan iki temiz satır, dört ret ve bir tam yinelenen
üretir. Eksik fiyat ileri doldurulmaz (yapay sıfır getiri riski). Ayrıntılar için
`notes/day01_math_and_architecture.md` ve `notes/day02_data_contract.md`.
