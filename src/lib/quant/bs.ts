/**
 * Full Black-Scholes-Merton pricer — the interactive quant lab's engine.
 *
 * Unlike the dealer-positioning stack (which fixes r = q = 0, a fine simplification for short-dated
 * intraday work), this module carries continuous rate r and dividend yield q so priced values match
 * the textbook model exactly and can be verified against published examples (Hull). European exercise,
 * flat vol. All functions are pure and unit-tested.
 *
 *   d1 = [ln(S/K) + (r − q + σ²/2)T] / (σ√T)        d2 = d1 − σ√T
 *   call = S·e^{−qT}·N(d1) − K·e^{−rT}·N(d2)         put via parity
 */

export type OptType = "call" | "put";

const SQRT_2PI = Math.sqrt(2 * Math.PI);
export const pdf = (x: number): number => Math.exp(-0.5 * x * x) / SQRT_2PI;

// Error function (Abramowitz–Stegun 7.1.26, ~1e-7) — same approximation used elsewhere in the app.
function erf(x: number): number {
  const t = 1 / (1 + 0.3275911 * Math.abs(x));
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t) * Math.exp(-x * x);
  return x >= 0 ? y : -y;
}
export const ncdf = (x: number): number => 0.5 * (1 + erf(x / Math.SQRT2));

export interface BsInputs {
  type: OptType;
  spot: number;
  strike: number;
  tYears: number;
  sigma: number; // annualized, e.g. 0.2
  r?: number; // continuous risk-free rate, e.g. 0.05
  q?: number; // continuous dividend yield
}

export interface BsQuote {
  price: number;
  intrinsic: number;
  timeValue: number;
  d1: number;
  d2: number;
  delta: number; // per $1 of spot
  gamma: number; // ∂Δ/∂S per $1
  vega: number; // per 1 VOL POINT (σ + 0.01)
  thetaDay: number; // per CALENDAR DAY (usually negative for longs)
  rho: number; // per 1 RATE POINT (r + 0.01)
  vanna: number; // ∂Δ per 1 vol point
  probItm: number; // risk-neutral P(expire ITM) = N(±d2)
}

export function bsQuote(i: BsInputs): BsQuote | null {
  const { type, spot: S, strike: K, tYears: T, sigma: v } = i;
  const r = i.r ?? 0;
  const q = i.q ?? 0;
  if (!(S > 0) || !(K > 0) || !(T > 0) || !(v > 0)) return null;
  const vt = v * Math.sqrt(T);
  const d1 = (Math.log(S / K) + (r - q + 0.5 * v * v) * T) / vt;
  const d2 = d1 - vt;
  const dfR = Math.exp(-r * T);
  const dfQ = Math.exp(-q * T);
  const sign = type === "call" ? 1 : -1;

  const price = sign * (S * dfQ * ncdf(sign * d1) - K * dfR * ncdf(sign * d2));
  const intrinsic = Math.max(0, sign * (S - K));
  const delta = type === "call" ? dfQ * ncdf(d1) : dfQ * (ncdf(d1) - 1);
  const gamma = (dfQ * pdf(d1)) / (S * vt);
  const vegaRaw = S * dfQ * pdf(d1) * Math.sqrt(T); // per 1.00 of σ
  const thetaYear =
    type === "call"
      ? (-S * dfQ * pdf(d1) * v) / (2 * Math.sqrt(T)) - r * K * dfR * ncdf(d2) + q * S * dfQ * ncdf(d1)
      : (-S * dfQ * pdf(d1) * v) / (2 * Math.sqrt(T)) + r * K * dfR * ncdf(-d2) - q * S * dfQ * ncdf(-d1);
  const rhoRaw = type === "call" ? K * T * dfR * ncdf(d2) : -K * T * dfR * ncdf(-d2); // per 1.00 of r
  const vannaRaw = (-dfQ * pdf(d1) * d2) / v; // per 1.00 of σ

  return {
    price,
    intrinsic,
    timeValue: price - intrinsic,
    d1,
    d2,
    delta,
    gamma,
    vega: vegaRaw * 0.01,
    thetaDay: thetaYear / 365,
    rho: rhoRaw * 0.01,
    vanna: vannaRaw * 0.01,
    probItm: ncdf(sign * d2),
  };
}

/** No-arbitrage price bounds for a European option under (r, q). */
export function bsBounds(i: Omit<BsInputs, "sigma">): { lo: number; hi: number } {
  const { type, spot: S, strike: K, tYears: T } = i;
  const dfR = Math.exp(-(i.r ?? 0) * T);
  const dfQ = Math.exp(-(i.q ?? 0) * T);
  return type === "call" ? { lo: Math.max(0, S * dfQ - K * dfR), hi: S * dfQ } : { lo: Math.max(0, K * dfR - S * dfQ), hi: K * dfR };
}

/**
 * Implied volatility from a price — robust bisection (monotone in σ, cannot diverge).
 * Returns null when the price sits outside the no-arbitrage bounds or inputs are degenerate.
 */
export function bsImpliedVol(i: Omit<BsInputs, "sigma">, price: number): number | null {
  const { spot: S, strike: K, tYears: T } = i;
  if (!(S > 0) || !(K > 0) || !(T > 0) || !(price > 0)) return null;
  const { lo, hi } = bsBounds(i);
  if (price <= lo + 1e-9 || price >= hi - 1e-9) return null;
  let a = 1e-4;
  let b = 5;
  const pa = bsQuote({ ...i, sigma: a })?.price ?? Number.NaN;
  const pb = bsQuote({ ...i, sigma: b })?.price ?? Number.NaN;
  if (!Number.isFinite(pa) || !Number.isFinite(pb)) return null;
  if (price <= pa) return a;
  if (price >= pb) return b;
  for (let k = 0; k < 80; k++) {
    const m = 0.5 * (a + b);
    const pm = bsQuote({ ...i, sigma: m })?.price;
    if (pm == null) return null;
    if (Math.abs(pm - price) < 1e-7) return m;
    if (pm < price) a = m;
    else b = m;
  }
  return 0.5 * (a + b);
}

/** BS value across a spot ladder (for the value-vs-spot curve), plus intrinsic payoff at expiry. */
export function valueCurve(i: BsInputs, points = 61, widthSigmas = 2.5): { spot: number; value: number; payoff: number }[] {
  const q = bsQuote(i);
  if (!q) return [];
  const half = Math.max(i.spot * i.sigma * Math.sqrt(i.tYears) * widthSigmas, i.spot * 0.02);
  const lo = Math.max(0.01, i.spot - half);
  const hi = i.spot + half;
  const out: { spot: number; value: number; payoff: number }[] = [];
  for (let k = 0; k < points; k++) {
    const s = lo + ((hi - lo) * k) / (points - 1);
    const v = bsQuote({ ...i, spot: s })?.price ?? 0;
    const payoff = Math.max(0, (i.type === "call" ? 1 : -1) * (s - i.strike));
    out.push({ spot: s, value: v, payoff });
  }
  return out;
}
