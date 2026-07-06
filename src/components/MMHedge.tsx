"use client";

import { useEffect, useMemo, useState } from "react";
import type { HistoryBar, OptionContract } from "@/lib/barchart/types";
import { loadChain, loadHistory } from "@/lib/client-data";
import { filterByExpiration, fmtUsd, levelStats } from "@/lib/flow/analytics";
import { probAbove } from "@/lib/flow/greeks";
import { mmHedge, planAtLevel, pressureAt, type Pressure } from "@/lib/flow/mmhedge";
import { EmptyState, ErrorState, Loading, Stat } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

const f2 = (n: number | null) => (n == null ? "—" : n.toLocaleString(undefined, { maximumFractionDigits: 2 }));
const kfmt = (n: number) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : String(Math.round(n)));
const pressColor = (p: Pressure) => (p === "up" ? "text-call" : p === "down" ? "text-put" : "text-neutral-300");
const dirDot = (p: Pressure) => (p === "up" ? "bg-call" : p === "down" ? "bg-put" : "bg-neutral-500");
const sideChip = (s: string) =>
  s === "long" ? "border-call/30 bg-call/10 text-call" : s === "short" ? "border-put/30 bg-put/10 text-put" : "border-white/10 bg-white/[0.03] text-neutral-300";

/** Shared grid template so breakdown + greeks label columns align. */
const ROW_GRID = "grid grid-cols-[8px_6rem_5rem_1fr] items-center gap-2 text-xs";

