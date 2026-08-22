import { clockFor, minutesSinceOpen, sessionIndex } from "../clock";
import { atr } from "../series";
import type { Bar, EntryIntent, Instrument, Params, Strategy } from "../types";

/**
 * Initial Balance breakout-retracement.
 *
 * Mechanism: the first hour of the NY session is where overnight information gets repriced by the
 * participants who actually move size. The high and low of that hour become the day's reference
 * auction — the levels every intraday desk is watching. A break of one edge signals the auction has
 * resolved in that direction, but the break itself is the worst price of the move: it is where
 * breakout traders pay up and where the resting stops get filled. The retracement back INTO the
 * range is the same directional bet at a price that leaves room for a stop, which is what makes the
 * geometry survivable at futures cost levels.
 *
 * The published geometry (25% retracement entry, 60% stop, 50% target, all as fractions of the IB
 * range) is a fixed 2.14 : 1 reward-to-risk before costs. Every one of those numbers is a parameter
 * here, because the whole point of the research stack is to find out whether the published values
 * are special or merely one point on a flat surface.
 *
 * Modelling notes, all conservative:
 *   - The IB is finalised only after the window has closed. Nothing is traded while it forms.
 *   - The break is a wick through the edge, detected on a closed bar.
 *   - The entry is a REAL resting limit order: it fills only if price trades through it, and it is
 *     cancelled at the session close if it never does. Modelling it as a market order would measure
 *     a different and much easier strategy.
 *   - One trade per day. A break of a side that is disabled still burns the day.
 */
