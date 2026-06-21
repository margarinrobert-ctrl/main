// Closed-form Black-Scholes second-order greeks (Vanna & Charm), used to estimate dealer
// vanna/charm exposure from the chain. CBOE gives delta/gamma but not these, so we derive them.
// Assumes zero rates/dividends (r = q = 0) — a fine simplification for short-dated index/ETF
// options and intraday work. With r = q = 0, both vanna and charm are identical for calls & puts.

const SQRT_2PI = Math.sqrt(2 * Math.PI);

/** Standard-normal probability density. */
export function pdf(x: number): number {
  return Math.exp(-0.5 * x * x) / SQRT_2PI;
}

// Error function (Abramowitz-Stegun 7.1.26, ~1e-7 accuracy).
function erf(x: number): number {
  const t = 1 / (1 + 0.3275911 * Math.abs(x));
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t) * Math.exp(-x * x);
  return x >= 0 ? y : -y;
}

/** Standard-normal cumulative distribution N(x). */
export function ncdf(x: number): number {
  return 0.5 * (1 + erf(x / Math.SQRT2));
}

/** Risk-neutral (driftless) probability S_T > level by expiry = N(d2). */
export function probAbove(spot: number, level: number, iv: number, tYears: number): number | null {
  const dd = d1d2(spot, level, iv, tYears);
  return dd ? ncdf(dd.d2) : null;
}

/**
 * Probability the underlying TOUCHES `level` at least once before expiry, under driftless GBM
 * (reflection principle): 2·N(−|ln(level/spot)| / (σ√T)). The right number for "will price reach
 * this target?" — always ≥ the probability of merely finishing past it.
 */
export function probTouch(spot: number, level: number, iv: number, tYears: number): number | null {
  if (spot <= 0 || level <= 0 || iv <= 0 || tYears <= 0) return null;
  if (level === spot) return 1;
  const x = Math.abs(Math.log(level / spot)) / (iv * Math.sqrt(tYears));
  return Math.max(0, Math.min(1, 2 * ncdf(-x)));
}

/** Black-Scholes d1/d2 with r = q = 0. Returns null when inputs are degenerate. */
export function d1d2(spot: number, strike: number, iv: number, tYears: number): { d1: number; d2: number } | null {
  if (spot <= 0 || strike <= 0 || iv <= 0 || tYears <= 0) return null;
  const vt = iv * Math.sqrt(tYears);
  const d1 = (Math.log(spot / strike) + 0.5 * iv * iv * tYears) / vt;
  return { d1, d2: d1 - vt };
}

/** Gamma = ∂Δ/∂S = φ(d1)/(S·σ·√T), per $1 move. Identical for calls and puts. */
export function bsGamma(spot: number, strike: number, iv: number, tYears: number): number | null {
  const dd = d1d2(spot, strike, iv, tYears);
  if (!dd) return null;
  return pdf(dd.d1) / (spot * iv * Math.sqrt(tYears));
}

/**
 * Vanna = ∂Δ/∂σ = ∂Vega/∂S, per 1.00 (=100 vol-point) change in σ. Same for calls and puts.
 * Positive when raising IV raises an option's delta (OTM calls / ITM puts move toward the money).
 */
export function bsVanna(spot: number, strike: number, iv: number, tYears: number): number | null {
  const dd = d1d2(spot, strike, iv, tYears);
  if (!dd) return null;
  return (-pdf(dd.d1) * dd.d2) / iv;
}

/**
 * Charm = ∂Δ/∂t (delta decay), per YEAR of calendar time passing. Same for calls and puts at
 * r = q = 0. Negative for OTM calls (delta bleeds to 0 into expiry), positive for ITM calls.
 */
export function bsCharm(spot: number, strike: number, iv: number, tYears: number): number | null {
  const dd = d1d2(spot, strike, iv, tYears);
  if (!dd) return null;
  return (pdf(dd.d1) * dd.d2) / (2 * tYears);
}
