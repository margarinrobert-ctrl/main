"use client";

import { useEffect, useMemo, useState } from "react";
import type { OptionContract } from "@/lib/barchart/types";
import { loadChain } from "@/lib/client-data";
import {
  atmIv,
  callOiWall,
  callResistance,
  deltaCallWall,
  deltaPutWall,
  dexByStrike,
  expectedMove1D,
  fmtUsd,
  gammaFlipNearest,
  gexByStrike,
  maxPain,
  netDex,
  netGex,
  oiByStrike,
  putCallRatio,
  putOiWall,
  putSupport,
} from "@/lib/flow/analytics";

const n0 = (x: number | null | undefined) => (x == null ? "—" : x.toLocaleString(undefined, { maximumFractionDigits: 0 }));
const n2 = (x: number | null | undefined) => (x == null ? "—" : x.toLocaleString(undefined, { maximumFractionDigits: 2 }));

function Kpi({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex shrink-0 flex-col gap-0.5 px-3 py-1.5">
      <span className="lbl">{label}</span>
      <span className={`text-sm font-semibold ${tone ?? "text-neutral-100"}`}>{value}</span>
    </div>
  );
}

/** GregFlow-style top ribbon: spot + dealer-positioning KPIs, color-coded, refreshed live. */
export function KpiRibbon({ symbol }: { symbol: string }) {
  const sym = symbol.toUpperCase();
  const [chain, setChain] = useState<OptionContract[]>([]);
  const [spot, setSpot] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      loadChain(sym)
        .then((r) => {
          if (!cancelled) {
            setChain(r.chain);
            setSpot(r.spot);
          }
        })
        .catch(() => {});
    load();
    const ms = Math.max(20_000, Number(process.env.NEXT_PUBLIC_REFRESH_MS ?? 60_000) || 60_000);
    const id = setInterval(load, ms);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [sym]);

  const k = useMemo(() => {
    if (!chain.length || spot == null) return null;
    const by = gexByStrike(chain, spot);
    const dby = dexByStrike(chain, spot);
    const oi = oiByStrike(chain);
    const exps = [...new Set(chain.map((c) => c.expiration))].sort();
    const front = exps.find((e) => (chain.find((c) => c.expiration === e)?.dte ?? -1) >= 0) ?? exps[0];
    const iv = front ? atmIv(chain, spot, front) : null;
    return {
      callWall: callResistance(by, spot),
      putWall: putSupport(by, spot),
      flip: gammaFlipNearest(by, spot),
      maxPain: front ? maxPain(chain, front) : null,
      ngex: netGex(chain, spot),
      ndex: netDex(chain, spot),
      iv,
      pcr: putCallRatio(chain).vol,
      em1: expectedMove1D(spot, iv),
      dcw: deltaCallWall(dby, spot),
      dpw: deltaPutWall(dby, spot),
      coi: callOiWall(oi),
      poi: putOiWall(oi),
    };
  }, [chain, spot]);

  const regime = k?.ngex == null ? "—" : k.ngex >= 0 ? "Long γ" : "Short γ";

  return (
    <div className="glass overflow-hidden">
      {/* row A — spot + walls */}
      <div className="tabs-scroll items-stretch divide-x divide-white/5 border-b border-white/5">
        <div className="flex shrink-0 flex-col gap-0.5 px-3 py-1.5">
          <span className="lbl">{sym} · spot</span>
          <span className="text-lg font-bold text-neutral-50">{spot == null ? "—" : `$${n2(spot)}`}</span>
        </div>
        <Kpi label="Call Wall" value={k ? `$${n0(k.callWall)}` : "—"} tone="text-call" />
        <Kpi label="Put Wall" value={k ? `$${n0(k.putWall)}` : "—"} tone="text-put" />
        <Kpi label="Max Pain" value={k ? `$${n0(k.maxPain)}` : "—"} tone="text-amber-300" />
        <Kpi label="Gamma Flip" value={k ? `$${n0(k.flip)}` : "—"} tone="text-violet-300" />
        <Kpi label="Δ Call Wall" value={k ? `$${n0(k.dcw)}` : "—"} tone="text-call" />
        <Kpi label="Δ Put Wall" value={k ? `$${n0(k.dpw)}` : "—"} tone="text-put" />
        <Kpi label="Net DEX" value={k && k.ndex != null ? fmtUsd(k.ndex) : "—"} tone={(k?.ndex ?? 0) >= 0 ? "text-call" : "text-put"} />
      </div>
      {/* row B — metrics */}
      <div className="tabs-scroll items-stretch divide-x divide-white/5">
        <Kpi label="ATM IV" value={k && k.iv != null ? `${(k.iv * 100).toFixed(1)}%` : "—"} tone="text-sky-300" />
        <Kpi label="P/C Ratio" value={k && k.pcr != null ? k.pcr.toFixed(2) : "—"} tone={(k?.pcr ?? 0) > 1 ? "text-put" : "text-call"} />
        <Kpi label="Net GEX" value={k && k.ngex != null ? fmtUsd(k.ngex) : "—"} tone={(k?.ngex ?? 0) >= 0 ? "text-call" : "text-put"} />
        <Kpi label="Regime" value={regime} tone={k?.ngex == null ? "text-neutral-300" : k.ngex >= 0 ? "text-call" : "text-put"} />
        <Kpi label="1σ Daily" value={k && k.em1 != null ? `±$${n2(k.em1.abs)}` : "—"} tone="text-neutral-200" />
        <Kpi label="Call OI" value={k ? `$${n0(k.coi)}` : "—"} tone="text-neutral-300" />
        <Kpi label="Put OI" value={k ? `$${n0(k.poi)}` : "—"} tone="text-neutral-300" />
      </div>
    </div>
  );
}
