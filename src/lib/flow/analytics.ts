import type { HistoryBar, OptionContract } from "../barchart/types";

const CONTRACT = 100; // shares per contract

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

export function fmtUsd(v: number): string {
  const a = Math.abs(v);
  const s = v < 0 ? "−" : "";
  if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(0)}K`;
  return `${s}$${Math.round(a)}`;
}
