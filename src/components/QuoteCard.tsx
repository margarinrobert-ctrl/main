"use client";

import { useCallback, useEffect, useState } from "react";
import { loadQuote } from "@/lib/client-data";
import type { NormalizedQuote } from "@/lib/barchart/types";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

function fmt(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : n.toFixed(2);
}

export function QuoteCard({ symbol }: { symbol: string }) {
  const [quote, setQuote] = useState<NormalizedQuote | null>(null);
  const [source, setSource] = useState("");
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");

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

  const up = (quote?.netChange ?? 0) >= 0;

  return (
    <div className="max-w-md glass p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-semibold">{symbol}</h2>
        <button onClick={load} className="rounded bg-neutral-800 px-2 py-1 text-xs hover:bg-neutral-700">
          Refresh
        </button>
      </div>

      {state === "loading" && <Loading />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No quote available." />}
      {state === "ok" && quote && (
        <div>
          <div className="font-mono text-2xl">{fmt(quote.last)}</div>
          <div className={`text-sm ${up ? "text-emerald-400" : "text-red-400"}`}>
            {fmt(quote.netChange)} ({fmt(quote.percentChange)}%)
          </div>
          <div className="mt-2 text-xs text-neutral-400">
            {quote.name ?? ""} · vol {quote.volume?.toLocaleString() ?? "—"}
          </div>
          {quote.tradeTimestamp && <div className="mt-1 text-xs text-neutral-500">{quote.tradeTimestamp}</div>}
        </div>
      )}
    </div>
  );
}
