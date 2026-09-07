import { mean, neweyWestT, sharpeRatio, std } from "./stats";

// Multi-strategy combination.
//
// Combining scalping systems is not about stacking the best backtests — it is about buying
// uncorrelated P&L streams. Two rules drive everything here:
//
//   1. Correlation of DAILY P&L is the only thing that decides whether a second strategy adds
//      anything. Two breakout rules at r = 0.8 are one strategy paying two sets of commissions.
//   2. Weights come from risk, not from backtest returns. Estimated means are pure noise at this
//      sample size and estimated covariances are merely noisy, so every scheme offered here is
//      risk-based and the covariance is shrunk before it is used.

export interface AlignedPnl {
  /** Sorted union of session-day indices across all strategies. */
  days: number[];
  /** matrix[k][d] = daily P&L of strategy k on days[d]; zero on days it did not trade. */
  matrix: number[][];
  labels: string[];
}

export function alignDaily(streams: { label: string; dailyPnl: Map<number, number> }[], allDays?: number[]): AlignedPnl {
  const days = allDays ?? [...new Set(streams.flatMap((s) => [...s.dailyPnl.keys()]))].sort((a, b) => a - b);
  return {
    days,
    labels: streams.map((s) => s.label),
    matrix: streams.map((s) => days.map((d) => s.dailyPnl.get(d) ?? 0)),
  };
}

export function correlationMatrix(matrix: number[][]): number[][] {
  const K = matrix.length;
  const means = matrix.map(mean);
  const sds = matrix.map((r) => std(r));
  const out: number[][] = Array.from({ length: K }, () => new Array<number>(K).fill(0));
  for (let i = 0; i < K; i++) {
    for (let j = i; j < K; j++) {
      if (sds[i] === 0 || sds[j] === 0) {
        out[i][j] = out[j][i] = i === j ? 1 : 0;
        continue;
      }
      let acc = 0;
      const n = matrix[i].length;
      for (let d = 0; d < n; d++) acc += (matrix[i][d] - means[i]) * (matrix[j][d] - means[j]);
      const r = acc / ((n - 1) * sds[i] * sds[j]);
      out[i][j] = out[j][i] = Math.max(-1, Math.min(1, r));
    }
  }
  return out;
}

export function covarianceMatrix(matrix: number[][]): number[][] {
  const K = matrix.length;
  const n = matrix[0]?.length ?? 0;
  const means = matrix.map(mean);
  const out: number[][] = Array.from({ length: K }, () => new Array<number>(K).fill(0));
  for (let i = 0; i < K; i++) {
    for (let j = i; j < K; j++) {
      let acc = 0;
      for (let d = 0; d < n; d++) acc += (matrix[i][d] - means[i]) * (matrix[j][d] - means[j]);
      const v = n > 1 ? acc / (n - 1) : 0;
      out[i][j] = out[j][i] = v;
    }
  }
  return out;
}

/** Shrink off-diagonal covariance toward a diagonal target — keeps the matrix well conditioned. */
export function shrinkCovariance(cov: number[][], lambda = 0.2): number[][] {
  return cov.map((row, i) => row.map((v, j) => (i === j ? v : v * (1 - lambda))));
}

export type WeightScheme = "equal" | "inverse-vol" | "risk-parity" | "min-variance";

const normalise = (w: number[]): number[] => {
  const s = w.reduce((a, b) => a + b, 0);
  return s > 0 ? w.map((x) => x / s) : w.map(() => 1 / w.length);
};

/** Naive risk parity by fixed-point iteration on marginal risk contributions (long-only). */
export function riskParityWeights(cov: number[][], iters = 400): number[] {
  const K = cov.length;
  let w = new Array<number>(K).fill(1 / K);
  for (let it = 0; it < iters; it++) {
    const mrc = w.map((_, i) => w.reduce((acc, wj, j) => acc + cov[i][j] * wj, 0));
    const portVar = Math.max(w.reduce((acc, wi, i) => acc + wi * mrc[i], 0), 1e-18);
    const port = Math.sqrt(portVar);
    const target = port / K;
    w = normalise(
      w.map((wi, i) => {
        const rc = (wi * mrc[i]) / port;
        return Math.max(wi * (rc > 0 ? Math.sqrt(target / rc) : 1.5), 1e-8);
      }),
    );
  }
  return w;
}

/** Long-only minimum variance by projected gradient descent — no inversion, no short weights. */
export function minVarianceWeights(cov: number[][], iters = 2000, step = 0.05): number[] {
  const K = cov.length;
  let w = new Array<number>(K).fill(1 / K);
  const scale = Math.max(...cov.map((r, i) => Math.abs(r[i])), 1e-12);
  for (let it = 0; it < iters; it++) {
    const grad = w.map((_, i) => (2 * w.reduce((acc, wj, j) => acc + cov[i][j] * wj, 0)) / scale);
    w = normalise(w.map((wi, i) => Math.max(wi - step * grad[i], 0)));
  }
  return w;
}

