"use client";

import { useEffect, useMemo, useState } from "react";
import type { HistoryBar, OptionContract } from "@/lib/barchart/types";
import { loadChain, loadHistory } from "@/lib/client-data";
import { buildHarvestReport, type HarvestLeg, type HarvestSide, type HarvestSignal } from "@/lib/flow/harvest";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

const sideChip: Record<HarvestSide, string> = {
  bullish: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  bearish: "border-red-500/40 bg-red-500/10 text-red-300",
  neutral: "border-sky-500/40 bg-sky-500/10 text-sky-300",
};
const sideBorder: Record<HarvestSide, string> = {
  bullish: "border-l-emerald-500",
  bearish: "border-l-red-500",
  neutral: "border-l-sky-500",
};

const pct = (n: number | null) => (n == null ? "—" : `${(n * 100).toFixed(1)}%`);
const usd0 = (n: number | null) => (n == null ? "—" : `$${Math.round(n).toLocaleString()}`);
const dlt = (d: number | null) => (d == null ? "" : ` (${Math.round(Math.abs(d) * 100)}Δ)`);

function regimeStyle(r: string) {
  if (r === "harvest") return "border-emerald-500/40 bg-emerald-500/10 text-emerald-300";
  if (r === "avoid") return "border-red-500/40 bg-red-500/10 text-red-300";
  return "border-amber-500/40 bg-amber-500/10 text-amber-300";
}
function scoreStyle(s: number) {
  return s >= 70 ? "bg-emerald-900 text-emerald-200" : s >= 45 ? "bg-amber-900 text-amber-200" : "bg-neutral-800 text-neutral-300";
}

function Leg({ leg }: { leg: HarvestLeg }) {
  const sell = leg.action === "sell";
  return (
    <span className={`rounded px-1.5 py-0.5 text-[11px] font-mono ${sell ? "bg-emerald-500/10 text-emerald-300" : "bg-red-500/10 text-red-300"}`}>
      {sell ? "SELL" : "BUY"} {leg.strike}
      {leg.type === "call" ? "C" : "P"}
      {dlt(leg.delta)}
    </span>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-neutral-500">{label}</div>
      <div className={`font-mono text-sm ${tone ?? "text-neutral-100"}`}>{value}</div>
    </div>
  );
}

function SignalCard({ s }: { s: HarvestSignal }) {
  return (
    <div className={`rounded-md border border-white/5 border-l-4 bg-white/[0.02] p-3 ${sideBorder[s.side]}`}>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="font-medium text-neutral-100">{s.name}</span>
          <span className={`rounded-full border px-2 py-0.5 text-[11px] ${sideChip[s.side]}`}>{s.side}</span>
        </div>
        <span className={`inline-block rounded px-2 py-0.5 text-center font-mono text-xs ${scoreStyle(s.score)}`} title="VRP-weighted conviction (0–100)">
          {s.score}
        </span>
      </div>

      <div className="mb-2 flex flex-wrap gap-1">
        {s.legs.map((l, i) => (
          <Leg key={i} leg={l} />
        ))}
      </div>

      <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
        <Metric label="Credit" value={`$${s.credit.toFixed(2)}`} tone="text-emerald-300" />
        <Metric label="Max profit" value={usd0(s.maxProfit)} tone="text-emerald-300" />
        <Metric label="Max loss" value={s.maxLoss == null ? "undef." : usd0(s.maxLoss)} tone={s.maxLoss == null ? "text-red-300" : "text-red-300"} />
        <Metric label="POP" value={pct(s.pop)} />
        <Metric label="Theta/day" value={s.thetaDay == null ? "—" : `$${s.thetaDay.toFixed(0)}`} tone="text-emerald-300" />
        <Metric label={s.dte != null ? `ROM (${s.dte}d)` : "ROM"} value={s.rom == null ? "—" : `${(s.rom * 100).toFixed(1)}%`} />
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-neutral-500">
        <span>
          Breakeven{s.breakevens.length > 1 ? "s" : ""}:{" "}
          <span className="font-mono text-neutral-300">{s.breakevens.map((b) => b.toFixed(2)).join(" / ")}</span>
        </span>
        {s.romAnnual != null && (
          <span>
            Annualized ROM: <span className="font-mono text-neutral-300">{(s.romAnnual * 100).toFixed(0)}%</span>
          </span>
        )}
        {s.capital != null && (
          <span>
            Capital: <span className="font-mono text-neutral-300">{usd0(s.capital)}</span>
          </span>
        )}
      </div>

      <p className="mt-2 text-xs text-neutral-400">{s.rationale}</p>
    </div>
  );
}

export function HarvestPanel({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
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

  const r = useMemo(() => buildHarvestReport(chain, spot, bars, exp), [chain, spot, bars, exp]);

  return (
    <div className="glass p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Premium Harvesting · {symbol}</h2>
        <span className="text-xs text-neutral-500">volatility risk premium → credit signals</span>
      </div>

      {state === "loading" && <Loading label="Scanning for premium…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options data to harvest." />}
      {state === "ok" && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className={`rounded-full border px-3 py-1 text-sm font-medium ${regimeStyle(r.regime)}`}>
              {r.regime === "harvest" ? "SELL premium" : r.regime === "avoid" ? "AVOID selling" : "Selective"}
            </span>
            {r.expiration && (
              <span className="rounded-full border border-white/15 px-3 py-1 text-xs text-neutral-300">
                Harvesting {r.expiration}
                {r.dte != null ? ` · ${r.dte}d` : ""}
              </span>
            )}
          </div>

          <p className="mb-3 text-sm text-neutral-300">{r.headline}</p>

          <div className="mb-4 grid grid-cols-3 gap-3 text-sm sm:grid-cols-4 lg:grid-cols-7">
            <Metric label="ATM IV" value={pct(r.iv)} />
            <Metric label="Realized 20d" value={pct(r.rv)} />
            <Metric
              label="VRP"
              value={r.vrpRatio == null ? "—" : `${r.vrpRatio.toFixed(2)}×`}
              tone={r.vrpRatio == null ? undefined : r.vrpRatio >= 1.1 ? "text-emerald-300" : r.vrpRatio <= 0.95 ? "text-red-300" : "text-amber-300"}
            />
            <Metric label="Term" value={r.termShape} />
            <Metric label="25Δ skew" value={r.skew == null ? "—" : `${r.skew >= 0 ? "+" : ""}${(r.skew * 100).toFixed(1)}`} />
            <Metric label="±1σ move" value={r.emExp == null ? "—" : `±${r.emExp.toFixed(2)}`} />
            <Metric
              label="Walls P/C"
              value={`${r.putWall ?? "—"} / ${r.callWall ?? "—"}`}
            />
          </div>

          {r.signals.length === 0 ? (
            <EmptyState label="No clean credit structures at the target deltas for this expiration." />
          ) : (
            <div className="space-y-2">
              {r.signals.map((s) => (
                <SignalCard key={s.name} s={s} />
              ))}
            </div>
          )}

          <div className="mt-4 space-y-1">
            {r.notes.map((n) => (
              <p key={n} className="text-[11px] text-neutral-500">
                {n}
              </p>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
