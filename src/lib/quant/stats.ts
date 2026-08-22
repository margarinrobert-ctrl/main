import type { Bar, Instrument, Trade } from "./types";
import type { BacktestResult } from "./backtest";

// Performance statistics. Two deliberate choices worth knowing about:
//
//  * Sharpe is computed on the DAILY P&L STREAM, including days the strategy traded nothing.
//    Dropping flat days is the most common way an intraday Sharpe gets inflated 2-3x.
//  * The headline edge number is expectancy in TICKS, shown next to the round-turn cost in ticks.
//    For a scalp those two numbers decide everything; a strategy whose gross edge is 1.4 ticks
//    against a 2.5-tick cost is not a marginal strategy, it is arithmetically impossible.

export interface PerfSummary {
  trades: number;
  tradesPerDay: number;
  winRate: number;
  /** Mean net P&L per trade, USD, at the configured size. */
  expectancyUsd: number;
  /** Mean net P&L per trade in R (multiples of the initial stop risk). */
  expectancyR: number;
  /** Mean GROSS move captured per trade, in ticks — the raw edge before costs. */
  grossEdgeTicks: number;
  /** Round-turn cost charged per trade, in ticks. */
  costTicks: number;
  /** Mean NET P&L per trade in ticks: grossEdgeTicks - costTicks. */
  netEdgeTicks: number;
  profitFactor: number;
  payoffRatio: number;
  totalPnl: number;
  maxDrawdown: number;
  maxDrawdownPct: number;
  /** Annualised Sharpe of the daily P&L stream (flat days included). */
  sharpe: number;
  sortino: number;
  calmar: number;
  /** HAC (Newey-West) t-statistic of mean daily P&L against zero. */
  tStat: number;
  pValue: number;
  skew: number;
  kurtosis: number;
  avgBarsHeld: number;
  exposurePct: number;
  days: number;
  /** Gross edge in ticks needed for net expectancy to reach zero — the break-even cost. */
  breakEvenCostTicks: number;
}

export const mean = (x: number[]): number => (x.length ? x.reduce((s, v) => s + v, 0) / x.length : 0);

export function std(x: number[], sample = true): number {
  if (x.length < 2) return 0;
  const m = mean(x);
  const v = x.reduce((s, val) => s + (val - m) ** 2, 0) / (x.length - (sample ? 1 : 0));
  return Math.sqrt(Math.max(v, 0));
}

export function skewness(x: number[]): number {
  const n = x.length;
  if (n < 3) return 0;
  const m = mean(x);
  const s = std(x, false);
  if (s === 0) return 0;
  return x.reduce((acc, v) => acc + ((v - m) / s) ** 3, 0) / n;
}

/** Excess kurtosis (0 = Gaussian). */
export function kurtosis(x: number[]): number {
  const n = x.length;
  if (n < 4) return 0;
  const m = mean(x);
  const s = std(x, false);
  if (s === 0) return 0;
  return x.reduce((acc, v) => acc + ((v - m) / s) ** 4, 0) / n - 3;
}

/** Abramowitz & Stegun 7.1.26 error function — |error| < 1.5e-7. */
export function erf(x: number): number {
  const sign = x < 0 ? -1 : 1;
  const a = Math.abs(x);
  const t = 1 / (1 + 0.3275911 * a);
  const y = 1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-a * a);
  return sign * y;
}

export const normalCdf = (z: number): number => 0.5 * (1 + erf(z / Math.SQRT2));

