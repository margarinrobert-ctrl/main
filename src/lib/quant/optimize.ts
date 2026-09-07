import { runBacktest, type BacktestConfig, type BacktestResult } from "./backtest";
import { mulberry32 } from "./rng";
import { dailySeries, sharpeRatio, summarize, type PerfSummary } from "./stats";
import type { Bar, Params, ParamSpace, Strategy } from "./types";

// Parameter search, and — more importantly — parameter-surface DIAGNOSIS.
//
// The optimiser's output is not "the best parameters". It is evidence about the shape of the
// objective surface. A single tall spike surrounded by losses is noise that has been mined; a broad
// plateau where the neighbours score nearly as well is a candidate for a real effect. Every search
// here therefore reports the neighbourhood behaviour of its winner, and the number of trials, which
// is what the Deflated Sharpe stage needs to price the search itself.

export type ObjectiveName = "sharpe" | "expectancyR" | "netEdgeTicks" | "profitFactor" | "totalPnl";

export interface OptimOptions {
  objective?: ObjectiveName;
  /** Configurations scoring below this trade count are rejected outright. */
  minTrades?: number;
  /** Cap on evaluated combinations; larger grids are sub-sampled deterministically. */
  maxCombos?: number;
  seed?: number;
}

export interface Trial {
  params: Params;
  summary: PerfSummary;
  objective: number;
  /** Per-period (daily) Sharpe, un-annualised — the unit the Deflated Sharpe stage consumes. */
  dailySharpe: number;
}

export function expandGrid(space: ParamSpace, maxCombos = 4000, seed = 42): Params[] {
  const keys = Object.keys(space);
  let total = 1;
  for (const k of keys) total *= space[k].values.length;

  const build = (n: number): Params => {
    const p: Params = {};
    let rem = n;
    for (const k of keys) {
      const vals = space[k].values;
      p[k] = vals[rem % vals.length];
      rem = Math.floor(rem / vals.length);
    }
    return p;
  };

  if (total <= maxCombos) return Array.from({ length: total }, (_, n) => build(n));

  // Deterministic sub-sample of a grid too large to enumerate. Reported as `trials` so the
  // deflation stage still knows how wide the search really was.
  const rand = mulberry32(seed);
  const seen = new Set<number>();
  const out: Params[] = [];
  while (out.length < maxCombos) {
    const n = Math.floor(rand() * total);
    if (seen.has(n)) continue;
    seen.add(n);
    out.push(build(n));
  }
  return out;
}

export function objectiveValue(name: ObjectiveName, s: PerfSummary): number {
  switch (name) {
    case "expectancyR":
      return s.expectancyR;
    case "netEdgeTicks":
      return s.netEdgeTicks;
    case "profitFactor":
      return Number.isFinite(s.profitFactor) ? s.profitFactor : 0;
    case "totalPnl":
      return s.totalPnl;
    default:
      return s.sharpe;
  }
}

export function evaluate(strategy: Strategy, bars: Bar[], params: Params, cfg: BacktestConfig, opts: OptimOptions = {}): Trial {
  const res: BacktestResult = runBacktest(bars, strategy.build(bars, params, cfg.inst), cfg);
  const summary = summarize(res, bars, cfg.inst);
  const minTrades = opts.minTrades ?? 30;
  const raw = objectiveValue(opts.objective ?? "sharpe", summary);
  return {
    params,
    summary,
    objective: summary.trades < minTrades ? -Infinity : raw,
    dailySharpe: sharpeRatio(dailySeries(res, bars), 1),
  };
}

export interface SearchResult {
  strategyId: string;
  trials: Trial[];
  best: Trial;
  /** Every trial evaluated — the honest N for Deflated Sharpe, including rejected ones. */
  trialCount: number;
}

export function gridSearch(strategy: Strategy, bars: Bar[], cfg: BacktestConfig, opts: OptimOptions = {}): SearchResult {
  const grid = expandGrid(strategy.space, opts.maxCombos ?? 600, opts.seed ?? 42);
  const trials = grid.map((p) => evaluate(strategy, bars, p, cfg, opts));
  const ranked = [...trials].sort((a, b) => b.objective - a.objective);
  return { strategyId: strategy.id, trials, best: ranked[0], trialCount: trials.length };
}

export interface PlateauReport {
  bestObjective: number;
  /** Median objective of the winner's one-step grid neighbours. */
  neighbourMedian: number;
  /** neighbourMedian / bestObjective — near 1 is a plateau, near 0 (or negative) is a mined spike. */
  stability: number;
  /** Share of neighbours that stay profitable on the objective. */
  neighbourHitRate: number;
  neighbours: number;
  verdict: "plateau" | "ridge" | "spike";
}

/**
 * Neighbourhood analysis of the winning parameter set: perturb each parameter one grid step in each
 * direction and see whether the result survives. This is the cheapest, most reliable overfit
 * detector in the whole toolkit — a strategy whose edge evaporates when a lookback moves from 20 to
 * 21 never had one.
 */
export function plateauReport(search: SearchResult, space: ParamSpace): PlateauReport {
  const best = search.best;
  const key = (p: Params) => Object.keys(space).map((k) => `${k}=${p[k]}`).join("|");
  const byKey = new Map(search.trials.map((t) => [key(t.params), t]));

  const neighbourScores: number[] = [];
  for (const k of Object.keys(space)) {
    const vals = space[k].values;
    const idx = vals.indexOf(best.params[k]);
    for (const step of [-1, 1]) {
      const j = idx + step;
      if (j < 0 || j >= vals.length) continue;
      const probe = { ...best.params, [k]: vals[j] };
      const t = byKey.get(key(probe));
      if (t && Number.isFinite(t.objective)) neighbourScores.push(t.objective);
    }
  }

  if (!neighbourScores.length) {
    return { bestObjective: best.objective, neighbourMedian: NaN, stability: NaN, neighbourHitRate: NaN, neighbours: 0, verdict: "spike" };
  }
  const sorted = [...neighbourScores].sort((a, b) => a - b);
  const median = sorted[Math.floor(sorted.length / 2)];
  const stability = best.objective !== 0 ? median / best.objective : 0;
  const hit = neighbourScores.filter((v) => v > 0).length / neighbourScores.length;
  const verdict: PlateauReport["verdict"] = stability >= 0.6 && hit >= 0.8 ? "plateau" : stability >= 0.3 && hit >= 0.5 ? "ridge" : "spike";
  return { bestObjective: best.objective, neighbourMedian: median, stability, neighbourHitRate: hit, neighbours: neighbourScores.length, verdict };
}
