"use client";

import { useEffect, useMemo, useState } from "react";
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
import { EmptyState, ErrorState, Loading } from "./states";

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
    const parts: string[] = [];
    if (levels.ngex != null)
      parts.push(
        levels.ngex >= 0
          ? "Long-gamma: dealers dampen moves (mean-reversion, pinning)."
          : "Short-gamma: dealers amplify moves (trends, air-pockets).",
      );
    if (levels.so.vanna != null)
      parts.push(
        levels.so.vanna >= 0
          ? "Positive vanna → falling IV is a tailwind (melt-up); a vol spike turns dealers into sellers."
          : "Negative vanna → falling IV is a headwind; vol spikes cushion the downside.",
      );
    if (levels.so.charm != null)
      parts.push(
        `Charm bleeds dealer delta ~${fmtUsd(Math.abs(levels.so.charm))}/day to the ${levels.so.charm >= 0 ? "SELL" : "BUY"} side into expiry.`,
      );
    return parts.join(" ");
  }, [levels]);

  return (
    <div className="glass p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="font-semibold">Dealer positioning &amp; key levels · {symbol}</h2>
        <button
          onClick={toggleAlerts}
          title="Browser notification when spot crosses the call wall / γ-flip / put wall (while a ticker tab is open)"
          className={`rounded-full border px-2.5 py-1 text-xs transition ${
            alerts
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
              : "border-white/15 text-neutral-400 hover:text-neutral-200"
          }`}
        >
          {alerts ? "🔔 Alerts on" : "🔕 Alerts"}
        </button>
      </div>
      {state === "loading" && <Loading />}
      {state === "error" && <ErrorState message={error} />}
      {state === "empty" && <EmptyState label="No options data." />}
      {state === "ok" && (
        <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3 lg:grid-cols-4">
          <Stat
            label="Dealer gamma"
            value={levels.ngex == null ? "—" : levels.ngex >= 0 ? "Long γ" : "Short γ"}
            sub={levels.ngex == null ? "" : `${fmtUsd(levels.ngex)}/1%`}
            tone={levels.ngex == null ? "neutral" : levels.ngex >= 0 ? "good" : "bad"}
          />
          <Stat
            label="Net Δ exposure"
            value={levels.ndex == null ? "—" : fmtUsd(levels.ndex)}
            sub="$Δ of open interest"
            tone={levels.ndex == null ? "neutral" : levels.ndex >= 0 ? "good" : "bad"}
            hint="Aggregate notional delta of all open interest (calls +, puts −). Positive = the option book leans net-long delta; negative = net-short. The directional weight dealers sit against."
          />
          <Stat label="Gamma flip" value={levels.flip == null ? "—" : levels.flip.toLocaleString(undefined, { maximumFractionDigits: 1 })} sub="zero-γ level" />
          <Stat label="Spot" value={spot == null ? "—" : spot.toLocaleString()} />
          <Stat label="Call wall" value={levels.cw == null ? "—" : String(levels.cw)} sub="max call γ" tone="good" />
          <Stat label="Put wall" value={levels.pw == null ? "—" : String(levels.pw)} sub="max put γ" tone="bad" />
          <Stat
            label="Δ Call wall"
            value={levels.dcw == null ? "—" : String(levels.dcw)}
            sub="max call Δ-exp"
            tone="good"
            hint="Delta call wall — the strike with the heaviest call delta-exposure (delta × OI) above spot. Delta-weighting favours the strikes that move with price, so it marks the hedgeable-delta resistance, a level rallies tend to stall under."
          />
          <Stat
            label="Δ Put wall"
            value={levels.dpw == null ? "—" : String(levels.dpw)}
            sub="max put Δ-exp"
            tone="bad"
            hint="Delta put wall — the strike with the heaviest put delta-exposure below spot. The hedgeable-delta support, a level dips tend to hold above."
          />
          <Stat
            label="Δ-neutral"
            value={levels.dflip == null ? "—" : levels.dflip.toLocaleString(undefined, { maximumFractionDigits: 1 })}
            sub="delta flip"
            hint="Delta-neutral / delta-flip strike: where cumulative net delta-exposure crosses zero — put-delta-dominated (net short) below, call-delta-dominated (net long) above. The pivot the book's directional weight balances on."
          />
          <Stat label="Max pain" value={levels.mp == null ? "—" : String(levels.mp)} sub={levels.exp ?? ""} />
          <Stat
            label="1-day range"
            value={levels.em1 == null ? "—" : `±${levels.em1.abs.toFixed(2)}`}
            sub={levels.em1 == null ? "" : `±${(levels.em1.pct * 100).toFixed(1)}% · 1σ from ATM IV`}
            hint="True single-session 1σ move = spot × ATM IV × √(1/252). Intraday scalp targets."
          />
          <Stat
            label="Exp move → exp"
            value={levels.em == null ? "—" : `±${levels.em.abs.toFixed(2)}`}
            sub={levels.em == null ? "" : `±${(levels.em.pct * 100).toFixed(1)}% · ${levels.exp ?? ""}`}
            hint="ATM straddle — the move priced in all the way TO the front expiration (multi-day)."
          />
          <Stat
            label="Vanna exp."
            value={levels.so.vanna == null ? "—" : fmtUsd(levels.so.vanna)}
            sub="$Δ / 1 vol-pt"
            tone={levels.so.vanna == null ? "neutral" : levels.so.vanna >= 0 ? "good" : "bad"}
            hint="Dealer ∂Δ/∂σ. Positive → falling IV makes dealers buy (vanna melt-up); a vol spike flips them to sellers."
          />
          <Stat
            label="Charm exp."
            value={levels.so.charm == null ? "—" : `${fmtUsd(levels.so.charm)}/d`}
            sub={levels.so.charm == null ? "" : levels.so.charm >= 0 ? "dealers sell into decay" : "dealers buy into decay"}
            tone={levels.so.charm == null ? "neutral" : levels.so.charm >= 0 ? "bad" : "good"}
            hint="Dealer ∂Δ/∂t — the delta they must trade per day from time decay, strongest into Thu/Fri expiry."
          />
          <Stat label="Put/Call (vol)" value={levels.pc.vol == null ? "—" : levels.pc.vol.toFixed(2)} tone={levels.pc.vol != null && levels.pc.vol > 1 ? "bad" : "good"} />
          <Stat label="Put/Call (OI)" value={levels.pc.oi == null ? "—" : levels.pc.oi.toFixed(2)} />
        </div>
      )}
      {state === "ok" && flowRead && (
        <p className="mt-3 border-t border-white/5 pt-3 text-xs leading-relaxed text-neutral-400">{flowRead}</p>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  tone = "neutral",
  hint,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "good" | "bad" | "neutral";
  hint?: string;
}) {
  const color = tone === "good" ? "text-emerald-400" : tone === "bad" ? "text-red-400" : "text-neutral-100";
  return (
    <div className="rounded border border-neutral-800 px-3 py-2" title={hint}>
      <div className="flex items-center gap-1 text-[11px] uppercase tracking-wide text-neutral-500">
        {label}
        {hint ? <span className="cursor-help text-neutral-600">ⓘ</span> : null}
      </div>
      <div className={`font-mono text-lg ${color}`}>{value}</div>
      {sub ? <div className="text-[11px] text-neutral-500">{sub}</div> : null}
    </div>
  );
}
