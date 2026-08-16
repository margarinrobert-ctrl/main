import { describe, expect, it } from "vitest";
import type { OptionContract } from "../barchart/types";
import { atmIv, gexByStrike, netGex } from "./analytics";
import { enrichGreeks } from "./enrich";

function c(p: Partial<OptionContract>): OptionContract {
  return {
    symbol: "X", underlying: "X", type: "call", strike: 100, expiration: "2026-07-14", dte: 0,
    bid: null, ask: null, last: null, volume: 100, openInterest: 5000, impliedVolatility: null,
    delta: null, gamma: null, theta: null, vega: null, underlyingPrice: 100, ...p,
  };
}

describe("enrichGreeks", () => {
  it("backfills IV/Δ/Γ for a 0DTE call missing them — finite, no T→0 blow-up", () => {
    const chain = [c({ type: "call", strike: 100, dte: 0, bid: 1.0, ask: 1.2 })];
    const out = enrichGreeks(chain, 100);
    expect(out[0].impliedVolatility).not.toBeNull();
    expect(out[0].impliedVolatility!).toBeGreaterThan(0);
    expect(out[0].gamma).not.toBeNull();
    expect(Number.isFinite(out[0].gamma!)).toBe(true);
    expect(out[0].gamma!).toBeGreaterThan(0);
    expect(out[0].delta).not.toBeNull();
    expect(out[0].delta!).toBeGreaterThan(0);
    expect(out[0].delta!).toBeLessThan(1);
  });

  it("gives a 0DTE put a negative delta", () => {
    const out = enrichGreeks([c({ type: "put", strike: 100, dte: 0, bid: 1.0, ask: 1.2 })], 100);
    expect(out[0].delta!).toBeLessThan(0);
    expect(out[0].delta!).toBeGreaterThan(-1);
  });

  it("leaves fully-populated contracts untouched (same array reference)", () => {
    const chain = [c({ impliedVolatility: 0.2, delta: 0.5, gamma: 0.03 })];
    const out = enrichGreeks(chain, 100);
    expect(out).toBe(chain);
    expect(out[0]).toBe(chain[0]);
  });

  it("no-ops without spot or without a price to imply from", () => {
    const noPrice = [c({ bid: null, ask: null, last: null })];
    expect(enrichGreeks(noPrice, 100)[0].gamma).toBeNull(); // can't imply IV without a price
    expect(enrichGreeks([c({ bid: 1, ask: 1.2 })], null)[0].gamma).toBeNull(); // no spot
  });

  it("takes a 0DTE chain from empty GEX/IV (the reported bug) to populated", () => {
    const spot = 719.91;
    const chain: OptionContract[] = [];
    for (const k of [700, 705, 710, 715, 720, 725, 730, 735, 740]) {
      const cP = Math.max(0.05, spot - k) + 2.5;
      const pP = Math.max(0.05, k - spot) + 2.5;
      chain.push(c({ type: "call", strike: k, dte: 0, bid: cP - 0.1, ask: cP + 0.1 }));
      chain.push(c({ type: "put", strike: k, dte: 0, bid: pP - 0.1, ask: pP + 0.1 }));
    }
    // before: no greeks → GEX empty, ATM IV null (exactly the QQQ 0DTE symptom)
    expect(netGex(chain, spot)).toBeNull();
    expect(gexByStrike(chain, spot).length).toBe(0);
    expect(atmIv(chain, spot, "2026-07-14")).toBeNull();
    // after: greeks backfilled → GEX and IV populated
    const e = enrichGreeks(chain, spot);
    expect(netGex(e, spot)).not.toBeNull();
    expect(gexByStrike(e, spot).length).toBeGreaterThan(0);
    expect(atmIv(e, spot, "2026-07-14")!).toBeGreaterThan(0);
  });

  it("uses last when there's no bid/ask, and only fills the missing fields", () => {
    const out = enrichGreeks([c({ type: "call", strike: 95, dte: 5, bid: null, ask: null, last: 6.0, delta: 0.7 })], 100);
    expect(out[0].gamma).not.toBeNull(); // gamma filled
    expect(out[0].impliedVolatility!).toBeGreaterThan(0); // iv filled
    expect(out[0].delta).toBe(0.7); // existing delta preserved
  });
});
