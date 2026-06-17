import { describe, expect, it } from "vitest";
import type { OptionContract } from "./barchart/types";
import { buildGexPine } from "./pine";

function c(p: Partial<OptionContract>): OptionContract {
  return {
    symbol: "X",
    underlying: "X",
    type: "call",
    strike: 100,
    expiration: "2026-06-19",
    dte: 1,
    bid: 1,
    ask: 1.2,
    last: 1.1,
    volume: 100,
    openInterest: 5000,
    impliedVolatility: 0.3,
    delta: 0.5,
    gamma: 0.02,
    theta: -0.05,
    vega: 0.1,
    underlyingPrice: 100,
    ...p,
  };
}

describe("buildGexPine", () => {
  it("emits a v6 indicator with named levels + OI/V/GEX/DEX detail and array-driven levels", () => {
    const chain = [
      c({ type: "call", strike: 105, gamma: 0.05, openInterest: 9000, volume: 12000 }),
      c({ type: "put", strike: 95, gamma: 0.02, openInterest: 4000, volume: 15000 }),
    ];
    const r = buildGexPine("TEST", chain, 100);
    expect(r.code).toContain("//@version=6");
    expect(r.code).toContain("OptionsFlow GEX • TEST");
    expect(r.code).toContain("Call Resistance"); // in hover detail
    expect(r.code).toContain("Put Support");
    expect(r.code).toContain("HVL");
    expect(r.code).toContain("0DTE");
    expect(r.code).toContain("OI "); // open-interest annotation
    expect(r.code).toContain("DEX "); // delta-exposure annotation
    expect(r.code).toContain("~15-min delayed"); // freshness note
    expect(r.code).toMatch(/P\s+=\s+array\.from\([^)]*\.\d/); // float price array
    expect(r.code).toContain("D  = array.from("); // hover-detail array
    expect(r.expiration).toBe("2026-06-19");
  });

  it("collapses to a single spot level when there is no data", () => {
    const empty = buildGexPine("EMPTY", [], 50);
    expect(empty.code).toContain("indicator(");
    expect(empty.code).toContain("array.from(50.0)");
    expect(empty.code).toContain("Spot");
  });

  it("adds Max Pain + OI-wall levels and never prints resistance == support", () => {
    // ATM strike dominates both call and put gamma — the bug that put them on the same line.
    const chain = [
      c({ type: "call", strike: 100, gamma: 0.1, openInterest: 6000, volume: 5000 }),
      c({ type: "put", strike: 100, gamma: 0.1, openInterest: 6000, volume: 5000 }),
      c({ type: "call", strike: 105, gamma: 0.05, openInterest: 7000, volume: 4000 }),
      c({ type: "put", strike: 95, gamma: 0.05, openInterest: 7000, volume: 4000 }),
    ];
    const r = buildGexPine("LVL", chain, 100);
    expect(r.code).toContain("Max Pain");
    expect(r.code).toContain("Call OI wall");
    expect(r.code).toContain("Put OI wall");
    expect(r.callRes!).toBeGreaterThan(100); // resistance above spot
    expect(r.putSup!).toBeLessThan(100); // support below spot
    expect(r.callRes).not.toBe(r.putSup);
  });

  it("notes the index-proxy basis for futures symbols", () => {
    const chain = [c({ type: "call", strike: 105, gamma: 0.02, openInterest: 8000 }), c({ type: "put", strike: 95, gamma: 0.03, openInterest: 9000 })];
    expect(buildGexPine("NQ", chain, 100).code).toContain("proxy");
    expect(buildGexPine("SPY", chain, 100).code).not.toContain("free proxy");
  });

  it("targets a chosen expiration when one is passed (e.g. 0DTE)", () => {
    const chain = [
      c({ expiration: "2026-06-16", dte: 0, strike: 100, gamma: 0.03, openInterest: 7000 }),
      c({ expiration: "2026-07-17", dte: 31, strike: 100, gamma: 0.02, openInterest: 5000 }),
    ];
    expect(buildGexPine("ZD", chain, 100).expiration).toBe("2026-06-16"); // nearest by default
    expect(buildGexPine("ZD", chain, 100, 10, "2026-07-17").expiration).toBe("2026-07-17");
    expect(buildGexPine("ZD", chain, 100, 10, "ALL").expiration).toBe("2026-06-16"); // ALL → nearest
  });
});