function Chevron({ dir, className = "h-3 w-3" }: { dir: "up" | "down" | "right"; className?: string }) {
  const d = dir === "up" ? "M2.5 7.5 6 4 9.5 7.5" : dir === "down" ? "M2.5 4.5 6 8 9.5 4.5" : "M4.5 2.5 8 6 4.5 9.5";
  return (
    <svg viewBox="0 0 12 12" className={className} aria-hidden>
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PressureMeter({ score }: { score: number }) {
  const pct = (score + 100) / 2;
  const p: Pressure = score > 15 ? "up" : score < -15 ? "down" : "balanced";
  return (
    <div className="w-full max-w-[260px]">
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <span className="lbl">Dealer pressure</span>
        <span className={`inline-flex items-center gap-1 font-mono text-xs ${pressColor(p)}`}>
          {p !== "balanced" && <Chevron dir={p === "up" ? "up" : "down"} className="h-3 w-3" />}
          {p === "up" ? "UP" : p === "down" ? "DOWN" : "BALANCED"} {score > 0 ? "+" : ""}
          {score}
        </span>
      </div>
      <div className="relative h-1.5 w-full rounded-full bg-gradient-to-r from-put/50 via-white/10 to-call/50">
        <div className="absolute left-1/2 top-1/2 h-3 w-px -translate-y-1/2 bg-white/25" />
        <div
          className="absolute top-1/2 h-3.5 w-[3px] -translate-y-1/2 rounded-full bg-white shadow-[0_0_10px_rgba(255,255,255,0.7)]"
          style={{ left: `calc(${pct}% - 1.5px)` }}
        />
      </div>
      <div className="mt-1 flex justify-between">
        <span className="lbl">Sell pressure</span>
        <span className="lbl">Buy pressure</span>
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

  // Pressure breakdown recomputed AT the selected level (gamma-pin/delta directions vs that price).
  const levelPressure = useMemo(
    () => (detail ? pressureAt(sub, spot, detail.lp.price, bars) : null),
    [detail, sub, spot, bars],
  );

  const convictionValue =
    r.conviction >= 35 && r.conviction < 60 ? <span className="text-amber-300">{r.conviction}/100</span> : `${r.conviction}/100`;

  return (
    <div className="glass fade-up p-4">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div>
          <div className="lbl mb-1">Dealer flow</div>
          <h2 className="display text-base text-neutral-50">Market-Maker Hedging · {symbol}</h2>
          <p className="mt-1 text-xs text-neutral-500">Dealer hedging pressure mapped to key levels</p>
        </div>
        <PressureMeter score={r.pressureScore} />
      </div>

      {state === "loading" && <Loading label="Loading dealer positioning…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options data for dealer positioning." />}
      {state === "ok" && (
        <>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span
              className={`rounded-full border px-3 py-1 font-medium ${
                r.regime === "long"
                  ? "border-call/30 bg-call/10 text-call"
                  : r.regime === "short"
                    ? "border-put/30 bg-put/10 text-put"
                    : "border-white/10 bg-white/[0.03] text-neutral-300"
              }`}
            >
              {r.regime === "long" ? "Long γ · pin/mean-revert" : r.regime === "short" ? "Short γ · amplify/trend" : "γ n/a"}
            </span>
            {r.magnet != null && (
              <span className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-neutral-300">Gamma magnet {f2(r.magnet)}</span>
            )}
            {r.nearestLevel && (
              <span
                className={`rounded-full border px-3 py-1 ${
                  r.atLevel ? "border-amber-400/40 bg-amber-400/10 text-amber-300" : "border-white/10 bg-white/[0.03] text-neutral-400"
                }`}
              >
                {r.atLevel ? "AT " : "Near "}
                {r.nearestLevel.name} {f2(r.nearestLevel.price)} ({r.nearestLevel.distPct >= 0 ? "+" : ""}
                {r.nearestLevel.distPct.toFixed(2)}%)
              </span>
            )}
          </div>

          {r.levelPlays.length > 0 && (
            <section className="mt-4 border-t border-white/5 pt-3">
              <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                <span className="lbl">Levels · dealer action & most-likely reaction</span>
                <span className="lbl">Select a row for detail</span>
              </div>
              <div className="overflow-x-auto rounded-lg border border-white/10">
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>Level</th>
                      <th className="text-right">Price</th>
                      <th>Dealer action</th>
                      <th>Most likely</th>
                      <th className="text-right">OI</th>
                      <th className="text-right">P(reach)</th>
                      <th className="w-8">
                        <span className="sr-only">Detail</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {r.levelPlays.map((lp) => {
                      const here = r.nearestLevel?.name === lp.name && r.atLevel;
                      const selected = selLevel === lp.name;
                      return (
                        <tr
                          key={lp.name}
                          onClick={() => setSelLevel((s) => (s === lp.name ? null : lp.name))}
                          className={`cursor-pointer ${
                            selected ? "bg-accent/[0.07] shadow-[inset_2px_0_0_var(--accent)]" : here ? "bg-amber-400/[0.07]" : ""
                          }`}
                        >
                          <td>
                            <span className={`mr-2 inline-block h-2 w-2 rounded-full ${dirDot(lp.bias)}`} />
                            {lp.name}
                            {here && <span className="ml-2 text-[10px] uppercase tracking-wider text-amber-300">price here</span>}
                          </td>
                          <td className="text-right font-mono">
                            {f2(lp.price)}{" "}
                            <span className="text-[10px] text-neutral-500">
                              {lp.distPct >= 0 ? "+" : ""}
                              {lp.distPct.toFixed(2)}%
                            </span>
                          </td>
                          <td className="text-neutral-300">{lp.action}</td>
                          <td className={`font-medium ${pressColor(lp.bias)}`}>{lp.outcome}</td>
                          <td className="text-right font-mono">
                            <span className={lp.callOi >= lp.putOi ? "text-call" : "text-put"}>{kfmt(lp.callOi + lp.putOi)}</span>
                            <span className="ml-1 text-[10px] text-neutral-500">{Math.round(lp.oiShare * 100)}%</span>
                          </td>
                          <td className="text-right font-mono text-accent-cyan">{lp.pReach != null ? Math.round(lp.pReach * 100) + "%" : "—"}</td>
                          <td className="text-neutral-600">
                            <Chevron dir={selected ? "down" : "right"} />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="mt-1.5 text-[11px] leading-relaxed text-neutral-500">
                Reaction = the dealer-hedging response if price reaches the level (long-γ defends/fades, short-γ amplifies/breaks). P(reach) is the
                modelled probability it trades there by the front expiry — independent per level.
              </p>

              {detail && (
                <div className="fade-up mt-2 rounded-xl border border-accent-cyan/30 bg-accent-cyan/[0.04] p-3.5">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium text-neutral-100">
                      {detail.lp.name} · <span className="font-mono">{f2(detail.lp.price)}</span>{" "}
                      <span className="text-xs text-neutral-500">
                        {detail.lp.distPct >= 0 ? "+" : ""}
                        {detail.lp.distPct.toFixed(2)}%{detail.distSigma != null ? ` · ${detail.distSigma.toFixed(2)}σ` : ""}
                      </span>
                    </span>
                    <span className={`rounded-full border border-white/10 bg-white/[0.03] px-2 py-0.5 text-[11px] ${pressColor(detail.lp.bias)}`}>
                      {detail.lp.outcome}
                    </span>
                  </div>
                  <p className="mb-2.5 text-xs text-neutral-400">Dealers: {detail.lp.action}.</p>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    <Stat label="Strike" value={detail.st.strike != null ? String(detail.st.strike) : "—"} sub={`γ-share ${Math.round(detail.st.gexShare * 100)}%`} />
                    <Stat label="Net GEX" value={fmtUsd(detail.st.gex)} tone={detail.st.gex >= 0 ? "call" : "put"} />
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
                      tone={detail.volOi != null && detail.volOi >= 0.5 ? "call" : undefined}
                    />
                    <Stat label="P(reach)" value={<span className="text-accent-cyan">{detail.lp.pReach != null ? `${Math.round(detail.lp.pReach * 100)}%` : "—"}</span>} />
                    <Stat label="P(close beyond)" value={<span className="text-accent-cyan">{detail.pBeyond != null ? `${Math.round(detail.pBeyond * 100)}%` : "—"}</span>} />
                  </div>
                </div>
              )}
            </section>
          )}

          <section className="mt-4 border-t border-white/5 pt-3">
            <div className="lbl mb-2">Positioning</div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat label="Conviction" value={convictionValue} tone={r.conviction >= 60 ? "call" : undefined} />
              <Stat
                label="Hedge / 1%"
                value={r.flowPer1pct == null ? "—" : fmtUsd(r.flowPer1pct)}
                sub={r.regime === "long" ? "stabilising" : r.regime === "short" ? "destabilising" : ""}
              />
              <Stat label="Pin (COM)" value={r.com == null ? "—" : f2(r.com)} sub={r.magnet != null ? `magnet ${r.magnet}` : ""} />
              <Stat
                label="EV (modelled)"
                value={plan?.ev == null ? "—" : `${plan.ev}R`}
                tone={plan?.ev == null ? undefined : plan.ev > 0 ? "call" : "put"}
              />
            </div>
          </section>

          <section className="mt-4 border-t border-white/5 pt-3">
            <div className="lbl mb-2">Flow</div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat label="Delta flip" value={r.deltaFlip == null ? "—" : f2(r.deltaFlip)} sub="delta-neutral pivot" />
              <Stat
                label="Net flow"
                value={r.flowNetPremium == null ? "—" : fmtUsd(r.flowNetPremium)}
                sub="bull − bear premium"
                tone={(r.flowNetPremium ?? 0) >= 0 ? "call" : "put"}
              />
              <Stat
                label="Flow Δ-imbal"
                value={r.flowDeltaImbalance == null ? "—" : fmtUsd(r.flowDeltaImbalance)}
                sub="call vs put Δ·vol"
                tone={(r.flowDeltaImbalance ?? 0) >= 0 ? "call" : "put"}
              />
              <Stat
                label="Net DEX"
                value={r.netDex == null ? "—" : fmtUsd(r.netDex)}
                sub="OI Δ (calls + / puts −)"
                tone={(r.netDex ?? 0) >= 0 ? "call" : "put"}
              />
            </div>
          </section>

          {plan && (
            <section className="mt-4 border-t border-white/5 pt-3">
              <div className="lbl mb-2">Trade plan</div>
              <div
                className={`rounded-xl border border-white/[0.06] border-l-2 bg-white/[0.02] p-3.5 transition-colors duration-200 hover:border-white/[0.12] ${
                  plan.side === "long" ? "border-l-call/80" : plan.side === "short" ? "border-l-put/80" : "border-l-accent-cyan/60"
                }`}
              >
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <span className={`rounded-full border px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wider ${sideChip(plan.side)}`}>
                    {plan.side}
                  </span>
                  {plan.anchorLevel && (
                    <span className="rounded-full border border-accent-cyan/30 bg-accent-cyan/10 px-2 py-0.5 text-[11px] text-accent-cyan">
                      @ {plan.anchorLevel}
                      {selLevel ? " (selected)" : ""}
                    </span>
                  )}
                  {plan.pWin != null && (
                    <span className="rounded-full border border-white/10 px-2 py-0.5 text-[11px] text-neutral-200">P(win) {Math.round(plan.pWin * 100)}%</span>
                  )}
                  {plan.rr != null && (
                    <span className="rounded-full border border-white/10 px-2 py-0.5 text-[11px] text-neutral-300">
                      R:R {plan.rr}× → TP1 · {plan.rrFinal}× final
                    </span>
                  )}
                  {plan.ev != null && (
                    <span
                      className={`rounded-full border px-2 py-0.5 text-[11px] ${
                        plan.ev > 0 ? "border-call/40 bg-call/10 text-call" : "border-put/40 bg-put/10 text-put"
                      }`}
                    >
                      EV {plan.ev}R
                    </span>
                  )}
                </div>

                {selLevel && (
                  <p className="mb-2 text-[11px] text-accent-cyan">Anchored to {selLevel} — select the row again to restore the auto plan.</p>
                )}
                <p className="mb-3 text-xs leading-relaxed text-neutral-400">{plan.rationale}</p>

                {plan.side !== "wait" && (
                  <div className="grid gap-3 sm:grid-cols-3">
                    <div className="rounded-lg border border-white/10 p-2.5">
                      <div className="lbl mb-1.5">Entry zone</div>
                      {plan.entries.map((e) => (
                        <div key={e.label} className="flex justify-between gap-2 text-sm">
                          <span className="text-neutral-500">{e.label}</span>
                          <span className="font-mono text-neutral-100">{f2(e.price)}</span>
                        </div>
                      ))}
                    </div>
                    <div className="rounded-lg border border-white/10 p-2.5">
                      <div className="lbl mb-1.5">Take-profit · R · P(touch)</div>
                      {plan.targets.map((t) => (
                        <div key={t.label} className="flex items-baseline justify-between gap-2 text-sm">
                          <span className="truncate text-neutral-500">{t.label}</span>
                          <span className="whitespace-nowrap font-mono text-call">
                            {f2(t.price)}
                            {t.r != null && <span className="ml-1 text-[10px] text-neutral-500">{t.r}R</span>}
                            {t.pTouch != null && <span className="ml-1 text-[10px] text-accent-cyan">{Math.round(t.pTouch * 100)}%</span>}
                          </span>
                        </div>
                      ))}
                    </div>
                    <div className="rounded-lg border border-white/10 p-2.5">
                      <div className="lbl mb-1.5">Stop / risk</div>
                      <div className="flex justify-between gap-2 text-sm">
                        <span className="text-neutral-500">Stop</span>
                        <span className="font-mono text-put">{f2(plan.stop)}</span>
                      </div>
                      <div className="text-[10px] text-neutral-500">{plan.stopLabel}</div>
                      {plan.risk != null && <div className="mt-1 text-[11px] text-neutral-400">Risk ≈ {f2(plan.risk)} / unit (= 1R)</div>}
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
            </section>
          )}

          <section className="mt-4 border-t border-white/5 pt-3">
            <div className="mb-2 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
              <span className="lbl">Pressure breakdown</span>
              {detail && levelPressure && (
                <span className="text-[11px] text-amber-300/90">
                  @ {detail.lp.name} {f2(detail.lp.price)} · score {levelPressure.pressureScore > 0 ? "+" : ""}
                  {levelPressure.pressureScore}
                </span>
              )}
            </div>
            <div className="space-y-1.5">
              {(detail && levelPressure ? levelPressure.components : r.components).map((cp) => (
                <div key={cp.label} className={ROW_GRID}>
                  <span className={`inline-block h-2 w-2 rounded-full ${dirDot(cp.dir)}`} />
                  <span className="truncate text-neutral-300">{cp.label}</span>
                  <span className={`inline-flex items-center gap-1 whitespace-nowrap font-mono ${pressColor(cp.dir)}`}>
                    {cp.dir === "balanced" ? <span className="text-neutral-500">·</span> : <Chevron dir={cp.dir === "up" ? "up" : "down"} className="h-2.5 w-2.5" />}
                    {cp.weight}
                  </span>
                  <span className="text-neutral-500">{cp.detail}</span>
                </div>
              ))}
            </div>
          </section>

          {detail && (
            <section className="mt-4 border-t border-white/5 pt-3">
              <div className="mb-2 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span className="lbl">Strike greeks</span>
                <span className="text-[11px] text-neutral-500">
                  @ {detail.st.strike ?? detail.lp.name} · dealer exposure at the strike
                </span>
              </div>
              <div className="space-y-1.5">
                {[
                  { k: "GEX (γ$)", v: detail.st.gex, fmt: (x: number) => fmtUsd(x), note: detail.st.gex >= 0 ? "call-γ — dealers dampen / support" : "put-γ — dealers amplify / destabilise" },
                  { k: "DEX (Δ$)", v: detail.st.dex, fmt: (x: number) => fmtUsd(x), note: detail.st.dex >= 0 ? "net long delta (call-heavy)" : "net short delta (put-heavy)" },
                  { k: "Vanna", v: detail.st.vanna, fmt: (x: number) => `${fmtUsd(x)}/vp`, note: detail.st.vanna >= 0 ? "IV↑ adds dealer delta" : "IV↑ sheds dealer delta" },
                  { k: "Charm", v: detail.st.charm, fmt: (x: number) => `${fmtUsd(x)}/d`, note: detail.st.charm >= 0 ? "decay → dealers buy" : "decay → dealers sell" },
                ].map((g) => (
                  <div key={g.k} className={ROW_GRID}>
                    <span className={`inline-block h-2 w-2 rounded-full ${dirDot(g.v >= 0 ? "up" : "down")}`} />
                    <span className="truncate text-neutral-300">{g.k}</span>
                    <span className={`whitespace-nowrap font-mono ${g.v >= 0 ? "text-call" : "text-put"}`}>{g.fmt(g.v)}</span>
                    <span className="text-neutral-500">{g.note}</span>
                  </div>
                ))}
                <div className={ROW_GRID}>
                  <span className="inline-block h-2 w-2 rounded-full bg-neutral-500" />
                  <span className="truncate text-neutral-300">IV · γ-share</span>
                  <span className="whitespace-nowrap font-mono text-neutral-200">
                    {detail.st.iv != null ? `${(detail.st.iv * 100).toFixed(1)}%` : "—"} · {Math.round(detail.st.gexShare * 100)}%
                  </span>
                  <span className="text-neutral-500">implied vol &amp; this strike&apos;s share of total |GEX|</span>
                </div>
              </div>
            </section>
          )}

          {r.notes.length > 0 && (
            <div className="mt-4 border-t border-white/5 pt-3">
              <div className="lbl mb-1.5">Model notes</div>
              <div className="space-y-1">
                {r.notes.map((n) => (
                  <p key={n} className="text-[11px] leading-relaxed text-neutral-500">
                    {n}
                  </p>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
