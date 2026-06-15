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
  it("emits a v6 indicator with named GEX levels", () => {
    const chain = [
      c({ type: "call", strike: 105, gamma: 0.02, openInterest: 8000 }),
      c({ type: "put", strike: 95, gamma: 0.03, openInterest: 9000 }),
    ];
    const r = buildGexPine("TEST", chain, 100);
    expect(r.code).toContain("//@version=6");
    expect(r.code).toContain("OptionsFlow GEX • TEST");
    expect(r.code).toContain("Call Resistance");
    expect(r.code).toContain("Put Support");
    expect(r.code).toContain("HVL");
    expect(r.code).toContain("0DTE");
    expect(r.code).toContain('"GEX " + str.tostring(i + 1)');
    expect(r.expiration).toBe("2026-06-19");
  });

  it("emits float arrays (never array<int>) and falls back to spot when empty", () => {
    const chain = [c({ type: "call", strike: 100, gamma: 0.01, openInterest: 1000000 })];
    const withData = buildGexPine("INTG", chain, 100);
    expect(withData.code).toMatch(/var float\[\] gexK = array\.from\([-0-9., ]*\.\d/);

    const empty = buildGexPine("EMPTY", [], 50);
    expect(empty.code).toContain("indicator(");
    expect(empty.code).toContain("array.from(50.0)");
  });
});
