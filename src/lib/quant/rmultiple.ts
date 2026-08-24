import { mulberry32 } from "./rng";
import { normalCdf } from "./stats";

/**
 * Trade-level validation in R-space (Viaggi, "A Standardized R-Multiple Framework for the
 * Statistical Validation of Trading Edge in Retail Trading Systems").
 *
 * Sharpe-based inference works on a return series. A retail system is usually specified at the
 * TRADE level — fixed stop, fixed target, outcomes recorded in multiples of initial risk — so the
 * unit the strategy is designed in is not the unit it gets judged in. This module closes that gap.
 *
 * The model: each trade pays +b with probability p, or -1 with probability 1-p.
 *
 *   expectancy          e  = p*b - (1-p)
 *   break-even win rate p0 = 1 / (b + 1)
 *   NULL VARIANCE       Var(X) = b            <-- the result the whole framework turns on
 *
 * That last line is the paper's real contribution and it is counter-intuitive. Raising the reward
 * multiple lowers the win rate you need, which feels like it makes the system easier. It also
 * raises the variance of the trade process one-for-one, so the evidence needed to prove an edge
 * grows at the same rate. A high reward-to-risk ratio makes a strategy easier to justify
 * arithmetically and HARDER to validate statistically. Those are not the same thing, and
 * conflating them is one of the most common ways a retail backtest is over-read.
 */

/** Win rate at which a +b / -1 system exactly breaks even. */
export function breakEvenWinRate(b: number): number {
  if (!(b > 0)) throw new Error(`reward multiple must be positive, got ${b}`);
  return 1 / (b + 1);
}

/** Variance of a single trade under the zero-edge null. Equals the reward multiple exactly. */
export function nullVariance(b: number): number {
  if (!(b > 0)) throw new Error(`reward multiple must be positive, got ${b}`);
  return b;
}

/** Expectancy per trade for a given win rate and reward multiple. */
export function expectancy(p: number, b: number): number {
  return p * b - (1 - p);
}

/** Standard normal quantile (Acklam's rational approximation, ~1e-9 absolute). */
export function normalQuantile(p: number): number {
  if (!(p > 0 && p < 1)) throw new Error(`quantile needs 0 < p < 1, got ${p}`);
  const a = [-3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2, 1.38357751867269e2, -3.066479806614716e1, 2.506628277459239];
  const b = [-5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2, 6.680131188771972e1, -1.328068155288572e1];
  const c = [-7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783];
  const d = [7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996, 3.754408661907416];
  const pl = 0.02425;
  let q: number, r: number;
  if (p < pl) {
    q = Math.sqrt(-2 * Math.log(p));
    return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  }
  if (p > 1 - pl) {
    q = Math.sqrt(-2 * Math.log(1 - p));
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  }
  q = p - 0.5;
  r = q * q;
  return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
}

/**
 * Cumulative R a system must exceed after n trades to be significant at `alpha`, one-sided.
 * Grows with SQRT(n) and with SQRT(b) — the second term is what punishes high reward multiples.
 */
export function criticalCumulativeR(n: number, b: number, alpha = 0.05): number {
  return normalQuantile(1 - alpha) * Math.sqrt(n * nullVariance(b));
}

/** The standardized endpoint statistic Z = S_n / sqrt(n*b), and its one-sided p-value. */
export function zStatistic(cumulativeR: number, n: number, b: number): { z: number; p: number } {
  const z = cumulativeR / Math.sqrt(n * nullVariance(b));
  return { z, p: 1 - normalCdf(z) };
}

/**
 * Minimum trade record length: how many trades before an edge of size `e` becomes detectable.
 * Linear in the reward multiple, QUADRATIC in the reciprocal of the edge — small edges need very
 * long records, and raising the reward multiple lengthens the requirement rather than shortening it.
 */
export function minTrackRecordLength(b: number, e: number, alpha = 0.05): number {
  if (!(e > 0)) return Infinity;
  const z = normalQuantile(1 - alpha);
  return (z * z * nullVariance(b)) / (e * e);
}

/**
 * Expected maximum of K independent standard normals — the post-selection adjustment.
 * Same expression the Deflated Sharpe Ratio uses, because it is the same problem: when the
 * reported system is the best of K tried, the threshold it must clear is the one for a maximum,
 * not for a single draw.
 */
export function expectedMaxZ(trials: number): number {
  const K = Math.max(1, Math.floor(trials));
  if (K === 1) return 0;
  const EULER = 0.5772156649015329;
  return (1 - EULER) * normalQuantile(1 - 1 / K) + EULER * normalQuantile(1 - 1 / (K * Math.E));
}

/** Cumulative R required when the reported system is the best of `trials` candidates. */
export function postSelectionCriticalR(n: number, b: number, trials: number, alpha = 0.05): number {
  const z = normalQuantile(1 - alpha) + expectedMaxZ(trials);
  return z * Math.sqrt(n * nullVariance(b));
}

