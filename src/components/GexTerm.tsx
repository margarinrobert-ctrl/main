"use client";

import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { loadChain } from "@/lib/client-data";
import type { OptionContract } from "@/lib/barchart/types";
import { fmtUsd, gexByExpiration } from "@/lib/flow/analytics";
import { AXIS_PROPS, CHART, GRID_PROPS, TOOLTIP_CURSOR, TOOLTIP_PROPS } from "@/lib/chartTheme";
import { EmptyState, ErrorState, Loading, SectionHeader } from "./states";
import { useChartFrame } from "./chartFrame";

type ViewState = "loading" | "error" | "empty" | "ok";

export function GexTerm({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [spot, setSpot] = useState<number | null>(null);
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");
  const frame = useChartFrame(`${symbol} GEX term`);

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

  const data = useMemo(
    () =>
      gexByExpiration(chain, spot).map((x) => ({
        label: x.dte != null ? `${x.dte}d` : x.expiration.slice(5),
        expiration: x.expiration,
        gex: x.gex,
      })),
    [chain, spot],
  );

  return (
    <div ref={frame.ref} className={`glass glass-hover fade-up p-4 sm:p-5 ${frame.expandedClass}`}>
      <SectionHeader
        eyebrow="Gamma term structure"
        title={symbol}
        right={
          <div className="flex items-center gap-2">
            <span className="lbl">Net GEX by expiration ($/1%)</span>
            {frame.controls}
          </div>
        }
      />
      {state === "loading" && <Loading label="Loading term structure…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="Greeks unavailable for this chain." />}
      {state === "ok" && (
        <>
          <div className={data.length > 14 ? "overflow-x-auto" : ""}>
            <div className={`${frame.expanded ? "h-[calc(100vh-200px)]" : "h-[320px]"} w-full`} style={data.length > 14 ? { minWidth: data.length * 44 } : undefined}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data} margin={{ top: 8, right: 8, left: 4, bottom: 8 }}>
                  <defs>
                    <linearGradient id="gt-pos" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={CHART.call} stopOpacity={0.9} />
                      <stop offset="100%" stopColor={CHART.call} stopOpacity={0.4} />
                    </linearGradient>
                    <linearGradient id="gt-neg" x1="0" y1="1" x2="0" y2="0">
                      <stop offset="0%" stopColor={CHART.put} stopOpacity={0.9} />
                      <stop offset="100%" stopColor={CHART.put} stopOpacity={0.4} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid {...GRID_PROPS} />
                  <XAxis dataKey="label" {...AXIS_PROPS} />
                  <YAxis tickFormatter={(v) => fmtUsd(Number(v))} {...AXIS_PROPS} width={64} />
                  <Tooltip
                    {...TOOLTIP_PROPS}
                    formatter={(v: number | string) => [fmtUsd(Number(v)), "Net GEX"]}
                    labelFormatter={(l, p) => `${p?.[0]?.payload?.expiration ?? l}`}
                    cursor={TOOLTIP_CURSOR}
                  />
                  <ReferenceLine y={0} stroke="rgba(255,255,255,0.16)" />
                  <Bar dataKey="gex" radius={[3, 3, 0, 0]} isAnimationActive={false}>
                    {data.map((d) => {
                      const selected = exp !== "ALL" && d.expiration === exp;
                      return (
                        <Cell
                          key={d.expiration}
                          fill={d.gex >= 0 ? "url(#gt-pos)" : "url(#gt-neg)"}
                          style={selected ? { filter: `drop-shadow(0 0 6px ${d.gex >= 0 ? "rgba(52,211,153,0.55)" : "rgba(248,113,113,0.55)"})` } : undefined}
                          opacity={exp !== "ALL" && !selected ? 0.45 : 1}
                        />
                      );
                    })}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-neutral-500">
            Dealer gamma concentration by tenor — front expirations drive intraday pinning.
          </p>
        </>
      )}
    </div>
  );
}
