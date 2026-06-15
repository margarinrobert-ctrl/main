import { describe, expect, it } from "vitest";
import { scoreContract } from "./heuristic";
import type { OptionContract } from "../barchart/types";

const base: OptionContract = {
  symbol: "TEST260619C100",
  underlying: "TEST",
  type: "call",
  strike: 100,
  expiration: "2026-06-19",
  dte: 5,
  bid: 1.0,
  ask: 1.2,
  last: 1.1,
  volume: 5000,
  openInterest: 500,
  impliedVolatility: 0.5,
  delta: 0.3,
  gamma: 0.01,
  theta: -0.05,
  vega: 0.1,
  underlyingPrice: 100,
};

describe("scoreContract", () => {
  it("fails the gates on tiny volume", () => {
    const r = scoreContract({ ...base, volume: 10 });
    expect(r.passedGates).toBe(false);
    expect(r.score).toBe(0);
  });

  it("scores and flags high vol/OI", () => {
    const r = scoreContract(base);
    expect(r.passedGates).toBe(true);
    expect(r.score).toBeGreaterThan(0);
    expect(r.flags).toContain("High Vol/OI");
  });

  it("flags short-dated far-OTM contracts", () => {
    const r = scoreContract({ ...base, strike: 110, underlyingPrice: 100, dte: 3 });
    expect(r.flags).toContain("Short-dated OTM");
  });

  it("redistributes spike weight when avgVolume is absent (score not capped)", () => {
    const withoutSpike = scoreContract(base);
    const withSpike = scoreContract(base, { avgVolume: 250 });
    expect(withSpike.signals.volSpike).not.toBeNull();
    expect(withoutSpike.signals.volSpike).toBeNull();
    expect(withoutSpike.score).toBeGreaterThan(0);
  });
});
