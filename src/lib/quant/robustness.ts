import { runBacktest, type BacktestConfig } from "./backtest";
import { roundTurnCostPoints } from "./instruments";
import { atr } from "./series";
import { mean, summarize, type PerfSummary } from "./stats";
import type { Bar, Params, Strategy, Trade } from "./types";

// Robustness probes. Each one is designed to FAIL a strategy that only worked by accident, and each
// maps to a specific way scalping research goes wrong in production.

export interface CostPoint {
  multiple: number;
  costTicks: number;
  expectancyUsd: number;
  sharpe: number;
  profitFactor: number;
  trades: number;
}

export interface CostSensitivity {
  points: CostPoint[];
  /** Cost multiple at which expectancy crosses zero (linear interpolation). */
  breakEvenMultiple: number;
  /** Round-turn cost in ticks the strategy could absorb before dying. */
  breakEvenCostTicks: number;
  /** Cost assumed in the base study, in ticks. */
  baseCostTicks: number;
  /** breakEvenCostTicks / baseCostTicks — under ~1.5 the result is a cost-assumption artefact. */
  margin: number;
}

/**
 * Sweep the round-turn cost and find where the edge dies.
 *
 * For a 5-minute scalp this is the most decision-relevant chart in the study. A strategy that only
 * survives at exactly the modelled spread is not a strategy — real spreads widen on the news prints
 * that generate most of the signals, so the safety margin has to be big enough to absorb that.
 */
export function costSensitivity(
  strategy: Strategy,
  bars: Bar[],
  params: Params,
  cfg: BacktestConfig,
  multiples: number[] = [0, 0.5, 1, 1.5, 2, 3],
): CostSensitivity {
  const base = roundTurnCostPoints(cfg.inst);
  const signal = strategy.build(bars, params, cfg.inst);
  const points: CostPoint[] = multiples.map((m) => {
    const res = runBacktest(bars, signal, { ...cfg, costPointsOverride: base * m });
    const s = summarize(res, bars, cfg.inst);
    return { multiple: m, costTicks: (base * m) / cfg.inst.tickSize, expectancyUsd: s.expectancyUsd, sharpe: s.sharpe, profitFactor: s.profitFactor, trades: s.trades };
  });

  let breakEven = Infinity;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1];
    const b = points[i];
    if (a.expectancyUsd > 0 && b.expectancyUsd <= 0) {
      const w = a.expectancyUsd / (a.expectancyUsd - b.expectancyUsd);
      breakEven = a.multiple + w * (b.multiple - a.multiple);
      break;
    }
  }
  if (points[0].expectancyUsd <= 0) breakEven = 0;

  const baseTicks = base / cfg.inst.tickSize;
  return {
    points,
    breakEvenMultiple: breakEven,
    breakEvenCostTicks: breakEven === Infinity ? Infinity : breakEven * baseTicks,
    baseCostTicks: baseTicks,
    margin: breakEven,
  };
}

export interface Bucket {
  key: string;
  trades: number;
  pnl: number;
  expectancy: number;
  winRate: number;
}

const bucketise = (trades: Trade[], keyOf: (t: Trade) => string): Bucket[] => {
  const map = new Map<string, Trade[]>();
  for (const t of trades) {
    const k = keyOf(t);
    const arr = map.get(k);
    if (arr) arr.push(t);
    else map.set(k, [t]);
  }
  return [...map.entries()]
    .map(([key, ts]) => ({
      key,
      trades: ts.length,
      pnl: ts.reduce((s, t) => s + t.pnl, 0),
      expectancy: mean(ts.map((t) => t.pnl)),
      winRate: ts.filter((t) => t.pnl > 0).length / ts.length,
    }))
    .sort((a, b) => a.key.localeCompare(b.key));
};

export interface RegimeBreakdown {
  byYear: Bucket[];
  byMonth: Bucket[];
  byHourUtc: Bucket[];
  byWeekday: Bucket[];
  byVolTercile: Bucket[];
  byExitReason: Bucket[];
  /** Share of the total P&L delivered by the single best year — concentration risk. */
  bestYearShare: number;
  /** Share of hours-of-day that are net profitable. */
  profitableHourShare: number;
  /** Share of calendar years that are net profitable. */
  profitableYearShare: number;
}

/**
 * Slice the trade list every way that can expose a fake edge: one lucky year, one lucky hour, one
 * volatility regime, or a P&L profile that is really just "the time stop rarely fires".
 */
