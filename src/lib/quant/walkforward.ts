import { runBacktest, type BacktestConfig } from "./backtest";
import { clockFor } from "./clock";
import { gridSearch, objectiveValue, type ObjectiveName, type OptimOptions } from "./optimize";
import { dailySeries, summarize, type PerfSummary } from "./stats";
import type { Bar, Params, Strategy, Trade } from "./types";

// Walk-forward analysis: the only backtest number worth quoting.
//
// Each fold re-optimises on a training window and then trades the NEXT, unseen window with those
// parameters and never touches it again. Stitching the test windows together gives an out-of-sample
// equity curve that includes the cost of having to choose parameters — which a single in-sample
// optimisation hides completely.

export interface WalkForwardOptions extends OptimOptions {
  /** Training window length in bars. */
  trainBars: number;
  /** Test window length in bars (also the step size). */
  testBars: number;
  /** Anchored keeps every past bar in the training set; rolling uses a fixed-length window. */
  mode?: "rolling" | "anchored";
}

export interface Fold {
  index: number;
  trainRange: [number, number];
  testRange: [number, number];
  params: Params;
  inSampleObjective: number;
  outOfSampleObjective: number;
  trades: number;
  oosPnl: number;
}

export interface WalkForwardResult {
  strategyId: string;
  folds: Fold[];
  /** Summary of the stitched out-of-sample trades only. */
  oos: PerfSummary;
  /** Daily OOS P&L, aligned to the test windows — the input to significance testing. */
  oosDaily: number[];
  /** Every stitched out-of-sample trade, indices remapped onto the full series. */
  oosTrades: Trade[];
  /** OOS P&L keyed by session day — the stream the portfolio layer combines. */
  oosDailyPnl: Map<number, number>;
  /** Bar range the stitched out-of-sample record covers. */
  oosRange: [number, number];
  /** Median OOS objective / median IS objective. Below ~0.5 means the fit does not transfer. */
  efficiency: number;
  /** Share of folds with a positive OOS objective. */
  foldHitRate: number;
  /** Per-parameter share of folds that agreed with the modal choice — parameter stability. */
  paramStability: Record<string, number>;
  totalTrials: number;
}

export function walkForward(strategy: Strategy, bars: Bar[], cfg: BacktestConfig, opts: WalkForwardOptions): WalkForwardResult {
  const objective: ObjectiveName = opts.objective ?? "sharpe";
  const mode = opts.mode ?? "rolling";
  const folds: Fold[] = [];
  const oosTrades: Trade[] = [];
  const oosDaily: number[] = [];
  let totalTrials = 0;
  let equity = cfg.startEquity ?? 100_000;
  const stitchedEquity: number[] = [equity];
  const dailyPnl = new Map<number, number>();

  let start = 0;
  let idx = 0;
  while (start + opts.trainBars + opts.testBars <= bars.length) {
    const trainStart = mode === "anchored" ? 0 : start;
    const trainEnd = start + opts.trainBars;
    const testEnd = Math.min(trainEnd + opts.testBars, bars.length);
    const train = bars.slice(trainStart, trainEnd);
    const test = bars.slice(trainEnd, testEnd);

    const search = gridSearch(strategy, train, cfg, { ...opts, objective });
    totalTrials += search.trialCount;
    const params = search.best.params;

    const res = runBacktest(test, strategy.build(test, params, cfg.inst), cfg);
    const s = summarize(res, test, cfg.inst);
    for (const d of dailySeries(res, test)) oosDaily.push(d);
    const foldClock = clockFor(test, cfg.inst.tz);
    for (const t of res.trades) {
      oosTrades.push({ ...t, entryIndex: t.entryIndex + trainEnd, exitIndex: t.exitIndex + trainEnd });
      equity += t.pnl;
      stitchedEquity.push(equity);
      const day = foldClock.dayIndex[t.exitIndex];
      dailyPnl.set(day, (dailyPnl.get(day) ?? 0) + t.pnl);
    }

    folds.push({
      index: idx++,
      trainRange: [trainStart, trainEnd],
      testRange: [trainEnd, testEnd],
      params,
      inSampleObjective: search.best.objective,
      outOfSampleObjective: objectiveValue(objective, s),
      trades: s.trades,
      oosPnl: s.totalPnl,
    });
    start += opts.testBars;
  }

  const testBarsAll = folds.length ? bars.slice(folds[0].testRange[0], folds[folds.length - 1].testRange[1]) : [];
  const oos = summarize(
    { trades: oosTrades, equity: stitchedEquity, dailyPnl, costPoints: 0, bars: testBarsAll.length, config: cfg, ambiguousExits: 0 },
    testBarsAll,
    cfg.inst,
  );
  // costPoints is per-trade bookkeeping from the fold runs; restate it for the stitched summary.
  oos.costTicks = oosTrades.length ? oosTrades[0].costPoints / cfg.inst.tickSize : 0;
  oos.netEdgeTicks = oos.grossEdgeTicks - oos.costTicks;

  const med = (xs: number[]) => {
    const v = xs.filter(Number.isFinite).sort((a, b) => a - b);
    return v.length ? v[Math.floor(v.length / 2)] : 0;
  };
  const isMed = med(folds.map((f) => f.inSampleObjective));
  const oosMed = med(folds.map((f) => f.outOfSampleObjective));

  const paramStability: Record<string, number> = {};
  for (const k of Object.keys(strategy.space)) {
    const counts = new Map<number, number>();
    for (const f of folds) counts.set(f.params[k], (counts.get(f.params[k]) ?? 0) + 1);
    const top = Math.max(0, ...counts.values());
    paramStability[k] = folds.length ? top / folds.length : 0;
  }

  return {
    strategyId: strategy.id,
    folds,
    oos,
    oosDaily,
    oosTrades,
    oosDailyPnl: dailyPnl,
    oosRange: folds.length ? [folds[0].testRange[0], folds[folds.length - 1].testRange[1]] : [0, 0],
    // A ratio against a non-positive in-sample median is not an efficiency, it is a sign artefact.
    efficiency: isMed > 0 ? oosMed / isMed : NaN,
    foldHitRate: folds.length ? folds.filter((f) => f.outOfSampleObjective > 0).length / folds.length : 0,
    paramStability,
    totalTrials,
  };
}
