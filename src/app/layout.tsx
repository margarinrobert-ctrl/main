import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import type { ReactNode } from "react";
import "./globals.css";
import { NavLinks } from "@/components/NavLinks";
import { config } from "@/lib/barchart/config";
import { withBase } from "@/lib/paths";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const jbm = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jbm", display: "swap" });

export const metadata: Metadata = {
  title: {
    default: "OptionsFlow — Dealer positioning & options-flow analytics",
    template: "%s · OptionsFlow",
  },
  description:
    "Institutional-grade dealer gamma/delta positioning, volatility surfaces and options-flow analytics. GEX, DEX, vanna/charm, vol smile, expected move and TradingView level export.",
};

export const viewport: Viewport = {
  themeColor: "#05060a",
  width: "device-width",
  initialScale: 1,
};

/** Brand mark: a gamma-exposure curve crossing its flip line, in a rounded tile. */
function BrandMark() {
  return (
    <svg aria-hidden viewBox="0 0 28 28" className="h-7 w-7">
      <defs>
        <linearGradient id="bm-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#34d399" />
          <stop offset="100%" stopColor="#22d3ee" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="26" height="26" rx="7" fill="rgba(255,255,255,0.03)" stroke="rgba(255,255,255,0.14)" />
      <path d="M5 17.5h18" stroke="rgba(255,255,255,0.18)" strokeWidth="1" strokeDasharray="2 2" />
      <path d="M5 20c3.5 0 4.5-9.5 9-9.5s5 5.5 9 3.5" fill="none" stroke="url(#bm-g)" strokeWidth="2" strokeLinecap="round" />
      <circle cx="14" cy="10.6" r="1.6" fill="#34d399" />
    </svg>
  );
}

export default function RootLayout({ children }: { children: ReactNode }) {
  const live = config.dataSource === "live";
  return (
    <html lang="en" className={`${inter.variable} ${jbm.variable}`}>
      <body className="flex min-h-screen flex-col">
        <a
          href="#content"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-accent focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-black"
        >
          Skip to content
        </a>

        <header className="sticky top-0 z-20 border-b border-white/[0.07] bg-[#05060a]/70 backdrop-blur-xl">
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-2.5">
            <a href={withBase("/")} className="group flex items-center gap-2.5" aria-label="OptionsFlow home">
              <BrandMark />
              <span className="brand text-[15px] leading-none text-neutral-50">
                OPTIONS<span className="glow-text">FLOW</span>
              </span>
            </a>
            <div className="flex items-center gap-3">
              <NavLinks />
              <span
                className={`hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider sm:inline-flex ${
                  live ? "border-accent/40 bg-accent/10 text-accent-bright" : "border-amber-500/40 bg-amber-500/10 text-amber-300"
                }`}
              >
                <span className={`inline-block h-1.5 w-1.5 rounded-full ${live ? "bg-accent-bright" : "bg-amber-400"}`} />
                {live ? "Live feed" : "Sim"}
              </span>
            </div>
          </div>
        </header>

        <main id="content" className="fade-up mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6">
          {children}
        </main>

        <footer className="mx-auto w-full max-w-7xl px-4 pb-10 pt-6 sm:px-6">
          <div className="border-t border-white/[0.06] pt-6">
            <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
              <div className="max-w-sm">
                <div className="flex items-center gap-2">
                  <BrandMark />
                  <span className="brand text-sm text-neutral-200">
                    OPTIONS<span className="glow-text">FLOW</span>
                  </span>
                </div>
                <p className="mt-3 text-[11px] leading-relaxed text-neutral-600">
                  Dealer-positioning &amp; options-flow research terminal — gamma/delta exposure, volatility structure and
                  systematic trade frameworks.
                </p>
              </div>
              <nav aria-label="Footer" className="grid grid-cols-2 gap-x-12 gap-y-1.5 text-xs sm:grid-cols-2">
                <div className="lbl col-span-2 mb-1">Terminals</div>
                {["SPY", "QQQ", "NVDA", "TSLA"].map((s) => (
                  <a key={s} href={withBase(`/ticker/${s}`)} className="text-neutral-500 transition hover:text-accent-bright">
                    {s} terminal
                  </a>
                ))}
                <a href={withBase("/live")} className="text-neutral-500 transition hover:text-accent-bright">
                  Live tape
                </a>
              </nav>
            </div>
            <div className="mt-6 border-t border-white/[0.04] pt-4 text-[11px] leading-relaxed text-neutral-600">
              Educational research &amp; analytics. Not financial advice. Options involve substantial risk and are not
              suitable for all investors.
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
