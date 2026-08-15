import { ncdf } from "./bs";

/**
 * Black-76 (futures) + 0DTE barrier math for the NQ1!/ES1! level scripts.
 *
 * WHY THE MODEL CHANGES FOR FUTURES. Black-Scholes-Merton prices an option on a SPOT asset that
 * carries cost-of-carry (r) and yield (q). A futures price is already a forward: under the
 * risk-neutral measure it is a MARTINGALE (zero drift), and there is no dividend yield. Substituting
 * F for S·e^{(r−q)T} collapses BSM to Black-76:
 *
 *     d1 = [ln(F/K) + σ²T/2] / (σ√T),   d2 = d1 − σ√T
 *     call = e^{−rT}[F·N(d1) − K·N(d2)],  put = e^{−rT}[K·N(−d2) − F·N(−d1)]
 *
 * THE 1:1 RESULT THAT DRIVES THE HONEST DESIGN. For a symmetric ±R bracket on a martingale, optional
 * stopping gives E[F_τ] = F_0, i.e. p(L+R) + (1−p)(L−R) = L  ⇒  **p = 1/2 exactly**. Not
 * approximately — exactly, and independently of σ, R and the level. (The log-space asymmetry of ±R and
 * the −σ²/2 log-drift cancel precisely; verified in the unit tests.) So a 1:1 R:R bracket cannot have
 * an edge from geometry alone: 50% is the null, and any honest ranking must come from elsewhere.
 *
 * What DOES differ per level within a 0DTE session, and is computed here:
 *   • P(touch the level at all before the close) — a level that never trades never fills.
 *   • P(the bracket resolves before the close) vs finishing unresolved (flat-ish exit at the bell).
 *   • Directional tilt ONLY if the trader supplies a drift; at zero drift everything returns to 50%.
 *
 * Pure — unit-tested.
 */

export interface B76Inputs {
  type: "call" | "put";
  fut: number; // futures price F
  strike: number;
  tYears: number;
  sigma: number;
  r?: number; // discount rate only (no carry — F is already the forward)
}

export interface B76Quote {
  price: number;
  d1: number;
  d2: number;
  delta: number; // ∂/∂F (discounted)
  gamma: number;
  vega: number; // per 1 vol point
  thetaDay: number;
  probItm: number;
}

export function black76(i: B76Inputs): B76Quote | null {
  const { type, fut: F, strike: K, tYears: T, sigma: v } = i;
  const r = i.r ?? 0;
  if (!(F > 0) || !(K > 0) || !(T > 0) || !(v > 0)) return null;
  const vt = v * Math.sqrt(T);
  const d1 = (Math.log(F / K) + 0.5 * v * v * T) / vt;
  const d2 = d1 - vt;
  const df = Math.exp(-r * T);
  const sign = type === "call" ? 1 : -1;
  const price = df * sign * (F * ncdf(sign * d1) - K * ncdf(sign * d2));
  const pdf1 = Math.exp(-0.5 * d1 * d1) / Math.sqrt(2 * Math.PI);
  const thetaYear = -(F * df * pdf1 * v) / (2 * Math.sqrt(T)) + r * price; // sign-consistent with BSM
  return {
    price,
    d1,
    d2,
    delta: df * (type === "call" ? ncdf(d1) : ncdf(d1) - 1),
    gamma: (df * pdf1) / (F * vt),
    vega: F * df * pdf1 * Math.sqrt(T) * 0.01,
    thetaDay: thetaYear / 365,
    probItm: ncdf(sign * d2),
  };
}

/** Session vol: annualized IV → the σ that applies over the remaining fraction of one trading day. */
export function sessionSigma(annualIv: number, fractionOfDayRemaining: number): number {
  if (!(annualIv > 0) || !(fractionOfDayRemaining > 0)) return 0;
  return (annualIv / Math.sqrt(252)) * Math.sqrt(Math.min(1, fractionOfDayRemaining));
}

/**
 * P(price touches `level` before the horizon) under driftless GBM — reflection principle:
 *   P = 2·N(−|ln(level/F)| / σ_rem)
 */
export function probTouch(fut: number, level: number, sigmaRem: number): number {
  if (!(fut > 0) || !(level > 0) || !(sigmaRem > 0)) return 0;
  if (level === fut) return 1;
  return Math.min(1, 2 * ncdf(-Math.abs(Math.log(level / fut)) / sigmaRem));
}

