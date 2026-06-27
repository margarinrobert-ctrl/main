"use client";

import { useEffect, useMemo, useState } from "react";
import type { HistoryBar, OptionContract } from "@/lib/barchart/types";
import { loadChain, loadHistory } from "@/lib/client-data";
import { filterByExpiration, fmtUsd, levelStats } from "@/lib/flow/analytics";
import { probAbove } from "@/lib/flow/greeks";
import { mmHedge, planAtLevel, type Pressure } from "@/lib/flow/mmhedge";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

const f2 = (n: number | null) => (n == null ? "—" : n.toLocaleString(undefined, { maximumFractionDigits: 2 }));
const kfmt = (n: number) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : String(Math.round(n)));
const pressColor = (p: Pressure) => (p === "up" ? "text-emerald-300" : p === "down" ? "text-red-300" : "text-sky-300");
const dirDot = (p: Pressure) => (p === "up" ? "bg-emerald-400" : p === "down" ? "bg-red-400" : "bg-neutral-400");
const sideChip = (s: string) =>
  s === "long" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" : s === "short" ? "border-red-500/40 bg-red-500/10 text-red-300" : "border-sky-500/40 bg-sky-500/10 text-sky-300";

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="rounded border border-white/10 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-neutral-500">{label}</div>
      <div className={`font-mono text-base ${tone ?? "text-neutral-100"}`}>{value}</div>
      {sub ? <div className="text-[10px] text-neutral-500">{sub}</div> : null}
    </div>
  );
}

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
  const [selLevel, setSelLevel] = useState<string | null>(null);

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

  const sub = useMemo(() => filterByExpiration(chain, exp), [chain, exp]);
  const r = useMemo(() => mmHedge(sub, spot, bars), [sub, spot, bars]);

  const detail = useMemo(() => {
    if (!selLevel || spot == null) return null;
    const lp = r.levelPlays.find((l) => l.name === selLevel);
    if (!lp) return null;
    const st = levelStats(sub, spot, lp.price);
    const iv = r.frontIv;
    const t = r.frontT;
    const pBeyond = iv != null && t > 0 ? (lp.price >= spot ? probAbove(spot, lp.price, iv, t) : 1 - (probAbove(spot, lp.price, iv, t) ?? 0)) : null;
    const sigma = iv != null && t > 0 ? spot * iv * Math.sqrt(t) : null;
    const distSigma = sigma ? Math.abs(lp.price - spot) / sigma : null;
    const oiSum = st.callOi + st.putOi;
    const volOi = oiSum > 0 ? (st.callVol + st.putVol) / oiSum : null; // >~0.5 = fresh positioning today
    return { lp, st, pBeyond, distSigma, volOi };
  }, [selLevel, sub, spot, r]);

  // The plan re-anchors to a selected level; otherwise it's the auto plan at the in-play level.
  const plan = useMemo(() => {
    if (selLevel) {
      const lp = r.levelPlays.find((l) => l.name === selLevel);
      if (lp) {
        const p = planAtLevel(r, spot, lp);
        if (p) return p;
      }
    }
    return r.trade;
  }, [selLevel, r, spot]);

  return (
    <div className="glass p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold">Market-Maker Hedging · {symbol}</h2>
          <p className="text-xs text-neutral-500">trade with dealer hedging pressure at the key levels</p>
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

          {r.levelPlays.length > 0 && (
            <div className="mb-4">
              <div className="mb-1 text-xs uppercase tracking-wide text-neutral-500">What dealers do at each level · most-likely reaction · <span className="text-neutral-400">tap a row for detail</span></div>
              <div className="overflow-x-auto rounded-lg border border-white/10">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[10px] uppercase tracking-wide text-neutral-500">
                      <th className="px-3 py-1.5">Level</th>
                      <th className="px-2 py-1.5 text-right">Price</th>
                      <th className="px-3 py-1.5">Dealer action</th>
                      <th className="px-3 py-1.5">Most likely</th>
                      <th className="px-3 py-1.5 text-right">OI</th>
                      <th className="px-3 py-1.5 text-right">P(reach)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {r.levelPlays.map((lp) => {
                      const here = r.nearestLevel?.name === lp.name && r.atLevel;
                      return (
                        <tr
                          key={lp.name}
                          onClick={() => setSelLevel((s) => (s === lp.name ? null : lp.name))}
                          className={`cursor-pointer border-t border-white/5 ${selLevel === lp.name ? "bg-sky-500/10" : here ? "bg-amber-500/10" : "hover:bg-white/[0.03]"}`}
                        >
                          <td className="px-3 py-1.5">
                            <span className={`mr-2 inline-block h-2 w-2 rounded-full ${dirDot(lp.bias)}`} />
                            {lp.name}
                            {here && <span className="ml-1 text-[10px] text-amber-300">← price here</span>}
                          </td>
                          <td className="px-2 py-1.5 text-right font-mono">
                            {f2(lp.price)} <span className="text-[10px] text-neutral-500">{lp.distPct >= 0 ? "+" : ""}{lp.distPct.toFixed(2)}%</span>
                          </td>
                          <td className="px-3 py-1.5 text-neutral-300">{lp.action}</td>
                          <td className={`px-3 py-1.5 font-medium ${pressColor(lp.bias)}`}>{lp.outcome}</td>
                          <td className="px-3 py-1.5 text-right font-mono">
                            <span className={lp.callOi >= lp.putOi ? "text-emerald-300" : "text-red-300"}>{kfmt(lp.callOi + lp.putOi)}</span>
                            <span className="ml-1 text-[10px] text-neutral-500">{Math.round(lp.oiShare * 100)}%</span>
                          </td>
                          <td className="px-3 py-1.5 text-right font-mono text-sky-300">{lp.pReach != null ? Math.round(lp.pReach * 100) + "%" : "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="mt-1 text-[10px] text-neutral-500">Reaction = the dealer-hedging response if price reaches the level (long-γ defends/fades, short-γ amplifies/breaks). P(reach) is the BS chance it gets there by the front expiry — independent per level.</p>

              {detail && (
                <div className="mt-2 rounded-lg border border-sky-500/30 bg-sky-500/[0.05] p-3">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium text-neutral-100">
                      {detail.lp.name} · <span className="font-mono">{f2(detail.lp.price)}</span>{" "}
                      <span className="text-xs text-neutral-500">
                        {detail.lp.distPct >= 0 ? "+" : ""}
                        {detail.lp.distPct.toFixed(2)}%{detail.distSigma != null ? ` · ${detail.distSigma.toFixed(2)}σ` : ""}
                      </span>
                    </span>
                    <span className={`rounded-full border border-white/15 px-2 py-0.5 text-[11px] ${pressColor(detail.lp.bias)}`}>{detail.lp.outcome}</span>
                  </div>
                  <p className="mb-2 text-xs text-neutral-400">Dealers: {detail.lp.action}.</p>
                  <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
                    <Stat label="Strike" value={detail.st.strike != null ? String(detail.st.strike) : "—"} sub={`γ-share ${Math.round(detail.st.gexShare * 100)}%`} />
                    <Stat label="Net GEX" value={fmtUsd(detail.st.gex)} tone={detail.st.gex >= 0 ? "text-emerald-300" : "text-red-300"} />
                    <Stat label="Net DEX" value={fmtUsd(detail.st.dex)} />
                    <Stat label="IV" value={detail.st.iv != null ? `${(detail.st.iv * 100).toFixed(1)}%` : "—"} />
                    <Stat label="Vanna" value={`${fmtUsd(detail.st.vanna)}/vp`} />
                    <Stat label="Charm" value={`${fmtUsd(detail.st.charm)}/d`} />
                    <Stat label="Call / Put OI" value={`${detail.st.callOi.toLocaleString()} / ${detail.st.putOi.toLocaleString()}`} />
                    <Stat label="Call / Put Vol" value={`${detail.st.callVol.toLocaleString()} / ${detail.st.putVol.toLocaleString()}`} />
                    <Stat
                      label="Vol / OI"
                      value={detail.volOi == null ? "—" : detail.volOi.toFixed(2)}
                      sub={detail.volOi == null ? "" : detail.volOi >= 0.5 ? "fresh positioning" : "mostly stale OI"}
                      tone={detail.volOi != null && detail.volOi >= 0.5 ? "text-emerald-300" : "text-neutral-100"}
                    />
                    <Stat label="P(reach)" value={detail.lp.pReach != null ? `${Math.round(detail.lp.pReach * 100)}%` : "—"} tone="text-sky-300" />
                    <Stat label="P(close beyond)" value={detail.pBeyond != null ? `${Math.round(detail.pBeyond * 100)}%` : "—"} tone="text-sky-300" />
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="mb-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
            <Stat label="Conviction" value={`${r.conviction}/100`} tone={r.conviction >= 60 ? "text-emerald-300" : r.conviction >= 35 ? "text-amber-300" : "text-neutral-100"} />
            <Stat label="Hedge / 1%" value={r.flowPer1pct == null ? "—" : fmtUsd(r.flowPer1pct)} sub={r.regime === "long" ? "stabilising" : r.regime === "short" ? "destabilising" : ""} />
            <Stat label="Pin (COM)" value={r.com == null ? "—" : f2(r.com)} sub={r.magnet != null ? `magnet ${r.magnet}` : ""} />
            <Stat label="EV (modelled)" value={plan?.ev == null ? "—" : `${plan.ev}R`} tone={plan?.ev == null ? "text-neutral-100" : plan.ev > 0 ? "text-emerald-300" : "text-red-300"} />
          </div>

          {plan && (
            <div className={`mb-4 rounded-lg border border-white/5 border-l-4 bg-white/[0.02] p-3 ${plan.side === "long" ? "border-l-emerald-500" : plan.side === "short" ? "border-l-red-500" : "border-l-sky-500"}`}>
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-neutral-100">The trade plan</span>
                <span className={`rounded-full border px-2 py-0.5 text-[11px] uppercase ${sideChip(plan.side)}`}>{plan.side}</span>
                {plan.anchorLevel && (
                  <span className="rounded-full border border-sky-500/40 bg-sky-500/10 px-2 py-0.5 text-[11px] text-sky-300">
                    @ {plan.anchorLevel}
                    {selLevel ? " (selected)" : ""}
                  </span>
                )}
                {plan.pWin != null && (
                  <span className="rounded-full border border-white/15 px-2 py-0.5 text-[11px] text-neutral-200">P(win) {Math.round(plan.pWin * 100)}%</span>
                )}
                {plan.rr != null && (
                  <span className="rounded-full border border-white/15 px-2 py-0.5 text-[11px] text-neutral-300">R:R {plan.rr}× → TP1 · {plan.rrFinal}× final</span>
                )}
                {plan.ev != null && (
                  <span className={`rounded-full border px-2 py-0.5 text-[11px] ${plan.ev > 0 ? "border-emerald-500/40 text-emerald-300" : "border-red-500/40 text-red-300"}`}>EV {plan.ev}R</span>
                )}
              </div>

              {selLevel && <p className="mb-2 text-[11px] text-sky-300">Synced to {selLevel} — tap it again to return to the auto plan.</p>}
              <p className="mb-3 text-xs text-neutral-400">{plan.rationale}</p>

              {plan.side !== "wait" && (
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="rounded border border-white/10 p-2">
                    <div className="mb-1 text-[10px] uppercase tracking-wide text-neutral-500">Entry zone</div>
                    {plan.entries.map((e) => (
                      <div key={e.label} className="flex justify-between text-sm">
                        <span className="text-neutral-500">{e.label}</span>
                        <span className="font-mono text-neutral-100">{f2(e.price)}</span>
                      </div>
                    ))}
                  </div>
                  <div className="rounded border border-white/10 p-2">
                    <div className="mb-1 text-[10px] uppercase tracking-wide text-neutral-500">Take-profit · R · P(touch)</div>
                    {plan.targets.map((t) => (
                      <div key={t.label} className="flex items-baseline justify-between gap-2 text-sm">
                        <span className="truncate text-neutral-500">{t.label}</span>
                        <span className="whitespace-nowrap font-mono text-emerald-300">
                          {f2(t.price)}
                          {t.r != null && <span className="ml-1 text-[10px] text-neutral-500">{t.r}R</span>}
                          {t.pTouch != null && <span className="ml-1 text-[10px] text-sky-300">{Math.round(t.pTouch * 100)}%</span>}
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className="rounded border border-white/10 p-2">
                    <div className="mb-1 text-[10px] uppercase tracking-wide text-neutral-500">Stop / risk</div>
                    <div className="flex justify-between text-sm">
                      <span className="text-neutral-500">stop</span>
                      <span className="font-mono text-red-300">{f2(plan.stop)}</span>
                    </div>
                    <div className="text-[10px] text-neutral-500">{plan.stopLabel}</div>
                    {plan.risk != null && <div className="mt-1 text-[11px] text-neutral-400">risk ≈ {f2(plan.risk)} / unit (= 1R)</div>}
                    {plan.pStop != null && <div className="text-[11px] text-neutral-500">P(touch stop) {Math.round(plan.pStop * 100)}%</div>}
                  </div>
                </div>
              )}

              {plan.management.length > 0 && (
                <ul className="mt-3 list-disc space-y-0.5 pl-4 text-[11px] text-neutral-400">
                  {plan.management.map((m) => (
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
