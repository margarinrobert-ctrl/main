"use client";

import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { readHistory } from "@/lib/gex-history";
import { intradayScan, type IntradayPoint, type IntradayState } from "@/lib/flow/intraday";
import { fmtUsd } from "@/lib/flow/analytics";
import { AXIS_PROPS, CHART, GRID_PROPS, TOOLTIP_CURSOR_LINE, TOOLTIP_PROPS, refLabel } from "@/lib/chartTheme";
import { Stat } from "./states";

const stateChip: Record<IntradayState, string> = {
  anomalous: "border-put/40 bg-put/10 text-put",
  watch: "border-amber-400/40 bg-amber-400/10 text-amber-300",
  calm: "border-call/40 bg-call/10 text-call",
};
const hhmm = (t: number) => new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

type DotProps = { cx?: number; cy?: number; payload?: IntradayPoint };
const renderDot = ({ cx, cy, payload }: DotProps) => {
  if (cx == null || cy == null || !payload?.flagged) return <g />;
  return <circle cx={cx} cy={cy} r={4.5} fill={payload.severity === "extreme" ? "#f87171" : "#fbbf24"} stroke="#05060a" strokeWidth={1} />;
};

export function AnomalyLive({ symbol }: { symbol: string }) {
  const [samples, setSamples] = useState(() => readHistory(symbol));

  useEffect(() => {
    setSamples(readHistory(symbol));
    const ms = Math.max(15_000, Number(process.env.NEXT_PUBLIC_REFRESH_MS ?? 30_000) || 30_000);
    const id = setInterval(() => setSamples(readHistory(symbol)), ms);
    return () => clearInterval(id);
  }, [symbol]);

  const r = useMemo(() => intradayScan(samples), [samples]);
  const data = useMemo(() => r.points.map((p) => ({ ...p, label: hhmm(p.t) })), [r.points]);

  return (
    <div className="glass glass-hover fade-up p-4 sm:p-5">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="lbl mb-1">Live anomaly monitor</div>
          <h2 className="display text-base text-neutral-50">{symbol}</h2>
          <p className="mt-0.5 text-xs text-neutral-500">Intraday spot / dealer-gamma / IV z-scores, recorded this session</p>
        </div>
        <span className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wider ${stateChip[r.current.state]}`}>
          {r.current.state === "anomalous" ? "ANOMALOUS" : r.current.state === "watch" ? "WATCH" : "CALM"} · {r.current.score}/100
        </span>
      </div>

      <div className="mb-3 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <Stat label="Samples" value={String(r.samples)} />
        <Stat label="Session range" value={r.rangePct == null ? "—" : `${r.rangePct.toFixed(2)}%`} />
        <Stat label="0DTE ATM IV" value={r.ivNow == null ? "—" : `${(r.ivNow * 100).toFixed(1)}%`} />
        <Stat label="Net GEX" value={r.gexNow == null ? "—" : fmtUsd(r.gexNow)} tone={r.gexNow == null ? undefined : r.gexNow >= 0 ? "call" : "put"} />
      </div>

      {r.samples < 4 ? (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-white/10 bg-white/[0.015] px-6 py-10 text-center">
          <span className="live-dot" />
          <div className="text-sm text-neutral-400">Recording this session — the monitor fills in as samples arrive.</div>
          <div className="text-[11px] text-neutral-600">
            {r.samples} sample{r.samples === 1 ? "" : "s"} so far · one every ~30s while the terminal is open
          </div>
        </div>
      ) : (
        <>
          <div className="h-[240px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
                <CartesianGrid {...GRID_PROPS} />
                <XAxis dataKey="label" {...AXIS_PROPS} minTickGap={40} />
                <YAxis domain={["auto", "auto"]} {...AXIS_PROPS} width={52} tickFormatter={(v) => Number(v).toLocaleString()} />
                <Tooltip
                  {...TOOLTIP_PROPS}
                  cursor={TOOLTIP_CURSOR_LINE}
                  formatter={(v: number | string) => [Number(v).toLocaleString(), "Spot"]}
                  labelFormatter={(l) => `${l}`}
                />
                <Line type="monotone" dataKey="spot" stroke={CHART.call} strokeWidth={1.6} dot={renderDot} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-1 h-[120px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 4, right: 12, left: 8, bottom: 4 }}>
                <defs>
                  <linearGradient id="anomScore" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={CHART.put} stopOpacity={0.5} />
                    <stop offset="100%" stopColor={CHART.put} stopOpacity={0.03} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="label" {...AXIS_PROPS} minTickGap={40} />
                <YAxis domain={[0, 100]} {...AXIS_PROPS} width={52} />
                <Tooltip {...TOOLTIP_PROPS} formatter={(v: number | string) => [`${v}/100`, "Anomaly"]} labelFormatter={(l) => `${l}`} />
                <ReferenceLine y={60} stroke={CHART.put} strokeDasharray="3 3" label={refLabel("Anomalous", CHART.put, "insideTopRight")} />
                <ReferenceLine y={30} stroke={CHART.amber} strokeDasharray="3 3" />
                <Area type="monotone" dataKey="score" stroke={CHART.put} strokeWidth={1.5} fill="url(#anomScore)" isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </>
      )}

      {r.current.flags.length > 0 && (
        <div className="mt-3 space-y-2">
          <div className="lbl">Live anomalies (latest sample)</div>
          {r.current.flags.map((f) => (
            <div key={f.metric} className={`rounded-xl border border-white/[0.06] border-l-2 bg-white/[0.02] p-3 ${f.severity === "extreme" ? "border-l-put/80" : "border-l-amber-400/80"}`}>
              <div className="flex items-center justify-between gap-2 text-sm">
                <span className="font-medium text-neutral-100">{f.metric}</span>
                <span className="font-mono text-xs text-neutral-400">
                  {f.z >= 0 ? "+" : ""}
                  {f.z.toFixed(1)}σ · <span className="uppercase">{f.severity}</span>
                </span>
              </div>
              <p className="text-xs text-neutral-400">{f.detail}</p>
            </div>
          ))}
        </div>
      )}

      <p className="mt-3 border-t border-white/[0.05] pt-3 text-[11px] leading-relaxed text-neutral-600">
        Recorded in this browser at ~30s cadence while a terminal is open. Dots mark flagged samples; the lower pane is the
        rolling anomaly score. Educational — not advice.
      </p>
    </div>
  );
}
