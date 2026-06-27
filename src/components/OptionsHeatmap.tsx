"use client";

import { useEffect, useMemo, useState } from "react";
import { loadChain } from "@/lib/client-data";
import type { OptionContract } from "@/lib/barchart/types";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";
type Metric = "volume" | "voir" | "notional";
type Side = "both" | "call" | "put";

const METRIC_LABEL: Record<Metric, string> = { volume: "Volume", voir: "Vol/OI", notional: "Notional $" };

function mid(c: OptionContract): number | null {
  if (c.bid != null && c.ask != null && c.ask > 0) return (c.bid + c.ask) / 2;
  return c.last != null && c.last > 0 ? c.last : null;
}

function metricValue(c: OptionContract, m: Metric): number {
  const vol = c.volume ?? 0;
  if (m === "volume") return vol;
  if (m === "voir") return c.openInterest && c.openInterest > 0 ? vol / c.openInterest : 0;
  const px = mid(c);
  return px != null ? vol * px * 100 : 0;
}

// blue (low) -> green -> amber -> red (high)
function heat(t: number): string {
  const stops = [
    [30, 58, 138],
    [16, 185, 129],
    [234, 179, 8],
    [239, 68, 68],
  ];
  const x = Math.max(0, Math.min(1, t)) * (stops.length - 1);
  const i = Math.floor(x);
  const f = x - i;
  const a = stops[i];
  const b = stops[Math.min(stops.length - 1, i + 1)];
  const c = a.map((v, k) => Math.round(v + (b[k] - v) * f));
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}

function fmt(v: number, m: Metric): string {
  if (m === "voir") return v.toFixed(1);
  if (m === "notional") return v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${Math.round(v / 1e3)}k` : String(Math.round(v));
  return v >= 1000 ? `${Math.round(v / 1000)}k` : String(Math.round(v));
}

export function OptionsHeatmap({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
  const isSel = (e: string) => exp !== "ALL" && e === exp;
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [source, setSource] = useState("");
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");
  const [metric, setMetric] = useState<Metric>("volume");
  const [side, setSide] = useState<Side>("both");

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

  const grid = useMemo(() => {
    const expirations = Array.from(new Set(chain.map((c) => c.expiration))).sort();
    const strikes = Array.from(new Set(chain.map((c) => c.strike))).sort((a, b) => b - a);
    const underlying = chain.find((c) => c.underlyingPrice != null)?.underlyingPrice ?? null;
    const atm = underlying != null ? strikes.reduce((p, s) => (Math.abs(s - underlying) < Math.abs(p - underlying) ? s : p), strikes[0]) : null;

    const cell = new Map<string, number>();
    let max = 0;
    for (const c of chain) {
      if (side !== "both" && c.type !== side) continue;
      const key = `${c.strike}|${c.expiration}`;
      const v = (cell.get(key) ?? 0) + metricValue(c, metric);
      cell.set(key, v);
      if (v > max) max = v;
    }
    return { expirations, strikes, cell, max, atm };
  }, [chain, metric, side]);

  return (
    <div className="glass p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Options heatmap · {symbol}</h2>
        <div className="flex items-center gap-2 text-xs">
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value as Metric)}
            className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1"
          >
            <option value="volume">Volume</option>
            <option value="voir">Vol/OI</option>
            <option value="notional">Notional $</option>
          </select>
          <select
            value={side}
            onChange={(e) => setSide(e.target.value as Side)}
            className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1"
          >
            <option value="both">calls + puts</option>
            <option value="call">calls</option>
            <option value="put">puts</option>
          </select>
        </div>
      </div>

      {state === "loading" && <Loading label="Loading heatmap…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options data for a heatmap." />}
      {state === "ok" && (
        <div className="overflow-x-auto">
          <table className="text-xs">
            <thead>
              <tr>
                <th className="sticky left-0 bg-neutral-950 px-2 py-1 text-right text-neutral-400">strike \ exp</th>
                {grid.expirations.map((e) => (
                  <th
                    key={e}
                    className={`px-2 py-1 text-center font-normal ${
                      isSel(e) ? "rounded-t bg-emerald-500/10 font-semibold text-emerald-300" : "text-neutral-400"
                    }`}
                  >
                    {e.slice(5)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grid.strikes.map((k) => (
                <tr key={k}>
                  <td
                    className={`sticky left-0 bg-neutral-950 px-2 py-1 text-right font-mono ${
                      k === grid.atm ? "font-bold text-emerald-400" : "text-neutral-300"
                    }`}
                  >
                    {k}
                    {k === grid.atm ? " ◄" : ""}
                  </td>
                  {grid.expirations.map((e) => {
                    const v = grid.cell.get(`${k}|${e}`) ?? 0;
                    const t = grid.max > 0 ? v / grid.max : 0;
                    return (
                      <td
                        key={e}
                        className={`px-2 py-1 text-center font-mono ${isSel(e) ? "ring-1 ring-inset ring-emerald-400/50" : ""}`}
                        style={{
                          backgroundColor: v > 0 ? heat(t) : "transparent",
                          color: t > 0.45 ? "#0a0a0a" : "#d4d4d4",
                        }}
                        title={`${symbol} ${k} ${e} — ${METRIC_LABEL[metric]}: ${fmt(v, metric)}`}
                      >
                        {v > 0 ? fmt(v, metric) : "·"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-3 flex items-center gap-2 text-[10px] text-neutral-500">
            <span>low</span>
            <div className="h-2 w-40 rounded" style={{ background: "linear-gradient(to right, rgb(30,58,138), rgb(16,185,129), rgb(234,179,8), rgb(239,68,68))" }} />
            <span>high · {METRIC_LABEL[metric]} ({side})</span>
          </div>
        </div>
      )}
    </div>
  );
}
