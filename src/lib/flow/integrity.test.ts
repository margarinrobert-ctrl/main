import { describe, expect, it } from "vitest";
import type { OptionContract } from "../barchart/types";
import { assessChain } from "./integrity";

function c(p: Partial<OptionContract>): OptionContract {
  return {
    symbol: "X",
    underlying: "X",
    type: "call",
    strike: 100,
    expiration: "2026-07-16",
    dte: 30,
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

describe("assessChain", () => {
  const good = [c({}), c({ type: "put", delta: -0.5 })];

  it("verifies complete live CBOE data and keeps its timestamp", () => {
    const r = assessChain(good, 100, "live", "2026-06-16 15:45");
    expect(r.status).toBe("live");
    expect(r.asOf).toBe("2026-06-16 15:45");
    expect(r.checks.find((x) => x.label === "Source")!.ok).toBe(true);
    expect(r.greeksPct).toBe(1);
  });

  it("flags sample/fixtures data", () => {
    const r = assessChain(good, 100, "fixtures");
    expect(r.status).toBe("sample");
    expect(r.checks.find((x) => x.label === "Source")!.ok).toBe(false);
  });

  it("flags degraded live data when greeks are missing", () => {
    const noGreeks = [c({ gamma: null, delta: null, impliedVolatility: null }), c({ gamma: null, delta: null, impliedVolatility: null })];
    expect(assessChain(noGreeks, 100, "live").status).toBe("degraded");
  });

  it("flags degraded when spot is missing", () => {
    expect(assessChain(good, null, "live").status).toBe("degraded");
  });

  it("reports empty when no contracts", () => {
    expect(assessChain([], 100, "live").status).toBe("empty");
  });
});
