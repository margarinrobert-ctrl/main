"use client";

import { useEffect, useMemo, useState } from "react";
import type { HistoryBar, OptionContract } from "@/lib/barchart/types";
import { loadChain, loadHistory } from "@/lib/client-data";
import { buildHarvestReport, type HarvestLeg, type HarvestSide, type HarvestSignal } from "@/lib/flow/harvest";
import { EmptyState, ErrorState, Loading, SectionHeader } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

const sideChip: Record<HarvestSide, string> = {
  bullish: "border-call/30 bg-call/10 text-call",
  bearish: "border-put/30 bg-put/10 text-put",
  neutral: "border-white/10 bg-white/[0.03] text-neutral-300",
};
const sideBorder: Record<HarvestSide, string> = {
  bullish: "border-l-call/80",
  bearish: "border-l-put/80",
  neutral: "border-l-accent-cyan/60",
};
const sideLabel: Record<HarvestSide, string> = { bullish: "Bullish", bearish: "Bearish", neutral: "Neutral" };

const pct = (n: number | null) => (n == null ? "—" : `${(n * 100).toFixed(1)}%`);
const usd0 = (n: number | null) => (n == null ? "—" : `$${Math.round(n).toLocaleString()}`);
const dlt = (d: number | null) => (d == null ? "" : ` (${Math.round(Math.abs(d) * 100)}Δ)`);

function regimeStyle(r: string) {
  if (r === "harvest") return "border-call/30 bg-call/10 text-call";
  if (r === "avoid") return "border-put/30 bg-put/10 text-put";
  return "border-amber-400/30 bg-amber-400/10 text-amber-300";
}
function scoreStyle(s: number) {
  return s >= 70 ? "border-call/40 bg-call/10 text-call" : s >= 45 ? "border-amber-400/40 bg-amber-400/10 text-amber-300" : "border-white/10 bg-white/[0.03] text-neutral-300";
}

function Leg({ leg }: { leg: HarvestLeg }) {
  const sell = leg.action === "sell";
  return (
    <span className={`inline-flex items-center rounded-md border px-1.5 py-0.5 font-mono text-[11px] ${sell ? "border-call/25 bg-call/[0.08] text-call" : "border-put/25 bg-put/[0.08] text-put"}`}>
      {sell ? "−" : "+"}&nbsp;{sell ? "SELL" : "BUY"} {leg.strike}
      {leg.type === "call" ? "C" : "P"}
      {dlt(leg.delta)}
    </span>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="px-3 py-2.5">
      <div className="lbl">{label}</div>
      <div className={`mt-0.5 font-mono text-sm tabular-nums ${tone ?? "text-neutral-100"}`}>{value}</div>
    </div>
  );
}

