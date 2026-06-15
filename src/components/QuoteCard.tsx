"use client";

import { useCallback, useEffect, useState } from "react";
import { EmptyState, ErrorState, Loading } from "./states";

interface Quote {
  symbol: string;
  name: string | null;
  last: number | null;
  netChange: number | null;
  percentChange: number | null;
  volume: number | null;
  tradeTimestamp: string | null;
  delayed: boolean | null;
}

type ViewState = "loading" | "error" | "empty" | "ok";

function fmt(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : n.toFixed(2);
}

export function QuoteCard({ symbol }: { symbol: string }) {
  const [quote, setQuote] = useState<Quote | null>(null);
  const [source, setSource] = useState("");
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setState("loading");
    try {
      const res = await fetch(`/api/barchart/quote?symbol=${encodeURIComponent(symbol)}`, { cache: "no-store" });
      const json = await res.json();
      if (!res.ok) {
        setError(json?.error ?? "Request failed");
        setState("error");
        return;
      }
      setSource(json.source ?? "");
      const q: Quote | undefined = json.quotes?.[0];
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

  const up = (quote?.netChange ?? 0) >= 0;

  return (
    <div className="max-w-md rounded-lg border border-neutral-800 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-semibold">{symbol}</h2>
        <button
          onClick={load}
          className="rounded bg-neutral-800 px-2 py-1 text-xs hover:bg-neutral-700"
        >
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
          <div className="mt-1 text-xs text-neutral-500">
            {quote.delayed === true ? "Delayed" : quote.delayed === false ? "Real-time" : "Timeliness unknown"}
            {quote.tradeTimestamp ? ` · ${quote.tradeTimestamp}` : ""} · src: {source}
          </div>
        </div>
      )}
    </div>
  );
}
