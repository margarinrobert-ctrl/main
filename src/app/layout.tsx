import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { config } from "@/lib/barchart/config";
import { withBase } from "@/lib/paths";

export const metadata: Metadata = {
  title: "OptionsFlow — GEX & unusual options activity",
  description: "Unusual options activity, dealer gamma & quant analytics",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  const live = config.dataSource === "live";
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="sticky top-0 z-20 border-b border-white/10 bg-black/40 px-6 py-3 backdrop-blur-xl">
          <div className="mx-auto flex max-w-7xl items-center justify-between">
            <a href={withBase("/")} className="flex items-center gap-2 tracking-tight">
              <span className="inline-block h-2.5 w-2.5 rounded-full bg-emerald-400 shadow-[0_0_12px_2px_rgba(16,185,129,0.7)]" />
              <span className="text-lg font-semibold">
                Options<span className="glow-text">Flow</span>
              </span>
            </a>
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
        <main className="mx-auto max-w-7xl px-6 py-6">{children}</main>
      </body>
    </html>
  );
}