export function regimeBreakdown(trades: Trade[], bars: Bar[]): RegimeBreakdown {
  const a = atr(bars, 14);
  const finite = a.filter(Number.isFinite).sort((x, y) => x - y);
  const q1 = finite[Math.floor(finite.length / 3)] ?? 0;
  const q2 = finite[Math.floor((2 * finite.length) / 3)] ?? 0;

  const byYear = bucketise(trades, (t) => String(new Date(t.entryTime).getUTCFullYear()));
  const byHourUtc = bucketise(trades, (t) => String(new Date(t.entryTime).getUTCHours()).padStart(2, "0"));
  const total = trades.reduce((s, t) => s + t.pnl, 0);
  const bestYear = Math.max(0, ...byYear.map((b) => b.pnl));

  return {
    byYear,
    byMonth: bucketise(trades, (t) => new Date(t.entryTime).toISOString().slice(0, 7)),
    byHourUtc,
    byWeekday: bucketise(trades, (t) => ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][new Date(t.entryTime).getUTCDay()]),
    byVolTercile: bucketise(trades, (t) => {
      const v = a[t.entryIndex];
      if (!Number.isFinite(v)) return "unknown";
      return v <= q1 ? "1-low" : v <= q2 ? "2-mid" : "3-high";
    }),
    byExitReason: bucketise(trades, (t) => t.reason),
    bestYearShare: total > 0 ? bestYear / total : 0,
    profitableHourShare: byHourUtc.length ? byHourUtc.filter((b) => b.pnl > 0).length / byHourUtc.length : 0,
    profitableYearShare: byYear.length ? byYear.filter((b) => b.pnl > 0).length / byYear.length : 0,
  };
}

export interface SubPeriodConsistency {
  chunks: { index: number; pnl: number; trades: number; sharpeLike: number }[];
  profitableShare: number;
  worstChunkPnl: number;
}

/** Chop the sample into equal chronological chunks: a real edge shows up in most of them. */
export function subPeriodConsistency(trades: Trade[], chunks = 6): SubPeriodConsistency {
  if (!trades.length) return { chunks: [], profitableShare: 0, worstChunkPnl: 0 };
  const sorted = [...trades].sort((a, b) => a.entryTime - b.entryTime);
  const size = Math.ceil(sorted.length / chunks);
  const out = [] as SubPeriodConsistency["chunks"];
  for (let i = 0; i < chunks; i++) {
    const slice = sorted.slice(i * size, (i + 1) * size);
    if (!slice.length) continue;
    const pnls = slice.map((t) => t.pnl);
    const m = mean(pnls);
    const sd = Math.sqrt(mean(pnls.map((p) => (p - m) ** 2)));
    out.push({ index: i, pnl: pnls.reduce((s, p) => s + p, 0), trades: slice.length, sharpeLike: sd > 0 ? m / sd : 0 });
  }
  return {
    chunks: out,
    profitableShare: out.length ? out.filter((c) => c.pnl > 0).length / out.length : 0,
    worstChunkPnl: Math.min(...out.map((c) => c.pnl)),
  };
}

export interface RobustnessVerdict {
  passes: string[];
  failures: string[];
  score: number;
  tradeable: boolean;
}

/**
 * Collapse the probes into a single go / no-go. The thresholds are deliberately harsh: at scalping
 * horizons the null hypothesis "there is no edge here" is right the overwhelming majority of the
 * time, so the burden of proof sits with the strategy.
 */
export function verdict(input: {
  oos: PerfSummary;
  pbo: number;
  dsr: number;
  costMargin: number;
  plateau: string;
  consistency: number;
  bestYearShare: number;
  wfEfficiency: number;
}): RobustnessVerdict {
  const passes: string[] = [];
  const failures: string[] = [];
  const check = (ok: boolean, msg: string) => (ok ? passes.push(msg) : failures.push(msg));

  check(input.oos.trades >= 100, `>=100 out-of-sample trades (${input.oos.trades})`);
  check(input.oos.netEdgeTicks > 0, `positive net edge after costs (${input.oos.netEdgeTicks.toFixed(2)} ticks)`);
  check(input.oos.tStat > 2, `HAC t-stat > 2 (${input.oos.tStat.toFixed(2)})`);
  check(input.dsr > 0.95, `deflated Sharpe > 0.95 (${input.dsr.toFixed(3)})`);
  check(input.pbo < 0.3, `PBO < 0.30 (${input.pbo.toFixed(2)})`);
  check(input.costMargin >= 1.5, `survives >=1.5x modelled costs (${Number.isFinite(input.costMargin) ? input.costMargin.toFixed(2) : "inf"}x)`);
  check(input.plateau !== "spike", `parameter surface is not a mined spike (${input.plateau})`);
  check(input.consistency >= 0.6, `profitable in >=60% of sub-periods (${(input.consistency * 100).toFixed(0)}%)`);
  check(input.bestYearShare <= 0.6, `no single year carries >60% of P&L (${(input.bestYearShare * 100).toFixed(0)}%)`);
  check(input.wfEfficiency >= 0.4, `walk-forward efficiency >=0.4 (${input.wfEfficiency.toFixed(2)})`);

  const score = passes.length / (passes.length + failures.length);
  return { passes, failures, score, tradeable: failures.length === 0 };
}
