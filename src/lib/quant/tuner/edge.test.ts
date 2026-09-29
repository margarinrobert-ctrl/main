/**
 * Edge diagnostics must fire on the failure modes they were written for, and stay quiet otherwise.
 * Each test below corresponds to a way a backtest has actually misled someone in this repository.
 */
import { describe, expect, it } from "vitest";
import { instrument } from "../instruments";
import { costHurdle, exitSplit, medianBarTicks, verdict } from "./edge";
import type { ControlResult, WalkStats } from "./tensor";

const NQ = instrument("NQ");

const stats = (over: Partial<WalkStats> = {}): WalkStats => ({
  n: 200, netUsd: 4000, wins: 120, grossWin: 9000, grossLoss: 5000, sumSq: 1e6,
  maxDrawdown: 900, byReason: [80, 110, 10, 0],
  nResearch: 130, netResearch: 2800, winsResearch: 80,
  nLocked: 70, netLocked: 1200, winsLocked: 40,
  ...over,
});

const ctrl = (over: Partial<ControlResult> = {}): ControlResult => ({
  draws: 2000, meanAll: 5, meanResearch: 5, meanLocked: 5,
  pAll: 0.2, pResearch: 0.2, pLocked: 0.2, meanWinPct: 50, pWin: 0.2,
  ...over,
});

describe("cost hurdle", () => {
  it("quotes the round turn in ticks and dollars, and the worst case above it", () => {
    const h = costHurdle(NQ);
    expect(h.ticks).toBeGreaterThan(0);
    expect(h.usd).toBeCloseTo(h.ticks * NQ.tickValue, 6);
    expect(h.worstTicks).toBeGreaterThan(h.ticks);
  });

  it("expresses the hurdle as a share of a typical bar when given one", () => {
    const h = costHurdle(NQ, 40);
    expect(h.shareOfBar).toBeCloseTo(h.ticks / 40, 9);
    expect(costHurdle(NQ).shareOfBar).toBeNull();
  });

  it("computes a median bar range in ticks", () => {
    const highs = [10, 20, 30, 40, 50];
    const lows = [9, 18, 27, 36, 45];
    // ranges in ticks (tickSize 0.25): 4, 8, 12, 16, 20 -> median 12
    expect(medianBarTicks(highs, lows, 0.25)).toBe(12);
  });
});

describe("exit split", () => {
  it("reports every reason and its share", () => {
    const rows = exitSplit(stats());
    expect(rows.map((r) => r.reason)).toEqual(["stop", "target", "time", "session"]);
    expect(rows.reduce((a, r) => a + r.n, 0)).toBe(200);
    expect(rows[1].share).toBeCloseTo(110 / 200, 9);
  });
});

describe("verdict", () => {
  it("scores the win rate against the geometry's own base rate, not against 50%", () => {
    const v = verdict(stats({ wins: 140 }), ctrl({ meanWinPct: 68 }), 1, costHurdle(NQ));
    expect(v.winPct).toBeCloseTo(70, 6);
    expect(v.baseRatePct).toBe(68);
    expect(v.excessWinPct).toBeCloseTo(2, 6);
  });

  it("flags a 70% win rate that is really a 68% base rate", () => {
    const v = verdict(stats({ wins: 138 }), ctrl({ meanWinPct: 68 }), 1, costHurdle(NQ));
    expect(v.warnings.join(" ")).toMatch(/mostly the barrier placement/);
  });

  it("flags a rule whose profit arrives at the time stop as a direction bet", () => {
    const v = verdict(stats({ byReason: [30, 20, 150, 0] }), ctrl(), 1, costHurdle(NQ));
    expect(v.timeStopShare).toBeCloseTo(0.75, 6);
    expect(v.warnings.join(" ")).toMatch(/bet on drift over a\s+fixed horizon|bet on drift/);
  });

  it("flags an edge too thin to survive a wrong cost assumption", () => {
    const v = verdict(stats({ netUsd: 1010, n: 200 }), ctrl({ meanAll: 5 }), 1, costHurdle(NQ));
    expect(v.warnings.join(" ")).toMatch(/thin enough that a wrong cost assumption erases it/);
  });

  it("flags too few trades", () => {
    const v = verdict(stats({ n: 12, wins: 8 }), ctrl(), 1, costHurdle(NQ));
    expect(v.warnings.join(" ")).toMatch(/too few to distinguish from noise/);
  });

  it("always states the multiplicity when more than one configuration was searched", () => {
    const v = verdict(stats(), ctrl({ meanWinPct: 40, meanAll: -20 }), 12_600, costHurdle(NQ));
    expect(v.bonferroni).toBeCloseTo(0.05 / 12_600, 12);
    expect(v.warnings.join(" ")).toMatch(/12,600 configurations were evaluated/);
    expect(v.warnings.join(" ")).toMatch(/630\.0 are expected to clear 0\.05 by chance/);
  });

  it("stays quiet on a clean single-configuration result", () => {
    // Big excess over base rate, mostly barrier exits, one configuration, fat per-trade edge.
    const v = verdict(
      stats({ n: 400, wins: 260, netUsd: 40_000, byReason: [140, 250, 10, 0] }),
      ctrl({ meanWinPct: 50, meanAll: 5 }),
      1,
      costHurdle(NQ),
    );
    expect(v.warnings).toEqual([]);
  });

  it("returns nulls rather than guesses when there is no control", () => {
    const v = verdict(stats(), null, 1, costHurdle(NQ));
    expect(v.baseRatePct).toBeNull();
    expect(v.excessWinPct).toBeNull();
    expect(v.excessPerTrade).toBeNull();
  });
});
