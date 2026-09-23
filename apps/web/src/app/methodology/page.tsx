import { Card, PageHeader } from "@/components/ui";

function Formula({ children }: { children: string }) {
  return <pre className="num my-2 overflow-x-auto rounded bg-surface-2 p-3 text-xs leading-relaxed text-primary">{children}</pre>;
}

export default function MethodologyPage() {
  return (
    <div className="space-y-4">
      <PageHeader
        title="Metodoloji"
        description="Seminerdeki bulanık parametreli bulanık esnek küme (fpfs) modelinin bu uygulamadaki karşılığı. Araştırma amaçlıdır; fiyat tahmini veya getiri garantisi içermez."
      />
      <div className="grid gap-3 lg:grid-cols-2">
        <Card title="FSS ile fpfs farkı">
          <p className="text-sm text-secondary">
            Bulanık esnek küme (FSS) her hisseyi kriter üyelikleriyle tanımlar ama kriterlerin önemini eşit sayar. fpfs (fuzzy parameterized
            fuzzy soft set) her kritere bir önem derecesi <span className="num">μ_j ∈ [0,1]</span> ekler. Matrisin <strong>sıfırıncı satırı</strong> bu
            önem derecelerini taşır; hisse satırları ise üyelikleri:
          </p>
          <Formula>{`a_0j = mu_j          (kriter j'nin önem derecesi)
a_ij = hisse i'nin kriter j üyeliği

Sütun sırası (sözleşme): return, dividend, liquidity, risk`}</Formula>
          <p className="text-sm text-secondary">
            Aynı üyelik matrisinde FSS ve fpfs farklı sıralamalar verebilir; seminer örneğinde C4 ile C7 yer değiştirir. Sıralama sayfasındaki
            “FSS farkı” sütunu bu kaymayı gösterir.
          </p>
        </Card>

        <Card title="CCE10 (ana operatör)">
          <Formula>{`score_i = (1 / n) * sum_j( mu_j * a_ij ),   n = 4`}</Formula>
          <p className="text-sm text-secondary">Ana sıralama CCE10 skoruna göredir. Karşılaştırma sekmesinde üç ek operatör gösterilir:</p>
          <Formula>{`FSS  (ağırlıksız)  fss_i = (1 / n) * sum_j( a_ij )
DRF  (ağırlıklı)   drf_i = sum_j( mu_j * a_ij )
DMF  (ağırlıklı)   C_ik  = sum_j( mu_j * (a_ij - a_kj) ),  D_i = sum_k( C_ik )`}</Formula>
          <p className="text-xs text-muted">
            Seminerdeki yedi hisselik örnek test fixture’ı olarak eklenmiştir; Dengeli profil ile FSS sırası C29 &gt; C21 &gt; C9 &gt; C4 &gt; C7 &gt; C16 &gt; C14, fpfs sırası
            C29 &gt; C21 &gt; C9 &gt; C7 &gt; C4 &gt; C16 &gt; C14 yeniden üretilir.
          </p>
        </Card>

        <Card title="Kriter formülleri">
          <Formula>{`r_it            = adj_close_t / adj_close_{t-1} - 1     (günlük basit getiri)
mean_return_i   = mean(r_it)                              (dönemsel; üyelikte bu kullanılır)
annualized      = mean_return_i * 252                     (yalnızca gösterim)
downside_risk_i = mean( max(0, mean_return_i - r_it) )    (yarı-mutlak sapma; cost)
dividend_yield  = son 12 ay nakit temettü / referans kapanış
liquidity       = median( close * volume ) / fiili dolaşım piyasa değeri   (gerçek devir hızı)
                  ya da median( close * volume )                          (payda yoksa TL hacim proxy'si)`}</Formula>
          <p className="text-xs text-muted">
            Getiri ve risk için düzeltilmiş kapanış (adj_close) kullanılır; böylece bedelsiz sermaye artırımı gibi kurumsal işlemler yapay getiri
            üretmez. Temettü gözlenmemesi (<span className="num">no_dividend_observed</span>, değer 0) ile sağlayıcının temettü verisi verememesi
            (<span className="num">unavailable</span>) ayrı işaretlenir.
          </p>
        </Card>

        <Card title="Üyelik değerleri (normalizasyon)">
          <Formula>{`benefit_membership = (x - min_x) / (max_x - min_x)        → return
cost_membership    = 1 - (x - min_x) / (max_x - min_x)    → risk
max_division       = x / max_x                            → dividend, liquidity`}</Formula>
          <p className="text-xs text-muted">
            Getiri negatif olabildiği için min-max kullanılır; temettü ve likidite negatif olmayan benefit kriterleri olduğundan seminer uyumlu
            maksimuma bölme uygulanır. Sabit sütunda sessiz bölme yapılmaz: açık politika (<span className="num">neutral</span> = 0.5,{" "}
            <span className="num">zero</span>, <span className="num">raise</span>) uygulanır ve uyarı üretilir. NaN, sonsuz ve [0,1] dışı değerde
            hesap durdurulur. Kullanılan yöntem her skor çalışmasıyla birlikte saklanır.
          </p>
        </Card>

        <Card title="Likidite: gerçek devir hızı">
          <p className="text-sm text-secondary">
            Seminerdeki likidite kriteri <strong>devir hızı</strong> ile tanımlanır. Uygulama, İş Yatırım&apos;dan gelen
            <strong> fiili dolaşımdaki piyasa değeri</strong> (HAO_PD) ile günlük TL işlem hacmini bu paydaya bölerek
            gerçek devir hızını hesaplar: bir günde el değiştiren serbest dolaşım payı.
          </p>
          <Formula>{`devir_hızı = median(kapanış × lot hacmi) / fiili dolaşım piyasa değeri`}</Formula>
          <p className="text-xs text-muted">
            Payda tek bir sembolde bile eksikse birim karışmaması için <strong>bütün semboller</strong> eski TL hacim
            proxy&apos;sine döner ve uyarı üretilir. Hangi yöntemin kullanıldığı her skor çalışmasına
            (<span className="num">liquidity_input</span>) yazılır.
          </p>
        </Card>

        <Card title="Veri doğrulama (iki kaynak)">
          <p className="text-sm text-secondary">
            Günlük fiyatlar Yahoo Finance&apos;ten alınır, ardından <strong>İş Yatırım</strong> verisiyle çapraz
            kontrol edilir: örtüşen her sembol-gün için kapanışlar karşılaştırılır, birincil kaynakta eksik kalan
            günler İş Yatırım kapanışlarıyla tamamlanır (satır <span className="num">source=&quot;isyatirim&quot;</span>
            ile işaretlenir).
          </p>
          <p className="text-xs text-muted">
            Sapmalar gizlenmez: tolerans (varsayılan %0,2) üstündeki semboller Veri Sağlığı sayfasında tarih ve iki
            kaynaktaki fiyatla listelenir. İş Yatırım ucunda açılış fiyatı bulunmadığı için giriş fiyatı (bir sonraki
            işlem gününün açılışı) her zaman birincil kaynaktan alınır; temettü verisi de yalnızca Yahoo&apos;dan gelir.
          </p>
        </Card>

        <Card title="Portföy katmanı (fpfs’ten ayrı)">
          <p className="text-sm text-secondary">
            fpfs hisseleri seçer ve sıralar; ağırlıklandırma ayrı, şeffaf bir uygulama katmanıdır. Genetik algoritma veya MOP uygulanmaz.
          </p>
          <Formula>{`Muhafazakâr: ilk 15, w_i ∝ 1 / downside_risk_i,             tek hisse ≤ %10
Dengeli:     ilk 10, w_i = 0.5·skor_payı + 0.5·ters_risk_payı, tek hisse ≤ %15
Agresif:     ilk 7,  w_i ∝ cce10_i,                          tek hisse ≤ %20
Tavan sonrası fazla ağırlık orantılı yeniden dağıtılır; toplam = 1.0

Lot:   quantity_i = floor(capital · w_i / entry_price_i)  (artan tutar nakit)
Değer: V_t = cash + Σ quantity_i · price_it,  getiri_t = V_t / capital − 1`}</Formula>
          <p className="text-xs text-muted">
            Look-ahead engeli: karar tarihindeki sıralama yalnızca o tarihe kadar olan veriyi kullanır; giriş fiyatı bir sonraki işlem gününün
            açılışından alınır (yoksa kapanış). O gün henüz oluşmamışsa portföy “beklemede” kalır. Üç profil başlangıç/demo parametresidir;
            akademik olarak doğrulanmış evrensel yatırımcı profilleri değildir.
          </p>
        </Card>

        <Card title="Veri kısıtları" className="lg:col-span-2">
          <ul className="list-disc space-y-1 pl-5 text-sm text-secondary">
            <li>Veri kaynağı Yahoo Finance (yfinance); günlük ve gecikmelidir, gerçek zamanlı değildir. Demo modunda veri sentetiktir.</li>
            <li>BIST 100 bileşenleri zamanla değişir; evren <span className="num">config/bist100_symbols.csv</span> dosyasından okunur ve geçerlilik tarihi taşır. Evren listesi 19.09.2026 tarihinde KAP (Kamuyu Aydınlatma Platformu) endeks sayfasından doğrulanmıştır; tarihsel bileşen değişimleri (survivorship) modellenmez.</li>
            <li>Temettü verisi sağlayıcıya bağlıdır; eksik/hatalı olabilir. Devir hızı paydası (fiili dolaşım piyasa değeri) İş Yatırım&apos;dan gelir; alınamazsa TL hacim proxy&apos;sine dönülür.</li>
            <li>Komisyon, vergi, kayma (slippage) ve emir derinliği modellenmez. Değerleme kapanış fiyatıyla yapılır; fiyatı olmayan günlerde son kapanış ileri taşınır ve uyarı verilir.</li>
            <li>Tarihsel volatilite ve maksimum düşüş geçmiş gözlemdir; gelecek performansın göstergesi değildir. Hiçbir çıktı garanti getiri veya fiyat tahmini değildir.</li>
            <li>Uygulama gerçek emir göndermez ve aracı kurum hesabına bağlanmaz.</li>
          </ul>
        </Card>
      </div>
    </div>
  );
}
