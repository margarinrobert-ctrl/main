import { clockFor } from "../clock";
import { atr, closes, percentRank } from "../series";
import type { Bar, EntryIntent, Instrument, Params, Strategy } from "../types";

/**
 * Opening-range breakout.
 *
 * Mechanism: the first minutes of a liquidity session price in the overnight information flow.
 * When the resulting range is NARROW relative to recent volatility, the auction has not resolved,
 * and the first decisive break tends to attract continuation (stops above/below the range are the
 * fuel). When the range is already wide, the move has happened and the break is the exit liquidity.
 * The `maxWidth` filter is that distinction, and it is the part of the rule that has to earn its
 * keep out of sample — a raw ORB with no width filter is close to a coin flip after costs.
 */
export const orb: Strategy = {
  id: "orb",
  label: "Opening-range breakout",
  family: "breakout",
  rationale:
    "Narrow opening ranges mark unresolved auctions; the first break runs the stops resting on the other side.",
  defaults: { orMinutes: 30, maxWidthAtr: 2.5, stopAtr: 1.0, rr: 1.5, maxBars: 24, buffTicks: 2 },
  space: {
    orMinutes: { values: [15, 30, 45, 60] },
    maxWidthAtr: { values: [1.2, 1.8, 2.5, 99] },
    stopAtr: { values: [0.75, 1.0, 1.5] },
    rr: { values: [1.0, 1.5, 2.0] },
    maxBars: { values: [12, 24, 48] },
    buffTicks: { values: [0, 2, 4] },
  },
  build(bars: Bar[], p: Params, inst: Instrument) {
    const a = atr(bars, 14);
    const clock = clockFor(bars, inst.tz);
    const day = clock.dayIndex;
    const mins = clock.minuteOfDay;
    const sessionStartMin = inst.session[0];
    const orEnd = sessionStartMin + p.orMinutes;

    // Rolling opening range, built forward bar by bar — never from the completed day.
    const orHigh = new Array<number>(bars.length).fill(NaN);
    const orLow = new Array<number>(bars.length).fill(NaN);
    let curDay = NaN;
    let hi = -Infinity;
    let lo = Infinity;
    for (let i = 0; i < bars.length; i++) {
      if (day[i] !== curDay) {
        curDay = day[i];
        hi = -Infinity;
        lo = Infinity;
      }
      if (mins[i] >= sessionStartMin && mins[i] < orEnd) {
        hi = Math.max(hi, bars[i].h);
        lo = Math.min(lo, bars[i].l);
      }
      if (mins[i] >= orEnd && Number.isFinite(hi) && hi > -Infinity) {
        orHigh[i] = hi;
        orLow[i] = lo;
      }
    }

    const buff = p.buffTicks * inst.tickSize;
    return (i: number): EntryIntent | null => {
      const h = orHigh[i];
      const l = orLow[i];
      const av = a[i];
      if (!Number.isFinite(h) || !Number.isFinite(l) || !Number.isFinite(av) || av <= 0) return null;
      if ((h - l) / av > p.maxWidthAtr) return null; // range already wide — no unresolved auction left
      const c = bars[i].c;
      const stop = p.stopAtr * av;
      if (c > h + buff) return { side: 1, stopDist: stop, targetDist: stop * p.rr, maxBars: p.maxBars, tag: "orb-long" };
      if (c < l - buff) return { side: -1, stopDist: stop, targetDist: stop * p.rr, maxBars: p.maxBars, tag: "orb-short" };
      return null;
    };
  },
};

/**
 * Volatility-regime-gated Donchian micro-breakout.
 *
 * Mechanism: momentum at scalping horizons only exists when volatility is EXPANDING; in compressed
 * tape the same signal is a spread-paying machine. The realised-vol percentile gate is the whole
 * strategy — remove it and the edge should vanish, which is exactly the falsification test in the
 * research protocol.
 */
export const volBreakout: Strategy = {
  id: "vol-breakout",
  label: "Vol-expansion Donchian break",
  family: "momentum",
  rationale: "Intraday momentum is conditional on volatility expansion; in compression the same break mean-reverts.",
  defaults: { lookback: 20, volLookback: 100, minVolPct: 0.6, stopAtr: 1.0, rr: 1.5, maxBars: 20 },
  space: {
    lookback: { values: [10, 20, 40] },
    volLookback: { values: [50, 100, 200] },
    minVolPct: { values: [0.0, 0.4, 0.6, 0.8] },
    stopAtr: { values: [0.75, 1.0, 1.5] },
    rr: { values: [1.0, 1.5, 2.0] },
    maxBars: { values: [10, 20, 40] },
  },
  build(bars: Bar[], p: Params) {
    const a = atr(bars, 14);
    const c = closes(bars);
    const volPct = percentRank(a, p.volLookback);
    const n = p.lookback;
    const hiPrior = new Array<number>(bars.length).fill(NaN);
    const loPrior = new Array<number>(bars.length).fill(NaN);
    for (let i = n; i < bars.length; i++) {
      let h = -Infinity;
      let l = Infinity;
      for (let j = i - n; j < i; j++) {
        h = Math.max(h, bars[j].h);
        l = Math.min(l, bars[j].l);
      }
      hiPrior[i] = h;
      loPrior[i] = l;
    }
    return (i: number): EntryIntent | null => {
      const av = a[i];
      if (!Number.isFinite(av) || av <= 0 || !Number.isFinite(volPct[i]) || !Number.isFinite(hiPrior[i])) return null;
      if (volPct[i] < p.minVolPct) return null;
      const stop = p.stopAtr * av;
      if (c[i] > hiPrior[i]) return { side: 1, stopDist: stop, targetDist: stop * p.rr, maxBars: p.maxBars, tag: "vb-long" };
      if (c[i] < loPrior[i]) return { side: -1, stopDist: stop, targetDist: stop * p.rr, maxBars: p.maxBars, tag: "vb-short" };
      return null;
    };
  },
};
