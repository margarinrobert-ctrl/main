"use client";

import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { loadChain } from "@/lib/client-data";
import type { OptionContract } from "@/lib/barchart/types";
import { fmtUsd, gexByExpiration } from "@/lib/flow/analytics";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

export function GexTerm({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
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
    <div className="glass p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-semibold">Gamma term structure · {symbol}</h2>
        <span className="text-xs text-neutral-500">net GEX by expiration ($/1%)</span>
      </div>
      {state === "loading" && <Loading label="Loading term structure…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No gamma data (needs greeks)." />}
      {state === "ok" && (
        <>
          <div className="h-[320px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
                <CartesianGrid stroke="#262626" />
                <XAxis dataKey="label" tick={{ fill: "#a3a3a3", fontSize: 11 }} stroke="#404040" />
                <YAxis tickFormatter={(v) => fmtUsd(Number(v))} tick={{ fill: "#a3a3a3", fontSize: 11 }} stroke="#404040" width={70} />
                <Tooltip
                  contentStyle={{ background: "#0a0a0a", border: "1px solid #404040", borderRadius: 6, fontSize: 12 }}
                  formatter={(v: number | string) => [fmtUsd(Number(v)), "net GEX"]}
                  labelFormatter={(l, p) => `${p?.[0]?.payload?.expiration ?? l}`}
                  cursor={{ fill: "rgba(255,255,255,0.04)" }}
                />
                <ReferenceLine y={0} stroke="#525252" />
                <Bar dataKey="gex" radius={[3, 3, 0, 0]} isAnimationActive={false}>
                  {data.map((d) => (
                    <Cell
                      key={d.expiration}
                      fill={d.gex >= 0 ? "#10b981" : "#ef4444"}
                      stroke={exp !== "ALL" && d.expiration === exp ? "#e5e5e5" : undefined}
                      strokeWidth={exp !== "ALL" && d.expiration === exp ? 2 : 0}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-xs text-neutral-500">
            Where dealer gamma concentrates by tenor — front expirations (e.g. 0DTE/weeklies) drive intraday pinning.
          </p>
        </>
      )}
    </div>
  );
}
