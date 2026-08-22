import { describe, expect, it } from "vitest";
import { PROP_RULES, simulatePropRun, dayPathsFromTrades, type DayPath, type PropRules } from "./propFirm";
import { instrument } from "./instruments";
import type { Bar, Trade } from "./types";

const flat = (day: number, pnl: number): DayPath => ({ day, pnl, marks: [pnl] });

const RULES: PropRules = {
  label: "test",
  startBalance: 50_000,
  trailingDrawdown: 2_500,
  trailMode: "intraday",
  lockAt: 100,
  profitTarget: 3_000,
  minTradingDays: 3,
};

describe("simulatePropRun", () => {
  it("passes once the target and the minimum day count are both met", () => {
    const days = [flat(0, 1_000), flat(1, 1_000), flat(2, 1_000)];
    const r = simulatePropRun(days, RULES, 1);
    expect(r.outcome).toBe("passed");
    expect(r.days).toBe(3);
    expect(r.profit).toBe(3_000);
  });

  it("does not pass on the target alone when the minimum day count is unmet", () => {
    const days = [flat(0, 3_000)];
    const r = simulatePropRun(days, RULES, 1);
    // Target hit on day 1, but three days are required and no more were supplied.
    expect(r.outcome).toBe("ran-out-of-days");
    expect(r.profit).toBe(3_000);
  });

  it("kills the account on a retracement from a peak that was never banked", () => {
    // Runs +2,000 unrealised, closes flat, then loses 600. Measured from the start that is a 600
    // drawdown and survives; measured from the 2,000 peak it is 2,600 and does not.
    const days: DayPath[] = [
      { day: 0, pnl: 0, marks: [0, 2_000, 0] },
      { day: 1, pnl: -600, marks: [0, -600] },
    ];
    expect(simulatePropRun(days, RULES, 1).outcome).toBe("blown");
    // Without the unrealised spike the same closed P&L is fine.
    const noSpike: DayPath[] = [flat(0, 0), flat(1, -600)];
    expect(simulatePropRun(noSpike, RULES, 1).outcome).not.toBe("blown");
  });

  it("locks the threshold at the lock point instead of trailing forever", () => {
    // A peak of 60,000 puts a pure trailing threshold at 57,500. Locked at start+100 it sits at
    // 50,100 instead, so a fall to 57,000 survives the locked account and kills the trailing one.
    const days: DayPath[] = [flat(0, 10_000), { day: 1, pnl: -3_000, marks: [0, -3_000] }];
    const r = simulatePropRun(days, { ...RULES, profitTarget: 1e9 }, 1);
    expect(r.outcome).not.toBe("blown");
    // With no lock, the same path dies.
    const trailing = simulatePropRun(days, { ...RULES, lockAt: Infinity, profitTarget: 1e9 }, 1);
    expect(trailing.outcome).toBe("blown");
  });

  it("scales the path by contract count, so size decides survival", () => {
    const days: DayPath[] = [{ day: 0, pnl: -1_200, marks: [0, -1_200] }, flat(1, 0), flat(2, 0)];
    expect(simulatePropRun(days, RULES, 1).outcome).not.toBe("blown");
    expect(simulatePropRun(days, RULES, 3).outcome).toBe("blown");
  });

  it("fails on a daily loss limit even when the trailing threshold is untouched", () => {
    const withLimit = { ...RULES, dailyLossLimit: 1_000 };
    const days: DayPath[] = [{ day: 0, pnl: -1_100, marks: [0, -1_100] }];
    expect(simulatePropRun(days, withLimit, 1).outcome).toBe("daily-loss");
    expect(simulatePropRun(days, RULES, 1).outcome).not.toBe("daily-loss");
  });

  it("eod mode ignores an intraday spike that intraday mode acts on", () => {
    const days: DayPath[] = [
      { day: 0, pnl: 0, marks: [0, 2_000, 0] },
      { day: 1, pnl: -600, marks: [0, -600] },
    ];
    expect(simulatePropRun(days, RULES, 1).outcome).toBe("blown");
    expect(simulatePropRun(days, { ...RULES, trailMode: "eod" }, 1).outcome).not.toBe("blown");
  });

  it("flags a consistency breach without failing the evaluation", () => {
    // One day carries 90% of the profit; a 30% rule cannot be satisfied at that point.
    const days = [flat(0, 2_700), flat(1, 150), flat(2, 150)];
    const r = simulatePropRun(days, { ...RULES, consistencyPct: 0.3 }, 1);
    expect(r.largestWinningDay).toBe(2_700);
    // The evaluation is passed; it is the payout that the rule blocks.
    expect(r.outcome).toBe("passed");
    expect(r.consistencyBlocked).toBe(true);
  });

  it("stops at the day budget", () => {
    const days = Array.from({ length: 50 }, (_, i) => flat(i, 10));
    const r = simulatePropRun(days, RULES, 1, 5);
    expect(r.days).toBe(5);
    expect(r.outcome).toBe("ran-out-of-days");
  });
});

