import type { HistoryBar, OptionContract } from "../barchart/types";
import { bsCharm, bsVanna } from "./greeks";

const CONTRACT = 100; // shares per contract
const TRADING_DAYS = 252;
const CALENDAR_DAYS = 365;

export interface StrikeGex {
  strike: number;
  callGex: number; // >= 0
  putGex: number; // <= 0
  gex: number; // callGex + putGex (net)
}

function midOf(c: OptionContract): number {
  if (c.bid != null && c.ask != null && c.ask > 0) return (c.bid + c.ask) / 2;
  return c.last ?? 0;
}

/** Dollar gamma exposure per 1% move, aggregated by strike (calls +, puts -). */
export function gexByStrike(chain: OptionContract[], spot: number | null): StrikeGex[] {
  if (!spot) return [];
  const m = new Map<number, { call: number; put: number }>();
  for (const c of chain) {
    if (c.gamma == null || c.openInterest == null) continue;
    const g = c.gamma * c.openInterest * CONTRACT * spot * spot * 0.01;
    const e = m.get(c.strike) ?? { call: 0, put: 0 };
    if (c.type === "call") e.call += g;
    else e.put += g;
    m.set(c.strike, e);
  }
  return [...m.entries()]
    .map(([strike, v]) => ({ strike, callGex: v.call, putGex: -v.put, gex: v.call - v.put }))
    .sort((a, b) => a.strike - b.strike);
}

export function netGex(chain: OptionContract[], spot: number | null): number | null {
  const by = gexByStrike(chain, spot);
  return by.length ? by.reduce((s, x) => s + x.gex, 0) : null;
}

export interface ExpGex {
  expiration: string;
  dte: number | null;
  gex: number;
}

/** Net dealer GEX aggregated by expiration (the gamma term structure). */
export function gexByExpiration(chain: OptionContract[], spot: number | null): ExpGex[] {
  if (!spot) return [];
  const m = new Map<string, { gex: number; dte: number | null }>();
  for (const c of chain) {
    if (c.gamma == null || c.openInterest == null) continue;
    const g = (c.type === "call" ? 1 : -1) * c.gamma * c.openInterest * CONTRACT * spot * spot * 0.01;
    const e = m.get(c.expiration) ?? { gex: 0, dte: c.dte };
    e.gex += g;
    if (e.dte == null) e.dte = c.dte;
    m.set(c.expiration, e);
  }
  return [...m.entries()]
    .map(([expiration, v]) => ({ expiration, dte: v.dte, gex: v.gex }))
    .sort((a, b) => a.expiration.localeCompare(b.expiration));
}

/** Aggregate notional delta of open interest (calls +, puts -). */
export function netDex(chain: OptionContract[], spot: number | null): number | null {
  if (!spot) return null;
  let d = 0;
  let any = false;
  for (const c of chain) {
    if (c.delta == null || c.openInterest == null) continue;
    any = true;
    d += c.delta * c.openInterest * CONTRACT * spot;
  }
  return any ? d : null;
}

/** Zero-gamma level: where cumulative net GEX (low→high strike) crosses zero. */
export function gammaFlip(by: StrikeGex[]): number | null {
  if (by.length < 2) return null;
  let cum = 0;
  let prevCum = 0;
  let prevStrike = by[0].strike;
  for (const x of by) {
    prevCum = cum;
    cum += x.gex;
    if ((prevCum < 0 && cum >= 0) || (prevCum > 0 && cum <= 0)) {
      const denom = Math.abs(cum - prevCum);
      const t = denom === 0 ? 0 : Math.abs(prevCum) / denom;
      return prevStrike + (x.strike - prevStrike) * t;
    }
    prevStrike = x.strike;
  }
  return null;
}

export function callWall(by: StrikeGex[]): number | null {
  return by.length ? by.reduce((m, x) => (x.callGex > m.callGex ? x : m)).strike : null;
}

export function putWall(by: StrikeGex[]): number | null {
  return by.length ? by.reduce((m, x) => (x.putGex < m.putGex ? x : m)).strike : null;
}

