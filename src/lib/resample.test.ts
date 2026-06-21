import { describe, expect, it } from "vitest";
import type { HistoryBar } from "./barchart/types";
import { resampleBars } from "./resample";

function b(min: number, o: number, h: number, l: number, c: number, v = 100): HistoryBar {
  return { timestamp: new Date(Date.UTC(2026, 5, 16, 13, min, 0)).toISOString(), open: o, high: h, low: l, close: c, volume: v };
}

describe("resampleBars", () => {
  it("is a no-op for minutes <= 1", () => {
    const bars = [b(0, 1, 2, 0.5, 1.5), b(1, 1.5, 2.5, 1, 2)];
    expect(resampleBars(bars, 1)).toBe(bars);
  });

  it("buckets 1m bars into N-minute OHLC", () => {
    const bars = [b(0, 10, 12, 9, 11), b(1, 11, 13, 10, 12), b(2, 12, 14, 11, 13), b(3, 13, 15, 12, 14), b(4, 14, 16, 13, 15), b(5, 15, 17, 14, 16)];
    const out = resampleBars(bars, 3);
    expect(out).toHaveLength(2);
    expect(out[0]).toMatchObject({ open: 10, high: 14, low: 9, close: 13, volume: 300 }); // bars 0-2
    expect(out[1]).toMatchObject({ open: 13, high: 17, low: 12, close: 16, volume: 300 }); // bars 3-5
    // ascending order preserved
    expect(Date.parse(out[1].timestamp)).toBeGreaterThan(Date.parse(out[0].timestamp));
  });
});
