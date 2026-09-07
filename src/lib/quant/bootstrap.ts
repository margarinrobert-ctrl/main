import { mulberry32 } from "./rng";
import { mean, neweyWestT, sharpeRatio } from "./stats";

// Resampling inference for dependent series.
//
// Trading P&L is not i.i.d. — volatility clusters and regimes persist — so the naive bootstrap
// understates uncertainty. Everything here uses the STATIONARY BOOTSTRAP of Politis & Romano (1994):
// resample geometric-length blocks (mean length b) with wrap-around, which preserves short-range
// dependence while keeping the resampled series stationary.

/** One stationary-bootstrap index path over 0..n-1. */
export function stationaryIndices(n: number, meanBlock: number, rand: () => number): number[] {
  const idx = new Array<number>(n);
  const p = 1 / Math.max(meanBlock, 1);
  let cur = Math.floor(rand() * n) % n;
  for (let i = 0; i < n; i++) {
    if (i > 0) cur = rand() < p ? Math.floor(rand() * n) % n : (cur + 1) % n;
    idx[i] = cur;
  }
  return idx;
}

/** Rule-of-thumb block length for a daily P&L series: n^(1/3), floored at 2. */
export const blockLength = (n: number): number => Math.max(2, Math.round(Math.cbrt(n)));

export interface BootstrapCI {
  point: number;
  lower: number;
  upper: number;
  /** Share of resamples where the statistic came out <= 0 — a one-sided bootstrap p-value. */
  pLessEqualZero: number;
  samples: number;
}

/** Percentile-bootstrap confidence interval for any statistic of a dependent series. */
export function bootstrapCI(
  x: number[],
  stat: (s: number[]) => number,
  opts: { samples?: number; alpha?: number; seed?: number; block?: number } = {},
): BootstrapCI {
  const B = opts.samples ?? 2000;
  const alpha = opts.alpha ?? 0.05;
  const rand = mulberry32(opts.seed ?? 12345);
  const b = opts.block ?? blockLength(x.length);
  const point = stat(x);
  const draws: number[] = [];
  let nonPositive = 0;
  for (let j = 0; j < B; j++) {
    const idx = stationaryIndices(x.length, b, rand);
    const s = stat(idx.map((i) => x[i]));
    if (Number.isFinite(s)) {
      draws.push(s);
      if (s <= 0) nonPositive++;
    }
  }
  draws.sort((p, q) => p - q);
  const at = (q: number) => draws[Math.min(draws.length - 1, Math.max(0, Math.floor(q * (draws.length - 1))))] ?? NaN;
  return {
    point,
    lower: at(alpha / 2),
    upper: at(1 - alpha / 2),
    pLessEqualZero: draws.length ? nonPositive / draws.length : 1,
    samples: draws.length,
  };
}

export const bootstrapSharpe = (daily: number[], perYear: number, opts?: Parameters<typeof bootstrapCI>[2]): BootstrapCI =>
  bootstrapCI(daily, (s) => sharpeRatio(s, perYear), opts);

export const bootstrapMean = (x: number[], opts?: Parameters<typeof bootstrapCI>[2]): BootstrapCI => bootstrapCI(x, mean, opts);

export interface RealityCheckResult {
  /** Best observed mean performance across the candidate set. */
  bestMean: number;
  bestIndex: number;
  bestLabel: string;
  /** White (2000) Reality Check p-value: P(best of K under the null of no edge >= observed). */
  pWhite: number;
  /** Hansen (2005) SPA p-value — studentised and recentred, less conservative under poor models. */
  pSpa: number;
  candidates: number;
  observations: number;
}

/**
 * White's Reality Check and Hansen's SPA over a set of candidate strategies.
 *
 * This is the test that answers the question that actually matters after a research sweep:
 * "I looked at K strategies and kept the best one — is the best one better than luck?"
 * Each `series[k]` is the daily P&L of candidate k over the SAME days, benchmarked against
 * not trading (a zero series). The block bootstrap is applied to the whole cross-section at
 * once so cross-strategy correlation is preserved.
 */
export function realityCheck(
  series: number[][],
  labels: string[],
  opts: { samples?: number; seed?: number; block?: number } = {},
): RealityCheckResult {
  const K = series.length;
  if (!K) throw new Error("realityCheck needs at least one candidate");
  const n = series[0].length;
  for (const s of series) if (s.length !== n) throw new Error("all candidate series must cover the same days");

  const B = opts.samples ?? 2000;
  const rand = mulberry32(opts.seed ?? 999);
  const b = opts.block ?? blockLength(n);

  const means = series.map(mean);
  // HAC scale for each candidate; sqrt(n) * se is the standard deviation of sqrt(n) * mean.
  const omega = series.map((s) => {
    const w = neweyWestT(s).se * Math.sqrt(n);
    return w > 0 ? w : 1e-12;
  });

  let bestIndex = 0;
  for (let k = 1; k < K; k++) if (means[k] > means[bestIndex]) bestIndex = k;

  const V = Math.sqrt(n) * means[bestIndex];
  const T = Math.max(...means.map((m, k) => (Math.sqrt(n) * m) / omega[k]));

  // Hansen's recentring: candidates that are sufficiently bad are pushed to zero so they cannot
  // inflate the null distribution (the "consistent" A_k threshold from the paper).
  const g = means.map((m, k) => (m >= -((1 / 4) * n ** -0.25 * omega[k]) ? m : 0));

  let countWhite = 0;
  let countSpa = 0;
  for (let j = 0; j < B; j++) {
    const idx = stationaryIndices(n, b, rand);
    let maxWhite = -Infinity;
    let maxSpa = 0;
    for (let k = 0; k < K; k++) {
      const s = series[k];
      let acc = 0;
      for (let i = 0; i < n; i++) acc += s[idx[i]];
      const mStar = acc / n;
      const white = Math.sqrt(n) * (mStar - means[k]);
      if (white > maxWhite) maxWhite = white;
      const spa = (Math.sqrt(n) * (mStar - g[k])) / omega[k];
      if (spa > maxSpa) maxSpa = spa;
    }
    if (maxWhite > V) countWhite++;
    if (maxSpa > T) countSpa++;
  }

  return {
    bestMean: means[bestIndex],
    bestIndex,
    bestLabel: labels[bestIndex] ?? `#${bestIndex}`,
    pWhite: countWhite / B,
    pSpa: countSpa / B,
    candidates: K,
    observations: n,
  };
}
