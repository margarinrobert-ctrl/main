"use client";

import { useEffect, useMemo, useState } from "react";
import type { HistoryBar, OptionContract } from "@/lib/barchart/types";
import { loadChain, loadHistory } from "@/lib/client-data";
import { filterByExpiration } from "@/lib/flow/analytics";
import { mmHedge, type Pressure } from "@/lib/flow/mmhedge";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

const f2 = (n: number | null) => (n == null ? "—" : n.toLocaleString(undefined, { maximumFractionDigits: 2 }));
const pressColor = (p: Pressure) => (p === "up" ? "text-emerald-300" : p === "down" ? "text-red-300" : "text-sky-300");
const dirDot = (p: Pressure) => (p === "up" ? "bg-emerald-400" : p === "down" ? "bg-red-400" : "bg-neutral-400");
const sideChip = (s: string) =>
  s === "long" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" : s === "short" ? "border-red-500/40 bg-red-500/10 text-red-300" : "border-sky-500/40 bg-sky-500/10 text-sky-300";

function PressureMeter({ score }: { score: number }) {
  const pct = (score + 100) / 2;
  const p: Pressure = score > 15 ? "up" : score < -15 ? "down" : "balanced";
  return (
    <div className="min-w-[220px] flex-1">
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-neutral-500">Dealer pressure</span>
        <span className={`font-mono ${pressColor(p)}`}>
          {p === "up" ? "▲ UP" : p === "down" ? "▼ DOWN" : "BALANCED"} {score > 0 ? "+" : ""}
          {score}
        </span>
      </div>
      <div className="relative h-2 w-full rounded-full bg-gradient-to-r from-red-500/40 via-neutral-600/40 to-emerald-500/40">
        <div className="absolute top-1/2 h-3 w-1 -translate-y-1/2 rounded bg-white" style={{ left: `calc(${pct}% - 2px)` }} />
        <div className="absolute left-1/2 top-1/2 h-3 w-px -translate-y-1/2 bg-white/30" />
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-neutral-600">
        <span>sell pressure</span>
        <span>buy pressure</span>
      </div>
    </div>
  );
}

