"use client";

import { useCallback, useEffect, useState } from "react";
import { loadChain } from "@/lib/client-data";
import { buildGexPine, type PineResult } from "@/lib/pine";
import { EmptyState, ErrorState, Loading, SectionHeader } from "./states";

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
      const { chain, spot, source, asOf } = await loadChain(symbol);
      setSource(source);
      if (!chain.length) {
        setState("empty");
        return;
      }
      setResult(buildGexPine(symbol, chain, spot, 10, exp, asOf));
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
    <div className="glass glass-hover fade-up p-4 sm:p-5">
      <SectionHeader
        eyebrow="TradingView export"
        title={symbol}
        right={result?.expiration ? <span className="lbl">Exp {result.expiration} · {result.strikes} strikes</span> : undefined}
      />

      <p className="mb-4 max-w-3xl text-xs leading-relaxed text-neutral-400">
        Compiles the current dealer map into a Pine v6 indicator — <span className="text-put">Call Resistance</span>,{" "}
        <span className="text-call">Put Support</span>, <span className="text-violet-300">HVL</span> (γ-flip), their 0DTE
        variants, the GEX ladder, <span className="text-amber-300">expected-move bands &amp; Max Pain</span>, OI walls and
        the delta-weighted <span className="text-call">Delta Support</span> / <span className="text-put">Resistance</span>{" "}
        walls. Paste into TradingView&apos;s Pine Editor, save, and add to chart.
      </p>

      {state === "loading" && <Loading label="Building Pine…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options data to build levels from." />}
      {state === "ok" && result && (
        <>
          <div className="mb-3 flex flex-wrap gap-2">
            <button onClick={copy} className="btn btn-primary">
              {copied ? "Copied ✓" : "Copy Pine"}
            </button>
            <button onClick={download} className="btn">
              Download .pine
            </button>
            <button onClick={load} className="btn">
              Re-generate
            </button>
          </div>
          <pre className="max-h-[420px] overflow-auto rounded-xl border border-white/10 bg-[#07080c] p-4 text-[11px] leading-relaxed text-neutral-200 shadow-panel">
            <code>{result.code}</code>
          </pre>
          <p className="mt-3 border-t border-white/[0.05] pt-3 text-[11px] leading-relaxed text-neutral-600">
            Labels are short — hover any label on the chart for its full OI / Volume / GEX / DEX; close levels auto-stagger.
            Values are a snapshot baked at generate time, so re-generate for fresh levels. To overlay on ES or NQ, keep the
            indicator&apos;s &quot;Convert levels to this chart&quot; on Auto — it scales by the live price ratio, locked on
            load so the levels stay put.
          </p>
        </>
      )}
    </div>
  );
}
