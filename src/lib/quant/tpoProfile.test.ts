import { describe, expect, it } from "vitest";
import { buildProfile, buildTpoProfile } from "./volumeProfile";
import { instrument } from "./instruments";
import type { Bar, Instrument } from "./types";

const inst: Instrument = { ...instrument("NQ"), tz: "UTC", session: [0, 1440] };

/** Bars every 5 minutes from 09:30, so 30-minute TPO periods are six bars each. */
const mk = (rows: [number, number, number, number, number][]): { bars: Bar[]; minuteOfDay: number[] } => {
  const bars = rows.map(([o, h, l, c, v], i) => ({ t: Date.UTC(2024, 0, 2, 9, 30) + i * 300_000, o, h, l, c, v }));
  const minuteOfDay = rows.map((_, i) => 570 + i * 5);
  return { bars, minuteOfDay };
};

describe("TPO profile", () => {
  it("weights price by TIME, not by volume — the defining difference", () => {
    // Six bars at 100 with tiny volume (one full 30-min period), then six at 200 with huge volume.
    const rows: [number, number, number, number, number][] = [];
    for (let i = 0; i < 6; i++) rows.push([100, 100, 100, 100, 1]);
    for (let i = 0; i < 6; i++) rows.push([200, 200, 200, 200, 10_000]);
    const { bars, minuteOfDay } = mk(rows);

    const vol = buildProfile(bars, inst, 4)!;
    const tpo = buildTpoProfile(bars, inst, minuteOfDay, 0, bars.length, 4)!;

    // Volume says the point of control is where the size traded.
    expect(vol.poc).toBeGreaterThan(150);
    // TPO says both prices got exactly one period each, so neither dominates on time.
    const tpoBins = tpo.bins.filter((b) => b.volume > 0);
    expect(tpoBins).toHaveLength(2);
    expect(tpoBins[0].volume).toBe(tpoBins[1].volume);
  });

  it("counts a price once per 30-minute period however many bars touch it", () => {
    // All twelve bars sit at the same price: two periods, so exactly two TPOs.
    const rows: [number, number, number, number, number][] = [];
    for (let i = 0; i < 12; i++) rows.push([100, 100, 100, 100, 5]);
    const { bars, minuteOfDay } = mk(rows);
    const tpo = buildTpoProfile(bars, inst, minuteOfDay, 0, bars.length, 4)!;
    expect(tpo.totalVolume).toBe(2);
    // The POC is reported as the CENTRE of its bin, so a 1-point bin holding 100 reports 100.5.
    expect(Math.abs(tpo.poc - 100)).toBeLessThanOrEqual(tpo.binSize);
  });

  it("builds a value area containing the point of control", () => {
    const rows: [number, number, number, number, number][] = [];
    for (let i = 0; i < 36; i++) {
      const p = 100 + Math.round(Math.sin(i / 3) * 8);
      rows.push([p, p + 1, p - 1, p, 100]);
    }
    const { bars, minuteOfDay } = mk(rows);
    const tpo = buildTpoProfile(bars, inst, minuteOfDay, 0, bars.length, 4)!;
    expect(tpo.val).toBeLessThanOrEqual(tpo.poc);
    expect(tpo.vah).toBeGreaterThanOrEqual(tpo.poc);
    expect(tpo.high).toBeGreaterThanOrEqual(tpo.vah);
    expect(tpo.low).toBeLessThanOrEqual(tpo.val);
  });

  it("returns null on an empty range rather than a degenerate profile", () => {
    const { bars, minuteOfDay } = mk([[100, 100, 100, 100, 1]]);
    expect(buildTpoProfile(bars, inst, minuteOfDay, 0, 0, 4)).toBeNull();
  });
});
