import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { config } from "@/lib/barchart/config";

export const metadata: Metadata = {
  title: "OptionsFlow",
  description: "Unusual options activity & quant analytics (Barchart OnDemand)",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  const live = config.dataSource === "live";
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="border-b border-neutral-800 px-6 py-3 flex items-center justify-between">
          <a href="/" className="font-semibold tracking-tight">
            Options<span className="text-emerald-400">Flow</span>
          </a>
          <span
            className={`rounded px-2 py-1 text-xs ${
              live ? "bg-emerald-900 text-emerald-300" : "bg-amber-900 text-amber-300"
            }`}
          >
            source: {config.dataSource}
          </span>
        </header>
        <main className="px-6 py-6">{children}</main>
      </body>
    </html>
  );
}
