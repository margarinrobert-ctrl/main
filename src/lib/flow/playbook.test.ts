import { describe, expect, it } from "vitest";
import type { OptionContract } from "../barchart/types";
import { buildPlaybook } from "./playbook";

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

describe("buildPlaybook", () => {
  it("classifies long-gamma regime and emits level plays", () => {
    const chain = [
      c({ type: "call", strike: 110, gamma: 0.02, openInterest: 9000 }),
      c({ type: "put", strike: 90, gamma: 0.02, openInterest: 4000 }),
    ];
    const pb = buildPlaybook(chain, 100);
    expect(pb.regime).toBe("long"); // net call gamma positive
    expect(pb.plays.length).toBeGreaterThan(2);
    expect(pb.plays.some((p) => p.title.includes("Call wall"))).toBe(true);
    expect(pb.notes.some((n) => n.toLowerCase().includes("not financial advice"))).toBe(true);
  });

  it("sets bullish bias when spot is above the gamma flip", () => {
    const chain = [
      c({ type: "put", strike: 95, gamma: 0.05, openInterest: 2000 }),
      c({ type: "call", strike: 105, gamma: 0.05, openInterest: 8000 }),
    ];
    const pb = buildPlaybook(chain, 120); // well above flip
    expect(pb.bias).toBe("bullish");
  });
});
