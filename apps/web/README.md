# apps/web — BIST 100 fpfs Lab arayüzü

Next.js (App Router) + TypeScript strict + Tailwind CSS + Recharts + Vitest.

```powershell
npm install
npm run dev        # http://localhost:3000
npm run typecheck  # next typegen + tsc --noEmit
npm test           # vitest
npm run lint
```

Backend adresi `.env.local` içindeki `NEXT_PUBLIC_API_BASE_URL` ile belirlenir
(varsayılan `http://localhost:8000`). Sayfalar: Panel `/`, Hisse Sıralaması
`/rankings`, Portföy Oluşturucu `/builder`, Portföylerim `/portfolios`,
Portföy Detayı `/portfolios/[id]`, Metodoloji `/methodology`, Veri Sağlığı
`/data-health`. API tipleri `src/lib/types.ts`, istemci `src/lib/api.ts`.

## Vercel

Vercel projesinde **Root Directory = `apps/web`** seçin ve `NEXT_PUBLIC_API_BASE_URL`
ortam değişkenine backend adresini verin. Başka ayar gerekmez (`vercel.json` bölgeyi fra1 yapar).
