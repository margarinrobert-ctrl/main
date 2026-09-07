import { clockFor } from "./clock";
import type { Bar, Instrument } from "./types";

// Overnight (Globex) structure and gap behaviour.
//
// Every other study in this repo filtered to the 09:30-16:00 cash session and threw away two thirds
// of the data. That discards the part of the day where the gap is FORMED — and the gap, together
// with the overnight range, is the only information about today that exists before today's cash
// session opens. If there is a day-level anomaly to find, this is where it lives.
//
// Definitions follow CME convention: the overnight block preceding cash session D runs from 18:00 ET
// on the prior session day to 09:29 ET on D, with the 17:00-18:00 maintenance break excluded.

export interface OvernightSession {
  /** Local day index of the cash session. */
  day: number;
  /** Bar index range of the cash session, [from, to). */
  from: number;
  to: number;
  rthOpen: number;
  rthClose: number;
  rthHigh: number;
  rthLow: number;
  /** The prior cash session's close — the reference the gap is measured from. */
  priorRthClose: number;
  priorRthHigh: number;
  priorRthLow: number;
  priorRthRange: number;
  /** Overnight extremes for the block immediately preceding this cash session. */
  onHigh: number;
  onLow: number;
  onRange: number;
  /** Bars in the overnight block — a liquidity/participation proxy. */
  onBars: number;
  onVolume: number;
  /** Cash open minus prior cash close. */
  gap: number;
  /** Gap as a fraction of the prior cash session's range — the scale-free version. */
  gapInPriorRanges: number;
  /** Did the cash session trade back through the prior cash close? */
  gapFilled: boolean;
  /** Minutes into the cash session before the gap filled, or null. */
  minutesToFill: number | null;
  /** Did the cash session take out the overnight high / low? */
  brokeOnHigh: boolean;
  brokeOnLow: boolean;
  /** Where the cash open sat inside the overnight range, 0 = at the low, 1 = at the high. */
  openInOnRange: number;
}

/**
 * Decompose a full-session bar series into cash sessions with their preceding overnight blocks.
 *
 * `bars` must be the UNFILTERED series (all 23 hours). Everything on the returned object that a
 * strategy could act on at the cash open — gap, overnight extremes, prior session levels — is fixed
 * before the cash session trades; the outcome fields (gapFilled, brokeOnHigh) describe what
 * happened afterwards and exist for measurement, not for conditioning entries.
 */
export function overnightSessions(bars: Bar[], inst: Instrument, rthStart = 570, rthEnd = 960): OvernightSession[] {
  const clock = clockFor(bars, inst.tz);
  const n = bars.length;

  // Index the cash sessions first.
  interface Cash { day: number; from: number; to: number }
  const cash: Cash[] = [];
  let cur: Cash | null = null;
  for (let i = 0; i < n; i++) {
    const m = clock.minuteOfDay[i];
    const inRth = m >= rthStart && m < rthEnd;
    if (inRth) {
      if (!cur || cur.day !== clock.dayIndex[i]) {
        if (cur) cash.push(cur);
        cur = { day: clock.dayIndex[i], from: i, to: i + 1 };
      } else cur.to = i + 1;
    }
  }
  if (cur) cash.push(cur);

  const out: OvernightSession[] = [];
  for (let k = 1; k < cash.length; k++) {
    const c = cash[k];
    const prev = cash[k - 1];

    let rthHigh = -Infinity;
    let rthLow = Infinity;
    for (let i = c.from; i < c.to; i++) {
      if (bars[i].h > rthHigh) rthHigh = bars[i].h;
      if (bars[i].l < rthLow) rthLow = bars[i].l;
    }
    let pHigh = -Infinity;
    let pLow = Infinity;
    for (let i = prev.from; i < prev.to; i++) {
      if (bars[i].h > pHigh) pHigh = bars[i].h;
      if (bars[i].l < pLow) pLow = bars[i].l;
    }

    // The overnight block: everything between the prior cash close and this cash open.
    let onHigh = -Infinity;
    let onLow = Infinity;
    let onBars = 0;
    let onVolume = 0;
    for (let i = prev.to; i < c.from; i++) {
      if (bars[i].h > onHigh) onHigh = bars[i].h;
      if (bars[i].l < onLow) onLow = bars[i].l;
      onBars++;
      onVolume += bars[i].v;
    }
    if (!Number.isFinite(onHigh) || onBars === 0) continue;

    const priorRthClose = bars[prev.to - 1].c;
    const rthOpen = bars[c.from].o;
    const gap = rthOpen - priorRthClose;

    // Did the cash session trade back through the prior close, and when?
    let filled = false;
    let minutesToFill: number | null = null;
    for (let i = c.from; i < c.to; i++) {
      if (bars[i].l <= priorRthClose && bars[i].h >= priorRthClose) {
        filled = true;
        minutesToFill = clock.minuteOfDay[i] - rthStart;
        break;
      }
    }

    const priorRthRange = pHigh - pLow;
    out.push({
      day: c.day,
      from: c.from,
      to: c.to,
      rthOpen,
      rthClose: bars[c.to - 1].c,
      rthHigh,
      rthLow,
      priorRthClose,
      priorRthHigh: pHigh,
      priorRthLow: pLow,
      priorRthRange,
      onHigh,
      onLow,
      onRange: onHigh - onLow,
      onBars,
      onVolume,
      gap,
      gapInPriorRanges: priorRthRange > 0 ? gap / priorRthRange : 0,
      gapFilled: filled,
      minutesToFill,
      brokeOnHigh: rthHigh > onHigh,
      brokeOnLow: rthLow < onLow,
      openInOnRange: onHigh > onLow ? (rthOpen - onLow) / (onHigh - onLow) : 0.5,
    });
  }
  return out;
}
