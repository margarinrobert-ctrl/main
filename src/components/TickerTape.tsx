"use client";

import { useEffect, useState } from "react";
import { loadQuote } from "@/lib/client-data";
import { withBase } from "@/lib/paths";

const SYMBOLS = ["SPY", "QQQ", "NVDA", "TSLA", "AAPL", "AMD", "META", "ES", "NQ"];

interface Q {
  sym: string;
  last: number | null;
  chg: number | null;
}

/** Bloomberg-style scrolling tape of live watchlist quotes (last + % change). */
export function TickerTape() {
  const [qs, setQs] = useState<Q[]>([]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const out = await Promise.all(
        SYMBOLS.map(async (s) => {
          try {
            const r = await loadQuote(s);
            const q = r.quotes[0];
            return { sym: s, last: q?.last ?? null, chg: q?.percentChange ?? null };
          } catch {
            return { sym: s, last: null, chg: null };
          }
        }),
      );
      if (!cancelled) setQs(out);
    };
    load();
    const ms = Math.max(20_000, Number(process.env.NEXT_PUBLIC_REFRESH_MS ?? 60_000) || 60_000);
    const id = setInterval(load, ms);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (!qs.length) return null;

  const item = (q: Q, key: string) => (
    <a key={key} href={withBase(`/ticker/${q.sym}`)} className="mx-4 inline-flex items-center gap-1.5 align-middle hover:opacity-80">
      <span className="font-semibold text-[#ffa028]">{q.sym}</span>
      <span className="font-mono text-neutral-300">{q.last != null ? q.last.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}</span>
      <span className={`font-mono ${(q.chg ?? 0) >= 0 ? "text-call" : "text-put"}`}>
        {q.chg != null ? `${q.chg >= 0 ? "▲" : "▼"} ${Math.abs(q.chg).toFixed(2)}%` : ""}
      </span>
      <span className="text-neutral-700">·</span>
    </a>
  );

  return (
    <div className="overflow-hidden border border-[#ffa028]/30 bg-black py-1.5 font-mono text-xs">
      <div className="flex w-max animate-marquee whitespace-nowrap">
        <div className="flex">{qs.map((q) => item(q, `a-${q.sym}`))}</div>
        <div className="flex" aria-hidden>
          {qs.map((q) => item(q, `b-${q.sym}`))}
        </div>
      </div>
    </div>
  );
}