describe("dayPathsFromTrades", () => {
  const inst = instrument("NQ"); // $20 per point
  const bar = (t: number, o: number, h: number, l: number, c: number): Bar => ({ t, o, h, l, c, v: 1 });

  it("charges the cost at entry and tracks unrealised excursion in both directions", () => {
    const bars = [bar(0, 100, 100, 100, 100), bar(1, 100, 110, 95, 105)];
    const trade: Trade = {
      side: 1, entryIndex: 1, exitIndex: 1, entryTime: 1, exitTime: 1,
      entryPx: 100, exitPx: 105, grossPoints: 5, costPoints: 1,
      pnl: (5 - 1) * 20, r: 0.5, barsHeld: 1, reason: "target",
    };
    const [d] = dayPathsFromTrades([trade], bars, inst, [0, 0]);
    expect(d.pnl).toBe(80);
    // First mark is the cost alone, before any price movement.
    expect(d.marks[0]).toBe(-20);
    // The favourable extreme (110) and the adverse one (95) both appear, net of the entry cost.
    expect(d.marks).toContain(-20 + 10 * 20);
    expect(d.marks).toContain(-20 - 5 * 20);
    expect(d.marks[d.marks.length - 1]).toBe(80);
  });

  it("mirrors the excursion logic for a short", () => {
    const bars = [bar(0, 100, 110, 95, 105)];
    const trade: Trade = {
      side: -1, entryIndex: 0, exitIndex: 0, entryTime: 0, exitTime: 0,
      entryPx: 100, exitPx: 95, grossPoints: 5, costPoints: 1,
      pnl: (5 - 1) * 20, r: 0.5, barsHeld: 1, reason: "target",
    };
    const [d] = dayPathsFromTrades([trade], bars, inst, [0]);
    // For a short the low is favourable and the high is adverse.
    expect(d.marks).toContain(-20 + 5 * 20);
    expect(d.marks).toContain(-20 - 10 * 20);
  });

  it("accumulates a second trade in the same session on top of the first", () => {
    const bars = [bar(0, 100, 100, 100, 100), bar(1, 100, 100, 100, 100)];
    const mk = (i: number, pnl: number): Trade => ({
      side: 1, entryIndex: i, exitIndex: i, entryTime: i, exitTime: i,
      entryPx: 100, exitPx: 100, grossPoints: 0, costPoints: 0, pnl, r: 0, barsHeld: 1, reason: "target",
    });
    const [d] = dayPathsFromTrades([mk(0, 100), mk(1, -40)], bars, inst, [0, 0]);
    expect(d.pnl).toBe(60);
    expect(d.marks[d.marks.length - 1]).toBe(60);
  });

  it("keeps sessions separate and in order", () => {
    const bars = [bar(0, 100, 100, 100, 100), bar(1, 100, 100, 100, 100)];
    const mk = (i: number, pnl: number): Trade => ({
      side: 1, entryIndex: i, exitIndex: i, entryTime: i, exitTime: i,
      entryPx: 100, exitPx: 100, grossPoints: 0, costPoints: 0, pnl, r: 0, barsHeld: 1, reason: "target",
    });
    const days = dayPathsFromTrades([mk(1, -40), mk(0, 100)], bars, inst, [0, 5]);
    expect(days.map((d) => d.day)).toEqual([0, 5]);
    expect(days.map((d) => d.pnl)).toEqual([100, -40]);
  });
});

describe("PROP_RULES", () => {
  it("models the two firms' trailing behaviour differently", () => {
    expect(PROP_RULES.apex50k.trailMode).toBe("intraday");
    expect(PROP_RULES.topstep50k.trailMode).toBe("eod");
    expect(PROP_RULES.topstep50k.dailyLossLimit).toBe(1_000);
    expect(PROP_RULES.apex50k.dailyLossLimit).toBeUndefined();
  });
});
