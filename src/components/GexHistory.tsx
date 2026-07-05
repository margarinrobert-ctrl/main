"use client";

import { useEffect, useMemo, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmtUsd } from "@/lib/flow/analytics";
import { AXIS_PROPS, CHART, GRID_PROPS, TOOLTIP_CURSOR_LINE, TOOLTIP_PROPS } from "@/lib/chartTheme";
import { type GexSample, readHistory } from "@/lib/gex-history";
import { EmptyState, SectionHeader } from "./states";

export function GexHistory({ symbol }: { symbol: string }) {
  const [series, setSeries] = useState<GexSample[]>([]);

  useEffect(() => {
    setSeries(readHistory(symbol));
    const id = setInterval(() => setSeries(readHistory(symbol)), 5000);
    return () => clearInterval(id);
  }, [symbol]);

  const data = useMemo(
    () =>
      series.map((s) => ({
        time: new Date(s.t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        spot: s.spot,
        gex: s.gex,
      })),
    [series],
  );

  return (
    <div className="glass glass-hover fade-up p-4 sm:p-5">
      <SectionHeader eyebrow="Intraday GEX" title={symbol} right={<span className="lbl">Spot &amp; net GEX over the session</span>} />

      {data.length < 2 ? (
        <EmptyState
          label="Collecting intraday history."
          hint="A point is recorded each minute while this terminal is open; the series persists in your browser."
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
            <span className="lbl">{data.length} samples this session</span>
          </div>
        </>
      )}
    </div>
  );
}