export const initialBalance: Strategy = {
  id: "initial-balance",
  label: "Initial Balance breakout-retracement",
  family: "breakout",
  rationale:
    "The first hour's range is the day's reference auction; a break signals resolution, and the retracement into the range buys that resolution at a price that leaves room for a stop.",
  defaults: {
    ibMinutes: 60,
    retrPct: 25,
    stopPct: 60,
    targetPct: 50,
    minRangePct: 0,
    maxRangePct: 100,
    sideMode: 0,
    breakBuffer: 0,
    rrMode: 0,
    rrMult: 2,
    stopMode: 0,
    atrLen: 14,
    atrMult: 1.5,
    stopPts: 40,
  },
  space: {
    /** Length of the initial-balance window in minutes, from the session open. */
    ibMinutes: { values: [30, 45, 60, 90] },
    /** Entry retracement into the range, as a percent of the IB range. */
    retrPct: { values: [10, 25, 40, 50] },
    /** Stop, as a percent of the IB range measured from the broken edge. */
    stopPct: { values: [40, 60, 80, 100] },
    /** Target, as a percent of the IB range beyond the broken edge. */
    targetPct: { values: [25, 50, 75, 100, 150] },
    /** Skip days whose IB range is below this percentile of the trailing 60-day distribution. */
    minRangePct: { values: [0, 20, 40] },
    /** Skip days whose IB range is above this percentile. */
    maxRangePct: { values: [60, 80, 100] },
    /** 0 = both sides, 1 = longs only, -1 = shorts only. */
    sideMode: { values: [0, 1, -1] },
    /** Ticks beyond the edge required to count as a break. */
    breakBuffer: { values: [0, 2, 4] },
    /** 0 = target a percent of the IB range beyond the edge; 1 = a fixed multiple of the risk. */
    rrMode: { values: [0, 1] },
    /** Reward-to-risk multiple, used only when rrMode is 1. */
    rrMult: { values: [1, 1.5, 2, 3] },
    /**
     * Where the stop comes from. These are genuinely different trades, not the same trade with a
     * different number: 0 and 3 scale with the day's own auction, 1 scales with recent volatility,
     * and 2 does not scale at all.
     *   0 = a percent of the IB range measured from the broken edge (stopPct)
     *   1 = a multiple of ATR measured from the entry (atrLen, atrMult)
     *   2 = a fixed number of points from the entry (stopPts)
     *   3 = the opposite edge of the initial balance
     */
    stopMode: { values: [0, 1, 2, 3] },
    atrLen: { values: [14, 30] },
    atrMult: { values: [1, 1.5, 2, 3] },
    stopPts: { values: [20, 40, 60, 80] },
  },
  build(bars: Bar[], p: Params, inst: Instrument) {
    const clock = clockFor(bars, inst.tz);
    const sessionStart = inst.session[0];
    const n = bars.length;
    // Session-relative time and a session id whose boundary is the open, so an overnight session
    // (Asia, 18:00-03:00) is one session rather than two halves split at midnight.
    const sess = sessionIndex(clock, sessionStart);

    // ---- pass 1: build each session's initial balance, forward only ----
    const ibHigh = new Float64Array(n).fill(NaN);
    const ibLow = new Float64Array(n).fill(NaN);
    const ibReady = new Uint8Array(n);
    let curDay = -1;
    let hi = -Infinity;
    let lo = Infinity;
    let sawWindow = false;
    for (let i = 0; i < n; i++) {
      if (sess[i] !== curDay) {
        curDay = sess[i];
        hi = -Infinity;
        lo = Infinity;
        sawWindow = false;
      }
      const m = minutesSinceOpen(clock.minuteOfDay[i], sessionStart);
      if (m < p.ibMinutes) {
        hi = Math.max(hi, bars[i].h);
        lo = Math.min(lo, bars[i].l);
        sawWindow = true;
      } else if (sawWindow && hi > -Infinity) {
        // The window has closed: from here on the IB is final and safe to trade against.
        ibHigh[i] = hi;
        ibLow[i] = lo;
        ibReady[i] = 1;
      }
    }

    // ---- pass 2: trailing distribution of IB range, for the size filters ----
    // Built from PRIOR sessions only, so a day is never filtered using its own place in the
    // distribution — that would be a look-ahead the truncation test would not catch, because the
    // percentile of the last day barely moves when the series is cut there.
    const dayRange = new Map<number, number>();
    for (let i = 0; i < n; i++) if (ibReady[i] && !dayRange.has(sess[i])) dayRange.set(sess[i], ibHigh[i] - ibLow[i]);
    const days = [...dayRange.keys()].sort((a, b) => a - b);
    const rangePercentile = new Map<number, number>();
    const history: number[] = [];
    for (const day of days) {
      const r = dayRange.get(day)!;
      if (history.length >= 20) {
        const below = history.filter((x) => x < r).length;
        rangePercentile.set(day, (below / history.length) * 100);
      } else {
        rangePercentile.set(day, 50); // not enough history to filter on: treat as neutral
      }
      history.push(r);
      if (history.length > 60) history.shift();
    }

    // ATR for the volatility stop. Computed on the segment handed in, so on a session-filtered
    // series it is an ATR of session bars only — which is what a session strategy should use.
    const atrSeries = atr(bars, Math.max(2, Math.round(p.atrLen)));

    const buffer = p.breakBuffer * inst.tickSize;
    // Day-scoped state: which side has already been used, so the day is one trade only.
    let stateDay = -1;
    let usedSide = 0;

    return (i: number): EntryIntent | null => {
      const day = sess[i];
      if (day !== stateDay) {
        stateDay = day;
        usedSide = 0;
      }
      if (!ibReady[i] || usedSide !== 0) return null;

      const h = ibHigh[i];
      const l = ibLow[i];
      const range = h - l;
      if (!(range > 0)) return null;

      const pctl = rangePercentile.get(day) ?? 50;
      if (pctl < p.minRangePct || pctl > p.maxRangePct) return null;

      const bar = bars[i];
      const brokeUp = bar.h > h + buffer;
      const brokeDn = bar.l < l - buffer;
      if (!brokeUp && !brokeDn) return null;

      // A bar that takes out both sides is resolved by its own close direction.
      const side: 1 | -1 = brokeUp && brokeDn ? (bar.c >= bar.o ? 1 : -1) : brokeUp ? 1 : -1;
      usedSide = side; // the day is spent either way, even if this side is disabled below
      if (p.sideMode !== 0 && p.sideMode !== side) return null;

      const edge = side === 1 ? h : l;
      const entry = edge - side * (range * p.retrPct) / 100;

      let stop: number;
      switch (p.stopMode) {
        case 1: {
          const a = atrSeries[i];
          if (!(a > 0)) return null; // no ATR yet: refuse the trade rather than invent a stop
          stop = entry - side * p.atrMult * a;
          break;
        }
        case 2:
          stop = entry - side * p.stopPts;
          break;
        case 3:
          stop = side === 1 ? l : h; // the far edge of the range
          break;
        default:
          stop = edge - side * (range * p.stopPct) / 100;
      }

      // Whatever produced it, a stop on the wrong side of the entry is not a stop. This catches
      // stopPct <= retrPct, an ATR too small to clear the retracement, and a zero fixed distance.
      if (side * (entry - stop) <= 0) return null;
      // Two target conventions: a percent of the IB range beyond the broken edge, or a fixed
      // multiple of the actual risk. They are NOT the same trade — the second makes reward scale
      // with the entry-to-stop distance, so widening the stop also widens the target.
      const target =
        p.rrMode === 1
          ? entry + side * p.rrMult * Math.abs(entry - stop)
          : edge + side * (range * p.targetPct) / 100;

      return {
        side,
        limitPrice: entry,
        stopPrice: stop,
        targetPrice: target,
        stopDist: Math.abs(entry - stop),
        targetDist: Math.abs(target - entry),
        maxBars: 10_000, // the session exit is the real time stop
        tag: side === 1 ? "ib-long" : "ib-short",
      };
    };
  },
};
