import { clockFor } from "../clock";
import { overnightSessions, type OvernightSession } from "../overnight";
import type { Bar, EntryIntent, Instrument, Params, Strategy } from "../types";

/**
 * Fade the overnight gap back toward the prior cash close.
 *
 * Mechanism: an overnight gap is priced in thin Globex liquidity by participants who cannot size,
 * against news the cash session has not yet voted on. When the gap is LARGE relative to yesterday's
 * range, it represents a price the deep-liquidity session never agreed to, and the cash auction
 * frequently drags it back toward the last price it did agree to — the prior close.
 *
 * The counter-intuitive part, and the reason the size filter is the strategy rather than a detail:
 * small gaps fill far more often (about 80% versus about 35%) and yet are a significantly LOSING
 * trade, while large gaps fill rarely and are a significantly winning one. A high eventual-touch
 * rate is not a win rate. With a small gap the target is close but so is the stop, and the fill
 * routinely arrives after the stop was hit; with a large gap both levels are far and the trade has
 * room to work. Trading gap fills on the strength of the fill rate gets the sign backwards.
 *
 * `minGapRatio` is measured against the prior cash session's RANGE rather than in points, so the
 * filter keeps its meaning as volatility drifts.
 */
export const gapFade: Strategy = {
  id: "gap-fade",
  label: "Overnight gap fade (size-filtered)",
  family: "mean-reversion",
  rationale:
    "A large overnight gap is a price set in thin Globex liquidity that the deep cash session never agreed to, and the cash auction drags it back toward the last agreed price.",
  defaults: { minGapRatio: 0.6, maxGapRatio: 99, rrStop: 0.5, entryDelayBars: 1, minGapPts: 5, sideMode: 0, maxBars: 999 },
  space: {
    /** Minimum gap as a fraction of the prior cash range. The whole strategy lives here. */
    minGapRatio: { values: [0.25, 0.4, 0.6, 0.8] },
    maxGapRatio: { values: [99] },
    /** Stop as a multiple of the gap. 0.5 is 2:1 reward-to-risk, 1.0 is 1:1. */
    rrStop: { values: [0.5, 0.75, 1.0] },
    /** Bars after the cash open before entering; the measurement used the open itself. */
    entryDelayBars: { values: [1, 3, 6] },
    minGapPts: { values: [5, 20, 40] },
    sideMode: { values: [0, 1, -1] },
    maxBars: { values: [999] },
  },
  build(bars: Bar[], p: Params, inst: Instrument) {
    const clock = clockFor(bars, inst.tz);
    // Needs the FULL 23-hour series: the gap is formed overnight, outside the cash session.
    const sessions = overnightSessions(bars, inst, inst.session[0], inst.session[1]);
    const byDay = new Map<number, OvernightSession>();
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
      if (!s) return null;
      if (i < s.from + p.entryDelayBars || i >= s.to) return null;

      const ratio = Math.abs(s.gapInPriorRanges);
      if (ratio < p.minGapRatio || ratio > p.maxGapRatio) return null;
      const dist = Math.abs(s.gap);
      if (dist < p.minGapPts) return null;

      const side: 1 | -1 = s.gap > 0 ? -1 : 1; // fade toward the prior cash close
      if (p.sideMode !== 0 && p.sideMode !== side) return null;

      const entry = bars[i].c;
      const target = s.priorRthClose;
      // Only act while the gap is still open; once price is through the prior close there is no trade.
      if (side === 1 && entry >= target) return null;
      if (side === -1 && entry <= target) return null;

      const stopDist = dist * p.rrStop;
      if (stopDist < inst.tickSize) return null;

      used = true;
      return {
        side,
        stopPrice: entry - side * stopDist,
        targetPrice: target,
        stopDist,
        targetDist: Math.abs(target - entry),
        maxBars: p.maxBars,
        tag: `gap-${side === 1 ? "long" : "short"}`,
      };
    };
  },
};
