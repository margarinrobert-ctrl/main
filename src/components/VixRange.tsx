"use client";

import { useEffect, useMemo, useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { HistoryBar, OptionContract } from "@/lib/barchart/types";
import { loadChain, loadHistory } from "@/lib/client-data";
import { atmIv } from "@/lib/flow/analytics";
import { AXIS_PROPS, CHART, GRID_PROPS, TOOLTIP_PROPS } from "@/lib/chartTheme";
import { dayProjection, rangeBacktest, vixIndex, RANGE_OVER_SIGMA, type BacktestDay } from "@/lib/edge/vixrange";
import { readHistory } from "@/lib/gex-history";
import { useChartFrame } from "./chartFrame";
import { EmptyState, ErrorState, Loading, SectionHeader, Stat } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

const utcDay = (t: number) => new Date(t).toISOString().slice(0, 10);
const FUT_DEFAULT: Record<string, { ratio: number; name: string }> = {
  SPY: { ratio: 10, name: "ES" },
  QQQ: { ratio: 41, name: "NQ" },
  IWM: { ratio: 10, name: "RTY" },
};
const px = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 2 });

export function VixRange({ symbol }: { symbol: string }) {
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [spot, setSpot] = useState<number | null>(null);
  const [bars, setBars] = useState<HistoryBar[]>([]);
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");
  const fut = FUT_DEFAULT[symbol.toUpperCase()];
  const [ratioStr, setRatioStr] = useState(String(fut?.ratio ?? 1));
  const frame = useChartFrame(`${symbol} vix range`);

  useEffect(() => {
    setRatioStr(String(FUT_DEFAULT[symbol.toUpperCase()]?.ratio ?? 1));
  }, [symbol]);

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

  const vix = useMemo(() => vixIndex(chain, spot), [chain, spot]);

  // Today's σ comes from the FRONT expiry (tenor-matched to "today"); the 30d index is the vol gauge.
  const frontIv = useMemo(() => {
    const exps = [...new Set(chain.map((c) => c.expiration))]
      .map((e) => ({ e, dte: chain.find((c) => c.expiration === e)?.dte ?? -1 }))
      .filter((x) => x.dte >= 0)
      .sort((a, b) => a.dte - b.dte);
    for (const { e } of exps) {
      const iv = atmIv(chain, spot, e);
      if (iv != null && iv > 0) return iv;
    }
    return vix.vix != null ? vix.vix / 100 : null;
  }, [chain, spot, vix]);

  // Anchor at today's session open when the daily bar exists; pre-open, anchor at spot.
  const todayKey = utcDay(Date.now());
  const todayBar = bars.find((b) => b.timestamp.slice(0, 10) === todayKey) ?? null;
  const proj = useMemo(() => dayProjection(todayBar?.open ?? spot, frontIv), [todayBar, spot, frontIv]);

  // Walk-forward set: earliest recorded IV per UTC day (known at the time) × that day's realized bar.
  const backtest = useMemo(() => {
    const ivByDay = new Map<string, number>();
    for (const s of [...readHistory(symbol)].sort((a, b) => a.t - b.t)) {
      const d = utcDay(s.t);
      if (s.iv != null && s.iv > 0 && !ivByDay.has(d)) ivByDay.set(d, s.iv);
    }
    const days: BacktestDay[] = [];
    for (const b of bars) {
      const d = b.timestamp.slice(0, 10);
      if (d === todayKey) continue; // today isn't finished — judged tomorrow
      const iv = ivByDay.get(d);
      if (iv != null) days.push({ day: d, ivOpen: iv, bar: b });
    }
    return rangeBacktest(days);
  }, [symbol, bars, todayKey]);

  const chartRows = useMemo(
    () =>
      backtest.rows.slice(-30).map((r) => ({
        day: r.day.slice(5),
        implied: r.impliedRange,
        realized: r.realizedRange,
      })),
    [backtest],
  );

  const ratio = Number(ratioStr) > 0 ? Number(ratioStr) : 1;
  const futName = fut?.name ?? "futures";

  const rangePos = (v: number) => {
    if (!proj) return 0;
    const lo = proj.low - proj.expRange * 0.12;
    const hi = proj.high + proj.expRange * 0.12;
    return Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100));
  };

  return (
    <div ref={frame.ref} className={`glass glass-hover fade-up p-4 sm:p-5 ${frame.expandedClass}`}>
      <SectionHeader
        eyebrow="Vol index & day range"
        title={symbol}
        right={
          <div className="flex items-center gap-2">
            {vix.vix != null && (
              <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider ${vix.method === "strip" ? "border-accent/30 bg-accent/10 text-accent-bright" : "border-amber-400/30 bg-amber-400/10 text-amber-300"}`}>
                {vix.method === "strip" ? "CBOE-style strip" : "ATM fallback"}
              </span>
            )}
            {frame.controls}
          </div>
        }
      />

      {state === "loading" && <Loading label="Computing vol index…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options data for a vol index." />}
      {state === "ok" && (
        <>
          {/* Vol gauges */}
          <div className="mb-4 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
            <Stat label={`${symbol} VIX · 30d`} value={vix.vix == null ? "—" : vix.vix.toFixed(1)} sub={vix.method === "strip" ? "model-free strip" : vix.method === "atm-fallback" ? "sparse book — ATM IV" : undefined} tone={vix.vix != null && vix.vix >= 25 ? "put" : undefined} />
            <Stat label="Front ATM IV" value={frontIv == null ? "—" : `${(frontIv * 100).toFixed(1)}%`} sub="drives today's numbers" />
            <Stat label="σ daily" value={proj ? `${(proj.sigmaDaily * 100).toFixed(2)}%` : "—"} sub="IV / √252" />
            <Stat label="Strip legs" value={vix.near ? `${vix.near.dte}d${vix.next ? ` / ${vix.next.dte}d` : ""}` : "—"} sub={vix.near ? `σ ${(vix.near.sigma * 100).toFixed(1)}%${vix.next ? ` / ${(vix.next.sigma * 100).toFixed(1)}%` : ""}` : undefined} />
          </div>

          {/* Today's projected session */}
          {proj && (
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div className="lbl">Today's projected session · anchored at {todayBar ? "the open" : "spot (pre-open)"}</div>
                <span className="lbl">E[range] = 1.596·σ · E|move| = 0.798·σ (driftless BM)</span>
              </div>
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                <Stat label="Projected high" value={px(proj.high)} tone="call" sub={`≈ ${futName} ${px(proj.high * ratio)}`} />
                <Stat label="Projected low" value={px(proj.low)} tone="put" sub={`≈ ${futName} ${px(proj.low * ratio)}`} />
                <Stat label="Avg move (E|Δ|)" value={`±${px(proj.expAbsMove)}`} sub={`±${((proj.expAbsMove / proj.anchor) * 100).toFixed(2)}%`} />
                <Stat label="Expected range" value={px(proj.expRange)} sub={`${((proj.expRange / proj.anchor) * 100).toFixed(2)}% of price`} />
              </div>

              {/* Range strip */}
              <div className="relative mt-5 h-12">
                <div className="absolute inset-x-0 top-5 h-2 rounded-full bg-white/[0.06]" />
                <div className="absolute top-5 h-2 rounded-full bg-gradient-to-r from-put/50 via-white/10 to-call/50" style={{ left: `${rangePos(proj.low)}%`, width: `${rangePos(proj.high) - rangePos(proj.low)}%` }} />
                <div className="absolute top-5 h-2 bg-accent/25" style={{ left: `${rangePos(proj.band68.lo)}%`, width: `${rangePos(proj.band68.hi) - rangePos(proj.band68.lo)}%` }} />
                {[
                  { v: proj.low, l: `Lo ${px(proj.low)}`, c: "text-put", up: false },
                  { v: proj.anchor, l: `open ${px(proj.anchor)}`, c: "text-neutral-300", up: true },
                  { v: proj.high, l: `Hi ${px(proj.high)}`, c: "text-call", up: false },
                  ...(spot != null && Math.abs(spot - proj.anchor) > proj.expRange * 0.01 ? [{ v: spot, l: `spot ${px(spot)}`, c: "text-accent-bright", up: true }] : []),
                ].map((m) => (
                  <div key={m.l} className="absolute" style={{ left: `${rangePos(m.v)}%` }}>
                    <div className={`absolute top-4 h-4 w-px -translate-x-1/2 ${m.c.replace("text-", "bg-")}`} />
                    <div className={`absolute ${m.up ? "-top-0.5" : "top-9"} -translate-x-1/2 whitespace-nowrap font-mono text-[10px] ${m.c}`}>{m.l}</div>
                  </div>
                ))}
              </div>
              <p className="mt-3 text-[11px] leading-relaxed text-neutral-600">
                Shaded core = ±1σ close band (~68% of closes land inside). High/Low are the expected-range bounds, not certainties — roughly a coin-flip
                each gets tagged on a given day.
              </p>
            </div>
          )}

          {/* Walk-forward verification */}
          <div className="mt-5 border-t border-white/[0.05] pt-4">
            <div className="mb-1 flex flex-wrap items-end justify-between gap-2">
              <div>
                <div className="lbl">Model verification · walk-forward</div>
                <h3 className="display mt-0.5 text-sm text-neutral-100">Forecast from each morning's recorded IV vs the day that actually printed</h3>
              </div>
              <span className="lbl">{backtest.n} days scored</span>
            </div>

            {backtest.n < 5 ? (
              <EmptyState
                label="Not enough matched days yet."
                hint="Scoring needs a morning IV recorded by the 24/7 collector AND that day's realized OHLC bar. The set grows automatically as the record builds."
              />
            ) : (
              <>
                <div className="mt-3 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                  <Stat
                    label="Range premium"
                    value={backtest.rangePremium == null ? "—" : `${backtest.rangePremium >= 0 ? "+" : ""}${(backtest.rangePremium * 100).toFixed(0)}%`}
                    tone={backtest.rangePremium != null && backtest.rangePremium > 0 ? "call" : "put"}
                    sub="implied vs realized range"
                  />
                  <Stat label="|Move| premium" value={backtest.movePremium == null ? "—" : `${backtest.movePremium >= 0 ? "+" : ""}${(backtest.movePremium * 100).toFixed(0)}%`} sub="implied vs realized |Δ|" />
                  <Stat label="±1σ hit rate" value={backtest.hitRate68 == null ? "—" : `${(backtest.hitRate68 * 100).toFixed(0)}%`} sub="theory ≈ 68%" />
                  <Stat label="Range / σ" value={backtest.realizedRangeOverSigma == null ? "—" : backtest.realizedRangeOverSigma.toFixed(2)} sub={`BM theory ${RANGE_OVER_SIGMA.toFixed(2)}`} />
                </div>

                <div className={`${frame.expanded ? "h-[34vh]" : "h-[220px]"} mt-3 w-full`}>
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={chartRows} margin={{ top: 6, right: 8, left: 4, bottom: 4 }}>
                      <CartesianGrid {...GRID_PROPS} />
                      <XAxis dataKey="day" {...AXIS_PROPS} minTickGap={28} />
                      <YAxis {...AXIS_PROPS} width={46} tickFormatter={(v) => px(Number(v))} />
                      <Tooltip {...TOOLTIP_PROPS} formatter={(v: number | string, n) => [`$${px(Number(v))}`, n]} />
                      <Bar dataKey="realized" name="Realized range" fill={CHART.put} opacity={0.55} isAnimationActive={false} radius={[2, 2, 0, 0]} />
                      <Line type="monotone" dataKey="implied" name="Implied range (forecast)" stroke={CHART.call} strokeWidth={2} dot={false} isAnimationActive={false} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </>
            )}
          </div>

          {/* Futures translation */}
          <div className="mt-5 rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <div className="lbl">Futures translation · {symbol} → {futName}</div>
              <label className="flex items-center gap-2 text-[11px] text-neutral-400">
                {futName}/{symbol} ratio
                <input
                  value={ratioStr}
                  onChange={(e) => setRatioStr(e.target.value)}
                  inputMode="decimal"
                  className="w-20 rounded-lg border border-white/10 bg-white/[0.03] px-2 py-1 text-right font-mono text-xs text-neutral-100 outline-none transition focus:border-accent/50"
                  aria-label="Futures conversion ratio"
                />
              </label>
            </div>
            {proj ? (
              <p className="text-sm leading-relaxed text-neutral-300">
                At a {px(ratio)}× ratio: projected {futName} high <span className="font-mono text-call">{px(proj.high * ratio)}</span>, low{" "}
                <span className="font-mono text-put">{px(proj.low * ratio)}</span>, expected range{" "}
                <span className="font-mono text-neutral-100">{px(proj.expRange * ratio)}</span> pts, average move ±
                <span className="font-mono text-neutral-100">{px(proj.expAbsMove * ratio)}</span> pts. Fine-tune the ratio to the live basis (
                {futName} price ÷ {symbol} price).
              </p>
            ) : (
              <p className="text-sm text-neutral-500">No projection available.</p>
            )}
            <p className="mt-2 text-[11px] leading-relaxed text-neutral-600">
              The measured range premium above is the documented edge range sellers harvest in index futures/options — implied day ranges tend to print
              wider than delivered. It is a risk premium, not free money: the same short-range positions take the full loss on gap and trend days, which
              is exactly what the premium pays for. Sizing and tail risk dominate the signal. Educational — not financial advice.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
