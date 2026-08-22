import { describe, expect, it } from "vitest";
import { overnightSessions } from "./overnight";
import { instrument } from "./instruments";
import type { Bar, Instrument } from "./types";

const inst: Instrument = { ...instrument("NQ"), tz: "UTC", session: [570, 960] };

/**
 * Build a synthetic 24-hour series: an overnight block then a cash session, per day.
 * Times are UTC and the instrument's tz is UTC, so minute-of-day is exactly the clock.
 */
const day = (dayOffset: number, opts: { onHi: number; onLo: number; open: number; hi: number; lo: number; close: number }): Bar[] => {
  const base = Date.UTC(2024, 0, 2 + dayOffset);
  const rows: Bar[] = [];
  // Overnight block, 04:00-09:29 (before the 09:30 cash open).
  for (let m = 240; m < 570; m += 30) {
    const mid = (opts.onHi + opts.onLo) / 2;
    rows.push({ t: base + m * 60_000, o: mid, h: opts.onHi, l: opts.onLo, c: mid, v: 10 });
  }
  // Cash session, 09:30-15:59.
  rows.push({ t: base + 570 * 60_000, o: opts.open, h: Math.max(opts.open, opts.hi), l: Math.min(opts.open, opts.lo), c: opts.open, v: 100 });
  for (let m = 600; m < 960; m += 30) {
    rows.push({ t: base + m * 60_000, o: opts.open, h: opts.hi, l: opts.lo, c: m >= 930 ? opts.close : opts.open, v: 100 });
  }
  return rows;
};

describe("overnight sessions", () => {
  it("measures the gap from the prior cash close, not the prior overnight", () => {
    const bars = [
      ...day(0, { onHi: 100, onLo: 90, open: 95, hi: 105, lo: 92, close: 100 }),  // prior cash closes at 100
      ...day(1, { onHi: 130, onLo: 118, open: 125, hi: 128, lo: 120, close: 126 }),
    ];
    const out = overnightSessions(bars, inst);
    expect(out).toHaveLength(1);
    expect(out[0].priorRthClose).toBeCloseTo(100, 6);
    expect(out[0].rthOpen).toBeCloseTo(125, 6);
    expect(out[0].gap).toBeCloseTo(25, 6);
  });

  it("reports the gap as unfilled when the cash session never trades back to the prior close", () => {
    const bars = [
      ...day(0, { onHi: 100, onLo: 90, open: 95, hi: 105, lo: 92, close: 100 }),
      ...day(1, { onHi: 130, onLo: 118, open: 125, hi: 128, lo: 120, close: 126 }), // low 120 > prior close 100
    ];
    const out = overnightSessions(bars, inst);
    expect(out[0].gapFilled).toBe(false);
    expect(out[0].minutesToFill).toBeNull();
  });

  it("detects a filled gap and reports minutes into the session", () => {
    const bars = [
      ...day(0, { onHi: 100, onLo: 90, open: 95, hi: 105, lo: 92, close: 100 }),
      ...day(1, { onHi: 130, onLo: 118, open: 125, hi: 128, lo: 95, close: 110 }), // trades down through 100
    ];
    const out = overnightSessions(bars, inst);
    expect(out[0].gapFilled).toBe(true);
    expect(out[0].minutesToFill).toBeGreaterThanOrEqual(0);
  });

  it("captures the overnight block's own extremes, separate from the cash session's", () => {
    const bars = [
      ...day(0, { onHi: 100, onLo: 90, open: 95, hi: 105, lo: 92, close: 100 }),
      ...day(1, { onHi: 140, onLo: 110, open: 125, hi: 128, lo: 120, close: 126 }),
    ];
    const out = overnightSessions(bars, inst);
    expect(out[0].onHigh).toBeCloseTo(140, 6);
    expect(out[0].onLow).toBeCloseTo(110, 6);
    expect(out[0].onRange).toBeCloseTo(30, 6);
    // The cash session stayed inside the overnight range, so neither extreme was taken out.
    expect(out[0].brokeOnHigh).toBe(false);
    expect(out[0].brokeOnLow).toBe(false);
  });

  it("scales the gap by the prior cash range so it is comparable across volatility regimes", () => {
    const bars = [
      ...day(0, { onHi: 100, onLo: 90, open: 95, hi: 110, lo: 90, close: 100 }), // prior cash range 20
      ...day(1, { onHi: 130, onLo: 118, open: 110, hi: 128, lo: 105, close: 126 }), // gap +10
    ];
    const out = overnightSessions(bars, inst);
    expect(out[0].priorRthRange).toBeCloseTo(20, 6);
    expect(out[0].gapInPriorRanges).toBeCloseTo(0.5, 6);
  });

  it("does not emit a session when there is no overnight block before it", () => {
    const bars = day(0, { onHi: 100, onLo: 90, open: 95, hi: 105, lo: 92, close: 100 });
    expect(overnightSessions(bars, inst)).toHaveLength(0);
  });
});
