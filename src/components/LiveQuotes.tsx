"use client";

import { useEffect, useState } from "react";
import type { NormalizedQuote } from "@/lib/barchart/types";
import { loadQuote } from "@/lib/client-data";
import { withBase } from "@/lib/paths";
import { Provenance } from "./Provenance";

const SYMBOLS = ["SPY", "QQQ", "NVDA", "TSLA", "AAPL", "AMD", "META", "ES", "NQ"];

export function LiveQuotes() {
  const [quotes, setQuotes] = useState<Record<string, NormalizedQuote | null>>({});
  const [source, setSource] = useState("");

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const results = await Promise.all(
        SYMBOLS.map(async (s) => {
          try {
            const r = await loadQuote(s);
            return { sym: s, quote: r.quotes[0] ?? null, source: r.source };
          } catch {
            return { sym: s, quote: null, source: "" };
          }
        }),
      );
      if (cancelled) return;
      setQuotes(Object.fromEntries(results.map((r) => [r.sym, r.quote])));
      // The tape is only as trustworthy as its WEAKEST symbol: if any one of them fell back to
      // fixtures the strip is part canned, and saying "live" would be a half-truth.
      const sources = results.filter((r) => r.quote != null).map((r) => r.source);
      setSource(sources.length && sources.every((x) => x === "live") ? "live" : (sources.find((x) => x !== "live") ?? ""));
    };
    load();
    const ms = Math.max(20_000, Number(process.env.NEXT_PUBLIC_REFRESH_MS ?? 60_000) || 60_000);
    const id = setInterval(load, ms);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const empty = Object.keys(quotes).length === 0;

  return (
    <div className="rounded-xl border border-amber-400/20 bg-base p-3 font-mono">
      <div className="mb-2 flex items-center gap-2">
        <span className="live-dot" />
        <span className="lbl text-amber-400">Watchlist · auto-refresh</span>
      </div>
      <Provenance source={source} feed="quotes" className="mb-2" />
      {empty ? (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {SYMBOLS.map((s) => (
            <div key={s} className="skeleton h-[74px] rounded-lg" />
          ))}
        </div>
      ) : (
        <div className="stagger grid grid-cols-2 gap-2 sm:grid-cols-3">
          {SYMBOLS.map((s) => {
            const q = quotes[s];
            const chg = q?.percentChange ?? null;
            const up = (chg ?? 0) >= 0;
            return (
              <a
                key={s}
                href={withBase(`/ticker/${s}`)}
                className="rounded-lg border border-amber-400/15 bg-white/[0.02] px-3 py-2 transition hover:border-amber-400/40 hover:bg-white/[0.04]"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-amber-400">{s}</span>
                  <span className={`font-mono text-[11px] tabular-nums ${chg == null ? "text-neutral-500" : up ? "text-call" : "text-put"}`}>
                    {chg != null ? `${up ? "▲" : "▼"} ${Math.abs(chg).toFixed(2)}%` : "—"}
                  </span>
                </div>
                <div className="mt-0.5 font-mono text-lg tabular-nums text-neutral-50">
                  {q?.last != null ? q.last.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}
                </div>
                {q?.netChange != null && (
                  <div className={`font-mono text-[11px] tabular-nums ${up ? "text-call" : "text-put"}`}>
                    {up ? "+" : ""}
                    {q.netChange.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                  </div>
                )}
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
}