/** Acklam's inverse normal CDF, refined once by Halley's method. */
export function normalInv(p: number): number {
  if (p <= 0) return -Infinity;
  if (p >= 1) return Infinity;
  const a = [-3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2, 1.38357751867269e2, -3.066479806614716e1, 2.506628277459239];
  const b = [-5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2, 6.680131188771972e1, -1.328068155288572e1];
  const c = [-7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783];
  const d = [7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996, 3.754408661907416];
  const pl = 0.02425;
  let x: number;
  if (p < pl) {
    const q = Math.sqrt(-2 * Math.log(p));
    x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  } else if (p <= 1 - pl) {
    const q = p - 0.5;
    const r = q * q;
    x = ((((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q) / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
  } else {
    const q = Math.sqrt(-2 * Math.log(1 - p));
    x = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  }
  const e = normalCdf(x) - p;
  const u = e * Math.sqrt(2 * Math.PI) * Math.exp((x * x) / 2);
  return x - u / (1 + (x * u) / 2);
}

/** Two-sided p-value of a t-statistic, normal approximation (n is large in every use here). */
export const pValueTwoSided = (t: number): number => 2 * (1 - normalCdf(Math.abs(t)));

/**
 * Newey-West HAC t-statistic for "is the mean of x different from zero?".
 * Intraday daily P&L is autocorrelated (vol clusters, regimes persist); the plain t-stat
 * over-states significance whenever it is, so HAC is the default here, not an option.
 */
export function neweyWestT(x: number[], lag?: number): { t: number; se: number; lag: number } {
  const n = x.length;
  if (n < 3) return { t: 0, se: 0, lag: 0 };
  const L = lag ?? Math.max(1, Math.floor(4 * (n / 100) ** (2 / 9)));
  const m = mean(x);
  const e = x.map((v) => v - m);
  let s = e.reduce((acc, v) => acc + v * v, 0) / n;
  for (let l = 1; l <= L; l++) {
    let cov = 0;
    for (let i = l; i < n; i++) cov += e[i] * e[i - l];
    cov /= n;
    s += 2 * (1 - l / (L + 1)) * cov;
  }
  const se = Math.sqrt(Math.max(s, 0) / n);
  return { t: se > 0 ? m / se : 0, se, lag: L };
}

export function maxDrawdown(equity: number[]): { abs: number; pct: number } {
  let peak = equity[0] ?? 0;
  let abs = 0;
  let pct = 0;
  for (const e of equity) {
    if (e > peak) peak = e;
    const dd = peak - e;
    if (dd > abs) abs = dd;
    if (peak > 0 && dd / peak > pct) pct = dd / peak;
  }
  return { abs, pct };
}

/** Sharpe of a per-period P&L (or return) stream, annualised by `periodsPerYear`. */
export function sharpeRatio(x: number[], periodsPerYear: number): number {
  const s = std(x);
  return s > 0 ? (mean(x) / s) * Math.sqrt(periodsPerYear) : 0;
}

export function sortinoRatio(x: number[], periodsPerYear: number): number {
  const downside = x.filter((v) => v < 0);
  if (!downside.length) return mean(x) > 0 ? Infinity : 0;
  const dd = Math.sqrt(mean(downside.map((v) => v * v)));
  return dd > 0 ? (mean(x) / dd) * Math.sqrt(periodsPerYear) : 0;
}

/**
 * Daily P&L over EVERY trading day present in `bars`, not just days with trades.
 * This is the series all significance testing runs on.
 */
export function dailySeries(result: BacktestResult, bars: Bar[]): number[] {
  const days = new Set<number>();
  for (const b of bars) days.add(Math.floor(b.t / 86_400_000));
  return [...days].sort((a, b) => a - b).map((d) => result.dailyPnl.get(d) ?? 0);
}

export function summarize(result: BacktestResult, bars: Bar[], inst: Instrument): PerfSummary {
  const t = result.trades;
  const daily = dailySeries(result, bars);
  const days = daily.length || 1;
  const pnls = t.map((x) => x.pnl);
  const wins = pnls.filter((p) => p > 0);
  const losses = pnls.filter((p) => p <= 0);
  const grossWin = wins.reduce((s, p) => s + p, 0);
  const grossLoss = -losses.reduce((s, p) => s + p, 0);
  const dd = maxDrawdown(result.equity);
  const nw = neweyWestT(daily);
  const perYear = inst.daysPerYear;
  const totalPnl = pnls.reduce((s, p) => s + p, 0);
  const years = days / perYear;
  const cagrLike = years > 0 ? totalPnl / years : 0;
  const grossTicks = t.length ? mean(t.map((x) => (x.side * (x.exitPx - x.entryPx)) / inst.tickSize)) : 0;
  // Under the `realistic` and `passive` fill models the cost charged depends on how each trade
  // exited (a target rests, a stop takes liquidity), so the reported figure is the realised mean.
  const costTicks = t.length ? mean(t.map((x) => x.costPoints)) / inst.tickSize : result.costPoints / inst.tickSize;
  const barsHeld = t.reduce((s, x) => s + x.barsHeld, 0);

  return {
    trades: t.length,
    tradesPerDay: t.length / days,
    winRate: t.length ? wins.length / t.length : 0,
    expectancyUsd: mean(pnls),
    expectancyR: mean(t.map((x) => x.r)),
    grossEdgeTicks: grossTicks,
    costTicks,
    netEdgeTicks: grossTicks - costTicks,
    profitFactor: grossLoss > 0 ? grossWin / grossLoss : grossWin > 0 ? Infinity : 0,
    payoffRatio: losses.length && wins.length ? mean(wins) / Math.abs(mean(losses)) : 0,
    totalPnl,
    maxDrawdown: dd.abs,
    maxDrawdownPct: dd.pct,
    sharpe: sharpeRatio(daily, perYear),
    sortino: sortinoRatio(daily, perYear),
    calmar: dd.abs > 0 ? cagrLike / dd.abs : 0,
    tStat: nw.t,
    pValue: pValueTwoSided(nw.t),
    skew: skewness(daily),
    kurtosis: kurtosis(daily),
    avgBarsHeld: t.length ? barsHeld / t.length : 0,
    exposurePct: result.bars > 0 ? barsHeld / result.bars : 0,
    days,
    breakEvenCostTicks: grossTicks,
  };
}

/** Per-trade R multiples — the unit most robustness tests resample. */
export const rMultiples = (trades: Trade[]): number[] => trades.map((t) => t.r);