/** Max-pain strike for an expiration: minimizes total in-the-money value owed to holders. */
export function maxPain(chain: OptionContract[], expiration: string): number | null {
  const opts = chain.filter((c) => c.expiration === expiration && c.openInterest != null);
  const strikes = [...new Set(opts.map((c) => c.strike))].sort((a, b) => a - b);
  if (!strikes.length) return null;
  let best = strikes[0];
  let bestVal = Infinity;
  for (const s of strikes) {
    let total = 0;
    for (const c of opts) {
      const oi = c.openInterest ?? 0;
      total += c.type === "call" ? Math.max(0, s - c.strike) * oi : Math.max(0, c.strike - s) * oi;
    }
    if (total < bestVal) {
      bestVal = total;
      best = s;
    }
  }
  return best;
}

/** Expected move from the ATM straddle for an expiration. */
export function expectedMove(
  chain: OptionContract[],
  spot: number | null,
  expiration: string,
): { abs: number; pct: number } | null {
  if (!spot) return null;
  const opts = chain.filter((c) => c.expiration === expiration);
  if (!opts.length) return null;
  const strikes = [...new Set(opts.map((c) => c.strike))];
  const atm = strikes.reduce((p, s) => (Math.abs(s - spot) < Math.abs(p - spot) ? s : p), strikes[0]);
  const call = opts.find((c) => c.strike === atm && c.type === "call");
  const put = opts.find((c) => c.strike === atm && c.type === "put");
  const abs = (call ? midOf(call) : 0) + (put ? midOf(put) : 0);
  return abs > 0 ? { abs, pct: abs / spot } : null;
}

/**
 * True 1-day (1σ) expected move from annualized ATM IV: spot × IV × √(1/252). Unlike the ATM
 * straddle (which prices the move all the way TO the expiration), this is a single-session range —
 * the correct number for "1D Max/Min" levels and intraday scalp targets.
 */
export function expectedMove1D(spot: number | null, iv: number | null): { abs: number; pct: number } | null {
  if (!spot || iv == null || iv <= 0) return null;
  const pct = iv * Math.sqrt(1 / TRADING_DAYS);
  return { abs: spot * pct, pct };
}

export function putCallRatio(chain: OptionContract[]): { vol: number | null; oi: number | null } {
  let cv = 0;
  let pv = 0;
  let co = 0;
  let po = 0;
  for (const c of chain) {
    if (c.type === "call") {
      cv += c.volume ?? 0;
      co += c.openInterest ?? 0;
    } else {
      pv += c.volume ?? 0;
      po += c.openInterest ?? 0;
    }
  }
  return { vol: cv > 0 ? pv / cv : null, oi: co > 0 ? po / co : null };
}

/** Annualized close-to-close realized volatility over the last `window` returns. */
export function realizedVol(bars: HistoryBar[], window: number): number | null {
  const closes = bars.map((b) => b.close).filter((x) => x > 0);
  if (closes.length < window + 1) return null;
  const slice = closes.slice(-(window + 1));
  const rets: number[] = [];
  for (let i = 1; i < slice.length; i++) rets.push(Math.log(slice[i] / slice[i - 1]));
  const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
  const varc = rets.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(1, rets.length - 1);
  return Math.sqrt(varc * 252);
}

/** ATM implied vol (avg of nearest-strike call+put IV) for an expiration. */
export function atmIv(chain: OptionContract[], spot: number | null, expiration: string): number | null {
  if (!spot) return null;
  const opts = chain.filter((c) => c.expiration === expiration && c.impliedVolatility != null && c.impliedVolatility > 0);
  if (!opts.length) return null;
  const strikes = [...new Set(opts.map((c) => c.strike))];
  const atm = strikes.reduce((p, s) => (Math.abs(s - spot) < Math.abs(p - spot) ? s : p), strikes[0]);
  const ivs = opts.filter((c) => c.strike === atm).map((c) => c.impliedVolatility as number);
  return ivs.length ? ivs.reduce((a, b) => a + b, 0) / ivs.length : null;
}

export interface ExpIv {
  expiration: string;
  dte: number | null;
  iv: number | null;
}

