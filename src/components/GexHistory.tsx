"use client";

import { useEffect, useMemo, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmtUsd } from "@/lib/flow/analytics";
import { dayStats, groupByDay } from "@/lib/flow/historyDays";
import { AXIS_PROPS, CHART, GRID_PROPS, TOOLTIP_CURSOR_LINE, TOOLTIP_PROPS } from "@/lib/chartTheme";
import { type GexSample, readHistory } from "@/lib/gex-history";
import { EmptyState, SectionHeader, Stat } from "./states";
import { useChartFrame } from "./chartFrame";

function dur(ms: number): string {
  const m = Math.max(0, Math.round(ms / 60000));
  if (m < 60) return `${m}m`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h}h`;
  return `${Math.round(h / 24)}d`;
}

// Right-axis metric: which recorded series to plot against spot.
type Metric = "gex" | "dex" | "iv" | "pcr";
const METRICS: { key: Metric; label: string; color: string; fmt: (v: number) => string }[] = [
  { key: "gex", label: "Net GEX (γ)", color: CHART.call, fmt: (v) => fmtUsd(v) },
  { key: "dex", label: "Net DEX (Δ)", color: "#22d3ee", fmt: (v) => fmtUsd(v) },
  { key: "iv", label: "ATM IV", color: "#7dd3fc", fmt: (v) => `${(v * 100).toFixed(1)}%` },
  { key: "pcr", label: "P/C ratio", color: "#fbbf24", fmt: (v) => v.toFixed(2) },
];

export function GexHistory({ symbol }: { symbol: string }) {
  const [series, setSeries] = useState<GexSample[]>([]);
  const [now, setNow] = useState(0);
  const [metric, setMetric] = useState<Metric>("gex");
  const [dayKey, setDayKey] = useState<string>("ALL"); // "ALL" = full record, else a YYYY-MM-DD day
  const frame = useChartFrame(`${symbol} positioning history`);

  useEffect(() => {
    const tick = () => {
      setSeries(readHistory(symbol));
      setNow(Date.now());
    };
    tick();
    const id = setInterval(tick, 5000);
    return () => clearInterval(id);
  }, [symbol]);

  // Reset the day selection when switching tickers.
  useEffect(() => setDayKey("ALL"), [symbol]);

  const days = useMemo(() => groupByDay(series), [series]);
  const dayIdx = days.findIndex((d) => d.key === dayKey);
  const visible = dayIdx >= 0 ? days[dayIdx].samples : series;
  const stats = useMemo(() => (dayIdx >= 0 ? dayStats(days[dayIdx].samples) : null), [days, dayIdx]);

  const m = METRICS.find((x) => x.key === metric) ?? METRICS[0];
  const spanMs = series.length > 1 ? series[series.length - 1].t - series[0].t : 0;
  const lastT = series.length ? series[series.length - 1].t : 0;
  const multiDay = dayIdx < 0 && spanMs > 20 * 3600_000;

  const data = useMemo(
    () =>
      visible.map((s) => ({
        time: new Date(s.t).toLocaleTimeString([], multiDay ? { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" } : { hour: "2-digit", minute: "2-digit" }),
        spot: s.spot,
        val: s[metric] ?? null,
      })),
    [visible, multiDay, metric],
  );
  const hasMetricData = data.some((d) => d.val != null);

  const stepDay = (dir: 1 | -1) => {
    if (!days.length) return;
    if (dayIdx < 0) {
      // from ALL, ◀ enters the most recent day
      if (dir === -1) setDayKey(days[days.length - 1].key);
      return;
    }
    const next = dayIdx + dir;
    if (next >= days.length) setDayKey("ALL");
    else if (next >= 0) setDayKey(days[next].key);
  };

  const navBtn = "flex h-7 w-7 items-center justify-center rounded-md border border-white/10 bg-white/[0.03] text-neutral-400 transition enabled:hover:border-white/20 enabled:hover:text-neutral-100 disabled:opacity-30";

  return (
    <div ref={frame.ref} className={`glass glass-hover fade-up p-4 sm:p-5 ${frame.expandedClass}`}>
      <SectionHeader
        eyebrow="Positioning history"
        title={symbol}
        right={
          <div className="flex items-center gap-2">
            <span className="lbl flex items-center gap-1.5">
              <span className="live-dot" style={{ height: 5, width: 5 }} />
              24/7 record
            </span>
            {frame.controls}
          </div>
        }
      />

      {/* Metric picker + past-day browser */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1">
          {METRICS.map((x) => (
            <button
              key={x.key}
              onClick={() => setMetric(x.key)}
              aria-pressed={metric === x.key}
              className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${metric === x.key ? "bg-accent/15 text-accent-bright" : "text-neutral-400 hover:bg-white/5 hover:text-neutral-200"}`}
            >
              {x.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1.5">
          <button type="button" onClick={() => stepDay(-1)} disabled={!days.length || dayIdx === 0} className={navBtn} aria-label="Earlier day" title="Earlier day">
            <svg aria-hidden viewBox="0 0 16 16" className="h-3.5 w-3.5"><path fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" d="M10 3 5 8l5 5" /></svg>
          </button>
          <select
            value={dayIdx >= 0 ? dayKey : "ALL"}
            onChange={(e) => setDayKey(e.target.value)}
            aria-label="Select a recorded day"
            className="rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-xs text-neutral-200 outline-none transition hover:border-white/20"
          >
            <option value="ALL">Full record ({days.length}d)</option>
            {[...days].reverse().map((d) => (
              <option key={d.key} value={d.key}>
                {d.label} · {d.samples.length} pts
              </option>
            ))}
          </select>
          <button type="button" onClick={() => stepDay(1)} disabled={dayIdx < 0} className={navBtn} aria-label="Later day" title="Later day">
            <svg aria-hidden viewBox="0 0 16 16" className="h-3.5 w-3.5"><path fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" d="m6 3 5 5-5 5" /></svg>
          </button>
        </div>
      </div>

      {data.length < 2 ? (
        <EmptyState
          label="Collecting round-the-clock history."
          hint="A scheduled collector records dealer positioning (GEX, DEX, IV, P/C) around the clock and merges it here — plus a point a minute while this terminal is open. Past days appear in the day browser as the record builds."
        />
      ) : (
        <>
          {/* Day summary (past-day view) */}
          {stats && (
            <div className="mb-3 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
              <Stat label="Spot o→c" value={stats.spotClose == null ? "—" : stats.spotClose.toLocaleString()} sub={stats.spotChangePct == null ? undefined : `${stats.spotChangePct >= 0 ? "+" : ""}${stats.spotChangePct.toFixed(2)}%`} tone={stats.spotChangePct == null ? undefined : stats.spotChangePct >= 0 ? "call" : "put"} />
              <Stat label="GEX close" value={stats.gexClose == null ? "—" : fmtUsd(stats.gexClose)} tone={stats.gexClose == null ? undefined : stats.gexClose >= 0 ? "call" : "put"} />
              <Stat label="GEX range" value={stats.gexMin == null || stats.gexMax == null ? "—" : `${fmtUsd(stats.gexMin)} … ${fmtUsd(stats.gexMax)}`} />
              <Stat label="Net DEX close" value={stats.dexClose == null ? "—" : fmtUsd(stats.dexClose)} sub={stats.dexClose == null ? "not recorded that day" : undefined} tone={stats.dexClose == null ? undefined : stats.dexClose >= 0 ? "call" : "put"} />
              <Stat label="ATM IV range" value={stats.ivMin == null || stats.ivMax == null ? "—" : `${(stats.ivMin * 100).toFixed(1)}–${(stats.ivMax * 100).toFixed(1)}%`} />
              <Stat label="γ-flip close" value={stats.flipClose == null ? "—" : `$${stats.flipClose.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
            </div>
          )}

          {!hasMetricData ? (
            <EmptyState label={`No ${m.label} recorded ${dayIdx >= 0 ? "on this day" : "yet"}.`} hint={metric === "dex" ? "Net DEX recording was added recently — it fills in from now on; older days predate it." : undefined} />
          ) : (
            <div className={`${frame.expanded ? "h-[calc(100vh-260px)]" : "h-[340px]"} w-full`}>
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={data} margin={{ top: 8, right: 8, left: 4, bottom: 8 }}>
                  <defs>
                    <linearGradient id="gh-metric" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={m.color} stopOpacity={0.22} />
                      <stop offset="100%" stopColor={m.color} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid {...GRID_PROPS} />
                  <XAxis dataKey="time" {...AXIS_PROPS} minTickGap={40} />
                  <YAxis yAxisId="spot" {...AXIS_PROPS} width={56} domain={["auto", "auto"]} tickFormatter={(v) => Number(v).toLocaleString()} />
                  <YAxis
                    yAxisId="val"
                    orientation="right"
                    tickFormatter={(v) => m.fmt(Number(v))}
                    {...AXIS_PROPS}
                    tick={{ fill: m.color, fontSize: 10, opacity: 0.8 }}
                    width={56}
                    domain={["auto", "auto"]}
                  />
                  <Tooltip
                    {...TOOLTIP_PROPS}
                    cursor={TOOLTIP_CURSOR_LINE}
                    formatter={(v: number | string, n) => (n === m.label ? [m.fmt(Number(v)), n] : [Number(v).toLocaleString(), n])}
                  />
                  {(metric === "gex" || metric === "dex") && <ReferenceLine yAxisId="val" y={0} stroke="rgba(255,255,255,0.16)" />}
                  <Area yAxisId="val" type="monotone" dataKey="val" name={m.label} stroke="none" fill="url(#gh-metric)" connectNulls isAnimationActive={false} />
                  <Line yAxisId="spot" type="monotone" dataKey="spot" name="Spot" stroke="#a3a3a3" dot={false} strokeWidth={1.5} connectNulls isAnimationActive={false} />
                  <Line yAxisId="val" type="monotone" dataKey="val" name={m.label} stroke={m.color} dot={false} strokeWidth={2} connectNulls isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}

          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.05] pt-3">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
              {[
                { c: "#a3a3a3", l: "Spot (left)" },
                { c: m.color, l: `${m.label} (right)` },
              ].map((it) => (
                <span key={it.l} className="flex items-center gap-1.5 text-[11px] text-neutral-500">
                  <span className="h-2 w-2 rounded-sm" style={{ background: it.c }} />
                  {it.l}
                </span>
              ))}
            </div>
            <span className="lbl">
              {dayIdx >= 0 ? `${days[dayIdx].label} · ${data.length} pts` : `${data.length} samples${spanMs > 0 ? ` · ${dur(spanMs)} span` : ""}`}
              {dayIdx < 0 && lastT ? ` · updated ${dur(now - lastT)} ago` : ""}
            </span>
          </div>
        </>
      )}
    </div>
  );
}
