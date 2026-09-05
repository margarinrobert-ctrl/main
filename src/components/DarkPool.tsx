"use client";

import { useEffect, useMemo, useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { loadDarkPool } from "@/lib/client-data";
import { fmtUsd } from "@/lib/flow/analytics";
import type { DarkPoolBias, DarkPoolDay, DarkPoolProfile, DarkPoolStats } from "@/lib/flow/darkpool";
import { DarkPoolLevelsChart } from "./DarkPoolLevelsChart";
import { Provenance } from "./Provenance";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

const pct = (x: number | null, d = 1) => (x == null ? "—" : `${(x * 100).toFixed(d)}%`);
const kfmt = (n: number) => (n >= 1e9 ? `${(n / 1e9).toFixed(2)}B` : n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : String(Math.round(n)));
const fmtPx = (p: number) => (Math.abs(p) >= 1000 ? String(Math.round(p)) : String(Math.round(p * 100) / 100));

const biasChip = (b: DarkPoolBias | null) =>
  b === "accumulation"
    ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
    : b === "distribution"
      ? "border-red-500/40 bg-red-500/10 text-red-300"
      : "border-sky-500/40 bg-sky-500/10 text-sky-300";
const biasLabel = (b: DarkPoolBias | null) =>
  b === "accumulation" ? "Accumulation" : b === "distribution" ? "Distribution" : "Neutral";

function Stat({ label, value, sub, tone = "neutral", hint }: { label: string; value: string; sub?: string; tone?: "good" | "bad" | "neutral"; hint?: string }) {
  const color = tone === "good" ? "text-emerald-400" : tone === "bad" ? "text-red-400" : "text-neutral-100";
  return (
    <div className="rounded border border-neutral-800 px-3 py-2" title={hint}>
      <div className="flex items-center gap-1 text-[11px] uppercase tracking-wide text-neutral-500">
        {label}
        {hint ? <span className="cursor-help text-neutral-600">ⓘ</span> : null}
      </div>
      <div className={`font-mono text-lg ${color}`}>{value}</div>
      {sub ? <div className="text-[11px] text-neutral-500">{sub}</div> : null}
    </div>
  );
}

export function DarkPool({ symbol }: { symbol: string }) {
  const [stats, setStats] = useState<DarkPoolStats | null>(null);
  const [levels, setLevels] = useState<DarkPoolProfile | null>(null);
  const [days, setDays] = useState<DarkPoolDay[]>([]);
  const [source, setSource] = useState("");
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setState("loading");
      try {
        const { stats, levels, days, source } = await loadDarkPool(symbol);
        if (cancelled) return;
        setStats(stats);
        setLevels(levels);
        setDays(days);
        setSource(source);
        setState(stats.available ? "ok" : "empty");
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

  const chart = useMemo(
    () => (stats?.series ?? []).map((p) => ({ date: p.date.slice(5), dpr: p.dpr * 100, vol: p.offExchangeVolume })),
    [stats],
  );

  return (
    <div className="glass p-4">
      <Provenance source={source} feed="FINRA off-exchange daily files" className="mb-3" />
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-semibold">Dark pool · off-exchange flow · {symbol}</h2>
          <p className="text-xs text-neutral-500">FINRA off-exchange (ATS + wholesaler) volume</p>
        </div>
        {state === "ok" && stats && (
          <span className={`rounded-full border px-3 py-1 text-xs font-medium ${biasChip(stats.bias)}`}>
            {biasLabel(stats.bias)}
            {stats.dprZ != null ? ` · ${stats.dprZ >= 0 ? "+" : ""}${stats.dprZ.toFixed(2)}σ` : ""}
          </span>
        )}
      </div>

      {state === "loading" && <Loading label="Loading dark-pool flow…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && (
        <EmptyState label="Dark-pool data unavailable — FINRA off-exchange feed isn't reachable here (works on the live deploy)." />
      )}
      {state === "ok" && stats && (
        <>
          <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3 lg:grid-cols-4">
            <Stat
              label="Dark-pool ratio"
              value={pct(stats.dpr)}
              sub={stats.dprAvg != null ? `avg ${pct(stats.dprAvg)} · ${stats.days}d` : `${stats.days}d`}
              tone={stats.bias === "accumulation" ? "good" : stats.bias === "distribution" ? "bad" : "neutral"}
              hint="Off-exchange SHORT volume ÷ off-exchange total. DIX thesis: a HIGH ratio = accumulation (market-makers print short to fill institutional BUYS off-exchange), a LOW ratio = distribution."
            />
            <Stat
              label="vs window"
              value={stats.dprZ == null ? "—" : `${stats.dprZ >= 0 ? "+" : ""}${stats.dprZ.toFixed(2)}σ`}
              sub={stats.dprPctile == null ? "" : `${Math.round(stats.dprPctile * 100)}th pctile`}
              tone={stats.dprZ == null ? "neutral" : stats.dprZ > 0.5 ? "good" : stats.dprZ < -0.5 ? "bad" : "neutral"}
              hint="Z-score and percentile of today's dark-pool ratio against the trailing window — how unusual today's off-exchange buying/selling pressure is."
            />
            <Stat
              label="Off-exchange %"
              value={pct(stats.offExchPct)}
              sub={stats.offExchPctAvg != null ? `avg ${pct(stats.offExchPctAvg)}` : "of total volume"}
              hint="Share of the day's CONSOLIDATED volume that printed off-exchange (dark). Liquid names typically run ~40–55%; spikes flag heavy dark activity."
            />
            <Stat
              label="Trend"
              value={stats.trend == null ? "—" : stats.trend === "rising" ? "▲ Rising" : stats.trend === "falling" ? "▼ Falling" : "• Flat"}
              sub="dark-pool ratio"
              tone={stats.trend === "rising" ? "good" : stats.trend === "falling" ? "bad" : "neutral"}
              hint="Direction of the dark-pool ratio over the window (OLS slope). Rising dark buying = building accumulation."
            />
            <Stat label="Off-exch volume" value={stats.latest ? kfmt(stats.latest.offExchangeVolume) : "—"} sub={stats.latest?.date ?? ""} hint="Latest day's off-exchange (dark) share volume reported to FINRA." />
            <Stat label="Short volume" value={stats.latest ? kfmt(stats.latest.shortVolume) : "—"} sub="off-exchange, latest day" />
          </div>

          {levels?.available && levels.poc != null && (
            <div className="mt-5">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div className="text-xs uppercase tracking-wide text-neutral-500">Dark-pool levels on price · last {stats.days}d</div>
                <div className="flex flex-wrap gap-3 text-[11px] text-neutral-400">
                  <span><span className="text-purple-300">━</span> POC {fmtPx(levels.poc)}</span>
                  {levels.val != null && levels.vah != null && (
                    <span className="text-neutral-500">value area {fmtPx(levels.val)}–{fmtPx(levels.vah)}</span>
                  )}
                </div>
              </div>
              <DarkPoolLevelsChart days={days} levels={levels} />
              {levels.levels.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-neutral-500">
                  {levels.levels.map((l) => {
                    const isPoc = levels.poc != null && Math.abs(l.price - levels.poc) < 1e-9;
                    return (
                      <span key={l.price} className="inline-flex items-center gap-1">
                        <span className="inline-block h-2 w-2 rounded-sm" style={{ background: isPoc ? "#c084fc" : "#8b5cf6" }} />
                        {isPoc ? "POC " : ""}
                        {fmtPx(l.price)} <span className="text-neutral-600">{Math.round(l.share * 100)}%</span>
                      </span>
                    );
                  })}
                </div>
              )}
              <p className="mt-2 text-[11px] leading-relaxed text-neutral-500">
                Each day&apos;s off-exchange (dark) volume spread across that day&apos;s price range, summed into a
                volume-by-price profile — the peaks are the prices that absorbed the most dark volume (support / resistance),
                the brightest being the dark-pool <b>Point of Control</b>. Daily resolution — a volume proxy, not an
                intraday print tape.
              </p>
            </div>
          )}

          <div className="mt-5 mb-2 text-xs uppercase tracking-wide text-neutral-500">Dark-pool ratio &amp; off-exchange volume · trend</div>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chart} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
                <CartesianGrid stroke="#1f1f1f" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: "#a3a3a3", fontSize: 10 }} stroke="#404040" />
                <YAxis yAxisId="vol" orientation="left" tickFormatter={(v) => kfmt(Number(v))} tick={{ fill: "#737373", fontSize: 10 }} stroke="#404040" width={44} />
                <YAxis yAxisId="dpr" orientation="right" domain={["dataMin - 3", "dataMax + 3"]} tickFormatter={(v) => `${Math.round(Number(v))}%`} tick={{ fill: "#a3a3a3", fontSize: 10 }} stroke="#404040" width={40} />
                <Tooltip
                  contentStyle={{ background: "#0a0a0a", border: "1px solid #404040", borderRadius: 6, fontSize: 12 }}
                  formatter={(v: number | string, name) => (name === "dpr" ? [`${Number(v).toFixed(1)}%`, "dark-pool ratio"] : [fmtUsd(Number(v) || 0).replace("$", ""), "off-exch vol"])}
                  labelFormatter={(l) => `date ${l}`}
                  cursor={{ fill: "rgba(255,255,255,0.04)" }}
                />
                {stats.dprAvg != null && (
                  <ReferenceLine yAxisId="dpr" y={stats.dprAvg * 100} stroke="#737373" strokeDasharray="4 4" label={{ value: "avg", position: "right", fill: "#737373", fontSize: 10 }} />
                )}
                <Bar yAxisId="vol" dataKey="vol" fill="#1e3a8a" radius={[2, 2, 0, 0]} isAnimationActive={false} />
                <Line yAxisId="dpr" type="monotone" dataKey="dpr" stroke="#d946ef" strokeWidth={2} dot={{ r: 2 }} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-neutral-400">
            <span><span className="text-fuchsia-400">━</span> dark-pool ratio (right)</span>
            <span><span className="text-blue-800">▮</span> off-exchange volume (left)</span>
          </div>

          <p className="mt-3 border-t border-white/5 pt-3 text-[11px] leading-relaxed text-neutral-500">
            Off-exchange volume = trades reported to FINRA&apos;s TRFs (dark pools + wholesaler internalization) rather than a
            lit exchange. The <b>dark-pool ratio</b> follows the DIX idea: persistently high dark short-selling tends to mark
            institutional <span className="text-emerald-400">accumulation</span>, not bearishness. Data is <b>daily / T+1</b> and
            carries no price, so there are no intraday prints or price levels — those need a paid real-time feed. Educational, not advice.
          </p>
        </>
      )}
    </div>
  );
}