/** ATM IV per expiration — the implied-vol term structure. */
export function ivTermStructure(chain: OptionContract[], spot: number | null): ExpIv[] {
  return [...new Set(chain.map((c) => c.expiration))]
    .sort()
    .map((e) => ({ expiration: e, dte: chain.find((c) => c.expiration === e)?.dte ?? null, iv: atmIv(chain, spot, e) }));
}

export interface StrikeOi {
  strike: number;
  callOi: number;
  putOi: number;
}

/** Open interest aggregated by strike (calls vs puts). */
export function oiByStrike(chain: OptionContract[]): StrikeOi[] {
  const m = new Map<number, { c: number; p: number }>();
  for (const x of chain) {
    if (x.openInterest == null) continue;
    const e = m.get(x.strike) ?? { c: 0, p: 0 };
    if (x.type === "call") e.c += x.openInterest;
    else e.p += x.openInterest;
    m.set(x.strike, e);
  }
  return [...m.entries()].map(([strike, v]) => ({ strike, callOi: v.c, putOi: v.p })).sort((a, b) => a.strike - b.strike);
}

export interface SecondOrderStrike {
  strike: number;
  vanna: number; // $ notional delta per 1 IV-point move
  charm: number; // $ notional delta drift per calendar day
}

export interface SecondOrder {
  vanna: number | null; // net dealer vanna exposure ($ delta / 1 vol-pt)
  charm: number | null; // net dealer charm exposure ($ delta / day)
  byStrike: SecondOrderStrike[];
}

/**
 * Dealer second-order exposure — Vanna (∂Δ/∂σ) and Charm (∂Δ/∂t) — derived per contract via
 * Black-Scholes from spot/strike/DTE/IV, then aggregated with the SAME dealer sign convention as
 * GEX (calls +, puts −, i.e. dealers long calls / short puts).
 *
 * - Vanna exposure is expressed as $ notional delta per **1 IV point** move.
 * - Charm exposure is expressed as $ notional delta drift per **calendar day**.
 */
export function secondOrderExposure(chain: OptionContract[], spot: number | null): SecondOrder {
  if (!spot) return { vanna: null, charm: null, byStrike: [] };
  const m = new Map<number, { v: number; c: number }>();
  let anyV = false;
  let anyC = false;
  for (const o of chain) {
    if (o.openInterest == null || o.impliedVolatility == null || o.impliedVolatility <= 0) continue;
    const tYears = Math.max(o.dte ?? 0, 0.5) / CALENDAR_DAYS; // floor 0DTE at ~half a session
    const sign = o.type === "call" ? 1 : -1;
    const e = m.get(o.strike) ?? { v: 0, c: 0 };
    const va = bsVanna(spot, o.strike, o.impliedVolatility, tYears);
    const ch = bsCharm(spot, o.strike, o.impliedVolatility, tYears);
    // vanna is per 1.00 (=100 vol-pt) σ; ×0.01 →per 1 vol-pt; ×OI×100 shares ×spot → $; the
    // 0.01 and 100 cancel, leaving vanna·OI·spot.
    if (va != null) {
      e.v += sign * va * o.openInterest * spot;
      anyV = true;
    }
    // charm is per year; /365 → per day; ×OI×100 shares ×spot → $ notional delta drift / day.
    if (ch != null) {
      e.c += (sign * (ch / CALENDAR_DAYS) * o.openInterest * CONTRACT * spot);
      anyC = true;
    }
    m.set(o.strike, e);
  }
  const byStrike = [...m.entries()]
    .map(([strike, x]) => ({ strike, vanna: x.v, charm: x.c }))
    .sort((a, b) => a.strike - b.strike);
  return {
    vanna: anyV ? byStrike.reduce((s, x) => s + x.vanna, 0) : null,
    charm: anyC ? byStrike.reduce((s, x) => s + x.charm, 0) : null,
    byStrike,
  };
}

export function fmtUsd(v: number): string {
  const a = Math.abs(v);
  const s = v < 0 ? "−" : "";
  if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(0)}K`;
  return `${s}$${Math.round(a)}`;
}
