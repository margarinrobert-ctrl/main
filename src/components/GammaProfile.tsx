"use client";

import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { loadChain } from "@/lib/client-data";
import type { OptionContract } from "@/lib/barchart/types";
import { callWall, fmtUsd, gammaFlip, gexByStrike, putWall } from "@/lib/flow/analytics";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

export function GammaProfile({ symbol }: { symbol: string }) {
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

  const { data, levels } = useMemo(() => {
    const by = gexByStrike(chain, spot);
    const flip = gammaFlip(by);
    const cw = callWall(by);
    const pw = putWall(by);

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
    const d = rows.map((x) => ({ strike: x.strike, gex: x.gex })).sort((a, b) => b.strike - a.strike);
    const snap = (target: number | null) =>
      target == null || d.length === 0
        ? null
        : d.reduce((p, c) => (Math.abs(c.strike - target) < Math.abs(p - target) ? c.strike : p), d[0].strike);
    return { data: d, levels: { S: snap(spot), C: snap(cw), G: snap(flip), P: snap(pw) } };
  }, [chain, spot]);

  const height = Math.min(720, Math.max(380, data.length * 20));

  return (
    <div className="glass p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-semibold">Gamma profile · {symbol}</h2>
        <span className="text-xs text-neutral-500">net GEX by strike ($/1%)</span>
      </div>
      {state === "loading" && <Loading label="Loading gamma…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No gamma data (needs greeks)." />}
      {state === "ok" && (
        <>
          <div style={{ height }} className="w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} layout="vertical" margin={{ top: 8, right: 44, left: 8, bottom: 8 }}>
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
                  formatter={(v: number | string) => [fmtUsd(Number(v)), "net GEX"]}
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
                {levels.G != null && (
                  <ReferenceLine y={levels.G} stroke="#f59e0b" strokeDasharray="4 4" label={{ value: "G", position: "right", fill: "#f59e0b", fontSize: 11 }} />
                )}
                {levels.P != null && (
                  <ReferenceLine y={levels.P} stroke="#ef4444" strokeDasharray="4 4" label={{ value: "P", position: "right", fill: "#ef4444", fontSize: 11 }} />
                )}
                <Bar dataKey="gex" radius={[0, 3, 3, 0]} isAnimationActive={false}>
                  {data.map((d) => (
                    <Cell key={d.strike} fill={d.gex >= 0 ? "#10b981" : "#ef4444"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-neutral-400">
            <span><span className="text-neutral-200">S</span> spot</span>
            <span><span className="text-emerald-400">C</span> call wall</span>
            <span><span className="text-amber-400">G</span> γ-flip</span>
            <span><span className="text-red-400">P</span> put wall</span>
            <span className="text-neutral-500">· green = positive dealer gamma, red = negative</span>
          </div>
        </>
      )}
    </div>
  );
}
