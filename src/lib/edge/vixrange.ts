import type { HistoryBar, OptionContract } from "../barchart/types";
import { atmIv } from "../flow/analytics";

/**
 * VIX-style volatility index + day-range quant model.
 *
 * 1. vixIndex — a 30-day MODEL-FREE implied vol for the symbol, computed with the CBOE VIX
 *    methodology on the chain itself: the variance-swap replication  σ² = (2/T)·Σ ΔK/K² · Q(K)
 *    − (1/T)(F/K0 − 1)²  over OTM quotes, on the two expirations bracketing 30 days, time-weighted
 *    to a constant 30-day horizon. r = 0 (consistent with the rest of the codebase — negligible at
 *    these tenors). Falls back to front ATM IV when the strip is too sparse, and says so.
 *
 * 2. dayProjection — the day's expected numbers from driftless Brownian motion with daily vol σ_d:
 *       E[|close − open|]  =  σ_d·S·√(2/π)           ≈ 0.798·σ_d·S     (the "average move")
 *       E[high − low]      =  2·σ_d·S·√(2/π)         ≈ 1.596·σ_d·S     (the expected day range)
 *    plus the ±1σ (68%) close band. High/Low are anchored at the session open.
 *
 * 3. rangeBacktest — the honesty layer: walk-forward verification of that model on days where BOTH
 *    the morning implied vol (recorded live by the 24/7 collector — known at forecast time, no
 *    look-ahead) and the realized OHLC bar exist. Measures the RANGE PREMIUM — how much implied
 *    overstates delivered range — and the band hit rate vs the 68% theory. This premium is the same
 *    documented risk premium that index-futures range sellers harvest; it pays for gap/tail risk,
 *    it is not free money. Pure — unit-tested. Educational — not advice.
 */

const SQRT_2_OVER_PI = Math.sqrt(2 / Math.PI); // E|Z| = 0.79788…
export const RANGE_OVER_SIGMA = 2 * SQRT_2_OVER_PI; // E[range]/σ for driftless BM = 1.59577…
const TRADING_DAYS = 252;
const CAL_DAYS = 365;

const mid = (c: OptionContract): number | null =>
  c.bid != null && c.ask != null && c.ask > 0 && c.ask >= c.bid ? (c.bid + c.ask) / 2 : c.last != null && c.last > 0 ? c.last : null;

/** Variance-swap σ² for one expiration from its OTM strip (r=0, F=spot). Null if the strip is too thin. */
function stripVariance(opts: OptionContract[], spot: number, tYears: number): number | null {
  if (tYears <= 0) return null;
  const strikes = [...new Set(opts.map((o) => o.strike))].sort((a, b) => a - b);
  if (strikes.length < 4) return null;
  // K0 = largest strike ≤ forward (falls back to the lowest strike when spot gaps below the grid)
  const k0 = [...strikes].reverse().find((k) => k <= spot) ?? strikes[0];

  const qAt = (k: number): number | null => {
    const put = opts.find((o) => o.strike === k && o.type === "put");
    const call = opts.find((o) => o.strike === k && o.type === "call");
    if (k < k0) return put ? mid(put) : null;
    if (k > k0) return call ? mid(call) : null;
    const pm = put ? mid(put) : null;
    const cm = call ? mid(call) : null;
    return pm != null && cm != null ? (pm + cm) / 2 : (pm ?? cm);
  };

  let sum = 0;
  let used = 0;
  for (let i = 0; i < strikes.length; i++) {
    const k = strikes[i];
    const q = qAt(k);
    if (q == null || q <= 0) continue;
    const dK = i === 0 ? strikes[1] - strikes[0] : i === strikes.length - 1 ? strikes[i] - strikes[i - 1] : (strikes[i + 1] - strikes[i - 1]) / 2;
    sum += (dK / (k * k)) * q;
    used++;
  }
  if (used < 4) return null;
  const v = (2 / tYears) * sum - (1 / tYears) * Math.pow(spot / k0 - 1, 2);
  return v > 0 ? v : null;
}

export interface VixResult {
  vix: number | null; // annualized %, e.g. 16.4
  method: "strip" | "atm-fallback" | "none";
  near: { exp: string; dte: number; sigma: number } | null; // per-leg annualized vol
  next: { exp: string; dte: number; sigma: number } | null;
}

