"use client";

import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { loadChain } from "@/lib/client-data";
import type { OptionContract } from "@/lib/barchart/types";
import { fmtUsd, gammaFlip, gexByStrike } from "@/lib/flow/analytics";
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

  const { data, spotX, flipX } = useMemo(() => {
    const by = gexByStrike(chain, spot);
    const flip = gammaFlip(by);
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
    const d = rows.map((x) => ({ strike: x.strike, gex: x.gex }));
    const nearest = (target: number | null) =>
      target == null || d.length === 0 ? null : d.reduce((p, c) => (Math.abs(c.strike - target) < Math.abs(p - target) ? c.strike : p), d[0].strike);
    return { data: d, spotX: nearest(spot), flipX: nearest(flip) };
  }, [chain, spot]);

  return (
    <div className="rounded-lg border border-neutral-800 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-semibold">Gamma profile · {symbol}</h2>
        <span className="text-xs text-neutral-500">net GEX by strike ($/1%)</span>
      </div>
      {state === "loading" && <Loading label="Loading gamma…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No gamma data (needs greeks)." />}
      {state === "ok" && (
        <>
          <div className="h-[340px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
                <XAxis dataKey="strike" tick={{ fill: "#a3a3a3", fontSize: 11 }} stroke="#404040" />
                <YAxis tickFormatter={(v) => fmtUsd(Number(v))} tick={{ fill: "#a3a3a3", fontSize: 11 }} stroke="#404040" width={70} />
                <Tooltip
                  contentStyle={{ background: "#0a0a0a", border: "1px solid #404040", borderRadius: 6, fontSize: 12 }}
                  formatter={(v: number | string) => [fmtUsd(Number(v)), "net GEX"]}
                  labelFormatter={(l) => `strike ${l}`}
                />
                <ReferenceLine y={0} stroke="#525252" />
                {spotX != null && <ReferenceLine x={spotX} stroke="#e5e5e5" strokeDasharray="3 3" label={{ value: "spot", fill: "#e5e5e5", fontSize: 10, position: "top" }} />}
                {flipX != null && <ReferenceLine x={flipX} stroke="#f59e0b" strokeDasharray="3 3" label={{ value: "γ-flip", fill: "#f59e0b", fontSize: 10, position: "insideTopRight" }} />}
                <Bar dataKey="gex">
                  {data.map((d) => (
                    <Cell key={d.strike} fill={d.gex >= 0 ? "#10b981" : "#ef4444"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-xs text-neutral-500">
            Green = positive dealer gamma (supportive/mean-reverting), red = negative (trend-amplifying). The amber line
            is the zero-gamma flip; below it dealers are typically short gamma.
          </p>
        </>
      )}
    </div>
  );
}
