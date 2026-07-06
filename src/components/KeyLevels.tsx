"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { alertsEnabled, requestNotifyPermission, setAlertsEnabled } from "@/lib/alerts";
import { loadChain } from "@/lib/client-data";
import type { OptionContract } from "@/lib/barchart/types";
import {
  atmIv,
  callWall,
  deltaCallWall,
  deltaFlip,
  deltaPutWall,
  dexByStrike,
  expectedMove,
  expectedMove1D,
  filterByExpiration,
  fmtUsd,
  gammaFlip,
  gexByStrike,
  maxPain,
  netDex,
  netGex,
  putCallRatio,
  putWall,
  secondOrderExposure,
} from "@/lib/flow/analytics";
import { EmptyState, ErrorState, Loading, SectionHeader } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

function nearestExp(chain: OptionContract[]): string | null {
  const exps = [...new Set(chain.map((c) => c.expiration))];
  const withDte = exps.map((e) => ({ e, dte: chain.find((c) => c.expiration === e)?.dte ?? 9999 }));
  const future = withDte.filter((x) => x.dte >= 0).sort((a, b) => a.dte - b.dte);
  return (future[0] ?? withDte[0])?.e ?? null;
}

export function KeyLevels({ symbol, exp = "ALL" }: { symbol: string; exp?: string }) {
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [spot, setSpot] = useState<number | null>(null);
  const [state, setState] = useState<ViewState>("loading");
  const [error, setError] = useState("");
  const [alerts, setAlerts] = useState(false);

  useEffect(() => {
    setAlerts(alertsEnabled(symbol));
  }, [symbol]);

  const toggleAlerts = async () => {
    if (alerts) {
      setAlertsEnabled(symbol, false);
      setAlerts(false);
      return;
    }
    if (await requestNotifyPermission()) {
      setAlertsEnabled(symbol, true);
      setAlerts(true);
    }
  };

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

  const levels = useMemo(() => {
    const sub = filterByExpiration(chain, exp);
    const by = gexByStrike(sub, spot);
    const dby = dexByStrike(sub, spot);
    const ngex = netGex(sub, spot);
    const e = nearestExp(sub);
    const em = e ? expectedMove(sub, spot, e) : null;
    const iv0 = e ? atmIv(sub, spot, e) : null;
    const em1 = expectedMove1D(spot, iv0);
    const pc = putCallRatio(sub);
    return {
      ngex,
      ndex: netDex(sub, spot),
      flip: gammaFlip(by),
      cw: callWall(by),
      pw: putWall(by),
      dcw: deltaCallWall(dby, spot),
      dpw: deltaPutWall(dby, spot),
      dflip: deltaFlip(dby, spot),
      mp: e ? maxPain(sub, e) : null,
      em,
      em1,
      iv0,
      so: secondOrderExposure(sub, spot),
      pc,
      exp: e,
    };
  }, [chain, spot, exp]);

  const flowRead = useMemo(() => {
    const gamma =
      levels.ngex == null
        ? null
        : levels.ngex >= 0
          ? "Long-gamma regime — dealer hedging dampens moves; mean-reversion and pinning dominate."
          : "Short-gamma regime — dealer hedging amplifies moves; trend extension and gap risk dominate.";
    const vanna =
      levels.so.vanna == null
        ? null
        : levels.so.vanna >= 0
          ? "Positive vanna — falling IV drives dealer buying; a vol spike flips dealers to sellers."
          : "Negative vanna — falling IV drives dealer selling; a vol spike cushions the downside.";
    const charm =
      levels.so.charm == null
        ? null
        : `Time decay moves dealer delta ~${fmtUsd(Math.abs(levels.so.charm))}/day to the ${levels.so.charm >= 0 ? "sell" : "buy"} side into expiry.`;
    return { gamma, vanna, charm };
  }, [levels]);

  return (
    <div className="glass fade-up p-4">
      <SectionHeader
        eyebrow="Positioning"
        title={<>Dealer positioning &amp; key levels · {symbol}</>}
        right={
          <button
            onClick={toggleAlerts}
            aria-pressed={alerts}
            title="Browser notification when spot crosses the call wall / gamma flip / put wall (while a ticker tab is open)"
            className={`inline-flex items-center gap-2 rounded-full border px-3 py-2 text-[10px] font-medium uppercase tracking-[0.1em] transition ${
              alerts
                ? "border-call/30 bg-call/10 text-call"
                : "border-white/10 bg-white/[0.03] text-neutral-400 hover:border-white/20 hover:text-neutral-200"
            }`}
          >
            {alerts ? (
              <span className="live-dot" aria-hidden />
            ) : (
              <span aria-hidden className="inline-block h-1.5 w-1.5 rounded-full bg-neutral-600" />
            )}
            {alerts ? "Alerts armed" : "Alerts"}
          </button>
        }
      />
      {state === "loading" && <Loading label="Loading key levels…" />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options data." />}
      {state === "ok" && (
        <div className="space-y-4">
          <Group title="Gamma">
            <Tile
              label="Dealer gamma"
              value={levels.ngex == null ? "—" : levels.ngex >= 0 ? "Long γ" : "Short γ"}
              sub={levels.ngex == null ? "" : `${fmtUsd(levels.ngex)}/1%`}
              tone={levels.ngex == null ? "neutral" : levels.ngex >= 0 ? "call" : "put"}
            />
            <Tile
              label="Gamma flip"
              value={levels.flip == null ? "—" : levels.flip.toLocaleString(undefined, { maximumFractionDigits: 1 })}
              sub="zero-γ level"
            />
            <Tile label="Call wall" value={levels.cw == null ? "—" : String(levels.cw)} sub="max call γ" tone="call" />
            <Tile label="Put wall" value={levels.pw == null ? "—" : String(levels.pw)} sub="max put γ" tone="put" />
          </Group>

          <Group title="Delta">
            <Tile
              label="Net Δ exposure"
              value={levels.ndex == null ? "—" : fmtUsd(levels.ndex)}
              sub="$Δ of open interest"
              tone={levels.ndex == null ? "neutral" : levels.ndex >= 0 ? "call" : "put"}
              hint="Aggregate notional delta of all open interest (calls +, puts −). Positive = the option book leans net-long delta; negative = net-short. The directional weight dealers sit against."
            />
            <Tile
              label="Δ Call wall"
              value={levels.dcw == null ? "—" : String(levels.dcw)}
              sub="max call Δ-exp"
              tone="call"
              hint="Delta call wall — the strike with the heaviest call delta-exposure (delta × OI) above spot. Delta-weighting favours the strikes that move with price, so it marks the hedgeable-delta resistance, a level rallies tend to stall under."
            />
            <Tile
              label="Δ Put wall"
              value={levels.dpw == null ? "—" : String(levels.dpw)}
              sub="max put Δ-exp"
              tone="put"
              hint="Delta put wall — the strike with the heaviest put delta-exposure below spot. The hedgeable-delta support, a level dips tend to hold above."
            />
            <Tile
              label="Δ-neutral"
              value={levels.dflip == null ? "—" : levels.dflip.toLocaleString(undefined, { maximumFractionDigits: 1 })}
              sub="delta flip"
              hint="Delta-neutral / delta-flip strike: where cumulative net delta-exposure crosses zero — put-delta-dominated (net short) below, call-delta-dominated (net long) above. The pivot the book's directional weight balances on."
            />
          </Group>

          <Group title="Vol">
            <Tile
              label="1-day range"
              value={levels.em1 == null ? "—" : `±${levels.em1.abs.toFixed(2)}`}
              sub={levels.em1 == null ? "" : `±${(levels.em1.pct * 100).toFixed(1)}% · 1σ from ATM IV`}
              hint="Single-session 1σ move = spot × ATM IV × √(1/252). The intraday distribution boundary."
            />
            <Tile
              label="Exp move → exp"
              value={levels.em == null ? "—" : `±${levels.em.abs.toFixed(2)}`}
              sub={levels.em == null ? "" : `±${(levels.em.pct * 100).toFixed(1)}% · ${levels.exp ?? ""}`}
              hint="ATM straddle — the move priced in all the way TO the front expiration (multi-day)."
            />
            <Tile
              label="Vanna exp."
              value={levels.so.vanna == null ? "—" : fmtUsd(levels.so.vanna)}
              sub="$Δ / 1 vol-pt"
              tone={levels.so.vanna == null ? "neutral" : levels.so.vanna >= 0 ? "call" : "put"}
              hint="Dealer ∂Δ/∂σ. Positive → falling IV drives dealer buying; a vol spike flips them to sellers."
            />
            <Tile
              label="Charm exp."
              value={levels.so.charm == null ? "—" : `${fmtUsd(levels.so.charm)}/d`}
              sub={levels.so.charm == null ? "" : levels.so.charm >= 0 ? "dealers sell into decay" : "dealers buy into decay"}
              tone={levels.so.charm == null ? "neutral" : levels.so.charm >= 0 ? "put" : "call"}
              hint="Dealer ∂Δ/∂t — the delta they must trade per day from time decay, strongest into Thu/Fri expiry."
            />
          </Group>

          <Group title="Positioning">
            <Tile label="Spot" value={spot == null ? "—" : spot.toLocaleString()} />
            <Tile label="Max pain" value={levels.mp == null ? "—" : String(levels.mp)} sub={levels.exp ?? ""} />
            <Tile
              label="Put/Call (vol)"
              value={levels.pc.vol == null ? "—" : levels.pc.vol.toFixed(2)}
              tone={levels.pc.vol == null ? "neutral" : levels.pc.vol > 1 ? "put" : "call"}
            />
            <Tile label="Put/Call (OI)" value={levels.pc.oi == null ? "—" : levels.pc.oi.toFixed(2)} />
          </Group>
        </div>
      )}
      {state === "ok" && (flowRead.gamma || flowRead.vanna || flowRead.charm) && (
        <div className="mt-4 space-y-1.5 border-t border-white/5 pt-3">
          {flowRead.gamma && <FlowLine k="Gamma" text={flowRead.gamma} />}
          {flowRead.vanna && <FlowLine k="Vanna" text={flowRead.vanna} />}
          {flowRead.charm && <FlowLine k="Charm" text={flowRead.charm} />}
        </div>
      )}
    </div>
  );
}

/** Micro-cap group divider: label + hairline rule, then a 4-up tile grid. */
function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-2.5">
        <span className="lbl">{title}</span>
        <span aria-hidden className="h-px flex-1 bg-white/5" />
      </div>
      <div className="grid grid-cols-2 gap-2.5 text-sm lg:grid-cols-4">{children}</div>
    </div>
  );
}

