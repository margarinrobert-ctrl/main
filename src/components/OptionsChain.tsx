"use client";

import { useEffect, useMemo, useState } from "react";
import { loadChain } from "@/lib/client-data";
import type { OptionContract } from "@/lib/barchart/types";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

function fmt(n: number | null): string {
  return n == null ? "—" : n.toFixed(2);
}

export function OptionsChain({ symbol }: { symbol: string }) {
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [source, setSource] = useState("");
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setState("loading");
      try {
        const { chain, source } = await loadChain(symbol);
        if (cancelled) return;
        setSource(source);
        setChain(chain);
        setState(chain.length ? "ok" : "empty");
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

  const summary = useMemo(() => {
    const ivs = chain.map((c) => c.impliedVolatility).filter((x): x is number => x != null);
    const avgIv = ivs.length ? ivs.reduce((a, b) => a + b, 0) / ivs.length : null;
    const callVol = chain.filter((c) => c.type === "call").reduce((a, c) => a + (c.volume ?? 0), 0);
    const putVol = chain.filter((c) => c.type === "put").reduce((a, c) => a + (c.volume ?? 0), 0);
    const pcr = callVol > 0 ? putVol / callVol : null;
    return { count: chain.length, avgIv, callVol, putVol, pcr };
  }, [chain]);

  const expirations = useMemo(() => Array.from(new Set(chain.map((c) => c.expiration))).sort(), [chain]);

  return (
    <div className="rounded-lg border border-neutral-800 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-semibold">Options chain · {symbol}</h2>
        {source && <span className="text-xs text-neutral-500">src: {source}</span>}
      </div>

      {state === "loading" && <Loading />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options chain." />}
      {state === "ok" && (
        <>
          <div className="mb-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
            <Stat label="contracts" value={String(summary.count)} />
            <Stat label="avg IV" value={summary.avgIv != null ? summary.avgIv.toFixed(2) : "—"} />
            <Stat label="put/call (vol)" value={summary.pcr != null ? summary.pcr.toFixed(2) : "—"} />
            <Stat label="call/put vol" value={`${summary.callVol.toLocaleString()} / ${summary.putVol.toLocaleString()}`} />
          </div>

          {expirations.map((exp) => (
            <div key={exp} className="mb-4">
              <div className="mb-1 text-xs text-neutral-400">exp {exp}</div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-neutral-800 text-left text-neutral-400">
                    <tr>
                      <th className="py-1 pr-3">Type</th>
                      <th className="pr-3 text-right">Strike</th>
                      <th className="pr-3 text-right">Bid</th>
                      <th className="pr-3 text-right">Ask</th>
                      <th className="pr-3 text-right">Last</th>
                      <th className="pr-3 text-right">Vol</th>
                      <th className="pr-3 text-right">OI</th>
                      <th className="pr-3 text-right">IV</th>
                      <th className="pr-3 text-right">Δ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {chain
                      .filter((c) => c.expiration === exp)
                      .sort((a, b) => (a.type === b.type ? a.strike - b.strike : a.type === "call" ? -1 : 1))
                      .map((c) => (
                        <tr key={c.symbol} className="border-b border-neutral-900">
                          <td className={`py-1 pr-3 ${c.type === "call" ? "text-emerald-400" : "text-red-400"}`}>
                            {c.type}
                          </td>
                          <td className="pr-3 text-right">{c.strike}</td>
                          <td className="pr-3 text-right">{fmt(c.bid)}</td>
                          <td className="pr-3 text-right">{fmt(c.ask)}</td>
                          <td className="pr-3 text-right">{fmt(c.last)}</td>
                          <td className="pr-3 text-right">{c.volume?.toLocaleString() ?? "—"}</td>
                          <td className="pr-3 text-right">{c.openInterest?.toLocaleString() ?? "—"}</td>
                          <td className="pr-3 text-right">{fmt(c.impliedVolatility)}</td>
                          <td className="pr-3 text-right">{fmt(c.delta)}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-neutral-800 px-2 py-1">
      <div className="text-neutral-500">{label}</div>
      <div className="font-mono text-neutral-200">{value}</div>
    </div>
  );
}