/**
 * P(log-price stays strictly inside a symmetric band ±h over the horizon) — the classic reflection
 * series. Converges in a handful of terms for the ranges used here.
 */
export function probNoTouchBand(h: number, sigmaRem: number, terms = 6): number {
  if (!(h > 0)) return 0;
  if (!(sigmaRem > 0)) return 1;
  const a = h / sigmaRem;
  let p = 0;
  for (let k = -terms; k <= terms; k++) {
    p += (k % 2 === 0 ? 1 : -1) * (ncdf((2 * k + 1) * a) - ncdf((2 * k - 1) * a));
  }
  return Math.max(0, Math.min(1, p));
}

export interface Setup {
  level: number;
  side: "long" | "short";
  entry: number;
  stop: number;
  target: number;
  risk: number; // points (= reward, 1:1)
  probTouchLevel: number; // chance the entry level trades before the close
  probResolve: number; // chance the bracket completes before the close
  winRate: number; // P(target first | bracket resolves) — 0.5 at zero drift, tilted by drift
  pWinSession: number; // P(entry fills AND target hits first, before the close)
  pLossSession: number;
  pUnresolved: number; // filled but neither barrier hit by the close
  expR: number; // expected R multiple per FILLED trade (0 at zero drift, before costs)
}

/**
 * Evaluate the 1:1 bracket at one grid level for the rest of a 0DTE session.
 *
 * `drift` is the trader's directional view over the remaining session, expressed in points. Zero drift
 * ⇒ winRate is exactly 0.5 and expR is exactly 0 — the honest null, before commissions and slippage.
 */
export function evalSetup(fut: number, level: number, risk: number, sigmaRem: number, side: "long" | "short", driftPts = 0): Setup | null {
  if (!(fut > 0) || !(level > 0) || !(risk > 0)) return null;
  const entry = level;
  const target = side === "long" ? level + risk : level - risk;
  const stop = side === "long" ? level - risk : level + risk;

  const h = Math.log((level + risk) / level); // band half-width in log space (symmetric proxy)
  const pNoTouch = probNoTouchBand(h, sigmaRem);
  const pResolve = 1 - pNoTouch;

  // Drift tilt: p(up first) from the scale function of BM with drift over a symmetric log band.
  // With zero drift this is exactly 0.5.
  let pUpFirst = 0.5;
  if (sigmaRem > 0 && driftPts !== 0) {
    const muLog = Math.log((fut + driftPts) / fut); // total log drift over the horizon
    // Scale function s(x) = e^{−θx}, θ = 2μ/σ²  ⇒  P(hit +h first) = (e^{θh} − 1)/(e^{θh} − e^{−θh}).
    // Reduces to ½ as θ→0 (the martingale null) and rises above ½ for upward drift.
    const theta = (2 * muLog) / (sigmaRem * sigmaRem);
    pUpFirst = Math.abs(theta * h) < 1e-9 ? 0.5 : (Math.exp(theta * h) - 1) / (Math.exp(theta * h) - Math.exp(-theta * h));
    pUpFirst = Math.max(0, Math.min(1, pUpFirst));
  }
  const winRate = side === "long" ? pUpFirst : 1 - pUpFirst;

  const pTouch = probTouch(fut, level, sigmaRem);
  const pWinSession = pTouch * pResolve * winRate;
  const pLossSession = pTouch * pResolve * (1 - winRate);
  const pUnresolved = pTouch * pNoTouch;

  return {
    level,
    side,
    entry,
    stop,
    target,
    risk,
    probTouchLevel: pTouch,
    probResolve: pResolve,
    winRate,
    pWinSession,
    pLossSession,
    pUnresolved,
    expR: pResolve * (winRate - (1 - winRate)), // R per filled trade; unresolved ≈ 0R
  };
}

/** Round-number grid of trade levels straddling the futures price (40 pts NQ, 10 pts ES). */
export function gridLevels(fut: number, step: number, count = 6): number[] {
  if (!(fut > 0) || !(step > 0)) return [];
  const base = Math.round(fut / step) * step;
  const out: number[] = [];
  for (let k = -count; k <= count; k++) {
    const v = base + k * step;
    if (v > 0) out.push(Math.round(v * 100) / 100);
  }
  return out;
}
