import { describe, expect, it } from "vitest";
import type { HistoryBar, OptionContract } from "../barchart/types";
import { bsPrice } from "../flow/greeks";
import { RANGE_OVER_SIGMA, dayProjection, rangeBacktest, vixIndex, type BacktestDay } from "./vixrange";

const SPOT = 100;

function c(p: Partial<OptionContract>): OptionContract {
  return {
    symbol: "X", underlying: "X", type: "call", strike: 100, expiration: "2026-09-08", dte: 30,
    bid: null, ask: null, last: null, volume: 10, openInterest: 100, impliedVolatility: null,
    delta: null, gamma: null, theta: null, vega: null, underlyingPrice: SPOT, ...p,
  };
}

/** Synthetic chain priced by Black-Scholes at a FLAT vol — the strip must recover that vol. */
function flatVolChain(sigma: number, legs: { exp: string; dte: number }[]): OptionContract[] {
  const out: OptionContract[] = [];
  for (const { exp, dte } of legs) {
    const t = dte / 365;
    for (let k = 60; k <= 145; k += 2.5) {
      for (const type of ["call", "put"] as const) {
        const px = bsPrice(type, SPOT, k, sigma, t)!;
        if (px < 0.005) continue; // deep-tail quotes a real book wouldn't show
        out.push(c({ type, strike: k, expiration: exp, dte, bid: px * 0.98, ask: px * 1.02 }));
      }
    }
  }
  return out;
}

describe("vixIndex (CBOE-style 30d model-free vol)", () => {
  it("recovers a flat 20% vol from a two-leg strip bracketing 30 days", () => {
    const r = vixIndex(flatVolChain(0.2, [{ exp: "2026-08-29", dte: 20 }, { exp: "2026-09-18", dte: 40 }]), SPOT);
    expect(r.method).toBe("strip");
    expect(r.vix).not.toBeNull();
    expect(r.vix!).toBeGreaterThan(18.5);
    expect(r.vix!).toBeLessThan(21.5);
    expect(r.near!.dte).toBe(20);
    expect(r.next!.dte).toBe(40);
  });

  it("works from a single usable leg (no 30d bracket)", () => {
    const r = vixIndex(flatVolChain(0.3, [{ exp: "2026-08-19", dte: 10 }]), SPOT);
    expect(r.method).toBe("strip");
    expect(r.vix!).toBeGreaterThan(27);
    expect(r.vix!).toBeLessThan(33);
    expect(r.next).toBeNull();
  });

  it("falls back to ATM IV on a sparse book, and says so", () => {
    const sparse = [
      c({ type: "call", strike: 100, impliedVolatility: 0.25, bid: 1, ask: 1.2 }),
      c({ type: "put", strike: 100, impliedVolatility: 0.25, bid: 1, ask: 1.2 }),
    ];
    const r = vixIndex(sparse, SPOT);
    expect(r.method).toBe("atm-fallback");
    expect(r.vix!).toBeCloseTo(25, 5);
  });

  it("returns none without data", () => {
    expect(vixIndex([], SPOT).method).toBe("none");
    expect(vixIndex(flatVolChain(0.2, [{ exp: "e", dte: 20 }]), null).method).toBe("none");
  });
});

describe("dayProjection (Brownian-motion day range)", () => {
  it("uses the exact BM constants: E|move| = 0.798σS, E[range] = 1.596σS", () => {
    const p = dayProjection(100, 0.16)!;
    const sd = 0.16 / Math.sqrt(252);
    expect(p.sigmaDaily).toBeCloseTo(sd, 10);
    expect(p.expAbsMove).toBeCloseTo(Math.sqrt(2 / Math.PI) * sd * 100, 8);
    expect(p.expRange).toBeCloseTo(RANGE_OVER_SIGMA * sd * 100, 8);
    expect(p.high - p.low).toBeCloseTo(p.expRange, 8);
    expect(p.band68.hi - 100).toBeCloseTo(sd * 100, 8);
    expect(RANGE_OVER_SIGMA).toBeCloseTo(1.59577, 4);
  });
  it("rejects degenerate inputs", () => {
    expect(dayProjection(null, 0.2)).toBeNull();
    expect(dayProjection(100, 0)).toBeNull();
  });
});

describe("rangeBacktest (walk-forward verification)", () => {
  const bar = (open: number, high: number, low: number, close: number): HistoryBar => ({ timestamp: "t", open, high, low, close, volume: 1 });

  it("measures the range premium: implied 25% above realized → +0.25", () => {
    const iv = 0.16;
    const sd = iv / Math.sqrt(252);
    const days: BacktestDay[] = ["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04"].map((day) => {
      const implied = RANGE_OVER_SIGMA * sd * 100;
      const realized = implied / 1.25; // day delivered less than implied
      return { day, ivOpen: iv, bar: bar(100, 100 + realized / 2, 100 - realized / 2, 100.1) };
    });
    const r = rangeBacktest(days);
    expect(r.n).toBe(4);
    expect(r.rangePremium!).toBeCloseTo(0.25, 6);
    expect(r.hitRate68).toBe(1); // close 100.1 well inside ±1σ (≈ ±1.0)
    expect(r.realizedRangeOverSigma!).toBeCloseTo(RANGE_OVER_SIGMA / 1.25, 6);
    expect(r.rows.map((x) => x.day)).toEqual(["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04"]);
  });

  it("counts closes outside the ±1σ band against the hit rate", () => {
    const iv = 0.16; // σ_d ≈ 1.0% → band ≈ ±1.0
    const days: BacktestDay[] = [
      { day: "2026-08-01", ivOpen: iv, bar: bar(100, 101, 99, 100.2) }, // inside
      { day: "2026-08-02", ivOpen: iv, bar: bar(100, 103, 99, 102.5) }, // outside (gap day)
    ];
    const r = rangeBacktest(days);
    expect(r.hitRate68).toBeCloseTo(0.5, 10);
  });

  it("skips malformed days and handles empty input", () => {
    const r = rangeBacktest([{ day: "2026-08-01", ivOpen: 0, bar: bar(100, 101, 99, 100) }]);
    expect(r.n).toBe(0);
    expect(r.rangePremium).toBeNull();
    expect(rangeBacktest([]).hitRate68).toBeNull();
  });
});
