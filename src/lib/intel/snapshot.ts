import type { OptionContract } from "../barchart/types";
import { atmIv, dexByStrike, gammaFlip, gexByStrike, netDex, netGex, putCallRatio } from "../flow/analytics";

/**
 * Daily per-strike positioning snapshots.
 *
 * The aggregate series (gex-history) answers "what was net GEX on Tuesday?", but not "where were the
 * walls?" — and expired chains can't be re-fetched from any free feed, so the shape of a past day's
 * dealer book is lost unless we record it as it happens. This captures a compact by-strike snapshot
 * (strike, GEX, DEX, call/put OI) once per calendar day, latest write of the day winning, so the day
 * ends up holding its closing picture.
 *
 * Compact on purpose: field names are single letters and values are rounded, because the whole set is
 * committed to the data branch every cycle. ~40 strikes/day/symbol ≈ a few KB.
 *
 * Pure — no network/IO — so it is unit-tested.
 */

export interface StrikeSnap {
  k: number; // strike
  g: number; // net dealer GEX at the strike ($/1%)
  d: number; // net dealer DEX at the strike ($ notional)
  co: number; // call open interest
  po: number; // put open interest
}

export interface DaySnapshot {
  day: string; // YYYY-MM-DD (UTC)
  t: number; // epoch ms this snapshot was taken
  spot: number | null;
  gex: number | null; // net, $/1%
  dex: number | null; // net, $ notional
  flip: number | null; // gamma-flip level
  iv: number | null; // front-expiry ATM IV
  pcr: number | null; // put/call volume ratio
  strikes: StrikeSnap[]; // ascending by strike
}

export const SNAPSHOT_CAP = 90; // ~3 months of daily snapshots per symbol

export const utcDay = (t: number): string => new Date(t).toISOString().slice(0, 10);

const r = (v: number, dp = 0): number => {
  const f = 10 ** dp;
  return Math.round(v * f) / f;
};

/** Build the day's per-strike snapshot from a live chain. Returns null when the chain can't support it. */
export function buildSnapshot(chain: OptionContract[], spot: number | null, now: number): DaySnapshot | null {
  if (!chain.length || spot == null || spot <= 0) return null;

  const gexRows = gexByStrike(chain, spot);
  const dexRows = dexByStrike(chain, spot);
  if (!gexRows.length && !dexRows.length) return null;

  const oi = new Map<number, { co: number; po: number }>();
  for (const c of chain) {
    if (c.openInterest == null) continue;
    const e = oi.get(c.strike) ?? { co: 0, po: 0 };
    if (c.type === "call") e.co += c.openInterest;
    else e.po += c.openInterest;
    oi.set(c.strike, e);
  }

  const dexAt = new Map(dexRows.map((x) => [x.strike, x.dex]));
  const strikeSet = new Set<number>([...gexRows.map((x) => x.strike), ...dexRows.map((x) => x.strike)]);
  const strikes: StrikeSnap[] = [...strikeSet]
    .sort((a, b) => a - b)
    .map((k) => {
      const g = gexRows.find((x) => x.strike === k)?.gex ?? 0;
      const e = oi.get(k) ?? { co: 0, po: 0 };
      return { k, g: r(g), d: r(dexAt.get(k) ?? 0), co: e.co, po: e.po };
    });

  const exps = [...new Set(chain.map((c) => c.expiration))].sort();
  const frontExp = exps.find((e) => (chain.find((c) => c.expiration === e)?.dte ?? -1) >= 0) ?? exps[0];
  const iv = frontExp ? atmIv(chain, spot, frontExp) : null;
  const gex = netGex(chain, spot);
  const dex = netDex(chain, spot);

  return {
    day: utcDay(now),
    t: now,
    spot: r(spot, 4),
    gex: gex == null ? null : r(gex),
    dex: dex == null ? null : r(dex),
    flip: gammaFlip(gexRows),
    iv,
    pcr: putCallRatio(chain).vol,
    strikes,
  };
}

/**
 * Merge a new snapshot into the stored list: one entry per day (the latest write of that day wins, so
 * the stored day converges on its closing picture), sorted ascending, capped to the most recent days.
 */
export function mergeSnapshots(prev: DaySnapshot[], next: DaySnapshot | null, cap = SNAPSHOT_CAP): DaySnapshot[] {
  const byDay = new Map<string, DaySnapshot>();
  for (const s of prev) if (s && s.day) byDay.set(s.day, s);
  if (next) {
    const existing = byDay.get(next.day);
    // keep the newer of the two so out-of-order writes can't rewind a day
    if (!existing || next.t >= existing.t) byDay.set(next.day, next);
  }
  return [...byDay.values()].sort((a, b) => a.day.localeCompare(b.day)).slice(-cap);
}
