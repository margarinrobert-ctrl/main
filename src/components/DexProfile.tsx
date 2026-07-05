"use client";

import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { loadChain } from "@/lib/client-data";
import type { OptionContract } from "@/lib/barchart/types";
import { deltaCallWall, deltaFlip, deltaPutWall, dexByStrike, fmtUsd, netDex } from "@/lib/flow/analytics";
import { AXIS_PROPS, CHART, CHART_TICK, TOOLTIP_CURSOR, TOOLTIP_PROPS, refLabel } from "@/lib/chartTheme";
import { EmptyState, ErrorState, Loading, SectionHeader } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

export function DexProfile({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
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

  const { data, levels, ndex } = useMemo(() => {
    const sub = exp === "ALL" ? chain : chain.filter((c) => c.expiration === exp);
    const by = dexByStrike(sub, spot);
    const cw = deltaCallWall(by, spot);
    const pw = deltaPutWall(by, spot);
    const flip = deltaFlip(by, spot);

    let rows = by;
    if (spot != null && by.length > 31) {
      let idx = 0;
      let best = Infinity;
      by.forEach((x, i) => {
        const d = Math.abs(x.strike - spot);
        if (d < best) {
          best = d;
          idx = i;
        }
      });
      rows = by.slice(Math.max(0, idx - 15), Math.min(by.length, idx + 16));
    }
    // high strikes at the top
    const d = rows.map((x) => ({ strike: x.strike, callDex: x.callDex, putDex: x.putDex, dex: x.dex })).sort((a, b) => b.strike - a.strike);
    const snap = (target: number | null) =>
      target == null || d.length === 0
        ? null
        : d.reduce((p, c) => (Math.abs(c.strike - target) < Math.abs(p - target) ? c.strike : p), d[0].strike);
    return { data: d, levels: { S: snap(spot), C: snap(cw), F: snap(flip), P: snap(pw) }, ndex: netDex(sub, spot) };
  }, [chain, spot, exp]);

  const height = Math.min(720, Math.max(380, data.length * 22));

  return (
    <div className="glass glass-hover fade-up p-4 sm:p-5">
      <SectionHeader
        eyebrow="Delta exposure"
        title={symbol}
        right={
          <span className="lbl">
            $Δ of OI by strike · {exp === "ALL" ? "all expirations" : exp}
            {ndex != null ? ` · net ${fmtUsd(ndex)}` : ""}
          </span>
        }
      />
      {state === "loading" && <Loading label="Loading delta exposure…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="Greeks unavailable for this chain." hint="Delta exposure requires per-contract delta; it appears once greeks are present." />}
      {state === "ok" && (
        <>
          <div style={{ height }} className="w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} layout="vertical" stackOffset="sign" margin={{ top: 8, right: 40, left: 4, bottom: 8 }} barCategoryGap={1}>
                <defs>
                  <linearGradient id="dx-call" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stopColor={CHART.call} stopOpacity={0.45} />
                    <stop offset="100%" stopColor={CHART.call} stopOpacity={0.9} />
                  </linearGradient>
                  <linearGradient id="dx-put" x1="1" y1="0" x2="0" y2="0">
                    <stop offset="0%" stopColor={CHART.put} stopOpacity={0.45} />
                    <stop offset="100%" stopColor={CHART.put} stopOpacity={0.9} />
                  </linearGradient>
                </defs>
                <XAxis type="number" tickFormatter={(v) => fmtUsd(Number(v))} {...AXIS_PROPS} />
                <YAxis type="category" dataKey="strike" {...AXIS_PROPS} tick={CHART_TICK} width={48} interval={0} />
                <Tooltip
                  {...TOOLTIP_PROPS}
                  formatter={(v: number | string, name) => [fmtUsd(Number(v)), name === "callDex" ? "Call Δ-exposure" : "Put Δ-exposure"]}
                  labelFormatter={(l) => `Strike ${l}`}
                  cursor={TOOLTIP_CURSOR}
                />
                <ReferenceLine x={0} stroke="rgba(255,255,255,0.16)" />
                {levels.S != null && (
                  <ReferenceLine y={levels.S} stroke={CHART.spot} strokeDasharray="4 4" label={refLabel("Spot", CHART.spot, "insideTopRight")} />
                )}
                {levels.C != null && (
                  <ReferenceLine y={levels.C} stroke={CHART.call} strokeDasharray="4 4" label={refLabel("Δ call wall", CHART.call, "insideTopLeft")} />
                )}
                {levels.F != null && (
                  <ReferenceLine y={levels.F} stroke={CHART.violet} strokeDasharray="4 4" label={refLabel("Δ-neutral", CHART.violet, "insideTopRight")} />
                )}
                {levels.P != null && (
                  <ReferenceLine y={levels.P} stroke={CHART.put} strokeDasharray="4 4" label={refLabel("Δ put wall", CHART.put, "insideTopLeft")} />
                )}
                <Bar dataKey="callDex" stackId="dex" fill="url(#dx-call)" radius={[0, 3, 3, 0]} isAnimationActive={false} />
                <Bar dataKey="putDex" stackId="dex" fill="url(#dx-put)" radius={[3, 0, 0, 3]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-white/[0.05] pt-3">
            {[
              { c: CHART.call, l: "Call Δ-exposure" },
              { c: CHART.put, l: "Put Δ-exposure" },
              { c: CHART.spot, l: "Spot" },
              { c: CHART.violet, l: "Δ-neutral" },
            ].map((it) => (
              <span key={it.l} className="flex items-center gap-1.5 text-[11px] text-neutral-500">
                <span className="h-2 w-2 rounded-sm" style={{ background: it.c }} />
                {it.l}
              </span>
            ))}
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-neutral-600">
            Delta-exposure = delta × open interest × 100 × spot, per strike. Peak call Δ-exposure above spot marks hedgeable
            resistance; peak put Δ-exposure below spot marks hedgeable support.
          </p>
        </>
      )}
    </div>
  );
}
