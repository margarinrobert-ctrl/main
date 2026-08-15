"use client";

import { useCallback, useEffect, useState } from "react";
import { loadChain } from "@/lib/client-data";
import { buildGexPine, type PineResult } from "@/lib/pine";
import { buildFuturesPine } from "@/lib/futuresPine";
import { atmIv } from "@/lib/flow/analytics";
import { EmptyState, ErrorState, Loading, SectionHeader } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

export function PineExport({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
  const [result, setResult] = useState<PineResult | null>(null);
  const [source, setSource] = useState("");
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  // Two independent exports: the equity GEX map, and the 0DTE 1:1 futures scripts (separate files).
  const [kind, setKind] = useState<"gex" | "NQ1!" | "ES1!">("gex");
  const [futIv, setFutIv] = useState<{ nq: number | null; es: number | null }>({ nq: null, es: null });

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
      // Seed the futures scripts' vol from THIS symbol when it is the matching proxy (QQQ→NQ, SPY→ES).
      const sym = symbol.toUpperCase();
      if (sym === "QQQ" || sym === "SPY") {
        const exps = [...new Map(chain.map((c) => [c.expiration, c.dte])).entries()]
          .filter(([, d]) => d != null && (d as number) >= 0)
          .sort((a, b) => (a[1] as number) - (b[1] as number));
        let iv: number | null = null;
        for (const [e] of exps) {
          const v = atmIv(chain, spot, e);
          if (v != null && v > 0) {
            iv = v * 100;
            break;
          }
        }
        if (iv != null) setFutIv((prev) => (sym === "QQQ" ? { ...prev, nq: iv } : { ...prev, es: iv }));
      }
      setState("ok");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error");
      setState("error");
    }
  }, [symbol, exp]);

  useEffect(() => {
    load();
  }, [load]);

  const futures =
    kind === "NQ1!"
      ? buildFuturesPine({ contract: "NQ1!", step: 40, ivPct: futIv.nq, proxy: "QQQ" })
      : kind === "ES1!"
        ? buildFuturesPine({ contract: "ES1!", step: 10, ivPct: futIv.es, proxy: "SPY" })
        : null;
  const activeCode = futures ? futures.code : (result?.code ?? "");
  const fileName = futures ? `OF_0DTE_1to1_${futures.contract.replace("!", "")}.pine` : `GEX_${symbol}.pine`;

  const copy = async () => {
    if (!activeCode) return;
    try {
      await navigator.clipboard.writeText(activeCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setError("Clipboard blocked — select the code and copy manually.");
    }
  };

  const download = () => {
    if (!activeCode) return;
    const url = URL.createObjectURL(new Blob([activeCode], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = fileName;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="glass glass-hover fade-up p-4 sm:p-5">
      <SectionHeader
        eyebrow="TradingView export"
        title={symbol}
        right={
          futures ? (
            <span className="lbl">{futures.contract} · {futures.step}-pt grid · 1:1</span>
          ) : result?.expiration ? (
            <span className="lbl">Exp {result.expiration} · {result.strikes} strikes</span>
          ) : undefined
        }
      />

      <div className="mb-3 flex flex-wrap items-center gap-1">
        {([
          { k: "gex" as const, l: "GEX levels (equity)" },
          { k: "NQ1!" as const, l: "NQ1! · 0DTE 1:1 (40 pt)" },
          { k: "ES1!" as const, l: "ES1! · 0DTE 1:1 (10 pt)" },
        ]).map((o) => (
          <button
            key={o.k}
            onClick={() => setKind(o.k)}
            aria-pressed={kind === o.k}
            className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${kind === o.k ? "bg-accent/15 text-accent-bright" : "text-neutral-400 hover:bg-white/5 hover:text-neutral-200"}`}
          >
            {o.l}
          </button>
        ))}
      </div>

      {futures ? (
        <p className="mb-4 max-w-3xl text-xs leading-relaxed text-neutral-400">
          A standalone <span className="text-neutral-200">{futures.contract}</span> indicator: a{" "}
          <span className="text-neutral-200">{futures.step}-point</span> round-number grid of intraday levels, each evaluated as a
          symmetric <span className="text-neutral-200">1:1 bracket</span> (risk = reward = {futures.step} pts) for the rest of
          today&apos;s session. Black-Scholes converted to futures (<span className="text-accent-bright">Black-76</span> — the future
          is the forward, so no dividend yield and zero drift). It draws each level with its{" "}
          <span className="text-call">P(touch)</span>, <span className="text-neutral-200">win rate</span> and{" "}
          <span className="text-neutral-200">E[R]</span>, and shades the best setup&apos;s bracket. Every probability is recomputed{" "}
          <span className="text-neutral-200">live</span> by TradingView — only the vol seed is baked.
        </p>
      ) : (
      <p className="mb-4 max-w-3xl text-xs leading-relaxed text-neutral-400">
        Compiles the current dealer map into a Pine v6 indicator — <span className="text-put">Call Resistance</span>,{" "}
        <span className="text-call">Put Support</span>, <span className="text-violet-300">HVL</span> (γ-flip), their 0DTE
        variants, the GEX ladder, <span className="text-amber-300">expected-move bands &amp; Max Pain</span>, OI walls and
        the delta-weighted <span className="text-call">Delta Support</span> / <span className="text-put">Resistance</span>{" "}
        walls. Paste into TradingView&apos;s Pine Editor, save, and add to chart.
      </p>
      )}

      {state === "loading" && !futures && <Loading label="Building Pine…" />}
      {state === "error" && !futures && <ErrorState message={error} />}
      {state === "empty" && !futures && <EmptyState label="No options data to build levels from." />}
      {(futures || (state === "ok" && result)) && (
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
            <code>{activeCode}</code>
          </pre>
          {futures ? (
            <p className="mt-3 border-t border-white/[0.05] pt-3 text-[11px] leading-relaxed text-neutral-600">
              Apply to <span className="text-neutral-400">{futures.contract}</span> on an intraday chart. Honest baseline, stated in the
              script: for a symmetric ±R bracket on a futures price (a martingale), optional stopping forces P(target first) =
              <span className="text-neutral-400"> exactly 50%</span> — independent of level, R and vol. So a 1:1 bracket has no edge from
              geometry, and with the drift input at 0 every level correctly prints 50% / 0.00R. What genuinely varies is P(touch) and
              whether the bracket resolves before the bell; set a session drift only if you actually hold that view. Educational — not advice.
            </p>
          ) : (
          <p className="mt-3 border-t border-white/[0.05] pt-3 text-[11px] leading-relaxed text-neutral-600">
            Labels are short — hover any label on the chart for its full OI / Volume / GEX / DEX; close levels auto-stagger.
            Values are a snapshot baked at generate time, so re-generate for fresh levels. To overlay on ES or NQ, keep the
            indicator&apos;s &quot;Convert levels to this chart&quot; on Auto — it scales by the live price ratio, locked on
            load so the levels stay put.
          </p>
          )}
        </>
      )}
    </div>
  );
}
