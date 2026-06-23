import type { PredictionRecord } from "./journal";
import { resolved } from "./resolve";

// Performance analytics over the resolved journal. Everything here is computed from REAL recorded
// predictions vs realised price: hit-rate with a Wilson confidence interval, expectancy/Sharpe/profit
// factor, Brier calibration, rolling edge & edge-decay, regime/vol/confidence breakdowns, model
// rankings, feature importance (association) and feature drift. Small samples are surfaced honestly.

export interface PerfSummary {
  n: number;
  hitRate: number | null; // 0..1
  ci: { lo: number; hi: number } | null; // Wilson 95% on hit-rate
  expectancy: number | null; // mean directional return, %
  stdev: number | null; // % of per-trade directional return
  sharpe: number | null; // expectancy / stdev (per-trade)
  profitFactor: number | null;
  brier: number | null; // mean Brier (lower = better calibrated)
  avgConfidence: number | null; // %
  mfe: number | null; // mean max-favourable-excursion, %
  mae: number | null; // mean max-adverse-excursion, %
}

export interface Group {
  key: string;
  summary: PerfSummary;
}
export interface DecayReport {
  baseline: number | null;
  recent: number | null;
  delta: number | null;
  decaying: boolean;
  n: number;
}
export interface CalBin {
  label: string;
  predicted: number; // mean confidence, %
  realized: number; // realised hit-rate, %
  n: number;
}
export interface FeatureScore {
  feature: string;
  corr: number; // Pearson with directional return (−1..1)
  n: number;
}
export interface DriftScore {
  feature: string;
  baseline: number;
  recent: number;
  z: number;
  drifting: boolean;
}
export type HealthState = "improving" | "stable" | "degrading" | "insufficient";

const mean = (a: number[]) => (a.length ? a.reduce((s, x) => s + x, 0) / a.length : 0);
const std = (a: number[]) => {
  if (a.length < 2) return 0;
  const m = mean(a);
  return Math.sqrt(a.reduce((s, x) => s + (x - m) * (x - m), 0) / (a.length - 1));
};

/** Wilson score interval for a binomial proportion — honest CI that behaves at small n. */
export function wilson(k: number, n: number, z = 1.96): { lo: number; hi: number } {
  if (n <= 0) return { lo: 0, hi: 0 };
  const p = k / n;
  const z2 = z * z;
  const denom = 1 + z2 / n;
  const centre = (p + z2 / (2 * n)) / denom;
  const half = (z * Math.sqrt((p * (1 - p)) / n + z2 / (4 * n * n))) / denom;
  return { lo: Math.max(0, centre - half), hi: Math.min(1, centre + half) };
}

export function summarize(records: PredictionRecord[]): PerfSummary {
  const recs = resolved(records);
  const n = recs.length;
  if (!n) return { n: 0, hitRate: null, ci: null, expectancy: null, stdev: null, sharpe: null, profitFactor: null, brier: null, avgConfidence: null, mfe: null, mae: null };
  const wins = recs.filter((r) => r.outcome!.correct).length;
  const rets = recs.map((r) => r.outcome!.dirReturn * 100);
  const sd = std(rets);
  const exp = mean(rets);
  const gains = rets.filter((x) => x > 0).reduce((s, x) => s + x, 0);
  const losses = rets.filter((x) => x < 0).reduce((s, x) => s + Math.abs(x), 0);
  return {
    n,
    hitRate: wins / n,
    ci: wilson(wins, n),
    expectancy: exp,
    stdev: sd,
    sharpe: sd > 0 ? exp / sd : null,
    profitFactor: losses > 0 ? gains / losses : gains > 0 ? Infinity : null,
    brier: mean(recs.map((r) => r.outcome!.brier)),
    avgConfidence: mean(recs.map((r) => r.confidence)),
    mfe: mean(recs.map((r) => r.outcome!.mfe * 100)),
    mae: mean(recs.map((r) => r.outcome!.mae * 100)),
  };
}

/** Group resolved records by a key function and summarise each group (sorted by expectancy desc). */
export function breakdown(records: PredictionRecord[], keyOf: (r: PredictionRecord) => string, minN = 1): Group[] {
  const m = new Map<string, PredictionRecord[]>();
  for (const r of resolved(records)) {
    const k = keyOf(r);
    (m.get(k) ?? m.set(k, []).get(k)!).push(r);
  }
  return [...m.entries()]
    .map(([key, recs]) => ({ key, summary: summarize(recs) }))
    .filter((g) => g.summary.n >= minN)
    .sort((a, b) => (b.summary.expectancy ?? -1e9) - (a.summary.expectancy ?? -1e9));
}

export const confidenceBand = (c: number): string => (c >= 80 ? "80–100" : c >= 70 ? "70–80" : c >= 60 ? "60–70" : c >= 50 ? "50–60" : "<50");

export function rankModels(records: PredictionRecord[], minN = 5): Group[] {
  return breakdown(records, (r) => r.model, minN).sort((a, b) => (b.summary.sharpe ?? -1e9) - (a.summary.sharpe ?? -1e9));
}

