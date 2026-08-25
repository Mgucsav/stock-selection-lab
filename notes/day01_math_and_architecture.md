# 1. Gün: Matematik ve Mimari

Bu not, sentetik fiyatlardan sıralama puanına giden bağımlılık zincirini açıklar:

```text
fiyat doğrulama → basit getiriler → risk/getiri özellikleri
                 → normalizasyon → ağırlık doğrulama → sıralama
```

`TRADING_DAYS = 252`, bir yıldaki yaklaşık işlem günü sayısı varsayımıdır.

## `simple_returns(price_frame)`

- **Girdi:** Tarih satırlı, hisse sütunlu pozitif fiyat `DataFrame`'i.
- **Çıktı:** İlk satırı olmayan basit getiri `DataFrame`'i.
- **Finansal anlam:** Bir dönemlik oransal fiyat değişimi.
- **Formül:** `r[t,i] = P[t,i] / P[t-1,i] - 1`.
- **Kod-formül karşılığı:** `div(shift(1)).sub(1.0)` sırasıyla önceki fiyatı,
  bölmeyi ve bir çıkarmayı temsil eder.
- **Varsayım:** Satırlar kronolojik ve dönem aralıkları karşılaştırılabilirdir.
- **Kenar durumları:** Eksik, metin, sonsuz, sıfır ve negatif fiyat reddedilir;
  çağıranın tablosu değiştirilmez.

## `max_drawdown(price_series)`

- **Girdi:** Tek varlığa ait pozitif fiyat `Series`'i.
- **Çıktı:** Sıfır veya negatif en büyük düşüş oranı.
- **Finansal anlam:** Gözlenen bir zirveden sonraki en ağır kayıp.
- **Formüller:**

  `DD[t,i] = P[t,i] / max(P[0,i], ..., P[t,i]) - 1`

  `MDD[i] = min(DD[:,i])`

- **Kod-formül karşılığı:** `cummax()` o güne kadarki zirveyi, `min()` en kötü
  düşüşü verir.
- **Varsayım:** Fiyatlar tarih sırasında bulunur.
- **Kenar durumları:** Sürekli yükselen veya tek gözlemli seri için sonuç
  `0.0`'dır; geçersiz fiyat reddedilir.

## `annualized_downside_volatility(returns)`

- **Girdi:** Bir varlık `Series`'i veya çok varlıklı getiri `DataFrame`'i.
- **Çıktı:** Tek sayı veya varlık başına yıllıklaştırılmış değer.
- **Finansal anlam:** Yalnızca negatif getirilerin kendi içindeki oynaklığı.
- **Formül:** `population_std({r[t,i] : r[t,i] < 0}, ddof=0) * sqrt(252)`.
- **Kod-formül karşılığı:** Negatif filtre, `std(ddof=0)` ve `sqrt(252)` aynı
  üç matematik adımıdır.
- **Varsayım:** Eğitim amaçlı “negatif-getiri standart sapması” kullanılır. Bu,
  hedef getiriye göre yarı sapma gibi her akademik downside deviation tanımıyla
  aynı değildir.
- **Kenar durumları:** Negatif getiri yoksa `0.0`; tek negatif gözlemde anakütle
  standart sapması da `0.0` olur.

## `build_features(price_frame)`

- **Girdi:** Doğrulanabilir çok varlıklı fiyat tablosu.
- **Çıktı:** Tam olarak `return`, `volatility`, `downside_volatility` ve
  `max_drawdown_abs` sütunları.
- **Finansal anlam:** Her alternatifi getiri ve risk boyutlarında özetler.
- **Formüller:**

  `R[i] = P[T,i] / P[0,i] - 1`

  `annual volatility = sample_std(r[:,i], ddof=1) * sqrt(252)`

- **Kod-formül karşılığı:** İlk/son satır bölümü kümülatif getiriyi; getirilerin
  `std(ddof=1) * sqrt(252)` işlemi yıllık oynaklığı verir. Maksimum düşüş mutlak
  değere çevrilir, çünkü puanlamada bir maliyet ölçütüdür.
- **Varsayım:** 252 işlem günü ve geçmiş örnek standart sapması kullanılır.
- **Kenar durumları:** Geçersiz herhangi bir fiyat bütün hesabı durdurur. Çok az
  gözlemde örnek standart sapması tanımsız olabilir.

## `minmax_benefit(series)` ve `minmax_cost(series)`

- **Girdi:** Aynı ölçüte ait alternatif değerleri.
- **Çıktı:** Aynı indeksli, `[0, 1]` aralığında puanlar.
- **Finansal anlam:** Farklı ölçeklerdeki ölçütleri karşılaştırılabilir yapar.
- **Fayda formülü:**
  `z[i,k] = (x[i,k] - min(x[:,k])) / (max(x[:,k]) - min(x[:,k]))`.
- **Maliyet formülü:**
  `z[i,k] = (max(x[:,k]) - x[i,k]) / (max(x[:,k]) - min(x[:,k]))`.
- **Kod-formül karşılığı:** `sub`, `rsub` ve `div` formüldeki çıkarma ve bölmedir.
- **Varsayım:** Getiri fayda; oynaklık ve mutlak düşüş maliyettir.
- **Kenar durumları:** Bütün değerler eşitse sıfıra bölmek yerine tüm
  alternatiflere tarafsız `0.5` verilir.

## `validate_weights(weights, expected_columns)`

- **Girdi:** Ölçüt-ağırlık eşlemesi ve beklenen ölçüt adları.
- **Çıktı:** Geçerliyse `None`; değilse Türkçe `ValueError`.
- **Finansal anlam:** Hiçbir ölçüte negatif bütçe verilmemesini ve toplam bütçenin
  tamamının dağıtılmasını sağlar.
- **Koşullar:** Her `k` için `w[k] >= 0` ve `sum(w[k]) = 1`.
- **Kod-formül karşılığı:** Küme eşitliği anahtarları, `isfinite` değerleri,
  negatif karşılaştırması işareti, `isclose` toplamı sınar.
- **Varsayım:** Ağırlıklar göreli önem katsayılarıdır.
- **Kenar durumları:** Eksik/fazla anahtar, NaN, sonsuz, negatif değer ve birden
  farklı toplam reddedilir.

## `score_stocks(features, weights)`

- **Girdi:** Özellik tablosu ve üç geçerli ağırlık.
- **Çıktı:** Normalize ölçütler, `total_score` ve `rank` içeren sıralı tablo.
- **Finansal anlam:** Çok ölçütlü, açıklanabilir bir göreli tercih sırası.
- **Formül:** `S[i] = sum(w[k] * z[i,k])`.
- **Kod-formül karşılığı:** Sütun-ağırlık çarpımlarının `sum` işlemi formülü
  doğrudan uygular; azalan `rank` yüksek puana ilk sırayı verir.
- **Varsayım:** Şimdilik yalnızca `return_score`, `volatility_score` ve
  `drawdown_score` puana girer.
- **Kenar durumları:** Gerekli özellik veya ağırlık yoksa hata oluşur; eşit puanlar
  aynı sırayı alır. `downside_volatility` hesaplanır ama bu ilk puana kasıtlı
  olarak katılmaz.
