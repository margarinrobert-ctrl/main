import { clockFor } from "../clock";
import { atr } from "../series";
import { sessionProfiles, type SessionProfile } from "../volumeProfile";
import type { Bar, EntryIntent, Instrument, Params, Strategy } from "../types";

/**
 * Value-area strategies from auction-market theory.
 *
 * Mechanism: yesterday's value area is where business got done at prices both sides accepted. When
 * today opens OUTSIDE it, the market is advertising a price that was not accepted yesterday, and it
 * must either attract new business there (acceptance, a trend day) or return to the prior area of
 * agreement (rejection, a rotation). Base rates on three years of NQ say rejection is the more
 * common outcome: opening above prior value, price returns to touch the prior VAH 65% of sessions
 * in the research half and 64% in the holdout.
 *
 * Modes, chosen from those base rates rather than from what is commonly published:
 *   0  FADE TO NEAR EDGE — open outside value, target the near value-area edge. The highest base
 *      rate available (65%), and the distance is usually large because opens outside value gap.
 *   1  TRAVERSE (the "80% rule") — open outside value, wait for price to re-enter and hold, then
 *      target the FAR edge. Conditional on re-entry the traverse completes 41% of the time in both
 *      halves; the payoff is the whole value-area width.
 *   2  POC ROTATION — open inside value, target the prior point of control. Highest raw hit rate of
 *      all (80% / 74%) but the distance is usually small, so it collides with a 40-point minimum.
 *   3  ACCEPTANCE CONTINUATION — open outside value and hold there, betting on a trend day.
 *
 * LOOK-AHEAD DISCIPLINE: the session profile object carries today's completed profile and day type,
 * which are NOT knowable during the session. This strategy reads only `prior`, `open` and
 * `openLocation` — all fixed at the opening bell — plus bars up to `i`.
 */
export const valueArea: Strategy = {
  id: "value-area",
  label: "Value-area rotation (auction-market theory)",
  family: "mean-reversion",
  rationale:
    "Yesterday's value area is the price range both sides accepted; opening outside it advertises an unaccepted price, which the market more often rejects than accepts.",
  defaults: { mode: 0, minTargetPts: 40, rrStop: 1, entryDelayBars: 3, maxBars: 999, holdBars: 2, sideMode: 0, minGapPts: 0, binTicks: 4 },
  space: {
    mode: { values: [0, 1, 2, 3] },
    /** Minimum structural target in POINTS. Setups offering less are skipped entirely. */
    minTargetPts: { values: [40] },
    /** Stop distance as a fraction of the target. 1 = 1:1; lower is a wider reward-to-risk. */
    rrStop: { values: [0.5, 0.75, 1] },
    /** Bars after the open before an entry is allowed, so the opening auction can resolve. */
    entryDelayBars: { values: [1, 3, 6, 12] },
    maxBars: { values: [999] },
    /** Mode 1 only: consecutive bars price must hold inside the value area to count as re-entry. */
    holdBars: { values: [1, 2, 4] },
    sideMode: { values: [0, 1, -1] },
    /** Skip sessions whose gap from the prior close is smaller than this, in points. */
    minGapPts: { values: [0, 20, 40] },
    binTicks: { values: [4] },
  },
  build(bars: Bar[], p: Params, inst: Instrument) {
    const clock = clockFor(bars, inst.tz);
    const a = atr(bars, 14);
    const profiles = sessionProfiles(bars, inst, Math.round(p.binTicks), 60);
    const byDay = new Map<number, SessionProfile>();
    for (const s of profiles) byDay.set(s.day, s);

    const minTarget = p.minTargetPts;
    let stateDay = -1;
    let used = false;
    let insideRun = 0;

    return (i: number): EntryIntent | null => {
      const day = clock.dayIndex[i];
      if (day !== stateDay) {
        stateDay = day;
        used = false;
        insideRun = 0;
      }
      const s = byDay.get(day);
      if (!s || !s.prior || !s.openLocation) return null;
      const prior = s.prior;
      const bar = bars[i];

      // Track how long price has been inside the prior value area (mode 1 needs it).
      const inside = bar.c <= prior.vah && bar.c >= prior.val;
      insideRun = inside ? insideRun + 1 : 0;

      if (used) return null;
      if (i - s.from < p.entryDelayBars) return null;
      if (Math.abs(s.gap) < p.minGapPts) return null;
      if (!Number.isFinite(a[i]) || a[i] <= 0) return null;

      const entry = bar.c;
      let side: 1 | -1 = 1;
      let target = NaN;

      if (p.mode === 0) {
        // Fade back to the near edge of prior value.
        if (s.openLocation === "above value") { side = -1; target = prior.vah; }
        else if (s.openLocation === "below value") { side = 1; target = prior.val; }
        else return null;
        // Only act while price is still outside value — once it is back inside, the trade is over.
        if (side === -1 && entry <= prior.vah) return null;
        if (side === 1 && entry >= prior.val) return null;
      } else if (p.mode === 1) {
        // The 80% rule: opened outside value, price has re-entered and held.
        if (s.openLocation === "inside value") return null;
        if (insideRun < p.holdBars) return null;
        if (s.openLocation === "above value") { side = -1; target = prior.val; }
        else { side = 1; target = prior.vah; }
      } else if (p.mode === 2) {
        // Rotation to the prior point of control from an in-value open.
        if (s.openLocation !== "inside value") return null;
        side = entry > prior.poc ? -1 : 1;
        target = prior.poc;
      } else {
        // Acceptance: opened outside value and has not returned — bet on continuation away.
        if (s.openLocation === "inside value") return null;
        if (s.openLocation === "above value") { side = 1; target = entry + (prior.vah - prior.val); }
        else { side = -1; target = entry - (prior.vah - prior.val); }
        if (inside) return null; // it came back, so this is not acceptance
      }

      if (!Number.isFinite(target)) return null;
      const targetDist = Math.abs(target - entry);
      if (targetDist < minTarget) return null; // enforces the minimum target in points
      if (p.sideMode !== 0 && p.sideMode !== side) return null;

      const stopDist = targetDist * p.rrStop;
      if (stopDist < inst.tickSize) return null;

      used = true;
      return {
        side,
        stopPrice: entry - side * stopDist,
        targetPrice: target,
        stopDist,
        targetDist,
        maxBars: p.maxBars,
        tag: `va${p.mode}-${side === 1 ? "long" : "short"}`,
      };
    };
  },
};
