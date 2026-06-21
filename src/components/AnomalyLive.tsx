"use client";

import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { readHistory } from "@/lib/gex-history";
import { intradayScan, type IntradayPoint, type IntradayState } from "@/lib/flow/intraday";
import { fmtUsd } from "@/lib/flow/analytics";

const stateChip: Record<IntradayState, string> = {
  anomalous: "border-red-500/40 bg-red-500/10 text-red-300",
  watch: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  calm: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
};
const hhmm = (t: number) => new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

type DotProps = { cx?: number; cy?: number; payload?: IntradayPoint };
const renderDot = ({ cx, cy, payload }: DotProps) => {
  if (cx == null || cy == null || !payload?.flagged) return <g />;
  return <circle cx={cx} cy={cy} r={4.5} fill={payload.severity === "extreme" ? "#ef4444" : "#f59e0b"} stroke="#0a0a0a" strokeWidth={1} />;
};

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded border border-white/10 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-neutral-500">{label}</div>
      <div className={`font-mono text-base ${tone ?? "text-neutral-100"}`}>{value}</div>
    </div>
  );
}

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
    <div className="glass p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-semibold">Live Anomaly Monitor · {symbol}</h2>
          <p className="text-xs text-neutral-500">intraday 0DTE — spot / dealer-gamma / IV z-scores, recorded this session</p>
        </div>
        <span className={`rounded-full border px-3 py-1 text-sm font-medium ${stateChip[r.current.state]}`}>
          {r.current.state === "anomalous" ? "ANOMALOUS" : r.current.state === "watch" ? "WATCH" : "CALM"} · {r.current.score}/100
        </span>
      </div>

      <div className="mb-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
        <Stat label="Samples" value={String(r.samples)} />
        <Stat label="Session range" value={r.rangePct == null ? "—" : `${r.rangePct.toFixed(2)}%`} />
        <Stat label="0DTE ATM IV" value={r.ivNow == null ? "—" : `${(r.ivNow * 100).toFixed(1)}%`} />
        <Stat label="Net GEX" value={r.gexNow == null ? "—" : fmtUsd(r.gexNow)} tone={r.gexNow == null ? undefined : r.gexNow >= 0 ? "text-emerald-300" : "text-red-300"} />
      </div>

      {r.samples < 4 ? (
        <div className="rounded border border-white/10 bg-white/[0.02] p-6 text-center text-sm text-neutral-400">
          Recording this session… keep the tab open. The live graph fills in as samples are collected
          (every ~30s). {r.samples} sample{r.samples === 1 ? "" : "s"} so far.
        </div>
      ) : (
        <>
          <div className="h-[240px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 8, right: 12, left: 8, bottom: 4 }}>
                <CartesianGrid stroke="#1f1f1f" />
                <XAxis dataKey="label" tick={{ fill: "#a3a3a3", fontSize: 10 }} stroke="#404040" minTickGap={40} />
                <YAxis domain={["auto", "auto"]} tick={{ fill: "#a3a3a3", fontSize: 10 }} stroke="#404040" width={56} tickFormatter={(v) => Number(v).toLocaleString()} />
                <Tooltip
                  contentStyle={{ background: "#0a0a0a", border: "1px solid #404040", borderRadius: 6, fontSize: 12 }}
                  formatter={(v: number | string) => [Number(v).toLocaleString(), "spot"]}
                  labelFormatter={(l) => `${l}`}
                />
                <Line type="monotone" dataKey="spot" stroke="#34d399" strokeWidth={1.6} dot={renderDot} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-1 h-[120px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 4, right: 12, left: 8, bottom: 4 }}>
                <defs>
                  <linearGradient id="anomScore" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#ef4444" stopOpacity={0.5} />
                    <stop offset="100%" stopColor="#ef4444" stopOpacity={0.03} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="label" tick={{ fill: "#a3a3a3", fontSize: 10 }} stroke="#404040" minTickGap={40} />
                <YAxis domain={[0, 100]} tick={{ fill: "#a3a3a3", fontSize: 10 }} stroke="#404040" width={56} />
                <Tooltip contentStyle={{ background: "#0a0a0a", border: "1px solid #404040", borderRadius: 6, fontSize: 12 }} formatter={(v: number | string) => [`${v}/100`, "anomaly"]} labelFormatter={(l) => `${l}`} />
                <ReferenceLine y={60} stroke="#ef4444" strokeDasharray="3 3" label={{ value: "anomalous", position: "insideTopRight", fill: "#f87171", fontSize: 10 }} />
                <ReferenceLine y={30} stroke="#f59e0b" strokeDasharray="3 3" />
                <Area type="monotone" dataKey="score" stroke="#ef4444" strokeWidth={1.5} fill="url(#anomScore)" isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </>
      )}

      {r.current.flags.length > 0 && (
        <div className="mt-3 space-y-2">
          <div className="text-xs uppercase tracking-wide text-neutral-500">Live anomalies (latest sample)</div>
          {r.current.flags.map((f) => (
            <div key={f.metric} className={`rounded-md border border-white/5 border-l-4 bg-white/[0.02] p-2 ${f.severity === "extreme" ? "border-l-red-500" : "border-l-amber-500"}`}>
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

      <p className="mt-3 text-[11px] text-neutral-500">
        Live, client-recorded (localStorage) at ~30s cadence while a ticker tab is open — chain is ~15-min delayed CBOE.
        Dots mark flagged samples; the lower pane is the rolling anomaly score. Educational — not advice.
      </p>
    </div>
  );
}