export interface PathBenchmarks {
  /** Deepest peak-to-trough decline of the cumulative-R curve, in R. */
  maxDrawdown: { p50: number; p95: number };
  /** Lowest point the cumulative-R curve reaches. */
  equityMAE: { p50: number; p95: number };
  /** Highest point it reaches. */
  equityMFE: { p50: number; p95: number };
  /** Longest run of consecutive losses. */
  longestLosingStreak: { p50: number; p95: number };
}

/**
 * What a ZERO-EDGE system's equity path looks like anyway.
 *
 * The practical point: a long losing streak or an ugly drawdown is not evidence the system broke,
 * and a smooth run of profit is not evidence it works. Both occur with no edge at all, and both
 * get more dramatic as n and b grow. Numbers are only interpretable against this benchmark.
 */
export function pathBenchmarks(n: number, b: number, paths = 20_000, seed = 7): PathBenchmarks {
  const rnd = mulberry32(seed);
  const p0 = breakEvenWinRate(b);
  const mdd: number[] = [], mae: number[] = [], mfe: number[] = [], lls: number[] = [];
  for (let k = 0; k < paths; k++) {
    let eq = 0, peak = 0, dd = 0, lo = 0, hi = 0, run = 0, maxRun = 0;
    for (let i = 0; i < n; i++) {
      const win = rnd() < p0;
      eq += win ? b : -1;
      if (win) run = 0;
      else if (++run > maxRun) maxRun = run;
      if (eq > peak) peak = eq;
      if (peak - eq > dd) dd = peak - eq;
      if (eq < lo) lo = eq;
      if (eq > hi) hi = eq;
    }
    mdd.push(dd); mae.push(lo); mfe.push(hi); lls.push(maxRun);
  }
  const q = (xs: number[], f: number) => {
    const v = xs.slice().sort((x, y) => x - y);
    return v[Math.min(v.length - 1, Math.max(0, Math.floor(f * v.length)))];
  };
  return {
    maxDrawdown: { p50: q(mdd, 0.5), p95: q(mdd, 0.95) },
    // MAE is a low-side quantity, so its "bad" tail is the 5th percentile of the distribution.
    equityMAE: { p50: q(mae, 0.5), p95: q(mae, 0.05) },
    equityMFE: { p50: q(mfe, 0.5), p95: q(mfe, 0.95) },
    longestLosingStreak: { p50: q(lls, 0.5), p95: q(lls, 0.95) },
  };
}

export interface RVerdict {
  n: number;
  cumulativeR: number;
  expectancy: number;
  winRate: number;
  /** Reward multiple implied by the realised wins — the b the framework should be applied with. */
  impliedB: number;
  breakEven: number;
  /** Variance the null model PREDICTS (= b) against the variance actually observed. */
  nullVar: number;
  observedVar: number;
  z: number;
  p: number;
  criticalR: number;
  significant: boolean;
  minTrades: number;
  postSelectionCriticalR: number;
  survivesSelection: boolean;
}

/**
 * Run a real trade record through the framework.
 *
 * `trials` is how many configurations were examined before this one was reported. Passing 1 claims
 * the system was pre-specified; if it was chosen from a search, saying so is the entire point of
 * the post-selection column.
 *
 * `observedVar` is reported next to `nullVar` deliberately. The framework assumes a clean binary
 * +b/-1 payoff, and real records are not that — partial exits, session flats and gap-throughs all
 * put mass between the two outcomes. When the two variances disagree, the analytic thresholds are
 * being applied to a process the model does not describe, and the empirical one should be trusted.
 */
export function validateRRecord(rs: number[], trials = 1, alpha = 0.05): RVerdict {
  const n = rs.length;
  if (n === 0) throw new Error("no trades to validate");
  const wins = rs.filter((r) => r > 0);
  const winRate = wins.length / n;
  const cumulativeR = rs.reduce((a, r) => a + r, 0);
  const e = cumulativeR / n;
  // Take b from the realised average win rather than from the nominal target: a record full of
  // session flats and partial exits has a different effective payoff than the order ticket implies.
  const impliedB = wins.length ? wins.reduce((a, r) => a + r, 0) / wins.length : 1;
  const mu = e;
  const observedVar = n > 1 ? rs.reduce((a, r) => a + (r - mu) ** 2, 0) / (n - 1) : 0;
  const { z, p } = zStatistic(cumulativeR, n, impliedB);
  const criticalR = criticalCumulativeR(n, impliedB, alpha);
  const psCritical = postSelectionCriticalR(n, impliedB, trials, alpha);
  return {
    n,
    cumulativeR,
    expectancy: e,
    winRate,
    impliedB,
    breakEven: breakEvenWinRate(impliedB),
    nullVar: nullVariance(impliedB),
    observedVar,
    z,
    p,
    criticalR,
    significant: cumulativeR > criticalR,
    minTrades: minTrackRecordLength(impliedB, e, alpha),
    postSelectionCriticalR: psCritical,
    survivesSelection: cumulativeR > psCritical,
  };
}
