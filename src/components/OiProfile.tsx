"use client";

import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { loadChain } from "@/lib/client-data";
import type { OptionContract } from "@/lib/barchart/types";
import { filterByExpiration, oiByStrike } from "@/lib/flow/analytics";
import { EmptyState, ErrorState, Loading } from "./states";

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
    <div className="glass p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-semibold">Open interest · {symbol}</h2>
        <span className="text-xs text-neutral-500">contracts by strike</span>
      </div>
      {state === "loading" && <Loading label="Loading OI…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No open-interest data." />}
      {state === "ok" && (
        <div className="h-[340px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
              <CartesianGrid stroke="#262626" />
              <XAxis dataKey="strike" tick={{ fill: "#a3a3a3", fontSize: 11 }} stroke="#404040" />
              <YAxis tickFormatter={(v) => (Number(v) >= 1000 ? `${Math.round(Number(v) / 1000)}k` : String(v))} tick={{ fill: "#a3a3a3", fontSize: 11 }} stroke="#404040" width={48} />
              <Tooltip
                contentStyle={{ background: "#0a0a0a", border: "1px solid #404040", borderRadius: 6, fontSize: 12 }}
                formatter={(v: number | string, n) => [Number(v).toLocaleString(), n]}
                labelFormatter={(l) => `strike ${l}`}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {spotX != null && <ReferenceLine x={spotX} stroke="#e5e5e5" strokeDasharray="3 3" label={{ value: "spot", fill: "#e5e5e5", fontSize: 10, position: "top" }} />}
              <Bar dataKey="callOi" name="Call OI" fill="#10b981" />
              <Bar dataKey="putOi" name="Put OI" fill="#ef4444" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
