"use client";

import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { loadChain } from "@/lib/client-data";
import type { OptionContract } from "@/lib/barchart/types";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

export function SkewChart({ symbol }: { symbol: string }) {
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

  return (
    <div className="rounded-lg border border-neutral-800 p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">IV skew · {symbol}</h2>
        <select
          value={exp}
          onChange={(e) => setExp(e.target.value)}
          className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-xs"
        >
          {expirations.map((e) => (
            <option key={e} value={e}>
              {e}
            </option>
          ))}
        </select>
      </div>
      {state === "loading" && <Loading label="Loading skew…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No IV data." />}
      {state === "ok" && (
        <div className="h-[320px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
              <CartesianGrid stroke="#262626" />
              <XAxis dataKey="strike" tick={{ fill: "#a3a3a3", fontSize: 11 }} stroke="#404040" />
              <YAxis tickFormatter={(v) => `${v}%`} tick={{ fill: "#a3a3a3", fontSize: 11 }} stroke="#404040" width={44} domain={["auto", "auto"]} />
              <Tooltip
                contentStyle={{ background: "#0a0a0a", border: "1px solid #404040", borderRadius: 6, fontSize: 12 }}
                formatter={(v: number | string, n) => [`${Number(v).toFixed(1)}%`, n]}
                labelFormatter={(l) => `strike ${l}`}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {spotX != null && <ReferenceLine x={spotX} stroke="#e5e5e5" strokeDasharray="3 3" />}
              <Line type="monotone" dataKey="call" name="Call IV" stroke="#34d399" dot={false} strokeWidth={2} connectNulls />
              <Line type="monotone" dataKey="put" name="Put IV" stroke="#f87171" dot={false} strokeWidth={2} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
