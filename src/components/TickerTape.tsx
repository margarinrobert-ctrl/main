"use client";

import { useEffect, useState } from "react";
import { loadQuote } from "@/lib/client-data";
import { withBase } from "@/lib/paths";
import { Provenance } from "./Provenance";

const SYMBOLS = ["SPY", "QQQ", "NVDA", "TSLA", "AAPL", "AMD", "META", "ES", "NQ"];

interface Q {
  sym: string;
  last: number | null;
  chg: number | null;
  source: string;
}

const EDGE_FADE = "linear-gradient(90deg, transparent, #000 5%, #000 95%, transparent)";

/** Scrolling tape of live watchlist quotes (last + % change). */
export function TickerTape() {
  const [qs, setQs] = useState<Q[]>([]);
  const [source, setSource] = useState("");

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const out = await Promise.all(
        SYMBOLS.map(async (s) => {
          try {
            const r = await loadQuote(s);
            const q = r.quotes[0];
            return { sym: s, last: q?.last ?? null, chg: q?.percentChange ?? null, source: r.source };
          } catch {
            return { sym: s, last: null, chg: null, source: "" };
          }
        }),
      );
      if (cancelled) return;
      setQs(out);
      // A tape is only as trustworthy as its weakest symbol; one canned quote makes the strip
      // part canned, and showing "live" over it would be a half-truth.
      const sources = out.filter((q) => q.last != null).map((q) => q.source);
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

  if (!qs.length) {
    return (
      <div className="flex h-9 items-center rounded-lg border border-amber-400/20 bg-base px-3">
        <div className="skeleton h-3 w-full" />
      </div>
    );
  }

  const item = (q: Q, key: string) => (
    <span key={key} className="inline-flex items-center">
      <a
        href={withBase(`/ticker/${q.sym}`)}
        className="mx-3 inline-flex h-9 items-center gap-1.5 rounded px-1 transition hover:opacity-80"
      >
        <span className="font-semibold text-amber-400">{q.sym}</span>
        <span className="font-mono tabular-nums text-neutral-300">
          {q.last != null ? q.last.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}
        </span>
        <span className={`font-mono tabular-nums ${(q.chg ?? 0) >= 0 ? "text-call" : "text-put"}`}>
          {q.chg != null ? `${q.chg >= 0 ? "▲" : "▼"} ${Math.abs(q.chg).toFixed(2)}%` : ""}
        </span>
      </a>
      <span aria-hidden className="text-white/15">
        ·
      </span>
    </span>
  );

  return (
    <div className="space-y-1.5">
      <Provenance source={source} feed="quotes" />
    <div className="h-9 overflow-hidden rounded-lg border border-amber-400/20 bg-base font-mono text-xs">
      <div className="h-full" style={{ maskImage: EDGE_FADE, WebkitMaskImage: EDGE_FADE }}>
        <div className="flex h-full w-max animate-marquee items-center whitespace-nowrap">
          <div className="flex items-center">{qs.map((q) => item(q, `a-${q.sym}`))}</div>
          <div className="flex items-center" aria-hidden>
            {qs.map((q) => item(q, `b-${q.sym}`))}
          </div>
        </div>
      </div>
    </div>
    </div>
  );
}
