/**
 * Cost-model invariants.
 *
 * These are the properties that decide whether a scalping result means anything, so they are
 * asserted rather than assumed. The values in `costs.ts` are dated assumptions and will be wrong
 * in detail; the RELATIONSHIPS here should hold whatever the numbers are replaced with.
 */
import { describe, expect, it } from "vitest";
import {
  BROKER_PRESETS,
  CALM,
  describe as describeCosts,
  effectiveFees,
  effectiveSlippage,
  feePoints,
  feesPerSide,
  feesRoundTurn,
  fillCostPoints,
  fillFrictionPoints,
  scheduleFor,
  slippageTicks,
  REALISTIC_SLIPPAGE,
} from "./costs";
import { instrument, roundTurnCostPoints, roundTurnCostTicks, worstRoundTurnCostPoints } from "./instruments";
import type { Instrument } from "./types";

const NQ = instrument("NQ");
const MNQ = instrument("MNQ");

describe("fee decomposition", () => {
  it("adds the four per-side lines and doubles them for a round turn", () => {
    const f = scheduleFor("NQ", "discount");
    expect(feesPerSide(f)).toBeCloseTo(f.brokerPerSide + f.exchangePerSide + f.clearingPerSide + f.regulatoryPerSide, 12);
    expect(feesRoundTurn(f)).toBeCloseTo(2 * feesPerSide(f), 12);
  });

  it("keeps every instrument's headline commission equal to its itemised fees", () => {
    for (const id of ["NQ", "MNQ", "ES", "GC", "MGC", "CL", "MCL"]) {
      const inst = instrument(id);
      expect(inst.fees, `${id} has no itemised fees`).toBeDefined();
      expect(inst.commissionRoundTurn, `${id} headline disagrees with its fee lines`).toBeCloseTo(feesRoundTurn(inst.fees!), 12);
    }
  });

  it("keeps every instrument's headline slippage equal to its model base", () => {
    for (const id of ["NQ", "MNQ", "ES", "GC", "MGC", "CL", "MCL", "XAUUSD"]) {
      const inst = instrument(id);
      expect(effectiveSlippage(inst).volCoef, `${id} fell back to a flat model`).toBe(REALISTIC_SLIPPAGE.volCoef);
    }
  });

  it("includes an exchange fee, which the old lumped number did not", () => {
    const f = scheduleFor("NQ", "discount");
    expect(f.exchangePerSide).toBeGreaterThan(0);
    expect(f.regulatoryPerSide).toBeGreaterThan(0);
  });

  it("charges more per POINT traded on the micro than on the E-mini", () => {
    // The economic point of the whole decomposition. MNQ carries a tenth of NQ's tick value
    // against roughly a third of its fee, so an identical strategy pays several times as much of
    // its edge away. A single lumped commission hides this; the split makes it unavoidable.
    const perPoint = (i: Instrument) => (2 * feesPerSide(effectiveFees(i))) / (i.tickValue / i.tickSize);
    expect(perPoint(MNQ)).toBeGreaterThan(2 * perPoint(NQ));
  });
});

describe("override precedence", () => {
  it("lets an explicit commissionRoundTurn beat the itemised fees", () => {
    const free: Instrument = { ...NQ, commissionRoundTurn: 0 };
    expect(feePoints(free)).toBe(0);
    const doubled: Instrument = { ...NQ, commissionRoundTurn: 2 * NQ.commissionRoundTurn };
    expect(feePoints(doubled)).toBeCloseTo(2 * feePoints(NQ), 12);
  });

  it("lets an explicit slippageTicks beat the model", () => {
    const none: Instrument = { ...NQ, slippageTicks: 0 };
    expect(slippageTicks(effectiveSlippage(none), "taker", CALM)).toBe(0);
    // and it stays flat: a scalar override means a scalar, including on a fast bar
    expect(slippageTicks(effectiveSlippage(none), "stop", { volRatio: 50, inSession: false })).toBe(0);
  });

  it("gives a zero-cost instrument exactly zero cost", () => {
    const free: Instrument = { ...NQ, spreadTicks: 0, slippageTicks: 0, commissionRoundTurn: 0 };
    expect(fillCostPoints(free, "taker", CALM)).toBe(0);
    expect(fillCostPoints(free, "stop", { volRatio: 10, inSession: false })).toBe(0);
    expect(roundTurnCostPoints(free)).toBe(0);
  });
});

