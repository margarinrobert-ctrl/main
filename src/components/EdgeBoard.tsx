"use client";

import { useEffect, useMemo, useState } from "react";
import type { HistoryBar, OptionContract } from "@/lib/barchart/types";
import { loadChain, loadHistory } from "@/lib/client-data";
import { netGex } from "@/lib/flow/analytics";
import { carryEngine, type CarryRead } from "@/lib/edge/carry";
import { volFactor, type FactorReport, type SymbolMetrics } from "@/lib/edge/factor";
import { vrpEngine, type VrpRead } from "@/lib/edge/vrp";
import { EmptyState, ErrorState, Loading, SectionHeader, Stat } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

const CROSS_DEFAULT = (process.env.NEXT_PUBLIC_WATCHLIST ?? "SPY,QQQ,NVDA,TSLA,AAPL,AMD,META")
  .split(",")
  .map((s) => s.trim().toUpperCase())
  .filter(Boolean);

const pct = (n: number | null | undefined) => (n == null ? "—" : `${(n * 100).toFixed(1)}%`);
const vp = (n: number | null | undefined) => (n == null ? "—" : `${n >= 0 ? "+" : ""}${(n * 100).toFixed(1)}vp`);

function frontExp(chain: OptionContract[]): string | null {
  const exps = [...new Set(chain.map((c) => c.expiration))].sort();
  return exps.find((e) => (chain.find((c) => c.expiration === e)?.dte ?? -1) >= 0) ?? exps[0] ?? null;
}

/** Lightweight 25-delta-ish skew proxy: OTM put IV (~0.95 moneyness) − OTM call IV (~1.05), front expiry. */
function skewProxy(chain: OptionContract[], spot: number | null): number | null {
  if (!spot) return null;
  const front = frontExp(chain);
  const opts = chain.filter((c) => c.expiration === front && c.impliedVolatility != null && c.impliedVolatility > 0);
  const puts = opts.filter((c) => c.type === "put" && c.strike < spot);
  const calls = opts.filter((c) => c.type === "call" && c.strike > spot);
  if (!puts.length || !calls.length) return null;
  const put = puts.reduce((p, c) => (Math.abs(c.strike / spot - 0.95) < Math.abs(p.strike / spot - 0.95) ? c : p));
  const call = calls.reduce((p, c) => (Math.abs(c.strike / spot - 1.05) < Math.abs(p.strike / spot - 1.05) ? c : p));
  return (put.impliedVolatility as number) - (call.impliedVolatility as number);
}

/** 0..100 conviction bar. */
function Conviction({ value, tone }: { value: number; tone: string }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="lbl">Conviction</span>
        <span className="font-mono text-xs tabular-nums text-neutral-300">{value}/100</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
        <div className={`h-full rounded-full ${tone} transition-[width] duration-500`} style={{ width: `${Math.max(2, value)}%` }} />
      </div>
    </div>
  );
}