export function MMHedge({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [spot, setSpot] = useState<number | null>(null);
  const [bars, setBars] = useState<HistoryBar[]>([]);
  const [source, setSource] = useState("");
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setState("loading");
      try {
        const [ch, hi] = await Promise.all([loadChain(symbol), loadHistory(symbol).catch(() => ({ bars: [] }))]);
        if (cancelled) return;
        setChain(ch.chain);
        setSpot(ch.spot);
        setSource(ch.source);
        setBars(("bars" in hi ? hi.bars : []) as HistoryBar[]);
        setState(ch.chain.length ? "ok" : "empty");
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

  const r = useMemo(() => mmHedge(filterByExpiration(chain, exp), spot, bars), [chain, spot, bars, exp]);

  return (
    <div className="glass p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold">Market-Maker Hedging · {symbol}</h2>
          <p className="text-xs text-neutral-500">trade with dealer hedging pressure at the key levels · src: {source}</p>
        </div>
        <PressureMeter score={r.pressureScore} />
      </div>

      {state === "loading" && <Loading label="Reading dealer flow…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options data to read dealer hedging." />}
      {state === "ok" && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
            <span className={`rounded-full border px-3 py-1 font-medium ${r.regime === "long" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" : r.regime === "short" ? "border-red-500/40 bg-red-500/10 text-red-300" : "border-white/15 text-neutral-300"}`}>
              {r.regime === "long" ? "Long γ · pin/mean-revert" : r.regime === "short" ? "Short γ · amplify/trend" : "γ n/a"}
            </span>
            {r.magnet != null && <span className="rounded-full border border-white/15 px-3 py-1 text-neutral-300">Gamma magnet {f2(r.magnet)}</span>}
            {r.nearestLevel && (
              <span className={`rounded-full border px-3 py-1 ${r.atLevel ? "border-amber-500/40 bg-amber-500/10 text-amber-300" : "border-white/15 text-neutral-400"}`}>
                {r.atLevel ? "AT " : "near "}
                {r.nearestLevel.name} {f2(r.nearestLevel.price)} ({r.nearestLevel.distPct >= 0 ? "+" : ""}
                {r.nearestLevel.distPct.toFixed(2)}%)
              </span>
            )}
          </div>

          {r.trade && (
            <div className={`mb-4 rounded-lg border border-white/5 border-l-4 bg-white/[0.02] p-3 ${r.trade.side === "long" ? "border-l-emerald-500" : r.trade.side === "short" ? "border-l-red-500" : "border-l-sky-500"}`}>
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-neutral-100">The trade plan</span>
                <span className={`rounded-full border px-2 py-0.5 text-[11px] uppercase ${sideChip(r.trade.side)}`}>{r.trade.side}</span>
                {r.trade.rr != null && (
                  <span className="rounded-full border border-white/15 px-2 py-0.5 text-[11px] text-neutral-300">R:R {r.trade.rr}× → TP1 · {r.trade.rrFinal}× final</span>
                )}
              </div>

              <p className="mb-3 text-xs text-neutral-400">{r.trade.rationale}</p>

              {r.trade.side !== "wait" && (
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="rounded border border-white/10 p-2">
                    <div className="mb-1 text-[10px] uppercase tracking-wide text-neutral-500">Entry zone</div>
                    {r.trade.entries.map((e) => (
                      <div key={e.label} className="flex justify-between text-sm">
                        <span className="text-neutral-500">{e.label}</span>
                        <span className="font-mono text-neutral-100">{f2(e.price)}</span>
                      </div>
                    ))}
                  </div>
                  <div className="rounded border border-white/10 p-2">
                    <div className="mb-1 text-[10px] uppercase tracking-wide text-neutral-500">Take-profit</div>
                    {r.trade.targets.map((t) => (
                      <div key={t.label} className="flex items-baseline justify-between gap-2 text-sm">
                        <span className="truncate text-neutral-500">{t.label}</span>
                        <span className="whitespace-nowrap font-mono text-emerald-300">
                          {f2(t.price)}
                          {t.r != null && <span className="ml-1 text-[10px] text-neutral-500">{t.r}R</span>}
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className="rounded border border-white/10 p-2">
                    <div className="mb-1 text-[10px] uppercase tracking-wide text-neutral-500">Stop / risk</div>
                    <div className="flex justify-between text-sm">
                      <span className="text-neutral-500">stop</span>
                      <span className="font-mono text-red-300">{f2(r.trade.stop)}</span>
                    </div>
                    <div className="text-[10px] text-neutral-500">{r.trade.stopLabel}</div>
                    {r.trade.risk != null && <div className="mt-1 text-[11px] text-neutral-400">risk ≈ {f2(r.trade.risk)} / unit (= 1R)</div>}
                  </div>
                </div>
              )}

              {r.trade.management.length > 0 && (
                <ul className="mt-3 list-disc space-y-0.5 pl-4 text-[11px] text-neutral-400">
                  {r.trade.management.map((m) => (
                    <li key={m}>{m}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className="mb-3">
            <div className="mb-1 text-xs uppercase tracking-wide text-neutral-500">Pressure breakdown</div>
            <div className="space-y-1">
              {r.components.map((cp) => (
                <div key={cp.label} className="flex items-center gap-2 text-xs">
                  <span className={`inline-block h-2 w-2 rounded-full ${dirDot(cp.dir)}`} />
                  <span className="w-24 text-neutral-300">{cp.label}</span>
                  <span className={`w-12 font-mono ${pressColor(cp.dir)}`}>{cp.dir === "up" ? "▲" : cp.dir === "down" ? "▼" : "•"} {cp.weight}</span>
                  <span className="flex-1 text-neutral-500">{cp.detail}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-1">
            {r.notes.map((n) => (
              <p key={n} className="text-[11px] text-neutral-500">
                {n}
              </p>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
