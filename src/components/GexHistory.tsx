"use client";

import { useEffect, useMemo, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmtUsd } from "@/lib/flow/analytics";
import { AXIS_PROPS, CHART, GRID_PROPS, TOOLTIP_CURSOR_LINE, TOOLTIP_PROPS } from "@/lib/chartTheme";
import { type GexSample, readHistory } from "@/lib/gex-history";
import { EmptyState, SectionHeader } from "./states";

function dur(ms: number): string {
  const m = Math.max(0, Math.round(ms / 60000));
  if (m < 60) return `${m}m`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h}h`;
  return `${Math.round(h / 24)}d`;
}

export function GexHistory({ symbol }: { symbol: string }) {
  const [series, setSeries] = useState<GexSample[]>([]);
  const [now, setNow] = useState(0);

  useEffect(() => {
    const tick = () => {
      setSeries(readHistory(symbol));
      setNow(Date.now());
    };
    tick();
    const id = setInterval(tick, 5000);
    return () => clearInterval(id);
  }, [symbol]);

  // Span of the record (server 24/7 samples merge in alongside this session), so labels stay unambiguous
  // once the series covers more than a day.
  const spanMs = series.length > 1 ? series[series.length - 1].t - series[0].t : 0;
  const lastT = series.length ? series[series.length - 1].t : 0;
  const multiDay = spanMs > 20 * 3600_000;

  const data = useMemo(
    () =>
      series.map((s) => ({
        time: new Date(s.t).toLocaleTimeString([], multiDay ? { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" } : { hour: "2-digit", minute: "2-digit" }),
        spot: s.spot,
        gex: s.gex,
      })),
    [series, multiDay],
  );

  return (
    <div className="glass glass-hover fade-up p-4 sm:p-5">
      <SectionHeader
        eyebrow="Intraday GEX"
        title={symbol}
        right={
          <span className="lbl flex items-center gap-1.5">
            <span className="live-dot" style={{ height: 5, width: 5 }} />
            24/7 spot &amp; net GEX
          </span>
        }
      />

      {data.length < 2 ? (
        <EmptyState
          label="Collecting round-the-clock history."
          hint="A scheduled collector records dealer positioning every ~10 minutes, 24/7, and merges it here — plus a point a minute while this terminal is open. The series builds up over the next few cycles."
        />
      ) : (
        <>
          <div className="h-[340px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data} margin={{ top: 8, right: 8, left: 4, bottom: 8 }}>
                <defs>
                  <linearGradient id="gh-gex" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={CHART.call} stopOpacity={0.22} />
                    <stop offset="100%" stopColor={CHART.call} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid {...GRID_PROPS} />
                <XAxis dataKey="time" {...AXIS_PROPS} minTickGap={40} />
                <YAxis yAxisId="spot" {...AXIS_PROPS} width={56} domain={["auto", "auto"]} tickFormatter={(v) => Number(v).toLocaleString()} />
                <YAxis
                  yAxisId="gex"
                  orientation="right"
                  tickFormatter={(v) => fmtUsd(Number(v))}
                  {...AXIS_PROPS}
                  tick={{ fill: CHART.call, fontSize: 10, opacity: 0.75 }}
                  width={56}
                  domain={["auto", "auto"]}
                />
                <Tooltip
                  {...TOOLTIP_PROPS}
                  cursor={TOOLTIP_CURSOR_LINE}
                  formatter={(v: number | string, n) => (n === "Net GEX" ? [fmtUsd(Number(v)), n] : [Number(v).toLocaleString(), n])}
                />
                <ReferenceLine yAxisId="gex" y={0} stroke="rgba(255,255,255,0.16)" />
                <Area yAxisId="gex" type="monotone" dataKey="gex" name="Net GEX" stroke="none" fill="url(#gh-gex)" connectNulls isAnimationActive={false} />
                <Line yAxisId="spot" type="monotone" dataKey="spot" name="Spot" stroke="#a3a3a3" dot={false} strokeWidth={1.5} connectNulls isAnimationActive={false} />
                <Line yAxisId="gex" type="monotone" dataKey="gex" name="Net GEX" stroke={CHART.call} dot={false} strokeWidth={2} connectNulls isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.05] pt-3">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
              {[
                { c: "#a3a3a3", l: "Spot (left)" },
                { c: CHART.call, l: "Net GEX (right)" },
              ].map((it) => (
                <span key={it.l} className="flex items-center gap-1.5 text-[11px] text-neutral-500">
                  <span className="h-2 w-2 rounded-sm" style={{ background: it.c }} />
                  {it.l}
                </span>
              ))}
            </div>
            <span className="lbl">
              {data.length} samples
              {spanMs > 0 ? ` · ${dur(spanMs)} span` : ""}
              {lastT ? ` · updated ${dur(now - lastT)} ago` : ""}
            </span>
          </div>
        </>
      )}
    </div>
  );
}
