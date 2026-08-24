import { clockFor } from "../clock";
import { atr } from "../series";
import { nakedPocsBySession, nearestNaked, sessionProfiles, type NakedPoc, type SessionProfile } from "../volumeProfile";
import type { Bar, EntryIntent, Instrument, Params, Strategy } from "../types";

/**
 * The Market Profile constructs the value-area study left untested: naked points of control and
 * low-volume nodes.
 *
 * NAKED POC — a prior session's point of control that price has not traded through since. Auction
 * theory calls it unfinished business: the most volume changed hands there, so both sides accepted
 * that price, and an untouched one is argued to remain a magnet. It is one of the few Market Profile
 * ideas that makes a falsifiable claim about a SPECIFIC price rather than a zone, which is exactly
 * why it deserves a test rather than an assumption.
 *
 * LOW-VOLUME NODE — a price inside the value area where little business was done. Two incompatible
 * stories are told about them and both are tested here: that price REJECTS from them (thin liquidity
 * means the auction failed there before and will again), and that price ACCELERATES through them
 * (nothing to slow it down). They cannot both be right, and the data can say which.
 */
export const profileLevels: Strategy = {
  id: "profile-levels",
  label: "Naked POC magnet / low-volume node reaction",
  family: "liquidity",
  rationale:
    "An untouched prior point of control is unfinished auction business and argued to act as a magnet; a low-volume node is a price the auction rejected once already.",
  defaults: { mode: 0, minTargetPts: 40, rrStop: 1, entryDelayBars: 3, maxAgeDays: 30, maxDistPts: 200, sideMode: 0, binTicks: 4, maxBars: 999 },
  space: {
    /** 0 = trade toward the nearest naked POC, 1 = fade a low-volume node, 2 = trade the break through one. */
    mode: { values: [0, 1, 2] },
    minTargetPts: { values: [40] },
    rrStop: { values: [0.5, 0.75, 1] },
    entryDelayBars: { values: [1, 3, 6] },
    /** Ignore naked POCs older than this many sessions — stale unfinished business. */
    maxAgeDays: { values: [5, 10, 30, 90] },
    /** Ignore targets further away than this, in points; they are unreachable in a session. */
    maxDistPts: { values: [120, 200, 300] },
    sideMode: { values: [0, 1, -1] },
    binTicks: { values: [4] },
    maxBars: { values: [999] },
  },
  build(bars: Bar[], p: Params, inst: Instrument) {
    const clock = clockFor(bars, inst.tz);
    const a = atr(bars, 14);
    const sessions = sessionProfiles(bars, inst, Math.round(p.binTicks), 60);
    const naked = nakedPocsBySession(bars, sessions);
    const byDay = new Map<number, SessionProfile>();
    for (const s of sessions) byDay.set(s.day, s);

    let stateDay = -1;
    let used = false;

    return (i: number): EntryIntent | null => {
      const day = clock.dayIndex[i];
      if (day !== stateDay) {
        stateDay = day;
        used = false;
      }
      if (used) return null;
      const s = byDay.get(day);
      if (!s || !s.prior) return null;
      if (i - s.from < p.entryDelayBars) return null;
      const av = a[i];
      if (!Number.isFinite(av) || av <= 0) return null;

      const price = bars[i].c;
      let side: 1 | -1;
      let target: number;

      if (p.mode === 0) {
        // Trade toward the nearest naked POC that is far enough to satisfy the target minimum.
        const list = (naked.get(day) ?? []).filter((n: NakedPoc) => n.age <= p.maxAgeDays);
        if (!list.length) return null;
        const { above, below } = nearestNaked(list, price);
        const candidates = [above, below].filter((n): n is NakedPoc => !!n);
        const usable = candidates
          .map((n) => ({ n, d: Math.abs(n.price - price) }))
          .filter((x) => x.d >= p.minTargetPts && x.d <= p.maxDistPts)
          .sort((x, y) => x.d - y.d);
        if (!usable.length) return null;
        target = usable[0].n.price;
        side = target > price ? 1 : -1;
      } else {
        // Low-volume nodes come from the PRIOR session's profile, so they are fixed before today
        // trades. Find the one price is currently interacting with.
        const lvns = s.prior.lowVolumeNodes;
        if (!lvns.length) return null;
        let nearest = lvns[0];
        for (const v of lvns) if (Math.abs(v - price) < Math.abs(nearest - price)) nearest = v;
        // "Interacting" means this bar's range straddles the node.
        if (!(bars[i].l <= nearest && bars[i].h >= nearest)) return null;

        if (p.mode === 1) {
          // Rejection: the bar touched the node and closed back away from it. Fade toward the POC.
          side = price > nearest ? 1 : -1;
          target = s.prior.poc;
          if (Math.abs(target - price) < p.minTargetPts) return null;
        } else {
          // Acceleration: the bar closed THROUGH the node; ride it to the far edge of value.
          side = price > nearest ? 1 : -1;
          target = side === 1 ? s.prior.vah : s.prior.val;
          if (Math.abs(target - price) < p.minTargetPts) {
            // Value area is too close to be a target; extend by the value-area width instead.
            target = price + side * (s.prior.vah - s.prior.val);
          }
        }
      }

      const targetDist = Math.abs(target - price);
      if (targetDist < p.minTargetPts || targetDist > p.maxDistPts) return null;
      if (p.sideMode !== 0 && p.sideMode !== side) return null;
      const stopDist = targetDist * p.rrStop;
      if (stopDist < inst.tickSize) return null;

      used = true;
      return {
        side,
        stopPrice: price - side * stopDist,
        targetPrice: target,
        stopDist,
        targetDist,
        maxBars: p.maxBars,
        tag: `pl${p.mode}-${side === 1 ? "long" : "short"}`,
      };
    };
  },
};
