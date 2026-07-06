"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { loadQuote } from "@/lib/client-data";
import type { NormalizedQuote } from "@/lib/barchart/types";
import { EmptyState, ErrorState, Loading, SectionHeader } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

function fmt(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : n.toFixed(2);
}

export function QuoteCard({ symbol }: { symbol: string }) {
  const [quote, setQuote] = useState<NormalizedQuote | null>(null);
  const [source, setSource] = useState("");
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");
  const [flash, setFlash] = useState<"up" | "down" | null>(null);
  const prevLast = useRef<number | null>(null);

  const load = useCallback(async () => {
    setState("loading");
    try {
      const { quotes, source } = await loadQuote(symbol);
      setSource(source);
      const q = quotes[0];
      if (!q) {
        setState("empty");
        return;
      }
      setQuote(q);
      setState("ok");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error");
      setState("error");
    }
  }, [symbol]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const ms = Number(process.env.NEXT_PUBLIC_REFRESH_MS ?? 60000) || 0;
    if (ms <= 0) return;
    const id = setInterval(() => load(), ms);
    return () => clearInterval(id);
  }, [load]);

  /* 300ms price flash on change — presentation only. */
  const last = quote?.last ?? null;
  useEffect(() => {
    const prev = prevLast.current;
    prevLast.current = last;
    if (last == null || prev == null || last === prev) return;
    setFlash(last > prev ? "up" : "down");
    const id = setTimeout(() => setFlash(null), 300);
    return () => clearTimeout(id);
  }, [last]);

  const up = (quote?.netChange ?? 0) >= 0;
  const sign = up ? "+" : "−";
  const flashCls = flash === "up" ? "bg-call/10" : flash === "down" ? "bg-put/10" : "bg-transparent";

  return (
    <div className="glass glass-hover fade-up p-4">
      <SectionHeader
        eyebrow="Quote"
        title={symbol}
        right={
          <button onClick={load} className="btn text-xs">
            Refresh
          </button>
        }
      />

      {state === "loading" && <Loading label="Loading quote…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No quote available." />}
      {state === "ok" && quote && (
        <div>
          {quote.name && <div className="lbl mb-1">{quote.name}</div>}
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span
              className={`-mx-1.5 rounded-lg px-1.5 font-mono text-3xl tabular-nums leading-tight text-neutral-50 transition-colors duration-300 ${flashCls}`}
            >
              {fmt(quote.last)}
            </span>
            <span className={`inline-flex items-center gap-1.5 font-mono text-sm tabular-nums ${up ? "text-call" : "text-put"}`}>
              <svg aria-hidden viewBox="0 0 8 8" className="h-2 w-2">
                {up ? <path fill="currentColor" d="M4 1 7.5 7h-7L4 1Z" /> : <path fill="currentColor" d="M4 7 .5 1h7L4 7Z" />}
              </svg>
              {quote.netChange == null ? "—" : `${sign}${Math.abs(quote.netChange).toFixed(2)}`}
              <span className="text-neutral-500">·</span>
              {quote.percentChange == null ? "—" : `${sign}${Math.abs(quote.percentChange).toFixed(2)}%`}
            </span>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3 border-t border-white/5 pt-3">
            <div>
              <div className="lbl">Volume</div>
              <div className="mt-1 font-mono text-sm tabular-nums text-neutral-200">
                {quote.volume?.toLocaleString() ?? "—"}
              </div>
            </div>
            <div className="min-w-0">
              <div className="lbl">Last trade</div>
              <div className="mt-1 truncate font-mono text-sm tabular-nums text-neutral-400">
                {quote.tradeTimestamp ?? "—"}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