function VrpCard({ r }: { r: VrpRead }) {
  const tone = r.side === "short-vol" ? "text-call" : r.side === "long-vol" ? "text-accent-cyan" : "text-neutral-300";
  const chip = r.side === "short-vol" ? "border-call/30 bg-call/10 text-call" : r.side === "long-vol" ? "border-accent-cyan/30 bg-accent-cyan/10 text-accent-cyan" : "border-white/10 bg-white/[0.03] text-neutral-300";
  const bar = r.side === "short-vol" ? "bg-call" : r.side === "long-vol" ? "bg-accent-cyan" : "bg-neutral-500";
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div>
          <div className="lbl">Variance risk premium</div>
          <div className="mt-0.5 text-[11px] text-neutral-500">Implied vs HAR-RV forecast realized</div>
        </div>
        <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider ${chip}`}>
          {r.side === "short-vol" ? "Sell vol · rich" : r.side === "long-vol" ? "Buy vol · cheap" : "No vol edge"}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2.5">
        <Stat label="ATM IV" value={pct(r.atmIv)} />
        <Stat label="HAR-RV forecast" value={pct(r.rvForecast)} sub={r.har.fitted ? `fit R² ${(r.har.r2 ?? 0).toFixed(2)}` : "canonical wts"} />
        <Stat label="VRP" value={r.vrpRatio == null ? "—" : `${r.vrpRatio.toFixed(2)}×`} tone={r.side === "short-vol" ? "call" : r.side === "long-vol" ? "neutral" : "neutral"} sub={vp(r.vrpVol)} />
      </div>
      <div className="mt-2.5 grid grid-cols-3 gap-2.5">
        <Stat label="Expected edge" value={r.edgeVolPts == null ? "—" : `${(r.edgeVolPts * 100).toFixed(1)}vp`} tone={r.edgeVolPts && r.edgeVolPts > 0 ? "call" : undefined} sub="est. vs forecast, if realized" />
        <Stat label="Implied daily move" value={r.impliedDailyMovePct == null ? "—" : `${(r.impliedDailyMovePct * 100).toFixed(2)}%`} sub={`fcst ${r.forecastDailyMovePct == null ? "—" : (r.forecastDailyMovePct * 100).toFixed(2) + "%"}`} />
        <Stat label="Short-straddle edge" value={r.edgeOnPremiumPct == null ? "—" : `${(r.edgeOnPremiumPct * 100).toFixed(0)}%`} sub="est. / premium · 1mo" tone={r.edgeOnPremiumPct && r.edgeOnPremiumPct > 0 ? "call" : "put"} />
      </div>
      <div className="mt-3">
        <Conviction value={r.conviction} tone={bar} />
      </div>
      <p className={`mt-3 text-xs leading-relaxed ${r.side === "neutral" ? "text-neutral-500" : "text-neutral-400"}`}>
        <span className={tone}>●</span> {r.notes[0]}
      </p>
    </div>
  );
}

function CarryCard({ r }: { r: CarryRead }) {
  const chip = r.shape === "backwardation" ? "border-put/30 bg-put/10 text-put" : r.shape === "contango" ? "border-call/30 bg-call/10 text-call" : "border-white/10 bg-white/[0.03] text-neutral-300";
  const bar = r.shape === "backwardation" ? "bg-put" : r.shape === "contango" ? "bg-call" : "bg-neutral-500";
  const label: Record<string, string> = { contango: "Contango", backwardation: "Backwardation", flat: "Flat", "n/a": "—" };
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div>
          <div className="lbl">Term-structure carry</div>
          <div className="mt-0.5 text-[11px] text-neutral-500">Front vs back tenor · roll-down</div>
        </div>
        <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider ${chip}`}>{label[r.shape]}</span>
      </div>
      <div className="grid grid-cols-3 gap-2.5">
        <Stat label={r.front ? `Front · ${r.front.dte}d` : "Front"} value={pct(r.front?.iv ?? null)} />
        <Stat label={r.back ? `Back · ${r.back.dte}d` : "Back"} value={pct(r.back?.iv ?? null)} />
        <Stat label="Slope" value={vp(r.slopeVolPts)} tone={r.slopeVolPts == null ? undefined : r.slopeVolPts >= 0 ? "call" : "put"} sub="back − front" />
      </div>
      <div className="mt-2.5 grid grid-cols-2 gap-2.5">
        <Stat label="Roll-down" value={r.rollDownVolPtsPerWeek == null ? "—" : `${(r.rollDownVolPtsPerWeek * 100).toFixed(2)}vp/wk`} sub="est. if curve holds" />
        <Stat label="Read" value={r.side === "sell-front" ? "Sell front" : r.side === "own-back-carry" ? "Own back" : "Neutral"} />
      </div>
      <div className="mt-3">
        <Conviction value={r.conviction} tone={bar} />
      </div>
      <p className="mt-3 text-xs leading-relaxed text-neutral-400">{r.notes[0]}</p>
    </div>
  );
}

/** Small signed z-bar for the cross-sectional table. */
function Zbar({ z }: { z: number | null }) {
  if (z == null) return <span className="text-neutral-600">—</span>;
  const w = Math.min(50, Math.abs(z) * 22);
  const pos = z >= 0;
  return (
    <span className="inline-flex h-3 w-[52px] items-center justify-center align-middle">
      <span className="relative h-1.5 w-full rounded-full bg-white/[0.06]">
        <span className="absolute left-1/2 top-0 h-full w-px bg-white/20" />
        <span className={`absolute top-0 h-full rounded-full ${pos ? "bg-call/70" : "bg-put/70"}`} style={{ left: pos ? "50%" : `calc(50% - ${w}%)`, width: `${w}%` }} />
      </span>
    </span>
  );
}

