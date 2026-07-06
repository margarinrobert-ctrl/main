"use client";

import { useEffect, useMemo, useState } from "react";
import type { OptionContract } from "@/lib/barchart/types";
import { loadChain } from "@/lib/client-data";
import { filterByExpiration } from "@/lib/flow/analytics";
import { optionsFlow, type FlowSide } from "@/lib/flow/optionsflow";
import { withBase } from "@/lib/paths";
import { EmptyState, ErrorState, Loading, SectionHeader } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";
type SideFilter = "all" | "call" | "put";
type SortKey = "premium" | "volume" | "openInterest" | "dte";

const usd = (n: number) => `${n < 0 ? "−" : ""}$${Math.abs(Math.round(n)).toLocaleString()}`;
const num = (n: number) => Math.round(n).toLocaleString();
const PREMIUM_STEPS = [0, 50_000, 100_000, 250_000, 1_000_000];

const sideChip: Record<FlowSide, string> = {
  ASK: "border-call/30 bg-call/10 text-call",
  BID: "border-put/30 bg-put/10 text-put",
  MID: "border-white/10 bg-white/[0.03] text-neutral-400",
  "—": "border-transparent text-neutral-600",
};

function Gauge({ title, value, left, right, fmt }: { title: string; value: number; left: number; right: number; fmt: (n: number) => string }) {
  const span = right - left || 1;
  const pct = Math.max(2, Math.min(98, ((value - left) / span) * 100));
  const bull = value >= 0;
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3.5">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="lbl">{title}</span>
        <span className={`font-mono text-sm font-bold tabular-nums ${bull ? "text-call" : "text-put"}`}>{fmt(value)}</span>
      </div>
      <div className="relative h-1.5 rounded-full bg-gradient-to-r from-put/50 via-white/10 to-call/50">
        <div className="absolute left-1/2 top-1/2 h-3 w-px -translate-y-1/2 bg-white/25" />
        <div
          className="absolute top-1/2 h-3.5 w-[3px] -translate-y-1/2 rounded-full bg-white shadow-[0_0_10px_rgba(255,255,255,0.7)] transition-[left] duration-500"
          style={{ left: `calc(${pct}% - 1.5px)` }}
        />
      </div>
      <div className="mt-1.5 flex justify-between text-[10px]">
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
    <div className="glass glass-hover fade-up p-4 sm:p-5">
      <SectionHeader eyebrow="Options flow" title={symbol} right={<span className="lbl">{rows.length} contracts</span>} />

      {state === "loading" && <Loading label="Loading options flow…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options data for the tape." />}
      {state === "ok" && (
        <>
          {/* sentiment gauges */}
          <div className="mb-3 grid gap-3 sm:grid-cols-2">
            <Gauge title="Net Trade Sentiment" value={s.netPremium} left={s.bearPremium} right={s.bullPremium} fmt={usd} />
            <Gauge title="Delta Imbalance" value={s.deltaImbalance} left={s.putDelta} right={s.callDelta} fmt={num} />
          </div>

          {/* toolbar */}
          <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
            <div className="flex overflow-hidden rounded-lg border border-white/10">
              {(["all", "call", "put"] as SideFilter[]).map((sf) => (
                <button
                  key={sf}
                  onClick={() => setSideF(sf)}
                  aria-pressed={sideF === sf}
                  className={`px-3 py-2 font-medium capitalize transition ${sideF === sf ? "bg-accent/15 text-accent-bright" : "text-neutral-400 hover:bg-white/5 hover:text-neutral-200"}`}
                >
                  {sf === "all" ? "All" : sf === "call" ? "Calls" : "Puts"}
                </button>
              ))}
            </div>
            {[
              { label: "Min premium", value: String(minPrem), set: (v: string) => setMinPrem(Number(v)), opts: PREMIUM_STEPS.map((v) => [String(v), v === 0 ? "Any" : usd(v)]) },
              { label: "Sort", value: sortKey, set: (v: string) => setSortKey(v as SortKey), opts: [["premium", "Premium"], ["volume", "Volume"], ["openInterest", "Open Int"], ["dte", "DTE"]] },
            ].map((sel) => (
              <label key={sel.label} className="flex items-center gap-1.5">
                <span className="lbl">{sel.label}</span>
                <div className="relative">
                  <select
                    value={sel.value}
                    onChange={(e) => sel.set(e.target.value)}
                    className="appearance-none rounded-lg border border-white/10 bg-white/[0.03] py-2 pl-2.5 pr-7 text-xs text-neutral-100 outline-none transition hover:border-white/20 focus:border-accent/50"
                  >
                    {sel.opts.map(([v, l]) => (
                      <option key={v} value={v} className="bg-neutral-900">
                        {l}
                      </option>
                    ))}
                  </select>
                  <svg aria-hidden viewBox="0 0 12 12" className="pointer-events-none absolute right-2 top-1/2 h-3 w-3 -translate-y-1/2 text-neutral-500">
                    <path fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" d="m2.5 4.5 3.5 3.5 3.5-3.5" />
                  </svg>
                </div>
              </label>
            ))}
          </div>

          {rows.length === 0 ? (
            <EmptyState label="No contracts traded above the premium filter." />
          ) : (
            <div className="max-h-[600px] overflow-auto rounded-xl border border-white/[0.08]">
              <table className="tbl w-full">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th className="!text-right">Price</th>
                    <th>Type</th>
                    <th className="!text-right">Strike</th>
                    <th>Exp</th>
                    <th className="!text-right">DTE</th>
                    <th className="!text-right">Bid</th>
                    <th className="!text-right">Ask</th>
                    <th className="!text-right">Trade</th>
                    <th className="!text-right">Premium</th>
                    <th className="!text-right">Vol</th>
                    <th className="!text-right">Open Int</th>
                    <th className="!text-right">IV</th>
                    <th className="!text-right">Delta</th>
                    <th>Side</th>
                  </tr>
                </thead>
                <tbody className="font-mono tabular-nums">
                  {rows.map((r) => (
                    <tr key={r.contract}>
                      <td>
                        <a href={withBase(`/ticker/${r.underlying}`)} className="font-semibold text-neutral-200 transition hover:text-accent-bright">{r.underlying}</a>
                      </td>
                      <td className="text-right text-neutral-300">{r.price != null ? r.price.toFixed(2) : "—"}</td>
                      <td className={`font-semibold ${r.type === "call" ? "text-call" : "text-put"}`}>{r.type === "call" ? "Call" : "Put"}</td>
                      <td className="text-right text-neutral-100">{r.strike}</td>
                      <td className="text-neutral-400">{r.expiration.slice(5)}</td>
                      <td className="text-right text-neutral-400">{r.dte ?? "—"}</td>
                      <td className="text-right text-neutral-400">{r.bid != null ? r.bid.toFixed(2) : "—"}</td>
                      <td className="text-right text-neutral-400">{r.ask != null ? r.ask.toFixed(2) : "—"}</td>
                      <td className="text-right text-neutral-200">{r.trade != null ? r.trade.toFixed(2) : "—"}</td>
                      <td className={`text-right font-semibold ${r.bullish == null ? "text-neutral-200" : r.bullish ? "text-call" : "text-put"}`}>{usd(r.premium)}</td>
                      <td className="text-right text-neutral-300">{r.volume.toLocaleString()}</td>
                      <td className="text-right text-neutral-400">{r.openInterest.toLocaleString()}</td>
                      <td className="text-right text-neutral-400">{r.iv != null ? `${(r.iv * 100).toFixed(1)}%` : "—"}</td>
                      <td className={`text-right ${(r.delta ?? 0) >= 0 ? "text-call/80" : "text-put/80"}`}>{r.delta != null ? r.delta.toFixed(4) : "—"}</td>
                      <td>
                        <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold ${sideChip[r.side]}`}>
                          {r.side === "ASK" ? "AT ASK" : r.side === "BID" ? "AT BID" : r.side}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p className="mt-3 border-t border-white/[0.05] pt-3 text-[11px] leading-relaxed text-neutral-600">
            Each row is a contract. Premium = volume × mid × 100 (day&apos;s traded premium); Side = where the last print sits
            in the bid/ask (at ask = aggressive buying; at bid = aggressive selling). Educational — not financial advice.
          </p>
        </>
      )}
    </div>
  );
}
