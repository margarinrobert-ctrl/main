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

function Kpi({ label, value, tone, loading }: { label: string; value: string; tone?: string; loading?: boolean }) {
  return (
    <div className="flex shrink-0 flex-col gap-1 px-3.5 py-2">
      <span className="lbl">{label}</span>
      {loading ? <span className="skeleton h-4 w-14" /> : <span className={`text-sm font-semibold tracking-tight ${tone ?? "text-neutral-100"}`}>{value}</span>}
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

  const busy = k == null;

  return (
    <div className="glass overflow-hidden">
      {/* row A — spot + dealer levels */}
      <div className="tabs-scroll items-stretch divide-x divide-white/[0.05] border-b border-white/[0.05]">
        <div className="flex shrink-0 flex-col gap-1 bg-white/[0.02] px-4 py-2">
          <span className="lbl flex items-center gap-1.5">
            <span className="live-dot" style={{ height: 5, width: 5 }} />
            {sym} · spot
          </span>
          {spot == null ? (
            <span className="skeleton h-5 w-20" />
          ) : (
            <span className="display text-lg leading-none text-neutral-50">${n2(spot)}</span>
          )}
        </div>
        <Kpi loading={busy} label="Call Wall" value={k ? `$${n0(k.callWall)}` : "—"} tone="text-call" />
        <Kpi loading={busy} label="Put Wall" value={k ? `$${n0(k.putWall)}` : "—"} tone="text-put" />
        <Kpi loading={busy} label="Max Pain" value={k ? `$${n0(k.maxPain)}` : "—"} tone="text-amber-300" />
        <Kpi loading={busy} label="Gamma Flip" value={k ? `$${n0(k.flip)}` : "—"} tone="text-violet-300" />
        <Kpi loading={busy} label="Δ Call Wall" value={k ? `$${n0(k.dcw)}` : "—"} tone="text-call" />
        <Kpi loading={busy} label="Δ Put Wall" value={k ? `$${n0(k.dpw)}` : "—"} tone="text-put" />
        <Kpi loading={busy} label="Net DEX" value={k && k.ndex != null ? fmtUsd(k.ndex) : "—"} tone={(k?.ndex ?? 0) >= 0 ? "text-call" : "text-put"} />
      </div>
      {/* row B — vol & positioning metrics */}
      <div className="tabs-scroll items-stretch divide-x divide-white/[0.05]">
        <Kpi loading={busy} label="ATM IV" value={k && k.iv != null ? `${(k.iv * 100).toFixed(1)}%` : "—"} tone="text-sky-300" />
        <Kpi loading={busy} label="P/C Ratio" value={k && k.pcr != null ? k.pcr.toFixed(2) : "—"} tone={(k?.pcr ?? 0) > 1 ? "text-put" : "text-call"} />
        <Kpi loading={busy} label="Net GEX" value={k && k.ngex != null ? fmtUsd(k.ngex) : "—"} tone={(k?.ngex ?? 0) >= 0 ? "text-call" : "text-put"} />
        <Kpi loading={busy} label="Regime" value={regime} tone={k?.ngex == null ? "text-neutral-300" : k.ngex >= 0 ? "text-call" : "text-put"} />
        <Kpi loading={busy} label="1σ Daily" value={k && k.em1 != null ? `±$${n2(k.em1.abs)}` : "—"} tone="text-neutral-200" />
        <Kpi loading={busy} label="Call OI Wall" value={k ? `$${n0(k.coi)}` : "—"} tone="text-neutral-300" />
        <Kpi loading={busy} label="Put OI Wall" value={k ? `$${n0(k.poi)}` : "—"} tone="text-neutral-300" />
      </div>
    </div>
  );
}
