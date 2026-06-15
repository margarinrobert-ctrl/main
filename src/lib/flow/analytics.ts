import type { OptionContract } from "../barchart/types";

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
