"use client";

import { useEffect, useState } from "react";
import type { NormalizedQuote } from "@/lib/barchart/types";
import { loadQuote } from "@/lib/client-data";
import { withBase } from "@/lib/paths";

const SYMBOLS = ["SPY", "QQQ", "NVDA", "TSLA", "AAPL", "AMD", "META", "ES", "NQ"];

export function LiveQuotes() {
  const [quotes, setQuotes] = useState<Record<string, NormalizedQuote | null>>({});

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const entries = await Promise.all(
        SYMBOLS.map(async (s) => {
          try {
            const r = await loadQuote(s);
            return [s, r.quotes[0] ?? null] as const;
          } catch {
            return [s, null] as const;
          }
        }),
      );
      if (!cancelled) setQuotes(Object.fromEntries(entries));
    };
    load();
    const ms = Math.max(20_000, Number(process.env.NEXT_PUBLIC_REFRESH_MS ?? 60_000) || 60_000);
    const id = setInterval(load, ms);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="glass p-3">
      <div className="lbl mb-2">Watchlist · live</div>
      <div className="grid grid-cols-2 gap-2">
        {SYMBOLS.map((s) => {
          const q = quotes[s];
          const chg = q?.percentChange ?? null;
          const up = (chg ?? 0) >= 0;
          return (
            <a
              key={s}
              href={withBase(`/ticker/${s}`)}
              className="glass-hover rounded border border-white/10 px-3 py-2 transition"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-neutral-100">{s}</span>
                <span className={`font-mono text-[11px] ${chg == null ? "text-neutral-500" : up ? "text-call" : "text-put"}`}>
                  {chg != null ? `${up ? "▲" : "▼"} ${Math.abs(chg).toFixed(2)}%` : "—"}
                </span>
              </div>
              <div className="mt-0.5 font-mono text-lg text-neutral-50">
                {q?.last != null ? q.last.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}
              </div>
              {q?.netChange != null && (
                <div className={`font-mono text-[11px] ${up ? "text-call" : "text-put"}`}>
                  {up ? "+" : ""}
                  {q.netChange.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                </div>
              )}
            </a>
          );
        })}
      </div>
    </div>
  );
}
