import { describe, expect, it } from "vitest";
import type { GexSample } from "../gex-history";
import { dayStats, groupByDay } from "./historyDays";

const at = (iso: string, p: Partial<GexSample> = {}): GexSample => ({ t: new Date(iso).getTime(), spot: 100, gex: 1e9, flip: 99, iv: 0.2, pcr: 1, ...p });

describe("groupByDay", () => {
  it("buckets samples into local days, oldest first, sorted within", () => {
    const series = [
      at("2026-07-30T18:00:00", { spot: 101 }),
      at("2026-07-29T15:00:00", { spot: 99 }),
      at("2026-07-30T10:00:00", { spot: 100 }),
    ];
    const days = groupByDay(series);
    expect(days.length).toBe(2);
    expect(days[0].samples[0].spot).toBe(99); // 29th first
    expect(days[1].samples.map((s) => s.spot)).toEqual([100, 101]); // sorted within the 30th
    expect(days[0].key < days[1].key).toBe(true);
    expect(days[1].label).toMatch(/Jul|30/);
  });
  it("handles empty input", () => {
    expect(groupByDay([])).toEqual([]);
  });
});

describe("dayStats", () => {
  it("computes open/close/min/max and change%", () => {
    const s = [
      at("2026-07-30T09:00:00", { spot: 100, gex: 2e9, iv: 0.2, dex: undefined }),
      at("2026-07-30T12:00:00", { spot: 103, gex: -1e9, iv: 0.25, dex: 5e8 }),
      at("2026-07-30T16:00:00", { spot: 102, gex: 3e9, iv: 0.22, dex: -2e8 }),
    ];
    const st = dayStats(s);
    expect(st.n).toBe(3);
    expect(st.spotOpen).toBe(100);
    expect(st.spotClose).toBe(102);
    expect(st.spotChangePct).toBeCloseTo(2, 5);
    expect(st.gexMin).toBe(-1e9);
    expect(st.gexMax).toBe(3e9);
    expect(st.gexClose).toBe(3e9);
    expect(st.dexClose).toBe(-2e8); // last recorded dex
    expect(st.ivMin).toBeCloseTo(0.2);
    expect(st.ivMax).toBeCloseTo(0.25);
  });
  it("returns nulls for days recorded before DEX existed / with gaps", () => {
    const st = dayStats([at("2026-06-25T10:00:00", { dex: undefined, iv: null })]);
    expect(st.dexClose).toBeNull();
    expect(st.ivMin).toBeNull();
    expect(st.spotOpen).toBe(100);
  });
});
