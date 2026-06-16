import { describe, expect, it } from "vitest";
import {
  expectedMove,
  expectedMove1D,
  gammaFlip,
  gexByExpiration,
  gexByStrike,
  maxPain,
  oiByStrike,
  putCallRatio,
  secondOrderExposure,
} from "./analytics";
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

  it("computes the 1-day expected move from ATM IV (not the to-expiry straddle)", () => {
    const em1 = expectedMove1D(100, 0.2);
    expect(em1).not.toBeNull();
    expect(em1!.pct).toBeCloseTo(0.2 * Math.sqrt(1 / 252), 6);
    expect(em1!.abs).toBeCloseTo(100 * 0.2 * Math.sqrt(1 / 252), 4);
    expect(expectedMove1D(null, 0.2)).toBeNull();
    expect(expectedMove1D(100, 0)).toBeNull();
    expect(expectedMove1D(100, null)).toBeNull();
  });

  it("derives dealer vanna & charm exposure with the GEX sign convention", () => {
    // OTM call: raising IV lifts delta (+vanna); delta bleeds to 0 into expiry (−charm).
    const so = secondOrderExposure([c({ type: "call", strike: 110, openInterest: 1000, impliedVolatility: 0.3, dte: 18 })], 100);
    expect(so.vanna).not.toBeNull();
    expect(so.charm).not.toBeNull();
    expect(so.vanna!).toBeGreaterThan(0);
    expect(so.charm!).toBeLessThan(0);
    expect(so.byStrike).toHaveLength(1);
  });

  it("returns null second-order exposure when spot or IV is missing", () => {
    expect(secondOrderExposure([c({})], null)).toMatchObject({ vanna: null, charm: null });
    const noIv = secondOrderExposure([c({ impliedVolatility: null })], 100);
    expect(noIv.vanna).toBeNull();
    expect(noIv.charm).toBeNull();
  });

  it("computes put/call ratios", () => {
    const r = putCallRatio([c({ type: "call", volume: 100 }), c({ type: "put", volume: 200 })]);
    expect(r.vol).toBeCloseTo(2, 5);
  });

  it("aggregates GEX by expiration (term structure)", () => {
    const term = gexByExpiration(
      [
        c({ type: "call", strike: 100, expiration: "2026-06-19", dte: 4, gamma: 0.02, openInterest: 5000 }),
        c({ type: "put", strike: 100, expiration: "2026-07-17", dte: 32, gamma: 0.02, openInterest: 5000 }),
      ],
      100,
    );
    expect(term).toHaveLength(2);
    expect(term[0].expiration).toBe("2026-06-19");
    expect(term[0].gex).toBeGreaterThan(0); // call -> positive
    expect(term[1].gex).toBeLessThan(0); // put -> negative
  });

  it("aggregates open interest by strike", () => {
    const oi = oiByStrike([
      c({ type: "call", strike: 100, openInterest: 500 }),
      c({ type: "put", strike: 100, openInterest: 300 }),
      c({ type: "call", strike: 110, openInterest: 200 }),
    ]);
    expect(oi).toHaveLength(2);
    expect(oi[0]).toMatchObject({ strike: 100, callOi: 500, putOi: 300 });
    expect(oi[1]).toMatchObject({ strike: 110, callOi: 200, putOi: 0 });
  });
});