/** Payoff-at-expiry diagram, evaluated directly from the structure's legs (pure presentation). */
function PayoffSpark({ s }: { s: HarvestSignal }) {
  const strikes = s.legs.map((l) => l.strike);
  if (!strikes.length) return null;
  const lo = Math.min(...strikes);
  const hi = Math.max(...strikes);
  const pad = Math.max((hi - lo) * 0.6, hi * 0.015);
  const x0 = lo - pad;
  const x1 = hi + pad;
  const N = 60;
  const payoff = (x: number) =>
    s.credit + s.legs.reduce((sum, l) => sum + (l.action === "buy" ? 1 : -1) * (l.type === "call" ? Math.max(0, x - l.strike) : Math.max(0, l.strike - x)), 0);
  const ys = Array.from({ length: N + 1 }, (_, i) => payoff(x0 + ((x1 - x0) * i) / N));
  const yMax = Math.max(...ys.map(Math.abs), 0.01);
  const W = 120;
  const H = 36;
  const px = (i: number) => (i / N) * W;
  const py = (y: number) => H / 2 - (y / yMax) * (H / 2 - 3);
  const line = ys.map((y, i) => `${px(i).toFixed(1)},${py(y).toFixed(1)}`).join(" ");
  const area = (sign: 1 | -1) =>
    `${ys.map((y, i) => `${px(i).toFixed(1)},${py(sign > 0 ? Math.max(0, y) : Math.min(0, y)).toFixed(1)}`).join(" ")} ${W},${H / 2} 0,${H / 2}`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-10 w-28 shrink-0" aria-hidden>
      <polygon points={area(1)} fill="rgba(52,211,153,0.14)" />
      <polygon points={area(-1)} fill="rgba(248,113,113,0.12)" />
      <line x1="0" y1={H / 2} x2={W} y2={H / 2} stroke="rgba(255,255,255,0.15)" strokeWidth="0.75" />
      <polyline points={line} fill="none" stroke="rgba(250,250,250,0.75)" strokeWidth="1.1" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function SignalCard({ s }: { s: HarvestSignal }) {
  return (
    <div className={`rounded-xl border border-white/[0.06] border-l-2 bg-white/[0.02] p-3.5 transition-colors hover:border-white/[0.14] hover:bg-white/[0.035] ${sideBorder[s.side]}`}>
      <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-neutral-100">{s.name}</span>
          <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] ${sideChip[s.side]}`}>{sideLabel[s.side]}</span>
        </div>
        <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 font-mono text-xs ${scoreStyle(s.score)}`} title="VRP-weighted conviction (0–100)">
          {s.score}
        </span>
      </div>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-wrap gap-1.5">
          {s.legs.map((l, i) => (
            <Leg key={i} leg={l} />
          ))}
        </div>
        <PayoffSpark s={s} />
      </div>

      <div className="mt-3 grid grid-cols-3 divide-x divide-white/[0.05] rounded-lg border border-white/[0.05] bg-white/[0.015] sm:grid-cols-6">
        <Metric label="Credit" value={`$${s.credit.toFixed(2)}`} tone="text-call" />
        <Metric label="Max profit" value={usd0(s.maxProfit)} tone="text-call" />
        {s.maxLoss == null ? (
          <div className="px-3 py-2.5">
            <div className="lbl">Max loss</div>
            <span className="mt-0.5 inline-flex items-center rounded-full border border-put/40 bg-put/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-put">
              Undefined risk
            </span>
          </div>
        ) : (
          <Metric label="Max loss" value={usd0(s.maxLoss)} tone="text-put" />
        )}
        <Metric label="POP" value={pct(s.pop)} />
        <Metric label="Theta/day" value={s.thetaDay == null ? "—" : `$${s.thetaDay.toFixed(0)}`} tone="text-call" />
        <Metric label={s.dte != null ? `ROM (${s.dte}d)` : "ROM"} value={s.rom == null ? "—" : `${(s.rom * 100).toFixed(1)}%`} />
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-neutral-500">
        <span>
          Breakeven{s.breakevens.length > 1 ? "s" : ""}:{" "}
          <span className="font-mono tabular-nums text-neutral-300">{s.breakevens.map((b) => b.toFixed(2)).join(" / ")}</span>
        </span>
        {s.romAnnual != null && (
          <span>
            Annualized ROM: <span className="font-mono tabular-nums text-neutral-300">{(s.romAnnual * 100).toFixed(0)}%</span>
          </span>
        )}
        {s.capital != null && (
          <span>
            Capital: <span className="font-mono tabular-nums text-neutral-300">{usd0(s.capital)}</span>
          </span>
        )}
      </div>

      <p className="mt-2.5 text-xs leading-relaxed text-neutral-400">{s.rationale}</p>
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
    <div className="glass glass-hover fade-up p-4 sm:p-5">
      <SectionHeader eyebrow="Premium structures" title={symbol} right={<span className="lbl">Volatility risk premium → credit structures</span>} />

      {state === "loading" && <Loading label="Loading structures…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options data for credit structures." />}
      {state === "ok" && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wider ${regimeStyle(r.regime)}`}>
              {r.regime === "harvest" ? "VRP rich · short-vol regime" : r.regime === "avoid" ? "VRP negative · no edge" : "Selective"}
            </span>
            {r.expiration && (
              <span className="chip">
                {r.expiration}
                {r.dte != null ? ` · ${r.dte}d` : ""}
              </span>
            )}
          </div>

          <p className="mb-4 text-sm leading-relaxed text-neutral-300">{r.headline}</p>

          <div className="mb-4 overflow-x-auto rounded-xl border border-white/[0.06] bg-white/[0.015]">
            <div className="grid min-w-[640px] grid-cols-7 divide-x divide-white/[0.05]">
              <Metric label="ATM IV" value={pct(r.iv)} />
              <Metric label="Realized 20d" value={pct(r.rv)} />
              <Metric
                label="VRP"
                value={r.vrpRatio == null ? "—" : `${r.vrpRatio.toFixed(2)}×`}
                tone={r.vrpRatio == null ? undefined : r.vrpRatio >= 1.1 ? "text-call" : r.vrpRatio <= 0.95 ? "text-put" : "text-amber-300"}
              />
              <Metric label="Term" value={r.termShape} />
              <Metric label="25Δ skew" value={r.skew == null ? "—" : `${r.skew >= 0 ? "+" : ""}${(r.skew * 100).toFixed(1)}`} />
              <Metric label="±1σ move" value={r.emExp == null ? "—" : `±${r.emExp.toFixed(2)}`} />
              <Metric label="Walls P/C" value={`${r.putWall ?? "—"} / ${r.callWall ?? "—"}`} />
            </div>
          </div>

          {r.signals.length === 0 ? (
            <EmptyState label="No credit structures at the target deltas for this expiration." />
          ) : (
            <div className="stagger space-y-2.5">
              {r.signals.map((s) => (
                <SignalCard key={s.name} s={s} />
              ))}
            </div>
          )}

          <div className="mt-4 border-t border-white/[0.05] pt-3">
            <div className="lbl mb-1.5">Model notes</div>
            <div className="space-y-1">
              {r.notes.map((n) => (
                <p key={n} className="text-[11px] leading-relaxed text-neutral-500">
                  {n}
                </p>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
