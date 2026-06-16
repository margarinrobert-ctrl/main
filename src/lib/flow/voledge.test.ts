import { describe, expect, it } from "vitest";
import type { HistoryBar, OptionContract } from "../barchart/types";
import { buildVolReport } from "./voledge";

function opt(p: Partial<OptionContract>): OptionContract {
  return {
    symbol: "X",
    underlying: "X",
    type: "call",
    strike: 100,
    expiration: "2026-06-19",
    dte: 3,
    bid: 1,
    ask: 1.2,
    last: 1.1,
    volume: 100,
    openInterest: 1000,
    impliedVolatility: 0.5,
    delta: 0.5,
    gamma: 0.02,
    theta: -0.05,
    vega: 0.1,
    underlyingPrice: 100,
    ...p,
  };
}

function bars(closes: number[]): HistoryBar[] {
  return closes.map((c, i) => ({
    timestamp: `2026-05-${String((i % 28) + 1).padStart(2, "0")}T00:00:00Z`,
    open: c,
    high: c,
    low: c,
    close: c,
    volume: 1000,
  }));
}

describe("buildVolReport", () => {
  it("flags short-vol when IV is far above realized", () => {
    const chain = [
      opt({ type: "call", strike: 100, impliedVolatility: 0.5, delta: 0.5 }),
      opt({ type: "put", strike: 100, impliedVolatility: 0.5, delta: -0.5 }),
    ];
    const calm = Array.from({ length: 25 }, (_, i) => 100 + Math.sin(i) * 0.05); // tiny moves -> low RV
    const r = buildVolReport(chain, 100, bars(calm));
    expect(r.atmIv).toBeCloseTo(0.5, 2);
    expect(r.rv20).not.toBeNull();
    expect(r.vrpRatio).not.toBeNull();
    expect(r.vrpRatio!).toBeGreaterThan(1.2);
    expect(r.reads.some((x) => x.side === "short-vol")).toBe(true);
  });

  it("flags long-vol when IV is below realized", () => {
    const chain = [
      opt({ type: "call", strike: 100, impliedVolatility: 0.05, delta: 0.5 }),
      opt({ type: "put", strike: 100, impliedVolatility: 0.05, delta: -0.5 }),
    ];
    const wild = Array.from({ length: 25 }, (_, i) => 100 * (1 + (i % 2 === 0 ? 0.04 : -0.04))); // big swings -> high RV
    const r = buildVolReport(chain, 100, bars(wild));
    expect(r.reads.some((x) => x.side === "long-vol")).toBe(true);
  });
});
