import { kurtosis, mean, normalCdf, normalInv, skewness, std } from "./stats";

// Selection-bias-aware Sharpe statistics (Bailey & López de Prado).
//
// A backtest Sharpe is not an estimate of an edge — it is the MAXIMUM of however many Sharpes you
// looked at. Search 200 parameter sets on noise and the best one lands near Sharpe 1.5 with no edge
// whatsoever. The Deflated Sharpe Ratio prices that in: it asks whether the observed Sharpe beats
// what the best of N independent trials would have produced by chance, given the skew and fat tails
// of the actual return stream.

const EULER = 0.5772156649015329;

export interface PsrResult {
  /** Per-period (NOT annualised) Sharpe of the return stream. */
  sr: number;
  /** Probabilistic Sharpe Ratio: P(true SR > benchmark) given skew/kurtosis and sample length. */
  psr: number;
  /** Minimum track record length, in periods, to establish SR > benchmark at `alpha`. */
  minTrackRecord: number;
  observations: number;
  skew: number;
  kurtosis: number;
}

/** Probabilistic Sharpe Ratio against a benchmark Sharpe (per-period units). */
export function probabilisticSharpe(returns: number[], benchmarkSr = 0, alpha = 0.05): PsrResult {
  const n = returns.length;
  const s = std(returns);
  const sr = s > 0 ? mean(returns) / s : 0;
  const g3 = skewness(returns);
  const g4 = kurtosis(returns) + 3; // non-excess kurtosis, as the formula expects
  const varTerm = 1 - g3 * sr + ((g4 - 1) / 4) * sr * sr;
  const denom = Math.sqrt(Math.max(varTerm, 1e-12));
  const psr = n > 1 ? normalCdf(((sr - benchmarkSr) * Math.sqrt(n - 1)) / denom) : 0.5;
  const gap = sr - benchmarkSr;
  const minTrl = gap > 0 ? 1 + varTerm * (normalInv(1 - alpha) / gap) ** 2 : Infinity;
  return { sr, psr, minTrackRecord: minTrl, observations: n, skew: g3, kurtosis: g4 - 3 };
}

export interface DsrResult extends PsrResult {
  /** Expected maximum per-period Sharpe under the null, given `trials` searches. */
  expectedMaxSr: number;
  /** Deflated Sharpe Ratio — PSR measured against that expected maximum. */
  dsr: number;
  trials: number;
  /** Annualised version of the raw Sharpe, for reading alongside the usual headline figure. */
  annualisedSr: number;
}

/**
 * Deflated Sharpe Ratio.
 *
 * @param returns    per-period returns / P&L of the SELECTED strategy
 * @param trials     how many configurations were actually evaluated before picking this one
 * @param trialSrStd cross-sectional std-dev of the per-period Sharpes across those trials.
 *                   Pass the real thing — using a guess here is the difference between an honest
 *                   deflation and a decorative one.
 */
export function deflatedSharpe(returns: number[], trials: number, trialSrStd: number, periodsPerYear = 252, alpha = 0.05): DsrResult {
  const N = Math.max(trials, 2);
  const emc = normalInv(1 - 1 / N);
  const emc2 = normalInv(1 - 1 / (N * Math.E));
  const expectedMaxSr = Math.max(trialSrStd, 0) * ((1 - EULER) * emc + EULER * emc2);
  const base = probabilisticSharpe(returns, expectedMaxSr, alpha);
  return {
    ...base,
    expectedMaxSr,
    dsr: base.psr,
    trials: N,
    annualisedSr: base.sr * Math.sqrt(periodsPerYear),
  };
}

/** Cross-sectional std-dev of per-period Sharpes across a search — the input DSR actually needs. */
export function trialSharpeDispersion(perPeriodSharpes: number[]): number {
  return std(perPeriodSharpes.filter(Number.isFinite));
}
