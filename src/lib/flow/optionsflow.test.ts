import { describe, expect, it } from "vitest";
import type { OptionContract } from "../barchart/types";
import { optionsFlow } from "./optionsflow";

function c(p: Partial<OptionContract>): OptionContract {
  return {
    symbol: "QQQ260626C710",
    underlying: "QQQ",
    type: "call",
    strike: 710,
    expiration: "2026-06-26",
    dte: 0,
    bid: 1.0,
    ask: 1.2,
    last: 1.2,
    volume: 1000,
    openInterest: 5000,
    impliedVolatility: 0.25,
    delta: 0.4,
    gamma: 0.02,
    theta: -0.1,
    vega: 0.05,
    underlyingPrice: 707,
    ...p,
  };
}

describe("optionsFlow", () => {
  it("computes premium (vol × mid × 100) and sorts rows by premium desc", () => {
    const f = optionsFlow([c({ symbol: "A", volume: 100 }), c({ symbol: "B", volume: 2000 })], 707);
    expect(f.rows[0].contract).toBe("B"); // bigger premium first
    expect(f.rows[0].premium).toBeCloseTo(2000 * 1.1 * 100, 4); // mid = (1.0+1.2)/2 = 1.1
  });

  it("classifies side from the last vs bid/ask and reads direction", () => {
    const atAsk = optionsFlow([c({ last: 1.2, bid: 1.0, ask: 1.2 })], 707).rows[0]; // call at ask → bullish
    expect(atAsk.side).toBe("ASK");
    expect(atAsk.bullish).toBe(true);
    const putAtAsk = optionsFlow([c({ type: "put", delta: -0.4, last: 1.2, bid: 1.0, ask: 1.2 })], 707).rows[0]; // put at ask → bearish
    expect(putAtAsk.side).toBe("ASK");
    expect(putAtAsk.bullish).toBe(false);
  });

  it("rolls up net-trade sentiment (bullish call buying > bearish)", () => {
    const f = optionsFlow(
      [
        c({ symbol: "C", type: "call", last: 1.2, bid: 1.0, ask: 1.2, volume: 3000 }), // bullish (call @ ask)
        c({ symbol: "P", type: "put", delta: -0.4, last: 1.2, bid: 1.0, ask: 1.2, volume: 500 }), // bearish (put @ ask)
      ],
      707,
    );
    expect(f.sentiment.bullPremium).toBeGreaterThan(0);
    expect(f.sentiment.bearPremium).toBeLessThan(0);
    expect(f.sentiment.netPremium).toBeGreaterThan(0); // net bullish
  });

  it("computes delta imbalance (call delta + / put delta −)", () => {
    const f = optionsFlow(
      [c({ type: "call", delta: 0.5, volume: 1000 }), c({ type: "put", delta: -0.5, volume: 400 })],
      707,
    );
    expect(f.sentiment.callDelta).toBeGreaterThan(0);
    expect(f.sentiment.putDelta).toBeLessThan(0);
    expect(f.sentiment.deltaImbalance).toBeGreaterThan(0); // calls dominate
  });

  it("skips zero-volume contracts and honors minPremium / limit", () => {
    const f = optionsFlow([c({ symbol: "Z", volume: 0 }), c({ symbol: "S", volume: 10 }), c({ symbol: "L", volume: 5000 })], 707, { minPremium: 100_000, limit: 1 });
    expect(f.rows).toHaveLength(1); // limit
    expect(f.rows[0].contract).toBe("L");
    expect(f.rows.every((r) => r.premium >= 100_000)).toBe(true);
  });
});
