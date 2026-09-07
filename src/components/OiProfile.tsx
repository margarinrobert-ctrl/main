"use client";

import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { loadChain } from "@/lib/client-data";
import type { OptionContract } from "@/lib/barchart/types";
import { filterByExpiration, oiByStrike } from "@/lib/flow/analytics";
import { AXIS_PROPS, CHART, GRID_PROPS, TOOLTIP_CURSOR, TOOLTIP_PROPS, refLabel } from "@/lib/chartTheme";
import { EmptyState, ErrorState, Loading, SectionHeader } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

export function OiProfile({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [spot, setSpot] = useState<number | null>(null);
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setState("loading");
      try {
        const res = await loadChain(symbol);
        if (cancelled) return;
        setChain(res.chain);
        setSpot(res.spot);
        setState(res.chain.length ? "ok" : "empty");
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

  const { data, spotX } = useMemo(() => {
    const by = oiByStrike(filterByExpiration(chain, exp));
    let rows = by;
    if (spot != null && by.length > 41) {
      let idx = 0;
      let best = Infinity;
      by.forEach((x, i) => {
        const d = Math.abs(x.strike - spot);
        if (d < best) {
          best = d;
          idx = i;
        }
      });
      rows = by.slice(Math.max(0, idx - 20), Math.min(by.length, idx + 21));
    }
    const d = rows.map((x) => ({ strike: x.strike, callOi: x.callOi, putOi: x.putOi }));
    const spotX =
      spot == null || d.length === 0
        ? null
        : d.reduce((p, c) => (Math.abs(c.strike - spot) < Math.abs(p - spot) ? c.strike : p), d[0].strike);
    return { data: d, spotX };
  }, [chain, spot, exp]);

  return (
    <div className="glass glass-hover fade-up p-4 sm:p-5">
      <SectionHeader eyebrow="Open interest" title={symbol} right={<span className="lbl">Contracts by strike</span>} />
      {state === "loading" && <Loading label="Loading open interest…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No open-interest data for this chain." />}
      {state === "ok" && (
        <>
          <div className="h-[340px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} margin={{ top: 8, right: 8, left: 4, bottom: 8 }}>
                <defs>
                  <linearGradient id="oi-call" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={CHART.call} stopOpacity={0.9} />
                    <stop offset="100%" stopColor={CHART.call} stopOpacity={0.4} />
                  </linearGradient>
                  <linearGradient id="oi-put" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={CHART.put} stopOpacity={0.9} />
                    <stop offset="100%" stopColor={CHART.put} stopOpacity={0.4} />
                  </linearGradient>
                </defs>
                <CartesianGrid {...GRID_PROPS} />
                <XAxis dataKey="strike" {...AXIS_PROPS} minTickGap={18} />
                <YAxis tickFormatter={(v) => (Number(v) >= 1000 ? `${Math.round(Number(v) / 1000)}k` : String(v))} {...AXIS_PROPS} width={44} />
                <Tooltip
                  {...TOOLTIP_PROPS}
                  formatter={(v: number | string, n) => [Number(v).toLocaleString(), n]}
                  labelFormatter={(l) => `Strike ${l}`}
                  cursor={TOOLTIP_CURSOR}
                />
                {spotX != null && <ReferenceLine x={spotX} stroke={CHART.spot} strokeDasharray="3 3" label={refLabel("Spot", CHART.spot, "insideTopRight")} />}
                <Bar dataKey="callOi" name="Call OI" fill="url(#oi-call)" radius={[2, 2, 0, 0]} isAnimationActive={false} />
                <Bar dataKey="putOi" name="Put OI" fill="url(#oi-put)" radius={[2, 2, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-white/[0.05] pt-3">
            {[
              { c: CHART.call, l: "Call OI" },
              { c: CHART.put, l: "Put OI" },
              { c: CHART.spot, l: "Spot" },
            ].map((it) => (
              <span key={it.l} className="flex items-center gap-1.5 text-[11px] text-neutral-500">
                <span className="h-2 w-2 rounded-sm" style={{ background: it.c }} />
                {it.l}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