export function EdgeBoard({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [spot, setSpot] = useState<number | null>(null);
  const [bars, setBars] = useState<HistoryBar[]>([]);
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");
  const [factor, setFactor] = useState<FactorReport | null>(null);
  const [factorLoading, setFactorLoading] = useState(true);

  // Current symbol: chain + bars for the per-symbol edge stack.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setState("loading");
      try {
        const [ch, hi] = await Promise.all([loadChain(symbol), loadHistory(symbol).catch(() => ({ bars: [] as HistoryBar[] }))]);
        if (cancelled) return;
        setChain(ch.chain);
        setSpot(ch.spot);
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

  // Cross-sectional factor across the watchlist (lazy, parallel).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setFactorLoading(true);
      const syms = [...new Set([symbol.toUpperCase(), ...CROSS_DEFAULT])];
      const metrics = await Promise.all(
        syms.map(async (s): Promise<SymbolMetrics | null> => {
          try {
            const [ch, hi] = await Promise.all([loadChain(s), loadHistory(s).catch(() => ({ bars: [] as HistoryBar[] }))]);
            if (!ch.chain.length) return null;
            const b = ("bars" in hi ? hi.bars : []) as HistoryBar[];
            const v = vrpEngine(ch.chain, ch.spot, b);
            const c = carryEngine(ch.chain, ch.spot);
            return { symbol: s, vrpRatio: v.vrpRatio, termSlope: c.slopeVolPts, skew: skewProxy(ch.chain, ch.spot), gammaRegime: netGex(ch.chain, ch.spot), ivRank: v.ivRank };
          } catch {
            return null;
          }
        }),
      );
      if (cancelled) return;
      setFactor(volFactor(metrics.filter((m): m is SymbolMetrics => m != null)));
      setFactorLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  const vrp = useMemo(() => {
    const sub = exp === "ALL" ? chain : chain.filter((c) => c.expiration === exp);
    return vrpEngine(sub, spot, bars);
  }, [chain, spot, bars, exp]);
  const carry = useMemo(() => carryEngine(chain, spot), [chain, spot]);

  return (
    <div className="glass glass-hover fade-up p-4 sm:p-5">
      <SectionHeader eyebrow="Edge engine" title={symbol} right={<span className="lbl">Risk-premium &amp; cross-sectional vol edges</span>} />

      {state === "loading" && <Loading label="Loading edge engine…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options data for the edge engine." />}
      {state === "ok" && (
        <>
          <div className="lbl mb-2">Edge stack · {symbol}</div>
          <div className="grid gap-3 lg:grid-cols-2">
            <VrpCard r={vrp} />
            <CarryCard r={carry} />
          </div>

          <div className="mt-6 border-t border-white/[0.05] pt-4">
            <div className="mb-1 flex flex-wrap items-end justify-between gap-2">
              <div>
                <div className="lbl">Cross-sectional vol factor</div>
                <h3 className="display mt-0.5 text-sm text-neutral-100">Rich-vs-cheap vol, market-neutral</h3>
              </div>
              <span className="lbl">{factor?.n ?? "…"} names · illustrative · short rich / long cheap</span>
            </div>

            {factorLoading ? (
              <div className="mt-3 space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="skeleton h-9 w-full" />
                ))}
              </div>
            ) : !factor || !factor.rows.length ? (
              <EmptyState label="Not enough symbols returned for a cross-section." />
            ) : (
              <div className="mt-3 overflow-x-auto rounded-xl border border-white/[0.08]">
                <table className="tbl w-full">
                  <thead>
                    <tr>
                      <th className="!text-right">#</th>
                      <th>Symbol</th>
                      <th className="!text-right">Composite</th>
                      <th>Signal</th>
                      <th className="!text-right">Weight</th>
                      <th className="!text-center">VRP z</th>
                      <th className="!text-center">Skew z</th>
                      <th className="!text-center">Term z</th>
                    </tr>
                  </thead>
                  <tbody className="font-mono tabular-nums">
                    {factor.rows.map((row) => {
                      const chip = row.side === "short-vol" ? "border-call/30 bg-call/10 text-call" : row.side === "long-vol" ? "border-accent-cyan/30 bg-accent-cyan/10 text-accent-cyan" : "border-white/10 bg-white/[0.03] text-neutral-400";
                      return (
                        <tr key={row.symbol} className={row.symbol === symbol.toUpperCase() ? "bg-accent/[0.05]" : ""}>
                          <td className="text-right text-neutral-500">{row.rank}</td>
                          <td className="font-semibold text-neutral-100">{row.symbol}</td>
                          <td className={`text-right ${row.composite >= 0 ? "text-call" : "text-accent-cyan"}`}>{row.composite >= 0 ? "+" : ""}{row.composite.toFixed(2)}</td>
                          <td>
                            <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${chip}`}>
                              {row.side === "short-vol" ? "Sell" : row.side === "long-vol" ? "Buy" : "—"}
                            </span>
                          </td>
                          <td className="text-right text-neutral-300">{row.weight === 0 ? "—" : `${row.weight > 0 ? "+" : ""}${(row.weight * 100).toFixed(0)}%`}</td>
                          <td className="text-center"><Zbar z={row.z.vrp} /></td>
                          <td className="text-center"><Zbar z={row.z.skew} /></td>
                          <td className="text-center"><Zbar z={row.z.term} /></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {factor?.notes?.map((n) => (
              <p key={n} className="mt-2 text-[11px] leading-relaxed text-neutral-600">
                {n}
              </p>
            ))}
          </div>

          <p className="mt-4 border-t border-white/[0.05] pt-3 text-[11px] leading-relaxed text-neutral-600">
            These are documented risk-premium and cross-sectional edges — the variance risk premium (implied &gt; realized),
            term-structure carry, and rich-vs-cheap vol across names. They pay for bearing convexity/correlation risk, not
            for free: the same regimes that make them profitable most of the time produce the losses that compensate the
            other side. Sizing and tail risk matter more than the signal. Educational — not financial advice.
          </p>
        </>
      )}
    </div>
  );
}
