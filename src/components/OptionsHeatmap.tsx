"use client";

import { useEffect, useMemo, useState } from "react";
import { loadChain } from "@/lib/client-data";
import type { OptionContract } from "@/lib/barchart/types";
import { EmptyState, ErrorState, Loading } from "./states";
import { useChartFrame } from "./chartFrame";

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

// Tokenized activity ramp: graphite -> emerald -> bright emerald (single-hue, terminal-clean).
function heat(t: number): string {
  const x = Math.max(0, Math.min(1, t));
  if (x <= 0) return "transparent";
  // ease so mid-activity cells stay readable and the hottest cells pop
  const a = 0.06 + Math.pow(x, 0.85) * 0.86;
  return `rgba(52, 211, 153, ${a.toFixed(3)})`;
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

  const frame = useChartFrame(`${symbol} options heatmap`);

  return (
    <div ref={frame.ref} className={`glass glass-hover fade-up p-4 sm:p-5 ${frame.expandedClass}`}>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="lbl mb-1">Options heatmap</div>
          <h2 className="display text-base text-neutral-50">{symbol}</h2>
        </div>
        <div className="flex items-center gap-2">
          {[
            { value: metric, set: (v: string) => setMetric(v as Metric), opts: [["volume", "Volume"], ["voir", "Vol/OI"], ["notional", "Notional $"]], label: "Metric" },
            { value: side, set: (v: string) => setSide(v as Side), opts: [["both", "Calls + puts"], ["call", "Calls"], ["put", "Puts"]], label: "Side" },
          ].map((sel) => (
            <div key={sel.label} className="relative">
              <select
                value={sel.value}
                onChange={(e) => sel.set(e.target.value)}
                aria-label={sel.label}
                className="appearance-none rounded-lg border border-white/10 bg-white/[0.03] py-2 pl-3 pr-8 text-xs text-neutral-100 outline-none transition hover:border-white/20 focus:border-accent/50"
              >
                {sel.opts.map(([v, l]) => (
                  <option key={v} value={v} className="bg-neutral-900">
                    {l}
                  </option>
                ))}
              </select>
              <svg aria-hidden viewBox="0 0 12 12" className="pointer-events-none absolute right-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-neutral-500">
                <path fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" d="m2.5 4.5 3.5 3.5 3.5-3.5" />
              </svg>
            </div>
          ))}
          {frame.controls}
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
                <th className="lbl sticky left-0 bg-[#0a0b10] px-2.5 py-2 text-right">Strike \ exp</th>
                {grid.expirations.map((e) => (
                  <th
                    key={e}
                    className={`px-2.5 py-2 text-center text-[10px] font-medium uppercase tracking-wider ${
                      isSel(e) ? "rounded-t bg-accent/10 text-accent-bright" : "text-neutral-500"
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
                    className={`sticky left-0 bg-[#0a0b10] px-2.5 py-1 text-right font-mono tabular-nums ${
                      k === grid.atm ? "border-l-2 border-l-accent-bright font-bold text-accent-bright" : "text-neutral-300"
                    }`}
                  >
                    {k}
                  </td>
                  {grid.expirations.map((e) => {
                    const v = grid.cell.get(`${k}|${e}`) ?? 0;
                    const t = grid.max > 0 ? v / grid.max : 0;
                    return (
                      <td
                        key={e}
                        className={`px-2.5 py-1 text-center font-mono tabular-nums transition-shadow hover:ring-1 hover:ring-inset hover:ring-white/40 ${isSel(e) ? "ring-1 ring-inset ring-accent/50" : ""}`}
                        style={{
                          backgroundColor: v > 0 ? heat(t) : "transparent",
                          color: t > 0.55 ? "#052e22" : "#d4d4d8",
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
          <div className="mt-3 flex items-center gap-2 border-t border-white/[0.05] pt-3 text-[10px] text-neutral-500">
            <span>Low</span>
            <div className="h-2 w-40 rounded-full" style={{ background: "linear-gradient(to right, rgba(52,211,153,0.06), rgba(52,211,153,0.5), rgba(52,211,153,0.92))" }} />
            <span>
              High · {METRIC_LABEL[metric]} ({side === "both" ? "calls + puts" : side + "s"}) · ATM strike marked
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
