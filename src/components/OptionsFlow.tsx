"use client";

import { useEffect, useMemo, useState } from "react";
import type { OptionContract } from "@/lib/barchart/types";
import { loadChain } from "@/lib/client-data";
import { filterByExpiration } from "@/lib/flow/analytics";
import { optionsFlow, type FlowSide } from "@/lib/flow/optionsflow";
import { withBase } from "@/lib/paths";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";
type SideFilter = "all" | "call" | "put";
type SortKey = "premium" | "volume" | "openInterest" | "dte";

const usd = (n: number) => `${n < 0 ? "−" : ""}$${Math.abs(Math.round(n)).toLocaleString()}`;
const num = (n: number) => Math.round(n).toLocaleString();
const PREMIUM_STEPS = [0, 50_000, 100_000, 250_000, 1_000_000];

const sideTone: Record<FlowSide, string> = {
  ASK: "text-emerald-300",
  BID: "text-red-300",
  MID: "text-neutral-400",
  "—": "text-neutral-600",
};

function Gauge({ title, value, left, right, fmt }: { title: string; value: number; left: number; right: number; fmt: (n: number) => string }) {
  const span = right - left || 1;
  const pct = Math.max(2, Math.min(98, ((value - left) / span) * 100));
  const bull = value >= 0;
  return (
    <div className="rounded border border-white/10 bg-white/[0.02] p-3">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="lbl">{title}</span>
        <span className={`font-mono text-sm font-bold ${bull ? "text-call" : "text-put"}`}>{fmt(value)}</span>
      </div>
      <div className="relative h-2 rounded-full bg-gradient-to-r from-red-500/40 via-neutral-600/30 to-emerald-500/40">
        <div className="absolute left-1/2 top-1/2 h-3 w-px -translate-y-1/2 bg-white/25" />
        <div className="absolute top-1/2 h-3.5 w-1 -translate-y-1/2 rounded bg-white shadow" style={{ left: `calc(${pct}% - 2px)` }} />
      </div>
      <div className="mt-1 flex justify-between text-[10px]">
        <span className="text-put">Bearish {fmt(left)}</span>
        <span className="text-call">Bullish {fmt(right)}</span>
      </div>
    </div>
  );
}

