import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { config } from "@/lib/barchart/config";
import { withBase } from "@/lib/paths";

export const metadata: Metadata = {
  title: "OptionsFlow — GEX, delta walls & dealer analytics",
  description: "Unusual options activity, dealer gamma/delta positioning & quant analytics",
};

const NAV = ["SPY", "QQQ", "NVDA", "TSLA"];

export default function RootLayout({ children }: { children: ReactNode }) {
  const live = config.dataSource === "live";
  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col">
        <header className="sticky top-0 z-20 border-b border-white/10 bg-black/50 backdrop-blur-xl">
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-3">
            <a href={withBase("/")} className="flex items-center gap-2.5 tracking-tight">
              <span className="relative inline-flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400/60" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400 shadow-[0_0_12px_2px_rgba(16,185,129,0.7)]" />
              </span>
              <span className="brand text-lg text-neutral-50">
                OPTIONS<span className="glow-text">FLOW</span>
              </span>
            </a>
            <nav className="hidden items-center gap-0.5 sm:flex">
              <a
                href={withBase("/live")}
                className="flex items-center gap-1.5 rounded px-2.5 py-1.5 text-xs font-semibold uppercase tracking-wider text-red-300 transition hover:bg-white/5"
              >
                <span className="relative inline-flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500/70" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-red-500" />
                </span>
                Live
              </a>
              {NAV.map((s) => (
                <a
                  key={s}
                  href={withBase(`/ticker/${s}`)}
                  className="rounded px-2.5 py-1.5 text-xs font-semibold uppercase tracking-wider text-neutral-400 transition hover:bg-white/5 hover:text-neutral-100"
                >
                  {s}
                </a>
              ))}
            </nav>
            <span
              className={`rounded-full border px-2.5 py-1 text-xs font-medium ${
                live
                  ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                  : "border-amber-500/40 bg-amber-500/10 text-amber-300"
              }`}
            >
              ● {config.dataSource}
            </span>
          </div>
        </header>
        <main className="fade-up mx-auto w-full max-w-7xl flex-1 px-5 py-6 sm:px-6">{children}</main>
        <footer className="mx-auto w-full max-w-7xl px-5 pb-8 pt-4 sm:px-6">
          <div className="border-t border-white/5 pt-4 text-[11px] leading-relaxed text-neutral-600">
            <span className="text-neutral-400">OptionsFlow</span> — educational options-flow &amp; dealer-gamma analytics. Not financial advice.
          </div>
        </footer>
      </body>
    </html>
  );
}