export function weightsFor(scheme: WeightScheme, matrix: number[][]): number[] {
  const K = matrix.length;
  if (scheme === "equal") return new Array<number>(K).fill(1 / K);
  if (scheme === "inverse-vol") {
    return normalise(
      matrix.map((r) => {
        const s = std(r);
        return s > 0 ? 1 / s : 0;
      }),
    );
  }
  const cov = shrinkCovariance(covarianceMatrix(matrix));
  return scheme === "risk-parity" ? riskParityWeights(cov) : minVarianceWeights(cov);
}

export interface PortfolioResult {
  scheme: WeightScheme;
  weights: number[];
  labels: string[];
  /** Combined daily stream, in units of each strategy's own daily volatility. */
  daily: number[];
  sharpe: number;
  tStat: number;
  maxDrawdownVolUnits: number;
  /** Weighted average standalone vol / portfolio vol. Above ~1.3 is real diversification. */
  diversificationRatio: number;
  /** Each strategy's share of total portfolio risk. */
  riskContribution: number[];
  averagePairwiseCorrelation: number;
  standaloneSharpes: number[];
  /** Portfolio Sharpe minus the best standalone Sharpe — what combining actually bought. */
  sharpeUplift: number;
}

/**
 * Build a portfolio. Each stream is first scaled to unit daily volatility, so weights express risk
 * allocation rather than an accident of contract size: a CL scalp and an NQ scalp have very
 * different dollar vol per contract, and equal dollar weights on those is not a decision anyone
 * would make deliberately.
 */
export function buildPortfolio(aligned: AlignedPnl, scheme: WeightScheme = "risk-parity", periodsPerYear = 252): PortfolioResult {
  const vols = aligned.matrix.map((r) => std(r) || 1);
  const scaled = aligned.matrix.map((r, i) => r.map((v) => v / vols[i]));
  const weights = weightsFor(scheme, scaled);
  const n = aligned.days.length;

  const daily = new Array<number>(n).fill(0);
  for (let d = 0; d < n; d++) for (let k = 0; k < scaled.length; k++) daily[d] += weights[k] * scaled[k][d];

  const cov = covarianceMatrix(scaled);
  const portVar = Math.max(
    weights.reduce((acc, wi, i) => acc + wi * weights.reduce((a2, wj, j) => a2 + cov[i][j] * wj, 0), 0),
    1e-18,
  );
  const portVol = Math.sqrt(portVar);
  const weightedVol = weights.reduce((acc, wi, i) => acc + wi * Math.sqrt(Math.max(cov[i][i], 0)), 0);
  const riskContribution = weights.map((wi, i) => (wi * weights.reduce((acc, wj, j) => acc + cov[i][j] * wj, 0)) / portVar);

  const corr = correlationMatrix(scaled);
  let pairSum = 0;
  let pairs = 0;
  for (let i = 0; i < corr.length; i++)
    for (let j = i + 1; j < corr.length; j++) {
      pairSum += corr[i][j];
      pairs++;
    }

  let cum = 0;
  let peak = 0;
  let dd = 0;
  for (const v of daily) {
    cum += v;
    peak = Math.max(peak, cum);
    dd = Math.max(dd, peak - cum);
  }

  const standaloneSharpes = scaled.map((r) => sharpeRatio(r, periodsPerYear));
  const portfolioSharpe = sharpeRatio(daily, periodsPerYear);

  return {
    scheme,
    weights,
    labels: aligned.labels,
    daily,
    sharpe: portfolioSharpe,
    tStat: neweyWestT(daily).t,
    maxDrawdownVolUnits: dd,
    diversificationRatio: portVol > 0 ? weightedVol / portVol : 1,
    riskContribution,
    averagePairwiseCorrelation: pairs ? pairSum / pairs : 0,
    standaloneSharpes,
    sharpeUplift: portfolioSharpe - Math.max(...standaloneSharpes),
  };
}

/** Drop near-duplicates: keep the higher-Sharpe stream whenever a pair exceeds `maxCorr`. */
export function pruneCorrelated(
  aligned: AlignedPnl,
  maxCorr = 0.7,
): { keep: number[]; dropped: { index: number; against: number; corr: number }[] } {
  const corr = correlationMatrix(aligned.matrix);
  const sharpe = aligned.matrix.map((r) => sharpeRatio(r, 252));
  const order = sharpe
    .map((s, i) => ({ s, i }))
    .sort((a, b) => b.s - a.s)
    .map((x) => x.i);
  const keep: number[] = [];
  const dropped: { index: number; against: number; corr: number }[] = [];
  for (const i of order) {
    const clash = keep.find((k) => Math.abs(corr[i][k]) > maxCorr);
    if (clash === undefined) keep.push(i);
    else dropped.push({ index: i, against: clash, corr: corr[i][clash] });
  }
  return { keep: keep.sort((a, b) => a - b), dropped };
}
