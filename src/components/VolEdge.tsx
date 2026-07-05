"use client";

import { useEffect, useMemo, useState } from "react";
import type { HistoryBar, OptionContract } from "@/lib/barchart/types";
import { loadChain, loadHistory } from "@/lib/client-data";
import { buildVolReport, type VolSide } from "@/lib/flow/voledge";
import { EmptyState, ErrorState, Loading, SectionHeader, Stat } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

const chip: Record<VolSide, string> = {
  "short-vol": "border-amber-400/30 bg-amber-400/10 text-amber-300",
  "long-vol": "border-sky-400/30 bg-sky-400/10 text-sky-300",
  neutral: "border-white/10 bg-white/[0.03] text-neutral-300",
  info: "border-accent-cyan/25 bg-accent-cyan/[0.06] text-neutral-300",
};
const leftBorder: Record<VolSide, string> = {
  "short-vol": "border-l-amber-400/70",
  "long-vol": "border-l-sky-400/70",
  neutral: "border-l-white/20",
  info: "border-l-accent-cyan/50",
};
const sideLabel: Record<VolSide, string> = { "short-vol": "Sell vol", "long-vol": "Buy vol", neutral: "Neutral", info: "Info" };

const pct = (n: number | null) => (n == null ? "—" : `${(n * 100).toFixed(1)}%`);
const shapeLabel: Record<string, string> = { contango: "Contango", backwardation: "Backwardation", flat: "Flat", "n/a": "—" };

/** Inline term-structure micro-chart: expiry IVs as a single gradient polyline. */
function TermSpark({ points }: { points: { iv: number | null }[] }) {
  const ivs = points.map((p) => p.iv).filter((v): v is number => v != null);
  if (ivs.length < 2) return null;
  const min = Math.min(...ivs);
  const max = Math.max(...ivs);
  const span = max - min || 1;
  const W = 100;
  const H = 28;
  const pts = ivs.map((v, i) => `${(i / (ivs.length - 1)) * W},${H - 4 - ((v - min) / span) * (H - 8)}`).join(" ");
  return (
    <div className="mt-3 rounded-lg border border-white/[0.05] bg-white/[0.015] px-3 py-2">
      <div className="lbl mb-1">Term structure</div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-8 w-full" aria-hidden>
        <defs>
          <linearGradient id="ts-g" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#34d399" />
            <stop offset="100%" stopColor="#22d3ee" />
          </linearGradient>
        </defs>
        <polyline points={pts} fill="none" stroke="url(#ts-g)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="mt-0.5 flex justify-between text-[10px] text-neutral-600">
        <span>front</span>
        <span>back</span>
      </div>
    </div>
  );
}

export function VolEdge({ symbol }: { symbol: string }) {
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [spot, setSpot] = useState<number | null>(null);
  const [bars, setBars] = useState<HistoryBar[]>([]);
  const [source, setSource] = useState("");
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setState("loading");
      try {
        const [ch, hi] = await Promise.all([loadChain(symbol), loadHistory(symbol).catch(() => ({ bars: [] }))]);
        if (cancelled) return;
        setChain(ch.chain);
        setSpot(ch.spot);
        setSource(ch.source);
        setBars(("bars" in hi ? hi.bars : []) as HistoryBar[]);
        setState(ch.chain.length ? "ok" : "empty");
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Network error");
          setState("error");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  const r = useMemo(() => buildVolReport(chain, spot, bars), [chain, spot, bars]);

  const vrpTone: "call" | "put" | "neutral" | undefined =
    r.vrpRatio == null ? undefined : r.vrpRatio >= 1.2 ? "put" : r.vrpRatio <= 0.95 ? "call" : "neutral";

  // Term-structure points for the sparkline (front → back), from the already-computed report bounds.
  const termPoints = useMemo(() => {
    if (r.termFront == null || r.termBack == null) return [];
    return [{ iv: r.termFront }, { iv: r.atmIv }, { iv: r.termBack }];
  }, [r.termFront, r.termBack, r.atmIv]);

  return (
    <div className="glass glass-hover fade-up p-4 sm:p-5">
      <SectionHeader eyebrow="Vol edge" title={symbol} right={<span className="lbl">VRP · term structure · skew</span>} />

      {state === "loading" && <Loading label="Loading volatility report…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options data for the volatility report." />}
      {state === "ok" && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-5">
            <Stat label="ATM IV (front)" value={pct(r.atmIv)} sub="implied" />
            <Stat label="Realized 20d" value={pct(r.rv20)} sub={`10d ${pct(r.rv10)}`} />
            <Stat
              label="VRP (IV/RV)"
              value={r.vrpRatio == null ? "—" : `${r.vrpRatio.toFixed(2)}×`}
              sub={r.vrpAbs == null ? "" : `${r.vrpAbs >= 0 ? "+" : ""}${(r.vrpAbs * 100).toFixed(1)} pts`}
              tone={vrpTone}
            />
            <Stat label="Term" value={shapeLabel[r.termShape] ?? r.termShape} sub={`${pct(r.termFront)} → ${pct(r.termBack)}`} />
            <Stat label="25Δ skew" value={r.skew == null ? "—" : `${r.skew >= 0 ? "+" : ""}${(r.skew * 100).toFixed(1)} pts`} sub="put − call IV" />
          </div>

          {termPoints.length >= 2 && <TermSpark points={termPoints} />}

          <div className="stagger mt-4 space-y-2">
            {r.reads.map((rd) => (
              <div
                key={rd.title}
                className={`rounded-xl border border-white/[0.06] border-l-2 bg-white/[0.02] p-3.5 transition-colors hover:border-white/[0.14] hover:bg-white/[0.035] ${leftBorder[rd.side]}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-medium text-neutral-100">{rd.title}</span>
                  <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] ${chip[rd.side]}`}>{sideLabel[rd.side]}</span>
                </div>
                <p className="mt-1.5 text-xs leading-relaxed text-neutral-400">{rd.detail}</p>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
