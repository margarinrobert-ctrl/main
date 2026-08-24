import { describe, expect, it } from "vitest";
import { instrument } from "./instruments";
import { volumeContext, weightedPressure, windowMean } from "./volumeFeatures";
import type { Bar, Instrument } from "./types";

const inst: Instrument = { ...instrument("NQ"), tz: "UTC", session: [0, 1440] };

/** `days` sessions of `perDay` 5-minute bars, each session starting at 10:00 UTC. */
function series(days: number, perDay: number, volumeAt: (day: number, slot: number) => number): Bar[] {
  const bars: Bar[] = [];
  for (let d = 0; d < days; d++) {
    const base = Date.UTC(2024, 0, 2 + d, 10, 0);
    for (let k = 0; k < perDay; k++) {
      bars.push({ t: base + k * 300_000, o: 100, h: 101, l: 99, c: 100.5, v: volumeAt(d, k) });
    }
  }
  return bars;
}

describe("volumeContext", () => {
  it("normalises a bar against the SAME minute-of-day on prior sessions, not the trailing mean", () => {
    // Slot 0 is always the busy one. A bar at slot 0 with the usual volume is NOT unusual, even
    // though it towers over a trailing average — that is the whole point of the normalisation.
    const bars = series(30, 6, (_, k) => (k === 0 ? 10_000 : 1_000));
    const v = volumeContext(bars, inst);
    const last = bars.length - 6; // slot 0 of the final session
    expect(v.rvolTod[last]).toBeCloseTo(1, 6);
    expect(v.rvolTrailing[last]).toBeGreaterThan(3);
  });

  it("flags a genuinely busy bar at a quiet slot", () => {
    const bars = series(30, 6, (d, k) => (k === 3 && d === 29 ? 4_000 : k === 0 ? 10_000 : 1_000));
    const v = volumeContext(bars, inst);
    expect(v.rvolTod[bars.length - 3]).toBeCloseTo(4, 6);
  });

  it("uses only COMPLETED prior sessions — a session cannot see itself", () => {
    // Every session identical except the last, which is 10x. If the reference window included the
    // current session the ratio would be pulled toward 1; it must stay at 10.
    const bars = series(21, 4, (d) => (d === 20 ? 10_000 : 1_000));
    const v = volumeContext(bars, inst);
    for (let i = bars.length - 4; i < bars.length; i++) expect(v.rvolTod[i]).toBeCloseTo(10, 6);
  });

  it("emits NaN until the minimum number of prior sessions exists", () => {
    const bars = series(12, 3, () => 1_000);
    const v = volumeContext(bars, inst, { minSessions: 10 });
    expect(Number.isNaN(v.rvolTod[0])).toBe(true);
    expect(Number.isNaN(v.rvolTod[9 * 3])).toBe(true); // 9 completed sessions is one short
    expect(v.rvolTod[10 * 3]).toBeCloseTo(1, 6);
  });

  it("accumulates session volume and resets it at the session boundary", () => {
    const bars = series(3, 4, () => 500);
    const v = volumeContext(bars, inst);
    expect(v.sessionVolume[3]).toBe(2_000);
    expect(v.sessionVolume[4]).toBe(500);
  });

  it("maps close location to [-1, +1] and leaves a zero-range bar undefined", () => {
    const bars: Bar[] = [
      { t: Date.UTC(2024, 0, 2, 10, 0), o: 100, h: 110, l: 100, c: 110, v: 1 },
      { t: Date.UTC(2024, 0, 2, 10, 5), o: 100, h: 110, l: 100, c: 100, v: 1 },
      { t: Date.UTC(2024, 0, 2, 10, 10), o: 100, h: 110, l: 100, c: 105, v: 1 },
      { t: Date.UTC(2024, 0, 2, 10, 15), o: 100, h: 100, l: 100, c: 100, v: 1 },
    ];
    const v = volumeContext(bars, inst);
    expect(v.pressure[0]).toBeCloseTo(1, 9);
    expect(v.pressure[1]).toBeCloseTo(-1, 9);
    expect(v.pressure[2]).toBeCloseTo(0, 9);
    expect(Number.isNaN(v.pressure[3])).toBe(true);
  });

  it("weights the session delta by volume, so a big bar counts more than a small one", () => {
    const bars: Bar[] = [
      { t: Date.UTC(2024, 0, 2, 10, 0), o: 100, h: 110, l: 100, c: 110, v: 300 }, // pressure +1
      { t: Date.UTC(2024, 0, 2, 10, 5), o: 100, h: 110, l: 100, c: 100, v: 100 }, // pressure -1
    ];
    const v = volumeContext(bars, inst);
    expect(v.sessionDelta[1]).toBeCloseTo((300 - 100) / 400, 9);
  });
});

describe("window helpers", () => {
  it("windowMean refuses a window containing a NaN rather than silently skipping it", () => {
    const xs = [1, NaN, 3, 4];
    expect(Number.isNaN(windowMean(xs, 2, 3))).toBe(true);
    expect(windowMean(xs, 3, 2)).toBeCloseTo(3.5, 9);
    expect(Number.isNaN(windowMean(xs, 1, 5))).toBe(true); // reaches before the start
  });

  it("weightedPressure is the volume-weighted mean of the window's pressures", () => {
    const bars: Bar[] = [
      { t: 0, o: 0, h: 1, l: 0, c: 1, v: 100 },
      { t: 1, o: 0, h: 1, l: 0, c: 0, v: 300 },
    ];
    const pressure = [1, -1];
    expect(weightedPressure(bars, pressure, 1, 2)).toBeCloseTo((100 - 300) / 400, 9);
  });
});