/** One line of the dealer-flow read, prefixed by its greek. */
function FlowLine({ k, text }: { k: string; text: string }) {
  return (
    <p className="flex items-baseline gap-2.5 text-xs leading-relaxed text-neutral-400">
      <span className="lbl w-12 shrink-0">{k}</span>
      <span>{text}</span>
    </p>
  );
}

function Tile({
  label,
  value,
  sub,
  tone = "neutral",
  hint,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "call" | "put" | "neutral";
  hint?: string;
}) {
  const color = tone === "call" ? "text-call" : tone === "put" ? "text-put" : "text-neutral-100";
  const accent = tone === "call" ? "border-l-call/60" : tone === "put" ? "border-l-put/60" : "border-l-transparent";
  return (
    <div
      className={`group relative rounded-lg border border-white/[0.06] border-l-2 ${accent} bg-white/[0.015] px-3 py-2.5 transition-colors duration-150 focus-within:border-white/[0.16] hover:border-white/[0.16]`}
    >
      <div className="flex items-center gap-1.5">
        <span className="lbl">{label}</span>
        {hint ? (
          <button type="button" aria-label={`Definition: ${label}`} className="shrink-0 rounded-full text-neutral-600 transition hover:text-neutral-300">
            <svg aria-hidden viewBox="0 0 14 14" className="h-3 w-3">
              <circle cx="7" cy="7" r="6" fill="none" stroke="currentColor" strokeWidth="1.2" />
              <path fill="currentColor" d="M6.3 6h1.4v4.2H6.3V6Zm0-2.3h1.4v1.4H6.3V3.7Z" />
            </svg>
          </button>
        ) : null}
      </div>
      <div className={`mt-1 font-mono text-lg tabular-nums leading-tight ${color}`}>{value}</div>
      {sub ? <div className="mt-0.5 text-[11px] leading-snug text-neutral-500">{sub}</div> : null}
      {hint ? (
        <div
          role="tooltip"
          className="pointer-events-none invisible absolute left-0 top-full z-20 mt-1.5 w-64 max-w-[78vw] rounded-xl border border-white/10 bg-[#0a0b10]/95 p-3 text-[11px] leading-relaxed text-neutral-300 opacity-0 shadow-panel-lift backdrop-blur-sm transition-opacity duration-150 group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100"
        >
          {hint}
        </div>
      ) : null}
    </div>
  );
}
