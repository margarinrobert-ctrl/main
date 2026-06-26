"use client";

import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { loadChain } from "@/lib/client-data";
import type { OptionContract } from "@/lib/barchart/types";
import { callWall, fmtUsd, gammaFlip, gexByStrike, putWall } from "@/lib/flow/analytics";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

const CALL = "#2f9e5f";
const PUT = "#b4493d";

export function GammaProfile({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
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
    const sub = exp === "ALL" ? chain : chain.filter((c) => c.expiration === exp);
    const by = gexByStrike(sub, spot);
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
    // high strikes at the top; callGex ≥0 (right), putGex ≤0 (left) → diverging profile
    const d = rows.map((x) => ({ strike: x.strike, callGex: x.callGex, putGex: x.putGex })).sort((a, b) => b.strike - a.strike);
    const snap = (target: number | null) =>
      target == null || d.length === 0 ? null : d.reduce((p, c) => (Math.abs(c.strike - target) < Math.abs(p - target) ? c.strike : p), d[0].strike);
    return { data: d, levels: { S: snap(spot), C: snap(cw), G: snap(flip), P: snap(pw) } };
  }, [chain, spot, exp]);

  const height = Math.min(720, Math.max(380, data.length * 20));

  return (
    <div className="glass p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Gamma exposure · {symbol}</h2>
        <span className="lbl">net GEX ($/1%) · {exp === "ALL" ? "all expirations" : exp}</span>
      </div>
      {state === "loading" && <Loading label="Loading gamma…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No gamma data (needs greeks)." />}
      {state === "ok" && (
        <>
          <div style={{ height }} className="relative w-full">
            {/* PUT / CALL watermark */}
            <div className="pointer-events-none absolute inset-0 flex items-center justify-between px-[18%] text-4xl font-bold tracking-widest text-white/[0.04]">
              <span>PUT</span>
              <span>CALL</span>
            </div>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} layout="vertical" stackOffset="sign" margin={{ top: 8, right: 44, left: 8, bottom: 8 }} barCategoryGap={1}>
                <XAxis type="number" tickFormatter={(v) => fmtUsd(Number(v))} tick={{ fill: "#a3a3a3", fontSize: 11 }} stroke="#404040" />
                <YAxis type="category" dataKey="strike" tick={{ fill: "#a3a3a3", fontSize: 10 }} stroke="#404040" width={56} interval={0} />
                <Tooltip
                  contentStyle={{ background: "#0a0a0a", border: "1px solid #404040", borderRadius: 6, fontSize: 12 }}
                  formatter={(v: number | string, n) => [fmtUsd(Number(v)), n === "callGex" ? "call GEX" : "put GEX"]}
                  labelFormatter={(l) => `strike ${l}`}
                  cursor={{ fill: "rgba(255,255,255,0.04)" }}
                />
                <ReferenceLine x={0} stroke="#525252" />
                {levels.S != null && <ReferenceLine y={levels.S} stroke="#d4c44a" strokeDasharray="4 4" label={{ value: "S", position: "right", fill: "#d4c44a", fontSize: 11 }} />}
                {levels.C != null && <ReferenceLine y={levels.C} stroke={CALL} strokeDasharray="4 4" label={{ value: "C", position: "right", fill: CALL, fontSize: 11 }} />}
                {levels.G != null && <ReferenceLine y={levels.G} stroke="#8b7bd8" strokeDasharray="4 4" label={{ value: "G", position: "right", fill: "#8b7bd8", fontSize: 11 }} />}
                {levels.P != null && <ReferenceLine y={levels.P} stroke={PUT} strokeDasharray="4 4" label={{ value: "P", position: "right", fill: PUT, fontSize: 11 }} />}
                <Bar dataKey="putGex" stackId="gex" fill={PUT} radius={[3, 0, 0, 3]} isAnimationActive={false} />
                <Bar dataKey="callGex" stackId="gex" fill={CALL} radius={[0, 3, 3, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-neutral-400">
            <span><span className="text-call">▮</span> call γ (right)</span>
            <span><span className="text-put">▮</span> put γ (left)</span>
            <span><span style={{ color: "#d4c44a" }}>S</span> spot</span>
            <span><span className="text-call">C</span> call wall</span>
            <span><span style={{ color: "#8b7bd8" }}>G</span> γ-flip</span>
            <span><span className="text-put">P</span> put wall</span>
          </div>
        </>
      )}
    </div>
  );
}
