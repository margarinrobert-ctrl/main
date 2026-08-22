import { clockFor } from "../clock";
import type { Bar, EntryIntent, Instrument, Params, Strategy } from "../types";

/**
 * Opening-range breakout, parameterised over the choices that actually distinguish one published
 * ORB from another.
 *
 * Mechanism: the first minutes after the cash open are when overnight information is repriced by
 * the day's heaviest participation. The range that forms is the market's first agreed boundary, and
 * resting stop orders accumulate just outside it. A break is therefore two things at once — genuine
 * repricing, and a pool of forced buying or selling. The strategy is a bet that the second effect
 * carries price far enough to pay for the spread before the first effect reverses.
 *
 * Where ORB variants differ, and what this covers:
 *   - entryMode 0: take the break itself (conservative model: a bar must CLOSE beyond the level,
 *     then fill at the next open — a real resting stop order would fill mid-bar and better, so this
 *     understates the strategy slightly and never overstates it).
 *   - entryMode 1: rest a limit at `retrPct` back inside the range and let the break come to you.
 *   - stopMode 0: stop at the opposite edge of the opening range.
 *   - stopMode 1: stop at `stopPct` of the range measured from the broken edge.
 *   - targetPct: profit target as a percent of the range beyond the broken edge.
 *   - targetPct = 0: no target at all, hold to the session close. Some ORBs are really a bet on the
 *     whole day's direction rather than a scalp, and that distinction shows up nowhere else.
 */
