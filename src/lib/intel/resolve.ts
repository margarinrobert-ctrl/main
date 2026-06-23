import type { GexSample } from "../gex-history";
import type { Outcome, PredictionRecord } from "./journal";

// Outcome resolution. A prediction recorded at time t with an entry price and a horizon is scored
// against the ACTUAL recorded spot path: the realised return at horizon, directional correctness,
// whether the target/stop was touched along the way, and max favourable/adverse excursion. This is
// the honest "did it work?" measurement — no simulation, just recorded price.

interface PriceP {
  t: number;
  spot: number;
}

/** Resolve one open record against a symbol's spot path. Returns null if it hasn't matured yet. */
export function resolveOne(rec: PredictionRecord, series: PriceP[], now: number): Outcome | null {
  if (rec.outcome) return rec.outcome;
  if (rec.entry <= 0 || rec.direction === "neutral") return null;
  const matureAt = rec.t + rec.horizonMs;
  const path = series.filter((s) => s.t >= rec.t && s.spot > 0);
  if (path.length < 2) return null;

  // need a sample at/after maturity; if the latest recorded sample is already past maturity but we
  // somehow have none beyond it, fall back to the last available point so it still resolves.
  const end = path.find((s) => s.t >= matureAt);
  const latest = path[path.length - 1];
  if (!end && !(latest.t >= matureAt || now - rec.t >= rec.horizonMs * 1.5)) return null;
  const exitP = end ?? latest;

  const entry = rec.entry;
  const exit = exitP.spot;
  const dirSign = rec.direction === "bullish" ? 1 : -1;
  const realizedReturn = (exit - entry) / entry;
  const dirReturn = dirSign * realizedReturn;
  const correct = dirReturn > 0;

  const window = path.filter((s) => s.t <= exitP.t);
  const hi = Math.max(...window.map((s) => s.spot));
  const lo = Math.min(...window.map((s) => s.spot));
  const mfe = dirSign > 0 ? (hi - entry) / entry : (entry - lo) / entry;
  const mae = dirSign > 0 ? (entry - lo) / entry : (hi - entry) / entry;
  const hitTarget = rec.target == null ? null : dirSign > 0 ? hi >= rec.target : lo <= rec.target;
  const hitStop = rec.stop == null ? null : dirSign > 0 ? lo <= rec.stop : hi >= rec.stop;
  const p = rec.confidence / 100;
  const brier = (p - (correct ? 1 : 0)) ** 2;

  return {
    resolvedAt: exitP.t,
    exit,
    realizedReturn,
    dirReturn,
    correct,
    hitTarget,
    hitStop,
    mfe: Math.max(0, mfe),
    mae: Math.max(0, mae),
    brier,
    bars: window.length,
  };
}

/** Resolve every matured open record for `symbol` against its session spot series (immutable). */
export function resolveForSymbol(records: PredictionRecord[], symbol: string, samples: GexSample[], now: number): PredictionRecord[] {
  const sym = symbol.toUpperCase();
  const series: PriceP[] = samples.filter((s): s is GexSample & { spot: number } => s.spot != null && s.spot > 0).map((s) => ({ t: s.t, spot: s.spot as number }));
  if (series.length < 2) return records;
  let changed = false;
  const next = records.map((r) => {
    if (r.symbol !== sym || r.outcome) return r;
    const o = resolveOne(r, series, now);
    if (!o) return r;
    changed = true;
    return { ...r, outcome: o };
  });
  return changed ? next : records;
}

export const resolved = (records: PredictionRecord[]): PredictionRecord[] => records.filter((r) => r.outcome != null);
export const open = (records: PredictionRecord[]): PredictionRecord[] => records.filter((r) => r.outcome == null);
