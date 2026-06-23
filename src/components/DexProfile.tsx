"use client";

import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { loadChain } from "@/lib/client-data";
import type { OptionContract } from "@/lib/barchart/types";
import { deltaCallWall, deltaFlip, deltaPutWall, dexByStrike, fmtUsd, netDex } from "@/lib/flow/analytics";
import { EmptyState, ErrorState, Loading } from "./states";

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
    <div className="glass p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Delta-exposure (DEX) profile · {symbol}</h2>
        <span className="text-xs text-neutral-500">
          $Δ of OI by strike · {exp === "ALL" ? "all expirations" : exp}
          {ndex != null ? ` · net ${fmtUsd(ndex)}` : ""}
        </span>
      </div>
      {state === "loading" && <Loading label="Loading delta exposure…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No delta data (needs greeks)." />}
      {state === "ok" && (
        <>
          <div style={{ height }} className="w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} layout="vertical" margin={{ top: 8, right: 44, left: 8, bottom: 8 }} barCategoryGap={1}>
                <XAxis
                  type="number"
                  tickFormatter={(v) => fmtUsd(Number(v))}
                  tick={{ fill: "#a3a3a3", fontSize: 11 }}
                  stroke="#404040"
                />
                <YAxis
                  type="category"
                  dataKey="strike"
                  tick={{ fill: "#a3a3a3", fontSize: 10 }}
                  stroke="#404040"
                  width={56}
                  interval={0}
                />
                <Tooltip
                  contentStyle={{ background: "#0a0a0a", border: "1px solid #404040", borderRadius: 6, fontSize: 12 }}
                  formatter={(v: number | string, name) => [fmtUsd(Number(v)), name === "callDex" ? "call Δ-exp" : "put Δ-exp"]}
                  labelFormatter={(l) => `strike ${l}`}
                  cursor={{ fill: "rgba(255,255,255,0.04)" }}
                />
                <ReferenceLine x={0} stroke="#525252" />
                {levels.S != null && (
                  <ReferenceLine y={levels.S} stroke="#e5e5e5" strokeDasharray="4 4" label={{ value: "S", position: "right", fill: "#e5e5e5", fontSize: 11 }} />
                )}
                {levels.C != null && (
                  <ReferenceLine y={levels.C} stroke="#34d399" strokeDasharray="4 4" label={{ value: "C", position: "right", fill: "#34d399", fontSize: 11 }} />
                )}
                {levels.F != null && (
                  <ReferenceLine y={levels.F} stroke="#f59e0b" strokeDasharray="4 4" label={{ value: "F", position: "right", fill: "#f59e0b", fontSize: 11 }} />
                )}
                {levels.P != null && (
                  <ReferenceLine y={levels.P} stroke="#ef4444" strokeDasharray="4 4" label={{ value: "P", position: "right", fill: "#ef4444", fontSize: 11 }} />
                )}
                <Bar dataKey="callDex" stackId="dex" radius={[0, 3, 3, 0]} isAnimationActive={false}>
                  {data.map((d) => (
                    <Cell key={`c-${d.strike}`} fill="#10b981" />
                  ))}
                </Bar>
                <Bar dataKey="putDex" stackId="dex" radius={[3, 0, 0, 3]} isAnimationActive={false}>
                  {data.map((d) => (
                    <Cell key={`p-${d.strike}`} fill="#ef4444" />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-neutral-400">
            <span><span className="text-neutral-200">S</span> spot</span>
            <span><span className="text-emerald-400">C</span> Δ call wall</span>
            <span><span className="text-amber-400">F</span> Δ-neutral flip</span>
            <span><span className="text-red-400">P</span> Δ put wall</span>
            <span className="text-neutral-500">· green = call delta (right), red = put delta (left)</span>
          </div>
          <p className="mt-2 text-[11px] text-neutral-500">
            Delta-exposure = delta × open interest × 100 × spot, per strike. The <b>call wall</b> (peak call Δ above spot)
            tends to act as resistance and the <b>put wall</b> (peak put Δ below spot) as support — delta-weighting favours
            the strikes that actually move with price, so these track the <i>hedgeable</i> delta dealers must trade.
          </p>
        </>
      )}
    </div>
  );
}
