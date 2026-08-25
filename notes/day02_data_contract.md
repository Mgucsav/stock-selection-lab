# 2. Gün: Veri Sözleşmesi

Bu sözleşme, bir fiyat satırının temiz veri kümesine girebilmesi için gereken
kuralları tanımlar. Amaç hatalı satırları görünmez biçimde silmek değil, nedenini
kaydederek ayrı tutmaktır.

## Sütunlar

| Sütun | Beklenen tür | Zorunlu | Finansal/işlemsel anlam |
|---|---|---|---|
| `date` | tarih | Evet | Fiyat gözleminin ait olduğu piyasa günü |
| `symbol` | metin | Evet | Varlık kodu; boşlukları kırpılır ve büyütülür |
| `open` | sonlu pozitif sayı | Evet | Açılış fiyatı |
| `high` | sonlu pozitif sayı | Evet | Gün içi en yüksek fiyat |
| `low` | sonlu pozitif sayı | Evet | Gün içi en düşük fiyat |
| `close` | sonlu pozitif sayı | Evet | Kapanış fiyatı |
| `adj_close` | sonlu pozitif sayı | Evet | Kaynağın sağladığı düzeltilmiş kapanış |
| `volume` | sonlu, negatif olmayan sayı | Evet | İşlem hacmi; uygunsa nullable `Int64` tutulur |
| `source` | metin | Evet | Verinin geldiği izinli kaynak |
| `ingested_at` | UTC zaman damgası | Evet | Satırın sisteme alındığı an |

Kod bu aşamada `adj_close` değerini kendisi kurumsal işlemlere göre düzeltmez;
yalnızca sözleşmeye uygunluğunu denetler.

## Anahtar ve fiyat kuralları

İş anahtarı `(symbol, date)` çiftidir. Fiyatların hepsi sıfırdan büyük olmalıdır.
Gün içi tutarlılık şu eşitsizliklerle sınanır:

```text
low <= min(open, close)
high >= max(open, close)
low <= high
```

İzinli kaynaklar yalnızca `demo`, `csv` ve `vendor_a` değerleridir. `ingested_at`
geçerli bir zaman damgası olmalı ve UTC olarak ayrıştırılmalıdır.

## Yinelenen kayıt politikası

- Bütün zorunlu alanları aynı olan sonraki satır **tam yinelenen** sayılır. Kural
  retlerine karıştırılmaz, ayrı denetim çıktısına alınır.
- Aynı `(symbol, date)` anahtarına sahip, birbirinden farklı ve kendi başına
  geçerli iki satır varsa hangisinin doğru olduğu bilinemez. İlk veya son satır
  sessizce seçilmez; çakışan satırların tamamı
  `conflicting_duplicate_key` nedeniyle reddedilir.

## Ret nedenleri

Bir satır birden çok kurala aykırıysa nedenler aşağıdaki sabit sırayla `|` ile
birleştirilebilir:

- `invalid_date`: tarih ayrıştırılamadı.
- `missing_symbol`: sembol eksik veya boş.
- `invalid_ingested_at`: alım zamanı ayrıştırılamadı.
- `invalid_price`: en az bir fiyat eksik, sayısal değil veya sonsuz.
- `non_positive_price`: en az bir fiyat sıfır ya da negatif.
- `invalid_volume`: hacim eksik, sayısal değil veya sonsuz.
- `negative_volume`: hacim negatif.
- `invalid_ohlc_relation`: OHLC eşitsizliklerinden biri bozuk.
- `missing_source`: kaynak eksik veya boş.
- `unknown_source`: kaynak izinli kümede değil.
- `conflicting_duplicate_key`: geçerli fakat aynı iş anahtarında farklı kayıtlar.

Satırlar sessizce silinmez. Ret nedeni hem CSV'de hem kalite raporundaki neden
sayımlarında görünür.

## Veri katmanları

- `data/raw/`: Kaynaktan geldiği haliyle değişmez ham dosyalar için ayrılır.
- `data/processed/`: Kuralları geçen temiz veri ve kalite raporu için kullanılır.
- `data/rejected/`: Kural retleri ve tam yinelenen denetim izi için kullanılır.

Ham dosyanın üzerine yazılmaz. Temizleme fonksiyonu da çağıranın `DataFrame`'ini
değiştirmez. Böylece dönüşüm yeniden çalıştırılabilir ve bir ret araştırılabilir.

## Eksik gözlem ve zaman bilgisi

Eksik fiyat ileri doldurulmaz. İleri doldurma gözlem yapılmayan bir güne yapay
bir sıfır getiri ekleyebilir ve risk ölçülerini değiştirebilir. Eksik değer açıkça
reddedilir; bu kararı daha sonraki bir veri iyileştirme aşaması verebilir.

Geçmiş dosyalar sonradan düzeltilmiş değerler içerebilir. Bugün indirilen revize
bir geçmiş dosyayı geçmişte zaten biliniyormuş gibi kullanmak **veri sızıntısı**
yaratır. “As-of” ilkesi, her analiz tarihinde yalnızca o tarihte gerçekten
erişilebilir olan veri sürümünün kullanılmasını ister. `ingested_at` bu denetim
izinin ilk parçasıdır; gerçek bir sistem ayrıca kaynak sürümünü ve yayın zamanını
da saklamalıdır.
