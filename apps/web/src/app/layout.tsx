import type { Metadata } from "next";

import { Shell } from "@/components/Shell";

import "./globals.css";

export const metadata: Metadata = {
  title: "BIST 100 fpfs Lab",
  description: "BIST 100 için bulanık parametreli bulanık esnek matris tabanlı hisse sıralaması ve model portföy simülasyonu.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="tr" className="h-full antialiased">
      <body className="min-h-full">
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
