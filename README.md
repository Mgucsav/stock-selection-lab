# Stock Selection Lab

Bu depo, hisse seçimi problemini küçük ve denetlenebilir adımlarla öğrenmek için
hazırlanmış bir Python çalışmasıdır. Bütün örnekler sentetik veriye dayanır.

**Eğitim ve araştırma amaçlıdır; yatırım tavsiyesi değildir.**

## Kapsam

Şimdiki kapsam yalnızca 1. Gün ve 2. Gün konularıdır:

- 1. Gün: basit getiri, oynaklık, aşağı yönlü oynaklık, maksimum düşüş,
  min-max normalizasyonu ve ağırlıklı sıralama.
- 2. Gün: veri sözleşmesi, tür dönüşümü, doğrulama, ret nedenleri, yinelenen
  kayıtlar ve kalite raporu.

Bu aşamada dört ayrı problem birbirine karıştırılmaz:

- **Tahmin**, gelecekteki bilinmeyen bir değeri kestirmeye çalışır.
- **Sıralama**, eldeki ölçütlerle alternatifleri göreli olarak dizer. 1. Gün
  kodunun yaptığı budur.
- **Portföy oluşturma**, varlık ağırlıklarını kısıtlar altında belirler.
- **İzleme**, veri ve model davranışını zaman içinde denetler.

## Proje yapısı

```text
stock-selection-lab/
├── README.md
├── requirements.txt
├── .gitignore
├── pytest.ini
├── data/
│   ├── raw/.gitkeep
│   ├── processed/.gitkeep
│   └── rejected/.gitkeep
├── notes/
│   ├── day01_math_and_architecture.md
│   └── day02_data_contract.md
├── src/
│   ├── __init__.py
│   ├── day01_baseline.py
│   └── day02_data_pipeline.py
└── tests/
    ├── test_day01_baseline.py
    └── test_day02_data_pipeline.py
```

## Windows PowerShell kurulumu

Depo kökünde çalıştırın:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

PowerShell çalıştırma ilkesi etkinleştirmeyi engellerse ortamın yorumlayıcısını
doğrudan kullanabilirsiniz:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Çalıştırma

```powershell
.\.venv\Scripts\python.exe src/day01_baseline.py
.\.venv\Scripts\python.exe src/day02_data_pipeline.py
.\.venv\Scripts\python.exe -m pytest -q
```

### Beklenen 1. Gün sonucu

Yaklaşık özellik değerleri şöyledir:

| Hisse | Getiri | Yıllık oynaklık | Aşağı yönlü oynaklık | Mutlak maksimum düşüş |
|---|---:|---:|---:|---:|
| ALFA | 0,0900 | 0,2979 | 0,0720 | 0,0192 |
| BETA | 0,1000 | 0,3200 | 0,0062 | 0,0100 |
| GAMA | 0,0400 | 0,0193 | 0,0000 | 0,0000 |

Varsayılan ağırlıklarla sıralama `GAMA` (yaklaşık 0,600), `BETA`
(yaklaşık 0,520), `ALFA` (yaklaşık 0,359) olur. `downside_volatility`
hesaplanır ve özellik tablosunda tutulur; ölçütlerin iki kere risk saymasına yol
açmamak ve ilk modeli sade tutmak için henüz ağırlıklı puana katılmaz.

### Beklenen 2. Gün sonucu

Yedi sentetik ham satırdan iki temiz satır, dört kurala dayalı ret ve bir tam
yinelenen satır çıkar. Ret oranı `4 / 7` olur. Betik şu çıktıları üretir:

- `data/processed/prices_clean.csv`: sözleşmeyi geçen, sıralanmış kayıtlar.
- `data/rejected/prices_rejected.csv`: bir veya birden çok açık ret nedeni olan
  kayıtlar.
- `data/rejected/prices_exact_duplicates.csv`: tam yinelenen kayıtların ayrı
  denetim izi.
- `data/processed/quality_report.json`: toplamlar, nedenler ve sembol özeti.

Ham veri değişmez ve üzerine yazılmaz. Temizleme sonucu yeni dosyalara yazılır;
böylece hatanın kaynağı incelenebilir ve işlem yeniden üretilebilir. Aynı
`(symbol, date)` anahtarındaki farklı ve geçerli kayıtların hiçbiri sessizce
seçilmez; hepsi `conflicting_duplicate_key` nedeniyle reddedilir.

## Eksik fiyat politikası

Eksik fiyatlar 1. Gün hesabında hata üretir, 2. Gün hattında açık bir ret nedeni
ile ayrılır. Otomatik ileri doldurma yapılmaz. İleri doldurma gerçek bir piyasa
gözlemi olmayan güne yapay bir sıfır getiri ekleyebilir:

```text
P[t] = P[t-1] ise
r[t] = P[t] / P[t-1] - 1 = 0
```

Bu işlem oynaklığı, düşüşü ve nihai sıralamayı fark edilmeden değiştirebilir.

## Bilinçli sınırlamalar

Gerçek veri API'si, ağ isteği ve API anahtarı yoktur. Kurumsal işlemlerin ayrıca
düzeltilmesi, aykırı değer silme, bulanık model, GARCH, ileri gün tahmini,
portföy optimizasyonu ve yatırım emri yürütme bu kapsamda değildir.

Ayrıntılı matematik için `notes/day01_math_and_architecture.md`, veri kuralları
için `notes/day02_data_contract.md` dosyasına bakın.
