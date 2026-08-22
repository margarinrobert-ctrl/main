import { describe, expect, it } from "vitest";
import { costSensitivity, subPeriodConsistency, verdict } from "./robustness";
import { instrument } from "./instruments";
import type { Bar, EntryIntent, Instrument, Params, Strategy, Trade } from "./types";

const inst: Instrument = { ...instrument("NQ"), tz: "UTC", session: [0, 1440] };

/** A strategy with a hand-controlled edge, so the cost sweep has a known answer. */
const fixedEdge = (pointsPerTrade: number): Strategy => ({
  id: "fixture",
  label: "fixture",
  family: "momentum",
  rationale: "test fixture",
  defaults: {},
  space: {},
  build: () => (i: number): EntryIntent | null => (i % 4 === 0 ? { side: 1, stopDist: 100, targetDist: pointsPerTrade, maxBars: 3 } : null),
});

/** Bars that rise by exactly `step` each bar, so a long target of `step` always fills next bar. */
const rising = (n: number, step: number): Bar[] =>
  Array.from({ length: n }, (_, i) => {
    const base = 20_000 + i * step;
    return { t: Date.UTC(2024, 0, 2) + i * 300_000, o: base, h: base + step, l: base, c: base + step, v: 100 };
  });

describe("costSensitivity", () => {
  // The regression this guards: `breakEvenMultiple` is Infinity both when a strategy outlives the
  // whole sweep and — superficially — looks non-finite when it never worked. Those are opposite
  // verdicts, and reporting them with the same phrase once inverted a headline number.
  it("reports SURVIVAL, not failure, when the edge outlives every cost level tested", () => {
    const bars = rising(2000, 40); // 160 ticks of move per trade dwarfs a 3.8-tick cost
    const cs = costSensitivity(fixedEdge(40), bars, {} as Params, { inst, sessionOnly: false });
    expect(cs.survivesSweep).toBe(true);
    expect(cs.breakEvenMultiple).toBe(Infinity);
    expect(cs.verdict).toMatch(/survives every cost level/);
    expect(cs.verdict).not.toMatch(/never profitable|unprofitable/);
    expect(cs.points[cs.points.length - 1].expectancyUsd).toBeGreaterThan(0);
  });

  it("says so plainly when the rule loses even with costs switched off", () => {
    const bars = rising(2000, 1);
    // A short in a monotonically rising series loses regardless of the cost model.
    const losing: Strategy = { ...fixedEdge(1), build: () => (i) => (i % 4 === 0 ? { side: -1, stopDist: 2, targetDist: 500, maxBars: 3 } : null) };
    const cs = costSensitivity(losing, bars, {} as Params, { inst, sessionOnly: false });
    expect(cs.survivesSweep).toBe(false);
    expect(cs.breakEvenMultiple).toBe(0);
    expect(cs.verdict).toMatch(/unprofitable even with costs switched off/);
  });

  it("keeps expectancy monotonically decreasing as costs rise", () => {
    const cs = costSensitivity(fixedEdge(40), rising(2000, 40), {} as Params, { inst, sessionOnly: false });
    for (let i = 1; i < cs.points.length; i++) expect(cs.points[i].expectancyUsd).toBeLessThan(cs.points[i - 1].expectancyUsd);
  });
});

describe("subPeriodConsistency", () => {
  const trade = (t: number, pnl: number): Trade => ({
    side: 1, entryIndex: 0, exitIndex: 1, entryTime: t, exitTime: t, entryPx: 1, exitPx: 1,
    grossPoints: 0, costPoints: 0, pnl, r: 0, barsHeld: 1, reason: "target",
  });

  it("catches P&L concentrated in one window", () => {
    // Sixty trades in six chunks of ten: only the final chunk makes money, and it makes all of it.
    const trades = Array.from({ length: 60 }, (_, i) => trade(i * 86_400_000, i < 50 ? -10 : 100));
    const c = subPeriodConsistency(trades, 6);
    expect(c.profitableShare).toBeCloseTo(1 / 6, 6);
    expect(c.worstChunkPnl).toBeLessThan(0);
  });

  it("recognises an evenly distributed edge", () => {
    const trades = Array.from({ length: 60 }, (_, i) => trade(i * 86_400_000, i % 3 === 0 ? -10 : 10));
    expect(subPeriodConsistency(trades, 6).profitableShare).toBe(1);
  });
});

describe("verdict gates", () => {
  const base = {
    oos: { trades: 500, netEdgeTicks: 4, tStat: 3.1 } as never,
    pbo: 0.1, dsr: 0.99, costMargin: 2.5, plateau: "plateau",
    consistency: 0.83, bestYearShare: 0.4, wfEfficiency: 0.8,
  };

  it("clears everything when every input is healthy", () => {
    const v = verdict(base);
    expect(v.tradeable).toBe(true);
    expect(v.failures).toHaveLength(0);
    expect(v.score).toBe(1);
  });

  it("fails the specific gate that is breached and no others", () => {
    const v = verdict({ ...base, pbo: 0.62 });
    expect(v.tradeable).toBe(false);
    expect(v.failures).toHaveLength(1);
    expect(v.failures[0]).toMatch(/PBO/);
  });
});
