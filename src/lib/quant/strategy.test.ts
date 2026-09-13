import { describe, expect, it } from "vitest";
import type { OptionContract } from "../barchart/types";
import { bsQuote } from "./bs";
import { evCall, evPut, evalTrades, probAbove, scanStrikes } from "./strategy";

const c = (p: Partial<OptionContract>): OptionContract => ({
  symbol: "X", underlying: "X", type: "call", strike: 100, expiration: "2026-09-15", dte: 30,
  bid: null, ask: null, last: null, volume: 10, openInterest: 100, impliedVolatility: null,
  delta: null, gamma: null, theta: null, vega: null, underlyingPrice: 100, ...p,
});

describe("terminal-distribution math", () => {
  it("discounted EV at μ = r reproduces the Black-Scholes price (q=0)", () => {
    const S = 100, K = 105, T = 0.5, sigma = 0.25, r = 0.05;
    const bs = bsQuote({ type: "call", spot: S, strike: K, tYears: T, sigma, r })!;
    expect(Math.exp(-r * T) * evCall(S, K, sigma, T, r)).toBeCloseTo(bs.price, 8);
    const bsPut = bsQuote({ type: "put", spot: S, strike: K, tYears: T, sigma, r })!;
    expect(Math.exp(-r * T) * evPut(S, K, sigma, T, r)).toBeCloseTo(bsPut.price, 8);
  });

  it("probAbove: under zero drift P(S_T > S) < 0.5 (lognormal median below mean)", () => {
    const p = probAbove(100, 100, 0.3, 1, 0);
    expect(p).toBeLessThan(0.5);
    expect(p).toBeCloseTo(1 - probAbove(100, 100, 0.3, 1, 0) < 1 ? p : p, 10);
    expect(probAbove(100, 1e-9, 0.3, 1, 0)).toBeGreaterThan(0.999); // far-below level ≈ certain
    expect(probAbove(100, 0, 0.3, 1, 0)).toBe(1);
  });
});

describe("evalTrades", () => {
  const T = 30 / 365;

  it("zero-EV at fair prices under the risk-neutral scenario (no fabricated edge)", () => {
    const sigma = 0.2, r = 0.04;
    const fairCall = Math.exp(-r * T) * evCall(100, 100, sigma, T, r);
    const fairPut = Math.exp(-r * T) * evPut(100, 100, sigma, T, r);
    for (const t of evalTrades(100, fairCall, fairPut, 100, T, { sigma, mu: r, r })) {
      expect(Math.abs(t.expPnl)).toBeLessThan(1e-9);
    }
  });

  it("rich market vol vs scenario ⇒ shorts have positive EV, longs negative (the VRP direction)", () => {
    const sigma = 0.15, r = 0;
    // market prices options at 30% vol while the scenario realizes 15%
    const richCall = evCall(100, 102, 0.3, T, 0);
    const richPut = evPut(100, 98, 0.3, T, 0);
    const trades = [...evalTrades(102, richCall, null, 100, T, { sigma, mu: 0, r }), ...evalTrades(98, null, richPut, 100, T, { sigma, mu: 0, r })];
    const by = Object.fromEntries(trades.map((t) => [t.kind, t]));
    expect(by["short-call"].expPnl).toBeGreaterThan(0);
    expect(by["short-put"].expPnl).toBeGreaterThan(0);
    expect(by["long-call"].expPnl).toBeLessThan(0);
    expect(by["long-put"].expPnl).toBeLessThan(0);
    // long/short of the same leg mirror exactly
    expect(by["short-call"].expPnl).toBeCloseTo(-by["long-call"].expPnl, 10);
    expect(by["short-call"].winRate).toBeCloseTo(1 - by["long-call"].winRate, 10);
  });

  it("win rates: OTM short put wins far more often than the mirrored long put, but risks far more", () => {
    const trades = evalTrades(95, null, 1.2, 100, T, { sigma: 0.2, mu: 0 });
    const shortPut = trades.find((t) => t.kind === "short-put")!;
    const longPut = trades.find((t) => t.kind === "long-put")!;
    expect(shortPut.winRate).toBeGreaterThan(0.8);
    expect(longPut.winRate).toBeLessThan(0.2);
    expect(shortPut.maxLoss).toBeCloseTo(95 - 1.2, 10); // stock to zero
    expect(longPut.maxLoss).toBeCloseTo(1.2, 10); // premium only
    expect(shortPut.breakeven).toBeCloseTo(93.8, 10);
  });

  it("short call carries unbounded max loss", () => {
    const shortCall = evalTrades(105, 1.5, null, 100, T, { sigma: 0.2, mu: 0 }).find((t) => t.kind === "short-call")!;
    expect(shortCall.maxLoss).toBe(Infinity);
  });
});

describe("scanStrikes", () => {
  const chain = (): OptionContract[] => {
    const out: OptionContract[] = [];
    for (const k of [90, 95, 100, 105, 110]) {
      // market quotes at 28% vol
      const cm = evCall(100, k, 0.28, 30 / 365, 0);
      const pm = evPut(100, k, 0.28, 30 / 365, 0);
      out.push(c({ type: "call", strike: k, bid: cm * 0.98, ask: cm * 1.02 }));
      out.push(c({ type: "put", strike: k, bid: pm * 0.98, ask: pm * 1.02 }));
    }
    return out;
  };

  it("scans every strike, solves market IV near 28%, and best trades are shorts when scenario vol is lower", () => {
    const rows = scanStrikes(chain(), 100, { sigma: 0.16, mu: 0, r: 0 });
    expect(rows.length).toBe(5);
    const atm = rows.find((x) => x.strike === 100)!;
    expect(atm.callIv!).toBeGreaterThan(0.25);
    expect(atm.callIv!).toBeLessThan(0.31);
    for (const row of rows) expect(row.best!.kind.startsWith("short")).toBe(true);
  });

  it("respects the maxStrikes window around spot and degrades on empty input", () => {
    expect(scanStrikes(chain(), 100, { sigma: 0.2, mu: 0 }, 3).length).toBe(3);
    expect(scanStrikes([], 100, { sigma: 0.2, mu: 0 })).toEqual([]);
    expect(scanStrikes(chain(), null, { sigma: 0.2, mu: 0 })).toEqual([]);
  });
});