export const openingRange: Strategy = {
  id: "opening-range",
  label: "Opening-range breakout (parameterised)",
  family: "breakout",
  rationale:
    "The first minutes after the open set the day's first agreed boundary, with resting stops just outside it; a break is repricing plus forced flow.",
  defaults: {
    orMinutes: 15,
    entryMode: 0,
    retrPct: 25,
    stopMode: 0,
    stopPct: 50,
    targetPct: 100,
    minRangePct: 0,
    maxRangePct: 100,
    sideMode: 0,
    breakBuffer: 0,
    dirMode: 0,
    atrFrac: 10,
    atrDays: 14,
  },
  space: {
    orMinutes: { values: [15] }, // fixed for this study; the question is the 9:30-9:45 range
    entryMode: { values: [0, 1] },
    retrPct: { values: [15, 25, 40] },
    stopMode: { values: [0, 1] },
    stopPct: { values: [30, 50, 75, 100] },
    targetPct: { values: [0, 50, 100, 150, 200] },
    minRangePct: { values: [0, 25, 50] },
    maxRangePct: { values: [50, 75, 100] },
    sideMode: { values: [0, 1, -1] },
    breakBuffer: { values: [0, 1, 2] },
    /**
     * Who decides the side.
     *   0 = whichever edge broke (the usual reading of an ORB)
     *   1 = the OPENING CANDLE'S OWN BODY — a bullish opening range permits only longs, a bearish
     *       one only shorts, regardless of which edge is breached. This is the parameter Zarattini,
     *       Barbon & Aziz call crucial, and it is a genuinely different strategy: on a bearish
     *       opening candle it refuses the upside break outright rather than trading it.
     */
    dirMode: { values: [0, 1] },
    /** stopMode 2 only: stop distance as a PERCENT of the trailing daily ATR. The paper uses 10. */
    atrFrac: { values: [5, 10, 20, 33, 50] },
    atrDays: { values: [14] },
  },
  build(bars: Bar[], p: Params, inst: Instrument) {
    const clock = clockFor(bars, inst.tz);
    const start = inst.session[0];
    const orEnd = start + p.orMinutes;
    const n = bars.length;

    // ---- pass 1: the opening range, built forward, final only after the window closes ----
    const orHigh = new Float64Array(n).fill(NaN);
    const orLow = new Float64Array(n).fill(NaN);
    const ready = new Uint8Array(n);
    let curDay = -1;
    let hi = -Infinity;
    let lo = Infinity;
    let sawWindow = false;
    for (let i = 0; i < n; i++) {
      if (clock.dayIndex[i] !== curDay) {
        curDay = clock.dayIndex[i];
        hi = -Infinity;
        lo = Infinity;
        sawWindow = false;
      }
      const m = clock.minuteOfDay[i];
      if (m >= start && m < orEnd) {
        hi = Math.max(hi, bars[i].h);
        lo = Math.min(lo, bars[i].l);
        sawWindow = true;
      } else if (m >= orEnd && sawWindow && hi > -Infinity) {
        orHigh[i] = hi;
        orLow[i] = lo;
        ready[i] = 1;
      }
    }

    // ---- pass 1b: the opening candle's own direction, and a trailing daily ATR ----
    // Both are per-session and both use only information available once the opening range closes.
    const orOpen = new Float64Array(n).fill(NaN);
    const orClose = new Float64Array(n).fill(NaN);
    {
      let d = -1;
      let seenOpen = false;
      for (let i = 0; i < n; i++) {
        const m = clock.minuteOfDay[i];
        if (clock.dayIndex[i] !== d) {
          d = clock.dayIndex[i];
          seenOpen = false;
        }
        if (m >= start && m < orEnd) {
          if (!seenOpen) {
            orOpen[i] = bars[i].o;
            seenOpen = true;
          }
          orClose[i] = bars[i].c;
        }
      }
    }
    /** Opening-candle direction per session: +1 bullish body, -1 bearish, 0 doji. */
    const orBody = new Map<number, number>();
    {
      let d = -1;
      let open = NaN;
      let close = NaN;
      for (let i = 0; i < n; i++) {
        if (clock.dayIndex[i] !== d) {
          if (d >= 0 && Number.isFinite(open) && Number.isFinite(close)) orBody.set(d, Math.sign(close - open));
          d = clock.dayIndex[i];
          open = NaN;
          close = NaN;
        }
        if (Number.isFinite(orOpen[i]) && !Number.isFinite(open)) open = orOpen[i];
        if (Number.isFinite(orClose[i])) close = orClose[i];
      }
      if (d >= 0 && Number.isFinite(open) && Number.isFinite(close)) orBody.set(d, Math.sign(close - open));
    }

    // Trailing daily ATR from COMPLETED prior sessions only. Built from the session-filtered bars,
    // so it is an ATR of the traded window rather than of the 24-hour day — the right reference for
    // a stop sized inside that window, and it never sees today.
    const sessH = new Map<number, number>();
    const sessL = new Map<number, number>();
    const sessC = new Map<number, number>();
    for (let i = 0; i < n; i++) {
      const d = clock.dayIndex[i];
      sessH.set(d, Math.max(sessH.get(d) ?? -Infinity, bars[i].h));
      sessL.set(d, Math.min(sessL.get(d) ?? Infinity, bars[i].l));
      sessC.set(d, bars[i].c);
    }
    const atrByDay = new Map<number, number>();
    {
      const days = [...sessH.keys()].sort((a, b) => a - b);
      const trs: number[] = [];
      const len = Math.max(2, Math.round(p.atrDays));
      for (let k = 0; k < days.length; k++) {
        // The ATR recorded against day k uses only days strictly before it.
        atrByDay.set(days[k], trs.length >= 5 ? trs.slice(-len).reduce((a, b) => a + b, 0) / Math.min(len, trs.length) : NaN);
        const h = sessH.get(days[k])!;
        const l = sessL.get(days[k])!;
        const pc = k > 0 ? sessC.get(days[k - 1])! : NaN;
        trs.push(Number.isFinite(pc) ? Math.max(h - l, Math.abs(h - pc), Math.abs(l - pc)) : h - l);
      }
    }

    // ---- pass 2: trailing range percentile, from PRIOR sessions only ----
    const dayRange = new Map<number, number>();
    for (let i = 0; i < n; i++) if (ready[i] && !dayRange.has(clock.dayIndex[i])) dayRange.set(clock.dayIndex[i], orHigh[i] - orLow[i]);
    const pctile = new Map<number, number>();
    const history: number[] = [];
    for (const day of [...dayRange.keys()].sort((a, b) => a - b)) {
      const r = dayRange.get(day)!;
      pctile.set(day, history.length >= 20 ? (history.filter((x) => x < r).length / history.length) * 100 : 50);
      history.push(r);
      if (history.length > 60) history.shift();
    }

    const buffer = p.breakBuffer * inst.tickSize;
    let stateDay = -1;
    let used = 0;

    return (i: number): EntryIntent | null => {
      const day = clock.dayIndex[i];
      if (day !== stateDay) {
        stateDay = day;
        used = 0;
      }
      if (!ready[i] || used !== 0) return null;

      const h = orHigh[i];
      const l = orLow[i];
      const range = h - l;
      if (!(range > 0)) return null;

      const q = pctile.get(day) ?? 50;
      if (q < p.minRangePct || q > p.maxRangePct) return null;

      const bar = bars[i];
      // A CLOSE beyond the level, not a wick: on the break-entry path the fill is the next open, so
      // requiring a close is what keeps this from being an intrabar peek.
      const upBreak = bar.c > h + buffer;
      const dnBreak = bar.c < l - buffer;
      if (!upBreak && !dnBreak) return null;

      const side: 1 | -1 = upBreak ? 1 : -1;
      used = side; // the day is spent whether or not this side is enabled
      if (p.sideMode !== 0 && p.sideMode !== side) return null;
      // dirMode 1: the opening candle's body vetoes the break. A bearish opening range refuses the
      // upside break entirely rather than trading it, which is what makes it a different strategy
      // and not a filter on the same one.
      if (p.dirMode === 1) {
        const body = orBody.get(day) ?? 0;
        if (body === 0 || body !== side) return null;
      }

      const edge = side === 1 ? h : l;
      let stop: number;
      if (p.stopMode === 2) {
        const atr = atrByDay.get(day) ?? NaN;
        if (!(atr > 0)) return null; // no ATR history yet: refuse rather than invent a stop
        stop = edge - side * (atr * p.atrFrac) / 100;
      } else if (p.stopMode === 1) {
        stop = edge - side * (range * p.stopPct) / 100;
      } else {
        stop = side === 1 ? l : h;
      }
      // targetPct 0 means "no target" — ride it to the session close.
      const target = p.targetPct > 0 ? edge + side * (range * p.targetPct) / 100 : edge + side * range * 50;

      if (p.entryMode === 1) {
        const entry = edge - side * (range * p.retrPct) / 100;
        if (Math.abs(entry - stop) < inst.tickSize) return null;
        return {
          side,
          limitPrice: entry,
          stopPrice: stop,
          targetPrice: target,
          stopDist: Math.abs(entry - stop),
          targetDist: Math.abs(target - entry),
          maxBars: 10_000,
          tag: side === 1 ? "orb-retr-long" : "orb-retr-short",
        };
      }

      const ref = bar.c;
      if (Math.abs(ref - stop) < inst.tickSize) return null;
      return {
        side,
        stopPrice: stop,
        targetPrice: target,
        stopDist: Math.abs(ref - stop),
        targetDist: Math.abs(target - ref),
        maxBars: 10_000,
        tag: side === 1 ? "orb-break-long" : "orb-break-short",
      };
    };
  },
};
