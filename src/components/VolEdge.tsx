"use client";

import { useEffect, useMemo, useState } from "react";
import type { HistoryBar, OptionContract } from "@/lib/barchart/types";
import { loadChain, loadHistory } from "@/lib/client-data";
import { buildVolReport, type VolSide } from "@/lib/flow/voledge";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

const chip: Record<VolSide, string> = {
  "short-vol": "border-amber-500/40 bg-amber-500/10 text-amber-300",
  "long-vol": "border-sky-500/40 bg-sky-500/10 text-sky-300",
  neutral: "border-neutral-500/40 bg-neutral-500/10 text-neutral-300",
  info: "border-white/15 bg-white/5 text-neutral-300",
};
const leftBorder: Record<VolSide, string> = {
  "short-vol": "border-l-amber-500",
  "long-vol": "border-l-sky-500",
  neutral: "border-l-neutral-500",
  info: "border-l-white/20",
};
const sideLabel: Record<VolSide, string> = { "short-vol": "Sell vol", "long-vol": "Buy vol", neutral: "Neutral", info: "Info" };

const pct = (n: number | null) => (n == null ? "—" : `${(n * 100).toFixed(1)}%`);

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="rounded border border-white/10 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-neutral-500">{label}</div>
      <div className={`font-mono text-lg ${tone ?? "text-neutral-100"}`}>{value}</div>
      {sub ? <div className="text-[11px] text-neutral-500">{sub}</div> : null}
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

  const vrpTone = r.vrpRatio == null ? undefined : r.vrpRatio >= 1.2 ? "text-amber-300" : r.vrpRatio <= 0.95 ? "text-sky-300" : "text-neutral-100";

  return (
    <div className="glass p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Vol Edge · {symbol}</h2>
        <span className="text-xs text-neutral-500">volatility risk premium · term structure · skew · src: {source}</span>
      </div>

      {state === "loading" && <Loading label="Measuring vol…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options data to measure volatility." />}
      {state === "ok" && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3 lg:grid-cols-5">
            <Stat label="ATM IV (front)" value={pct(r.atmIv)} sub="implied" />
            <Stat label="Realized 20d" value={pct(r.rv20)} sub={`10d ${pct(r.rv10)}`} />
            <Stat
              label="VRP (IV/RV)"
              value={r.vrpRatio == null ? "—" : `${r.vrpRatio.toFixed(2)}×`}
              sub={r.vrpAbs == null ? "" : `${r.vrpAbs >= 0 ? "+" : ""}${(r.vrpAbs * 100).toFixed(1)} pts`}
              tone={vrpTone}
            />
            <Stat label="Term" value={r.termShape} sub={`${pct(r.termFront)} → ${pct(r.termBack)}`} />
            <Stat label="25Δ skew" value={r.skew == null ? "—" : `${r.skew >= 0 ? "+" : ""}${(r.skew * 100).toFixed(1)} pts`} sub="put − call IV" />
          </div>

          <div className="space-y-2">
            {r.reads.map((rd) => (
              <div key={rd.title} className={`rounded-md border border-white/5 border-l-4 bg-white/[0.02] p-3 ${leftBorder[rd.side]}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-neutral-100">{rd.title}</span>
                  <span className={`rounded-full border px-2 py-0.5 text-[11px] ${chip[rd.side]}`}>{sideLabel[rd.side]}</span>
                </div>
                <p className="mt-1 text-xs text-neutral-400">{rd.detail}</p>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