describe("slippage model", () => {
  const m = REALISTIC_SLIPPAGE;

  it("orders the roles: maker is free, a stop costs more than a plain taker", () => {
    expect(slippageTicks(m, "maker", CALM)).toBe(0);
    expect(slippageTicks(m, "stop", CALM)).toBeGreaterThan(slippageTicks(m, "taker", CALM));
  });

  it("is monotone in how fast the bar was", () => {
    let prev = -Infinity;
    for (const volRatio of [0.5, 1, 1.5, 2, 3]) {
      const t = slippageTicks(m, "taker", { volRatio, inSession: true });
      expect(t).toBeGreaterThanOrEqual(prev);
      prev = t;
    }
  });

  it("never charges less than the quiet-market base", () => {
    // A bar quieter than the median does not earn a discount: the spread is still the spread.
    expect(slippageTicks(m, "taker", { volRatio: 0, inSession: true })).toBeCloseTo(m.base, 12);
  });

  it("caps the volatility stretch so one freak bar cannot set the cost of a study", () => {
    const wild = slippageTicks(m, "taker", { volRatio: 1e6, inSession: true });
    expect(wild).toBeCloseTo(m.base * m.maxStretch, 12);
  });

  it("charges more outside the instrument's own session", () => {
    const inside = slippageTicks(m, "taker", { volRatio: 1, inSession: true });
    const outside = slippageTicks(m, "taker", { volRatio: 1, inSession: false });
    expect(outside).toBeCloseTo(inside * m.illiquidMult, 12);
  });
});

describe("round-turn reference", () => {
  it("quotes the calm market-in market-out case", () => {
    expect(roundTurnCostPoints(NQ)).toBeCloseTo(2 * fillCostPoints(NQ, "taker", CALM), 12);
  });

  it("is never cheaper than the fees alone", () => {
    for (const id of ["NQ", "MNQ", "ES"]) {
      const inst = instrument(id);
      expect(roundTurnCostPoints(inst)).toBeGreaterThan(2 * feePoints(inst));
    }
  });

  it("is strictly cheaper than the worst case", () => {
    for (const id of ["NQ", "MNQ", "ES"]) {
      const inst = instrument(id);
      expect(worstRoundTurnCostPoints(inst)).toBeGreaterThan(roundTurnCostPoints(inst));
    }
  });

  it("still reports MNQ as the more expensive contract to trade", () => {
    expect(roundTurnCostTicks(MNQ)).toBeGreaterThan(roundTurnCostTicks(NQ));
  });

  it("makes a maker exit cheaper than a taker exit, which is cheaper than a stop", () => {
    const maker = fillCostPoints(NQ, "maker", CALM);
    const taker = fillCostPoints(NQ, "taker", CALM);
    const stop = fillCostPoints(NQ, "stop", CALM);
    expect(maker).toBeLessThan(taker);
    expect(taker).toBeLessThan(stop);
    expect(fillFrictionPoints(NQ, "maker")).toBe(0);
  });
});

describe("broker presets", () => {
  it("orders the presets by what they cost, and every one is itemised", () => {
    const cost = (b: string) => feesRoundTurn(scheduleFor("MNQ", b));
    expect(cost("ibkr")).toBeLessThan(cost("premium"));
    expect(cost("discount")).toBeLessThan(cost("premium"));
    for (const id of Object.keys(BROKER_PRESETS)) {
      const f = scheduleFor("NQ", id);
      expect(f.source).toContain(BROKER_PRESETS[id].label);
      expect(f.exchangePerSide).toBeGreaterThan(0);
    }
  });

  it("says so loudly when it has no exchange schedule for a product", () => {
    const f = scheduleFor("SOMETHING_UNKNOWN", "discount");
    expect(f.exchangePerSide).toBe(0);
    expect(f.source).toMatch(/UNDERSTATES/);
  });

  it("rejects an unknown broker rather than silently costing nothing", () => {
    expect(() => scheduleFor("NQ", "not-a-broker")).toThrow(/unknown broker preset/);
  });

  it("prints a breakdown that can be held next to a statement", () => {
    const text = describeCosts(NQ);
    for (const line of ["broker", "exchange", "clearing", "regulatory", "ROUND TURN", "source"]) {
      expect(text).toContain(line);
    }
  });
});