/** 30-day model-free implied vol (CBOE methodology, r=0), ATM-IV fallback when the strip is sparse. */
export function vixIndex(chain: OptionContract[], spot: number | null): VixResult {
  const none: VixResult = { vix: null, method: "none", near: null, next: null };
  if (!chain.length || spot == null || spot <= 0) return none;

  const byExp = new Map<string, { dte: number; opts: OptionContract[] }>();
  for (const c of chain) {
    if (c.dte == null || c.dte < 0) continue;
    const e = byExp.get(c.expiration) ?? { dte: c.dte, opts: [] };
    e.opts.push(c);
    byExp.set(c.expiration, e);
  }
  // usable legs: variance computable, tenor floored at half a session so 0DTE stays finite
  const legs = [...byExp.entries()]
    .map(([exp, { dte, opts }]) => {
      const t = Math.max(dte, 0.5) / CAL_DAYS;
      const v = stripVariance(opts, spot, t);
      return v == null ? null : { exp, dte, t, v, sigma: Math.sqrt(v) };
    })
    .filter((x): x is NonNullable<typeof x> => x != null)
    .sort((a, b) => a.dte - b.dte);

  if (legs.length) {
    const T30 = 30 / CAL_DAYS;
    // bracket 30d like CBOE; degrade to the closest pair / single leg when no bracket exists
    const near = [...legs].reverse().find((l) => l.t <= T30) ?? legs[0];
    const next = legs.find((l) => l.t > T30) ?? legs[legs.length - 1];
    let var30: number;
    if (near === next || next.t === near.t) {
      var30 = near.v;
    } else {
      const w = (next.t - T30) / (next.t - near.t); // weight on the near leg (can extrapolate slightly)
      var30 = (near.t * near.v * w + next.t * next.v * (1 - w)) / T30;
    }
    if (var30 > 0) {
      return {
        vix: Math.sqrt(var30) * 100,
        method: "strip",
        near: { exp: near.exp, dte: near.dte, sigma: near.sigma },
        next: next === near ? null : { exp: next.exp, dte: next.dte, sigma: next.sigma },
      };
    }
  }

  // sparse book → fall back to front ATM IV, honestly labeled
  const exps = [...byExp.entries()].sort((a, b) => a[1].dte - b[1].dte);
  for (const [exp] of exps) {
    const iv = atmIv(chain, spot, exp);
    if (iv != null && iv > 0) return { vix: iv * 100, method: "atm-fallback", near: { exp, dte: byExp.get(exp)!.dte, sigma: iv }, next: null };
  }
  return none;
}

export interface DayProjection {
  anchor: number; // session open (or spot when the day hasn't opened)
  sigmaDaily: number; // fractional, e.g. 0.0104
  expAbsMove: number; // $ E|close-open| = 0.798·σ·S
  expRange: number; // $ E[high-low] = 1.596·σ·S
  high: number; // anchor + expRange/2
  low: number; // anchor − expRange/2
  band68: { hi: number; lo: number }; // anchor ± 1σ·S (close lands inside ~68% of days)
}

/** Project today's expected move / range / high-low from an annualized vol. */
export function dayProjection(anchor: number | null, annualVol: number | null): DayProjection | null {
  if (anchor == null || anchor <= 0 || annualVol == null || annualVol <= 0) return null;
  const sigmaDaily = annualVol / Math.sqrt(TRADING_DAYS);
  const expAbsMove = SQRT_2_OVER_PI * sigmaDaily * anchor;
  const expRange = RANGE_OVER_SIGMA * sigmaDaily * anchor;
  return {
    anchor,
    sigmaDaily,
    expAbsMove,
    expRange,
    high: anchor + expRange / 2,
    low: anchor - expRange / 2,
    band68: { hi: anchor + sigmaDaily * anchor, lo: anchor - sigmaDaily * anchor },
  };
}

export interface BacktestDay {
  day: string; // YYYY-MM-DD (UTC)
  ivOpen: number; // annualized vol known at forecast time (earliest recorded that day)
  bar: HistoryBar; // that day's realized OHLC
}

export interface BacktestRow {
  day: string;
  impliedRange: number; // $ forecast E[high-low]
  realizedRange: number; // $ actual high-low
  impliedMove: number; // $ forecast E|close-open|
  realizedMove: number; // $ actual |close-open|
  inBand68: boolean; // close landed inside the ±1σ band
}

export interface BacktestResult {
  n: number;
  rows: BacktestRow[]; // chronological
  rangePremium: number | null; // mean(implied/realized range) − 1; >0 ⇒ implied overstates (seller's edge)
  movePremium: number | null; // same for |close−open|
  hitRate68: number | null; // fraction of closes inside ±1σ (theory ≈ 0.68)
  realizedRangeOverSigma: number | null; // mean realized range / (σ_d·open); BM theory = 1.596
}

/** Walk-forward verification: forecasts from morning IV only, judged against the day's actual OHLC. */
export function rangeBacktest(days: BacktestDay[]): BacktestResult {
  const rows: BacktestRow[] = [];
  const ratiosR: number[] = [];
  const ratiosM: number[] = [];
  const rOverS: number[] = [];
  let inBand = 0;

  for (const d of [...days].sort((a, b) => a.day.localeCompare(b.day))) {
    const { open, high, low, close } = d.bar;
    if (!(open > 0) || !(high >= low) || d.ivOpen <= 0) continue;
    const p = dayProjection(open, d.ivOpen);
    if (!p) continue;
    const realizedRange = high - low;
    const realizedMove = Math.abs(close - open);
    const row: BacktestRow = {
      day: d.day,
      impliedRange: p.expRange,
      realizedRange,
      impliedMove: p.expAbsMove,
      realizedMove,
      inBand68: close <= p.band68.hi && close >= p.band68.lo,
    };
    rows.push(row);
    if (realizedRange > 0) {
      ratiosR.push(p.expRange / realizedRange);
      rOverS.push(realizedRange / (p.sigmaDaily * open));
    }
    if (realizedMove > 0) ratiosM.push(p.expAbsMove / realizedMove);
    if (row.inBand68) inBand++;
  }

  const mean = (a: number[]) => (a.length ? a.reduce((s, x) => s + x, 0) / a.length : null);
  return {
    n: rows.length,
    rows,
    rangePremium: ratiosR.length ? (mean(ratiosR) as number) - 1 : null,
    movePremium: ratiosM.length ? (mean(ratiosM) as number) - 1 : null,
    hitRate68: rows.length ? inBand / rows.length : null,
    realizedRangeOverSigma: mean(rOverS),
  };
}
