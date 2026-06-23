import { describe, expect, it } from "vitest";
import {
  callOiWall,
  callResistance,
  expectedMove,
  expectedMove1D,
  exposureProfile,
  filterByExpiration,
  flipFromProfile,
  gammaFlip,
  gexByExpiration,
  gexByStrike,
  greekSurface,
  levelStats,
  maxPain,
  oiByStrike,
  putCallRatio,
  putOiWall,
  putSupport,
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

  it("re-prices the exposure profile across spot and finds the regime flip", () => {
    // Puts below, calls above → short gamma under spot, long gamma over it: a flip in between.
    const chain = [
      c({ type: "put", strike: 95, gamma: 0.05, openInterest: 6000, impliedVolatility: 0.3, dte: 10 }),
      c({ type: "call", strike: 105, gamma: 0.05, openInterest: 6000, impliedVolatility: 0.3, dte: 10 }),
    ];
    const prof = exposureProfile(chain, 100, 41);
    expect(prof).toHaveLength(41);
    expect(prof[0].spot).toBeLessThan(prof[prof.length - 1].spot); // ascending
    const flip = flipFromProfile(prof);
    expect(flip).not.toBeNull();
    expect(flip!).toBeGreaterThan(95);
    expect(flip!).toBeLessThan(105);
    expect(exposureProfile(chain, null)).toHaveLength(0);
  });

  it("builds a (strike × expiration) greek surface ordered near→far by DTE", () => {
    const chain = [
      c({ strike: 100, expiration: "2026-07-17", dte: 31, openInterest: 100 }),
      c({ strike: 110, expiration: "2026-07-17", dte: 31, openInterest: 200 }),
      c({ strike: 100, expiration: "2026-06-19", dte: 3, openInterest: 300 }),
      c({ strike: 110, expiration: "2026-06-19", dte: 3, openInterest: 400 }),
    ];
    const surf = greekSurface(chain, 100, "oi");
    expect(surf.strikes).toEqual([100, 110]);
    expect(surf.expirations.map((e) => e.dte)).toEqual([3, 31]); // near→far
    expect(surf.z).toHaveLength(2);
    expect(surf.z[0]).toHaveLength(2);
    expect(surf.z[0]).toEqual([300, 400]); // front expiry OI row
    expect(surf.signed).toBe(false);
    expect(greekSurface(chain, 100, "gex").signed).toBe(true);
  });

  it("filters a chain by expiration (ALL / empty = passthrough)", () => {
    const chain = [c({ expiration: "2026-06-19" }), c({ expiration: "2026-07-17" })];
    expect(filterByExpiration(chain, "2026-06-19")).toHaveLength(1);
    expect(filterByExpiration(chain, "ALL")).toHaveLength(2);
    expect(filterByExpiration(chain, undefined)).toHaveLength(2);
  });

  it("keeps call resistance above spot and put support below it (no same-strike collision)", () => {
    // ATM strike 100 dominates BOTH call and put gamma — raw walls would collide there.
    const by = gexByStrike(
      [
        c({ type: "call", strike: 100, gamma: 0.1, openInterest: 5000 }),
        c({ type: "put", strike: 100, gamma: 0.1, openInterest: 5000 }),
        c({ type: "call", strike: 105, gamma: 0.04, openInterest: 5000 }),
        c({ type: "put", strike: 95, gamma: 0.04, openInterest: 5000 }),
      ],
      100,
    );
    const cr = callResistance(by, 100);
    const ps = putSupport(by, 100);
    expect(cr).toBe(105); // strictly above spot
    expect(ps).toBe(95); // strictly below spot
    expect(cr).not.toBe(ps);
  });

  it("finds the call/put open-interest walls", () => {
    const oi = oiByStrike([
      c({ type: "call", strike: 100, openInterest: 8000 }),
      c({ type: "call", strike: 110, openInterest: 2000 }),
      c({ type: "put", strike: 90, openInterest: 9000 }),
      c({ type: "put", strike: 100, openInterest: 1000 }),
    ]);
    expect(callOiWall(oi)).toBe(100);
    expect(putOiWall(oi)).toBe(90);
  });

  it("aggregates deep stats for the strike nearest a price", () => {
    const chain = [
      c({ type: "call", strike: 110, openInterest: 8000, volume: 5000, gamma: 0.04, delta: 0.3, impliedVolatility: 0.22 }),
      c({ type: "put", strike: 110, openInterest: 2000, volume: 1000, gamma: 0.04, delta: -0.7, impliedVolatility: 0.24 }),
      c({ type: "call", strike: 100, openInterest: 500, gamma: 0.02 }),
    ];
    const s = levelStats(chain, 100, 109); // nearest strike = 110
    expect(s.strike).toBe(110);
    expect(s.callOi).toBe(8000);
    expect(s.putOi).toBe(2000);
    expect(s.callVol).toBe(5000);
    expect(s.iv).toBeCloseTo(0.23, 5);
    expect(s.gexShare).toBeGreaterThan(0);
    expect(s.gexShare).toBeLessThanOrEqual(1);
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
