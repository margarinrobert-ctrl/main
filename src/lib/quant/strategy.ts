import type { OptionContract } from "../barchart/types";
import { bsImpliedVol, ncdf } from "./bs";

/**
 * Per-strike trade scanner — expected P&L and win rate for the four single-leg trades at every strike,
 * priced at the LIVE market mid, evaluated under an explicit scenario (σ_scenario, drift μ).
 *
 * Honesty first: at the market's own prices under the risk-neutral measure every option trade has
 * ~zero expected value — there is no free "most profitable" table. Rankings here are conditional on
 * the scenario: with μ = r − q and σ_scenario equal to each contract's implied vol, expected P&L
 * collapses to ≈ 0 (unit-tested). Positive short-side EV appears exactly when the market's implied
 * vol exceeds your σ_scenario — that's the variance-risk-premium trade, and it pays for tail risk.
 * Win rate is P(profit at expiry), NOT safety: short options win often and lose big.
 *
 * Terminal distribution: GBM ⇒ ln S_T ~ N(ln S + (μ − σ²/2)T, σ²T), one scenario σ for the world
 * (each contract's own IV is what you trade AGAINST, not what you simulate WITH).
 * Expected payoffs are closed-form (Black-Scholes with μ in place of r, undiscounted):
 *   E[max(S_T−K,0)] = S·e^{μT}·N(d1μ) − K·N(d2μ)
 * P&L discounts the payoff at r: long = e^{−rT}·E[payoff] − mid; short = mid − e^{−rT}·E[payoff].
 * Pure — unit-tested. Educational — not advice.
 */

export type TradeKind = "long-call" | "short-call" | "long-put" | "short-put";

const d12 = (S: number, K: number, sigma: number, T: number, mu: number) => {
  const vt = sigma * Math.sqrt(T);
  const d1 = (Math.log(S / K) + (mu + 0.5 * sigma * sigma) * T) / vt;
  return { d1, d2: d1 - vt };
};

/** E[max(S_T − K, 0)] under GBM(μ, σ), undiscounted. */
export function evCall(S: number, K: number, sigma: number, T: number, mu: number): number {
  const { d1, d2 } = d12(S, K, sigma, T, mu);
  return S * Math.exp(mu * T) * ncdf(d1) - K * ncdf(d2);
}
/** E[max(K − S_T, 0)] under GBM(μ, σ), undiscounted. */
export function evPut(S: number, K: number, sigma: number, T: number, mu: number): number {
  const { d1, d2 } = d12(S, K, sigma, T, mu);
  return K * ncdf(-d2) - S * Math.exp(mu * T) * ncdf(-d1);
}
/** P(S_T > level) under GBM(μ, σ). */
export function probAbove(S: number, level: number, sigma: number, T: number, mu: number): number {
  if (level <= 0) return 1;
  return ncdf((Math.log(S / level) + (mu - 0.5 * sigma * sigma) * T) / (sigma * Math.sqrt(T)));
}

export interface TradeEval {
  kind: TradeKind;
  premium: number; // per share (market mid)
  expPnl: number; // per share, under the scenario
  winRate: number; // P(profit at expiry)
  breakeven: number;
  maxLoss: number; // per share; Infinity for short calls
}

export interface StrikeScan {
  strike: number;
  callMid: number | null;
  putMid: number | null;
  callIv: number | null; // market IV (solved from mid; vendor fallback)
  putIv: number | null;
  trades: TradeEval[]; // evaluated trades at this strike
  best: TradeEval | null; // highest expected P&L
}

export interface ScanScenario {
  sigma: number; // scenario vol (annualized) driving the terminal distribution
  mu: number; // annualized drift of the underlying
  r?: number; // discount rate for the payoff leg
  q?: number;
}

const mid = (c: OptionContract): number | null =>
  c.bid != null && c.ask != null && c.ask > 0 && c.ask >= c.bid ? (c.bid + c.ask) / 2 : c.last != null && c.last > 0 ? c.last : null;

export function evalTrades(strike: number, callMid: number | null, putMid: number | null, S: number, T: number, sc: ScanScenario): TradeEval[] {
  const { sigma, mu } = sc;
  const df = Math.exp(-(sc.r ?? 0) * T);
  const out: TradeEval[] = [];
  if (callMid != null && callMid > 0) {
    const ev = df * evCall(S, strike, sigma, T, mu);
    const be = strike + callMid;
    const pAbove = probAbove(S, be, sigma, T, mu);
    out.push({ kind: "long-call", premium: callMid, expPnl: ev - callMid, winRate: pAbove, breakeven: be, maxLoss: callMid });
    out.push({ kind: "short-call", premium: callMid, expPnl: callMid - ev, winRate: 1 - pAbove, breakeven: be, maxLoss: Infinity });
  }
  if (putMid != null && putMid > 0) {
    const ev = df * evPut(S, strike, sigma, T, mu);
    const be = strike - putMid;
    const pAbove = probAbove(S, be, sigma, T, mu);
    out.push({ kind: "long-put", premium: putMid, expPnl: ev - putMid, winRate: 1 - pAbove, breakeven: be, maxLoss: putMid });
    out.push({ kind: "short-put", premium: putMid, expPnl: putMid - ev, winRate: pAbove, breakeven: be, maxLoss: Math.max(0, strike - putMid) });
  }
  return out;
}

/** Scan one expiry's strikes around spot. Contracts must already be filtered to the expiry. */
export function scanStrikes(contracts: OptionContract[], spot: number | null, sc: ScanScenario, maxStrikes = 17): StrikeScan[] {
  if (spot == null || spot <= 0 || !(sc.sigma > 0) || !contracts.length) return [];
  const dte = contracts.find((c) => c.dte != null)?.dte ?? null;
  if (dte == null) return [];
  const T = Math.max(dte, 0.5) / 365;

  let strikes = [...new Set(contracts.map((c) => c.strike))].sort((a, b) => a - b);
  if (strikes.length > maxStrikes) {
    const iAtm = strikes.reduce((best, k, i) => (Math.abs(k - spot) < Math.abs(strikes[best] - spot) ? i : best), 0);
    const half = Math.floor(maxStrikes / 2);
    strikes = strikes.slice(Math.max(0, iAtm - half), Math.max(0, iAtm - half) + maxStrikes);
  }

  return strikes.map((k) => {
    const call = contracts.find((c) => c.strike === k && c.type === "call");
    const put = contracts.find((c) => c.strike === k && c.type === "put");
    const cm = call ? mid(call) : null;
    const pm = put ? mid(put) : null;
    const ivOf = (c: OptionContract | undefined, m: number | null): number | null => {
      if (!c) return null;
      const solved = m != null ? bsImpliedVol({ type: c.type, spot, strike: k, tYears: T, r: sc.r ?? 0, q: sc.q ?? 0 }, m) : null;
      return solved ?? (c.impliedVolatility != null && c.impliedVolatility > 0 ? c.impliedVolatility : null);
    };
    const trades = evalTrades(k, cm, pm, spot, T, sc);
    const best = trades.length ? trades.reduce((m2, t) => (t.expPnl > m2.expPnl ? t : m2)) : null;
    return { strike: k, callMid: cm, putMid: pm, callIv: ivOf(call, cm), putIv: ivOf(put, pm), trades, best };
  });
}