/** Rolling mean directional edge (over `window` resolved trades) ordered by resolution time. */
export function rollingEdge(records: PredictionRecord[], window = 20): { t: number; edge: number; hitRate: number; n: number }[] {
  const recs = resolved(records).sort((a, b) => a.outcome!.resolvedAt - b.outcome!.resolvedAt);
  const out: { t: number; edge: number; hitRate: number; n: number }[] = [];
  for (let i = 0; i < recs.length; i++) {
    const slice = recs.slice(Math.max(0, i - window + 1), i + 1);
    const rets = slice.map((r) => r.outcome!.dirReturn * 100);
    out.push({ t: recs[i].outcome!.resolvedAt, edge: mean(rets), hitRate: slice.filter((r) => r.outcome!.correct).length / slice.length, n: slice.length });
  }
  return out;
}

/** Split resolved history into older/newer halves and compare expectancy — edge-decay detection. */
export function edgeDecay(records: PredictionRecord[], minN = 12): DecayReport {
  const recs = resolved(records).sort((a, b) => a.outcome!.resolvedAt - b.outcome!.resolvedAt);
  if (recs.length < minN) return { baseline: null, recent: null, delta: null, decaying: false, n: recs.length };
  const mid = Math.floor(recs.length / 2);
  const baseline = mean(recs.slice(0, mid).map((r) => r.outcome!.dirReturn * 100));
  const recent = mean(recs.slice(mid).map((r) => r.outcome!.dirReturn * 100));
  const delta = recent - baseline;
  return { baseline, recent, delta, decaying: delta < -0.05 && recent < 0, n: recs.length };
}

/** Calibration: realised hit-rate within each predicted-confidence band, and the weighted error. */
export function calibration(records: PredictionRecord[]): { bins: CalBin[]; error: number | null } {
  const recs = resolved(records);
  if (!recs.length) return { bins: [], error: null };
  const bands = ["50–60", "60–70", "70–80", "80–100"];
  const bins: CalBin[] = [];
  let werr = 0;
  let wtot = 0;
  for (const band of bands) {
    const g = recs.filter((r) => confidenceBand(r.confidence) === band || (band === "80–100" && r.confidence >= 80));
    if (!g.length) continue;
    const predicted = mean(g.map((r) => r.confidence));
    const realized = (g.filter((r) => r.outcome!.correct).length / g.length) * 100;
    bins.push({ label: band, predicted, realized, n: g.length });
    werr += Math.abs(predicted - realized) * g.length;
    wtot += g.length;
  }
  return { bins, error: wtot ? werr / wtot / 100 : null };
}

const pearson = (xs: number[], ys: number[]): number => {
  const n = xs.length;
  if (n < 3) return 0;
  const mx = mean(xs);
  const my = mean(ys);
  let sxy = 0;
  let sxx = 0;
  let syy = 0;
  for (let i = 0; i < n; i++) {
    const dx = xs[i] - mx;
    const dy = ys[i] - my;
    sxy += dx * dy;
    sxx += dx * dx;
    syy += dy * dy;
  }
  return sxx > 0 && syy > 0 ? sxy / Math.sqrt(sxx * syy) : 0;
};

/** Association of each numeric feature with directional return (Pearson) — feature importance. */
export function featureImportance(records: PredictionRecord[], minN = 8): FeatureScore[] {
  const recs = resolved(records);
  if (recs.length < minN) return [];
  const keys = new Set<string>();
  for (const r of recs) for (const k of Object.keys(r.features)) keys.add(k);
  const ys = recs.map((r) => r.outcome!.dirReturn);
  const out: FeatureScore[] = [];
  for (const k of keys) {
    const xs = recs.map((r) => r.features[k] ?? 0);
    out.push({ feature: k, corr: pearson(xs, ys), n: recs.length });
  }
  return out.sort((a, b) => Math.abs(b.corr) - Math.abs(a.corr));
}

/** Feature drift: compare each feature's older vs recent mean across ALL records (z of the shift). */
export function featureDrift(records: PredictionRecord[], minN = 16): DriftScore[] {
  const recs = [...records].sort((a, b) => a.t - b.t);
  if (recs.length < minN) return [];
  const mid = Math.floor(recs.length / 2);
  const keys = new Set<string>();
  for (const r of recs) for (const k of Object.keys(r.features)) keys.add(k);
  const out: DriftScore[] = [];
  for (const k of keys) {
    const oldV = recs.slice(0, mid).map((r) => r.features[k] ?? 0);
    const newV = recs.slice(mid).map((r) => r.features[k] ?? 0);
    const pooled = Math.sqrt((std(oldV) ** 2) / oldV.length + (std(newV) ** 2) / newV.length);
    const z = pooled > 0 ? (mean(newV) - mean(oldV)) / pooled : 0;
    out.push({ feature: k, baseline: mean(oldV), recent: mean(newV), z, drifting: Math.abs(z) >= 2 });
  }
  return out.sort((a, b) => Math.abs(b.z) - Math.abs(a.z));
}

/** Overall health from rolling edge + decay: improving / stable / degrading / insufficient. */
export function healthState(records: PredictionRecord[], minN = 12): HealthState {
  const recs = resolved(records);
  if (recs.length < minN) return "insufficient";
  const d = edgeDecay(records, minN);
  if (d.delta == null) return "insufficient";
  if (d.delta > 0.05 && (d.recent ?? 0) > 0) return "improving";
  if (d.decaying) return "degrading";
  return "stable";
}
