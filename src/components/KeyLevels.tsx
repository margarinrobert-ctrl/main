"use client";

import { useEffect, useMemo, useState } from "react";
import { alertsEnabled, requestNotifyPermission, setAlertsEnabled } from "@/lib/alerts";
import { loadChain } from "@/lib/client-data";
import type { OptionContract } from "@/lib/barchart/types";
import {
  callWall,
  expectedMove,
  fmtUsd,
  gammaFlip,
  gexByStrike,
  maxPain,
  netDex,
  netGex,
  putCallRatio,
  putWall,
} from "@/lib/flow/analytics";
import { EmptyState, ErrorState, Loading } from "./states";

type ViewState = "loading" | "error" | "empty" | "ok";

function nearestExp(chain: OptionContract[]): string | null {
  const exps = [...new Set(chain.map((c) => c.expiration))];
  const withDte = exps.map((e) => ({ e, dte: chain.find((c) => c.expiration === e)?.dte ?? 9999 }));
  const future = withDte.filter((x) => x.dte >= 0).sort((a, b) => a.dte - b.dte);
  return (future[0] ?? withDte[0])?.e ?? null;
}

export function KeyLevels({ symbol }: { symbol: string }) {
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
    const by = gexByStrike(chain, spot);
    const ngex = netGex(chain, spot);
    const exp = nearestExp(chain);
    const em = exp ? expectedMove(chain, spot, exp) : null;
    const pc = putCallRatio(chain);
    return {
      ngex,
      ndex: netDex(chain, spot),
      flip: gammaFlip(by),
      cw: callWall(by),
      pw: putWall(by),
      mp: exp ? maxPain(chain, exp) : null,
      em,
      pc,
      exp,
    };
  }, [chain, spot]);

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
          <Stat label="Net Δ exposure" value={levels.ndex == null ? "—" : fmtUsd(levels.ndex)} />
          <Stat label="Gamma flip" value={levels.flip == null ? "—" : levels.flip.toLocaleString(undefined, { maximumFractionDigits: 1 })} sub="zero-γ level" />
          <Stat label="Spot" value={spot == null ? "—" : spot.toLocaleString()} />
          <Stat label="Call wall" value={levels.cw == null ? "—" : String(levels.cw)} sub="max call γ" tone="good" />
          <Stat label="Put wall" value={levels.pw == null ? "—" : String(levels.pw)} sub="max put γ" tone="bad" />
          <Stat label="Max pain" value={levels.mp == null ? "—" : String(levels.mp)} sub={levels.exp ?? ""} />
          <Stat
            label="Expected move"
            value={levels.em == null ? "—" : `±${levels.em.abs.toFixed(2)}`}
            sub={levels.em == null ? "" : `±${(levels.em.pct * 100).toFixed(1)}% · ${levels.exp ?? ""}`}
          />
          <Stat label="Put/Call (vol)" value={levels.pc.vol == null ? "—" : levels.pc.vol.toFixed(2)} tone={levels.pc.vol != null && levels.pc.vol > 1 ? "bad" : "good"} />
          <Stat label="Put/Call (OI)" value={levels.pc.oi == null ? "—" : levels.pc.oi.toFixed(2)} />
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "good" | "bad" | "neutral";
}) {
  const color = tone === "good" ? "text-emerald-400" : tone === "bad" ? "text-red-400" : "text-neutral-100";
  return (
    <div className="rounded border border-neutral-800 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-neutral-500">{label}</div>
      <div className={`font-mono text-lg ${color}`}>{value}</div>
      {sub ? <div className="text-[11px] text-neutral-500">{sub}</div> : null}
    </div>
  );
}
