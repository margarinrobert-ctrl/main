"use client";

import { useEffect, useMemo, useState } from "react";
import { ensembleForecast } from "@/lib/intel/ensemble";
import type { IntelDir } from "@/lib/intel/journal";
import { readJournal } from "@/lib/intel/journal";
import { calibrateConfidence, learnedProfile } from "@/lib/intel/profile";

const dirChip = (d: IntelDir) =>
  d === "bullish" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" : d === "bearish" ? "border-red-500/40 bg-red-500/10 text-red-300" : "border-sky-500/40 bg-sky-500/10 text-sky-300";
const dirLabel = (d: IntelDir) => (d === "bullish" ? "▲ BULLISH" : d === "bearish" ? "▼ BEARISH" : "■ NEUTRAL");
const dirDot = (d: IntelDir) => (d === "bullish" ? "bg-emerald-400" : d === "bearish" ? "bg-red-400" : "bg-neutral-400");
const sp = (x: number | null | undefined) => (x == null ? "—" : `${x >= 0 ? "+" : ""}${x.toFixed(2)}%`);
const SRC_LABEL: Record<string, string> = { anomaly: "Anomaly", signals: "Signals", mmhedge: "MM-Hedge" };

/**
 * Overview headline: the self-optimizing read. Blends every engine's latest call into one forecast,
 * weighted by each engine's REALISED track record on the Intel journal, with confidence recalibrated to
 * realised hit-rates. The same learned profile tunes the badges on every section below.
 */
export function EdgeOptimizer({ symbol }: { symbol: string }) {
  const sym = symbol.toUpperCase();
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const ms = Math.max(15_000, Number(process.env.NEXT_PUBLIC_REFRESH_MS ?? 30_000) || 30_000);
    const id = setInterval(() => setTick((t) => t + 1), ms);
    return () => clearInterval(id);
  }, []);

  const { profile, ens } = useMemo(() => {
    void tick;
    const j = readJournal();
    return { profile: learnedProfile(j), ens: ensembleForecast(j.filter((r) => r.symbol === sym)) };
  }, [sym, tick]);

  if (profile.n === 0 && !ens.available) return null; // nothing learned yet — stay out of the way

  const calConf = ens.available ? calibrateConfidence(ens.confidence, profile) : null;

  return (
    <div className="glass p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-semibold">Edge-optimized read · {symbol}</h2>
          <p className="text-xs text-neutral-500">every engine blended &amp; calibrated by its realised track record · {profile.n} resolved calls</p>
        </div>
        {ens.available && <span className={`rounded-full border px-3 py-1 text-sm font-semibold ${dirChip(ens.direction)}`}>{dirLabel(ens.direction)}</span>}
      </div>

      {ens.available ? (
        <div className="mb-3 flex flex-wrap items-center gap-2 font-mono text-xs">
          <span className="rounded border border-white/10 px-2 py-1 text-neutral-200">P(up) {Math.round(ens.pUp * 100)}%</span>
          <span className="rounded border border-white/10 px-2 py-1 text-neutral-200">
            conf {ens.confidence}%{calConf != null && calConf !== ens.confidence ? ` → cal ${calConf}%` : ""}
          </span>
          <span className="rounded border border-white/10 px-2 py-1 text-neutral-200">agree {Math.round(ens.agreement * 100)}%</span>
          {ens.kelly != null && <span className="rounded border border-white/10 px-2 py-1 text-emerald-300">¼-Kelly {(ens.kelly * 100).toFixed(1)}%</span>}
        </div>
      ) : (
        <p className="mb-3 text-xs text-neutral-500">No live directional call on record for {symbol} yet — the engines are neutral or this ticker hasn&apos;t been sampled. Learned weights below still tune the sections.</p>
      )}

      {/* learned engine weights */}
      <div className="space-y-1.5">
        <div className="text-[11px] uppercase tracking-wide text-neutral-500">Engine weights (learned from realised edge)</div>
        {profile.sources.map((s) => (
          <div key={s.source} className="flex items-center gap-2 text-xs">
            <span className="w-20 shrink-0 text-neutral-300">{SRC_LABEL[s.source] ?? s.source}</span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/10">
              <div className="h-full rounded-full bg-neutral-200/70" style={{ width: `${Math.round(s.weight * 100)}%` }} />
            </div>
            <span className="w-10 shrink-0 text-right font-mono text-neutral-400">{Math.round(s.weight * 100)}%</span>
            <span className="hidden w-32 shrink-0 text-right font-mono text-neutral-500 sm:inline">
              {s.n >= 5 ? `${sp(s.edge)} · hit ${s.hitRate != null ? Math.round(s.hitRate * 100) : "—"}% · n${s.n}` : `n${s.n} (thin)`}
            </span>
          </div>
        ))}
      </div>

      {profile.bestFilters.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] uppercase tracking-wide text-neutral-500">What&apos;s working:</span>
          {profile.bestFilters.map((f) => (
            <span key={f.rule} className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-300" title={`${f.n} resolved · hit ${f.hitRate != null ? Math.round(f.hitRate * 100) : "—"}%`}>
              {f.rule} {sp(f.deltaVsAll)}
            </span>
          ))}
        </div>
      )}

      <p className="mt-3 border-t border-white/5 pt-2 text-[11px] text-neutral-500">
        {profile.ready
          ? "Weights & calibration are learned from resolved outcomes and applied as the ✦ edge badges on the sections below."
          : `Still calibrating — ${profile.n}/12 resolved calls. Sections show ✦ learning… until weights stabilise.`}{" "}
        Educational, not financial advice.
      </p>
    </div>
  );
}
