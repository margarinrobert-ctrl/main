import { describe, expect, it } from "vitest";
import { expectedMove, gammaFlip, gexByStrike, maxPain, putCallRatio } from "./analytics";
import type { OptionContract } from "../barchart/types";

function c(p: Partial<OptionContract>): OptionContract {
  return {
    symbol: "X",
    underlying: "X",
    type: "call",
    strike: 100,
    expiration: "2026-06-19",
    dte: 5,
    bid: 1,
    ask: 1.2,
    last: 1.1,
    volume: 100,
    openInterest: 1000,
    impliedVolatility: 0.3,
    delta: 0.5,
    gamma: 0.02,
    theta: -0.05,
    vega: 0.1,
    underlyingPrice: 100,
    ...p,
  };
}

describe("analytics", () => {
  it("aggregates GEX by strike (calls +, puts -)", () => {
    const by = gexByStrike([c({ type: "call", strike: 100 }), c({ type: "put", strike: 100 })], 100);
    expect(by).toHaveLength(1);
    expect(by[0].callGex).toBeGreaterThan(0);
    expect(by[0].putGex).toBeLessThan(0);
  });

  it("finds a gamma flip between negative and positive cumulative GEX", () => {
    const by = gexByStrike(
      [
        c({ type: "put", strike: 95, gamma: 0.05, openInterest: 2000 }),
        c({ type: "call", strike: 105, gamma: 0.05, openInterest: 8000 }),
      ],
      100,
    );
    const flip = gammaFlip(by);
    expect(flip).not.toBeNull();
    expect(flip!).toBeGreaterThan(95);
    expect(flip!).toBeLessThan(105);
  });

  it("computes max pain near the heaviest OI strike", () => {
    const chain = [
      c({ type: "call", strike: 100, openInterest: 10000 }),
      c({ type: "put", strike: 100, openInterest: 10000 }),
      c({ type: "call", strike: 120, openInterest: 100 }),
      c({ type: "put", strike: 80, openInterest: 100 }),
    ];
    expect(maxPain(chain, "2026-06-19")).toBe(100);
  });

  it("computes expected move from the ATM straddle", () => {
    const em = expectedMove(
      [c({ type: "call", strike: 100, bid: 2, ask: 2.2 }), c({ type: "put", strike: 100, bid: 1.8, ask: 2 })],
      100,
      "2026-06-19",
    );
    expect(em).not.toBeNull();
    expect(em!.abs).toBeCloseTo(4.0, 1);
  });

  it("computes put/call ratios", () => {
    const r = putCallRatio([c({ type: "call", volume: 100 }), c({ type: "put", volume: 200 })]);
    expect(r.vol).toBeCloseTo(2, 5);
  });
});
