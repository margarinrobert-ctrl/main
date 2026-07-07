"use client";

import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { loadChain } from "@/lib/client-data";
import type { OptionContract } from "@/lib/barchart/types";
import { AXIS_PROPS, CHART, GRID_PROPS, TOOLTIP_CURSOR_LINE, TOOLTIP_PROPS, refLabel } from "@/lib/chartTheme";
import { EmptyState, ErrorState, Loading, SectionHeader } from "./states";
import { useChartFrame } from "./chartFrame";

type ViewState = "loading" | "error" | "empty" | "ok";

export function SkewChart({ symbol, exp: globalExp = "ALL" }: { symbol: string; exp?: string }) {
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [spot, setSpot] = useState<number | null>(null);
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");
  const [exp, setExp] = useState("");

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

  const expirations = useMemo(() => [...new Set(chain.map((c) => c.expiration))].sort(), [chain]);
  useEffect(() => {
    if (expirations.length && !expirations.includes(exp)) {
      const withDte = expirations.map((e) => ({ e, dte: chain.find((c) => c.expiration === e)?.dte ?? 9999 }));
      const future = withDte.filter((x) => x.dte >= 0).sort((a, b) => a.dte - b.dte);
      setExp((future[0] ?? withDte[0]).e);
    }
  }, [expirations, chain, exp]);

  // Honor the dashboard-wide expiration selector (overrides the local default).
  useEffect(() => {
    if (globalExp && globalExp !== "ALL" && chain.some((c) => c.expiration === globalExp)) setExp(globalExp);
  }, [globalExp, chain]);

  const data = useMemo(() => {
    const m = new Map<number, { strike: number; call?: number; put?: number }>();
    for (const c of chain) {
      if (c.expiration !== exp || c.impliedVolatility == null) continue;
      const e = m.get(c.strike) ?? { strike: c.strike };
      if (c.type === "call") e.call = c.impliedVolatility * 100;
      else e.put = c.impliedVolatility * 100;
      m.set(c.strike, e);
    }
    return [...m.values()].sort((a, b) => a.strike - b.strike);
  }, [chain, exp]);

  const spotX = useMemo(
    () =>
      spot == null || data.length === 0
        ? null
        : data.reduce((p, c) => (Math.abs(c.strike - spot) < Math.abs(p - spot) ? c.strike : p), data[0].strike),
    [data, spot],
  );

  const frame = useChartFrame(`${symbol} IV skew`);

  return (
    <div ref={frame.ref} className={`glass glass-hover fade-up p-4 sm:p-5 ${frame.expandedClass}`}>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="lbl mb-1">IV skew</div>
          <h2 className="display text-base text-neutral-50">{symbol}</h2>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <select
              value={exp}
              onChange={(e) => setExp(e.target.value)}
              aria-label="Expiration"
              className="appearance-none rounded-lg border border-white/10 bg-white/[0.03] py-2 pl-3 pr-8 text-xs text-neutral-100 outline-none transition hover:border-white/20 focus:border-accent/50"
            >
              {expirations.map((e) => (
                <option key={e} value={e} className="bg-neutral-900">
                  {e}
                </option>
              ))}
            </select>
            <svg aria-hidden viewBox="0 0 12 12" className="pointer-events-none absolute right-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-neutral-500">
              <path fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" d="m2.5 4.5 3.5 3.5 3.5-3.5" />
            </svg>
          </div>
          {frame.controls}
        </div>
      </div>
      {state === "loading" && <Loading label="Loading IV skew…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No implied-volatility data for this chain." />}
      {state === "ok" && (
        <>
          <div className={`${frame.expanded ? "h-[calc(100vh-200px)]" : "h-[320px]"} w-full`}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 8, right: 8, left: 4, bottom: 8 }}>
                <CartesianGrid {...GRID_PROPS} />
                <XAxis dataKey="strike" {...AXIS_PROPS} minTickGap={18} />
                <YAxis tickFormatter={(v) => `${v}%`} {...AXIS_PROPS} width={44} domain={["auto", "auto"]} />
                <Tooltip
                  {...TOOLTIP_PROPS}
                  cursor={TOOLTIP_CURSOR_LINE}
                  formatter={(v: number | string, n) => [`${Number(v).toFixed(1)}%`, n]}
                  labelFormatter={(l) => `Strike ${l}`}
                />
                {spotX != null && <ReferenceLine x={spotX} stroke={CHART.spot} strokeDasharray="3 3" label={refLabel("Spot", CHART.spot, "insideTopRight")} />}
                <Line type="monotone" dataKey="call" name="Call IV" stroke={CHART.call} dot={false} strokeWidth={2} connectNulls isAnimationActive={false} />
                <Line type="monotone" dataKey="put" name="Put IV" stroke={CHART.put} dot={false} strokeWidth={2} connectNulls isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-white/[0.05] pt-3">
            {[
              { c: CHART.call, l: "Call IV" },
              { c: CHART.put, l: "Put IV" },
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