export function OptionsFlow({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [spot, setSpot] = useState<number | null>(null);
  const [source, setSource] = useState("");
  const [asOf, setAsOf] = useState<string | null>(null);
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");
  const [sideF, setSideF] = useState<SideFilter>("all");
  const [minPrem, setMinPrem] = useState(0);
  const [sortKey, setSortKey] = useState<SortKey>("premium");

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await loadChain(symbol);
        if (cancelled) return;
        setChain(res.chain);
        setSpot(res.spot);
        setSource(res.source);
        setAsOf(res.asOf);
        setState(res.chain.length ? "ok" : "empty");
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Network error");
          setState("error");
        }
      }
    };
    setState("loading");
    load();
    const ms = Math.max(20_000, Number(process.env.NEXT_PUBLIC_REFRESH_MS ?? 60_000) || 60_000);
    const id = setInterval(load, ms);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [symbol]);

  const flow = useMemo(() => optionsFlow(filterByExpiration(chain, exp), spot, { minPremium: minPrem, limit: 200 }), [chain, spot, exp, minPrem]);

  const rows = useMemo(() => {
    const r = flow.rows.filter((x) => sideF === "all" || x.type === sideF);
    const v = (x: (typeof r)[number]) => (sortKey === "volume" ? x.volume : sortKey === "openInterest" ? x.openInterest : sortKey === "dte" ? -(x.dte ?? 9999) : x.premium);
    return [...r].sort((a, b) => v(b) - v(a));
  }, [flow.rows, sideF, sortKey]);

  const s = flow.sentiment;

  return (
    <div className="glass p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Options Flow · {symbol}</h2>
        <span className="lbl">{source ? `src: ${source}` : ""}{asOf ? ` · ${asOf}` : ""} · {rows.length} contracts</span>
      </div>

      {state === "loading" && <Loading label="Loading flow…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options data." />}
      {state === "ok" && (
        <>
          {/* Barchart-style sentiment gauges */}
          <div className="mb-3 grid gap-3 sm:grid-cols-2">
            <Gauge title="Net Trade Sentiment" value={s.netPremium} left={s.bearPremium} right={s.bullPremium} fmt={usd} />
            <Gauge title="Delta Imbalance" value={s.deltaImbalance} left={s.putDelta} right={s.callDelta} fmt={num} />
          </div>

          {/* toolbar */}
          <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
            <div className="flex overflow-hidden rounded border border-white/10">
              {(["all", "call", "put"] as SideFilter[]).map((sf) => (
                <button key={sf} onClick={() => setSideF(sf)} className={`px-2.5 py-1 capitalize transition ${sideF === sf ? "bg-emerald-500/15 text-emerald-300" : "text-neutral-400 hover:bg-white/5"}`}>
                  {sf === "all" ? "All" : sf === "call" ? "Calls" : "Puts"}
                </button>
              ))}
            </div>
            <label className="flex items-center gap-1 text-neutral-500">
              min premium
              <select value={minPrem} onChange={(e) => setMinPrem(Number(e.target.value))} className="rounded border border-white/10 bg-neutral-900 px-2 py-1 text-neutral-100">
                {PREMIUM_STEPS.map((p) => (
                  <option key={p} value={p}>{p === 0 ? "any" : usd(p)}</option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-1 text-neutral-500">
              sort
              <select value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)} className="rounded border border-white/10 bg-neutral-900 px-2 py-1 text-neutral-100">
                <option value="premium">Premium</option>
                <option value="volume">Volume</option>
                <option value="openInterest">Open Int</option>
                <option value="dte">DTE</option>
              </select>
            </label>
          </div>

          {rows.length === 0 ? (
            <EmptyState label="No contracts traded above the premium filter." />
          ) : (
            <div className="max-h-[600px] overflow-auto rounded-lg border border-white/10">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-black/80 text-left uppercase tracking-wide text-neutral-500 backdrop-blur">
                  <tr>
                    <th className="px-2 py-1.5">Symbol</th>
                    <th className="px-2 py-1.5 text-right">Price</th>
                    <th className="px-2 py-1.5">Type</th>
                    <th className="px-2 py-1.5 text-right">Strike</th>
                    <th className="px-2 py-1.5">Exp</th>
                    <th className="px-2 py-1.5 text-right">DTE</th>
                    <th className="px-2 py-1.5 text-right">Bid</th>
                    <th className="px-2 py-1.5 text-right">Ask</th>
                    <th className="px-2 py-1.5 text-right">Trade</th>
                    <th className="px-2 py-1.5 text-right">Premium</th>
                    <th className="px-2 py-1.5 text-right">Vol</th>
                    <th className="px-2 py-1.5 text-right">Open Int</th>
                    <th className="px-2 py-1.5 text-right">IV</th>
                    <th className="px-2 py-1.5 text-right">Delta</th>
                    <th className="px-2 py-1.5">Side</th>
                  </tr>
                </thead>
                <tbody className="font-mono">
                  {rows.map((r) => (
                    <tr key={r.contract} className="border-t border-white/5 hover:bg-white/[0.03]">
                      <td className="px-2 py-1">
                        <a href={withBase(`/ticker/${r.underlying}`)} className="text-[#ffa028] hover:underline">{r.underlying}</a>
                      </td>
                      <td className="px-2 py-1 text-right text-neutral-300">{r.price != null ? r.price.toFixed(2) : "—"}</td>
                      <td className={`px-2 py-1 font-semibold ${r.type === "call" ? "text-call" : "text-put"}`}>{r.type === "call" ? "Call" : "Put"}</td>
                      <td className="px-2 py-1 text-right text-neutral-100">{r.strike}</td>
                      <td className="px-2 py-1 text-neutral-400">{r.expiration.slice(5)}</td>
                      <td className="px-2 py-1 text-right text-neutral-400">{r.dte ?? "—"}</td>
                      <td className="px-2 py-1 text-right text-neutral-400">{r.bid != null ? r.bid.toFixed(2) : "—"}</td>
                      <td className="px-2 py-1 text-right text-neutral-400">{r.ask != null ? r.ask.toFixed(2) : "—"}</td>
                      <td className="px-2 py-1 text-right text-neutral-200">{r.trade != null ? r.trade.toFixed(2) : "—"}</td>
                      <td className={`px-2 py-1 text-right font-semibold ${r.bullish == null ? "text-neutral-200" : r.bullish ? "text-call" : "text-put"}`}>{usd(r.premium)}</td>
                      <td className="px-2 py-1 text-right text-neutral-300">{r.volume.toLocaleString()}</td>
                      <td className="px-2 py-1 text-right text-neutral-400">{r.openInterest.toLocaleString()}</td>
                      <td className="px-2 py-1 text-right text-neutral-400">{r.iv != null ? `${(r.iv * 100).toFixed(1)}%` : "—"}</td>
                      <td className={`px-2 py-1 text-right ${(r.delta ?? 0) >= 0 ? "text-emerald-300/80" : "text-red-300/80"}`}>{r.delta != null ? r.delta.toFixed(4) : "—"}</td>
                      <td className={`px-2 py-1 font-semibold ${sideTone[r.side]}`}>{r.side === "ASK" ? "AT ASK" : r.side === "BID" ? "AT BID" : r.side}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p className="mt-2 text-[11px] leading-relaxed text-neutral-500">
            Barchart-style flow from the options chain ({source === "fixtures" ? "sample" : source || "live"}). Each row is a
            contract: <b>Premium</b> = volume × mid × 100 (day&apos;s traded premium), <b>Side</b> = where the last print sits
            in the bid/ask (AT ASK = aggressive buy → bullish; AT BID → bearish). The true per-print tape (single-trade
            size/exchange-code/time) needs Barchart&apos;s premium flow feed; set <code>BARCHART_API_KEY</code> to pull the
            chain straight from Barchart. Delayed data — not financial advice.
          </p>
        </>
      )}
    </div>
  );
}
