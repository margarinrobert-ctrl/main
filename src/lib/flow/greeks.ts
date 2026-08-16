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

/** Delta = ∂V/∂S with r = q = 0. Call: N(d1); Put: N(d1) − 1. */
export function bsDelta(type: "call" | "put", spot: number, strike: number, iv: number, tYears: number): number | null {
  const dd = d1d2(spot, strike, iv, tYears);
  if (!dd) return null;
  const nc = ncdf(dd.d1);
  return type === "call" ? nc : nc - 1;
}

/** Black-Scholes option price with r = q = 0 (used to imply vol from a quote). */
export function bsPrice(type: "call" | "put", spot: number, strike: number, iv: number, tYears: number): number | null {
  const dd = d1d2(spot, strike, iv, tYears);
  if (!dd) return null;
  return type === "call" ? spot * ncdf(dd.d1) - strike * ncdf(dd.d2) : strike * ncdf(-dd.d2) - spot * ncdf(-dd.d1);
}

/**
 * Implied volatility from an option price via bisection (r = q = 0). Robust (no derivative, can't
 * diverge). Returns null when the price is below intrinsic, above the no-arb cap, or degenerate.
 */
export function impliedVol(type: "call" | "put", spot: number, strike: number, tYears: number, price: number): number | null {
  if (spot <= 0 || strike <= 0 || tYears <= 0 || price <= 0) return null;
  const intrinsic = type === "call" ? Math.max(0, spot - strike) : Math.max(0, strike - spot);
  if (price < intrinsic - 1e-4) return null; // below intrinsic → bad quote
  if (price >= (type === "call" ? spot : strike)) return null; // above the r=q=0 no-arb cap
  let lo = 1e-4;
  let hi = 5;
  const plo = bsPrice(type, spot, strike, lo, tYears);
  const phi = bsPrice(type, spot, strike, hi, tYears);
  if (plo == null || phi == null) return null;
  if (price <= plo) return lo;
  if (price >= phi) return hi;
  for (let k = 0; k < 64; k++) {
    const m = 0.5 * (lo + hi);
    const pm = bsPrice(type, spot, strike, m, tYears);
    if (pm == null) return null;
    if (Math.abs(pm - price) < 1e-6) return m;
    if (pm < price) lo = m;
    else hi = m;
  }
  return 0.5 * (lo + hi);
}
