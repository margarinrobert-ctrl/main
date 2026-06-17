"use client";

import { useCallback, useEffect, useState } from "react";
import { loadChain } from "@/lib/client-data";
import { buildGexPine, type PineResult } from "@/lib/pine";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

export function PineExport({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
  const [result, setResult] = useState<PineResult | null>(null);
  const [source, setSource] = useState("");
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    setState("loading");
    try {
      const { chain, spot, source } = await loadChain(symbol);
      setSource(source);
      if (!chain.length) {
        setState("empty");
        return;
      }
      setResult(buildGexPine(symbol, chain, spot, 10, exp));
      setState("ok");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error");
      setState("error");
    }
  }, [symbol, exp]);

  useEffect(() => {
    load();
  }, [load]);

  const copy = async () => {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result.code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setError("Clipboard blocked — select the code and copy manually.");
    }
  };

  const download = () => {
    if (!result) return;
    const url = URL.createObjectURL(new Blob([result.code], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `GEX_${symbol}.pine`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="glass p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">TradingView Pine · {symbol}</h2>
        <span className="text-xs text-neutral-500">
          {result?.expiration ? `exp ${result.expiration} · ${result.strikes} strikes · ` : ""}src: {source}
        </span>
      </div>

      <p className="mb-3 text-xs text-neutral-400">
        Generates a Pine v6 indicator with named GEX levels — <span className="text-red-400">Call Resistance</span>{" "}
        (above spot), <span className="text-green-400">Put Support</span> (below spot),{" "}
        <span className="text-blue-400">HVL</span> (γ-flip), their <b>0DTE</b> variants, the{" "}
        <span className="text-teal-300">GEX 1…N</span> ladder, <span className="text-amber-400">1D Max/Min</span>,{" "}
        <span className="text-yellow-300">Max Pain</span> and the <span className="text-lime-400">Call/Put OI</span> walls.
        Copy into TradingView → <b>Pine Editor</b> → paste → <b>Save</b> → <b>Add to chart</b>. Re-generate to refresh.
      </p>

      {state === "loading" && <Loading label="Building Pine…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options data to build levels from." />}
      {state === "ok" && result && (
        <>
          <div className="mb-2 flex flex-wrap gap-2">
            <button onClick={copy} className="rounded bg-emerald-600 px-3 py-1 text-sm font-medium hover:bg-emerald-500">
              {copied ? "Copied ✓" : "Copy Pine"}
            </button>
            <button onClick={download} className="rounded bg-neutral-800 px-3 py-1 text-sm hover:bg-neutral-700">
              Download .pine
            </button>
            <button onClick={load} className="rounded bg-neutral-800 px-3 py-1 text-sm hover:bg-neutral-700">
              Re-generate
            </button>
          </div>
          <pre className="max-h-[420px] overflow-auto rounded-lg border border-white/10 bg-black/50 p-3 text-[11px] leading-relaxed text-neutral-200">
            <code>{result.code}</code>
          </pre>
          <p className="mt-2 text-[11px] text-neutral-500">
            Note: TradingView has no public API to auto-add scripts to an account, so this is copy/paste (save it once as
            an indicator and it stays on your charts). Levels are a delayed snapshot, not a live TradingView feed.
          </p>
        </>
      )}
    </div>
  );
}
