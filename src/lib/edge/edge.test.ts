import { describe, expect, it } from "vitest";
import type { HistoryBar, OptionContract } from "../barchart/types";
import { harRvForecast } from "./harrv";
import { vrpEngine } from "./vrp";
import { carryEngine } from "./carry";
import { volFactor, type SymbolMetrics } from "./factor";

// Bars whose Garman–Klass daily variance implies a target annualized vol σ (O=C, H/L symmetric).
// GK = 0.5·ln(H/L)² with O=C ⇒ daily var = 2k², k = ln(H)/1. Set k = σ/√504 ⇒ annualized σ.
function bars(sigmas: number[], px = 100): HistoryBar[] {
  return sigmas.map((s, i) => {
    const k = s / Math.sqrt(504);
    return { timestamp: `2026-01-${String((i % 28) + 1).padStart(2, "0")}`, open: px, close: px, high: px * Math.exp(k), low: px * Math.exp(-k), volume: 1e6 };
  });
}

function c(p: Partial<OptionContract>): OptionContract {
  return {
    symbol: "X", underlying: "X", type: "call", strike: 100, expiration: "2026-06-19", dte: 20,
    bid: 1, ask: 1.2, last: 1.1, volume: 100, openInterest: 5000, impliedVolatility: 0.25,
    delta: 0.5, gamma: 0.03, theta: -0.05, vega: 0.1, underlyingPrice: 100, ...p,
  };
}
// ATM chain at spot=100 for one expiration with a given IV.
function atmChain(iv: number, exp = "2026-06-19", dte = 20): OptionContract[] {
  return [
    c({ type: "call", strike: 100, impliedVolatility: iv, expiration: exp, dte }),
    c({ type: "put", strike: 100, impliedVolatility: iv, expiration: exp, dte }),
    c({ type: "call", strike: 105, impliedVolatility: iv + 0.01, expiration: exp, dte }),
    c({ type: "put", strike: 95, impliedVolatility: iv + 0.02, expiration: exp, dte }),
  ];
}

describe("harRvForecast", () => {
  it("returns nulls below ~30 bars", () => {
    const r = harRvForecast(bars(Array(20).fill(0.16)));
    expect(r.forecastVol).toBeNull();
    expect(r.n).toBe(0);
  });
  it("recovers a constant vol", () => {
    const r = harRvForecast(bars(Array(80).fill(0.16)));
    expect(r.forecastVol).not.toBeNull();
    expect(r.forecastVol!).toBeGreaterThan(0.13);
    expect(r.forecastVol!).toBeLessThan(0.19);
    expect(r.rvMonth!).toBeGreaterThan(0.13);
  });
  it("tracks a vol regime shift upward", () => {
    const calm = harRvForecast(bars(Array(80).fill(0.12)));
    const spiked = harRvForecast(bars([...Array(60).fill(0.12), ...Array(20).fill(0.4)]));
    expect(spiked.forecastVol!).toBeGreaterThan(calm.forecastVol! * 1.3);
  });
});

describe("vrpEngine", () => {
  it("flags RICH vol (short-vol) when IV >> forecast RV", () => {
    const r = vrpEngine(atmChain(0.35), 100, bars(Array(80).fill(0.15)));
    expect(r.side).toBe("short-vol");
    expect(r.vrpRatio!).toBeGreaterThan(1.1);
    expect(r.edgeVolPts!).toBeGreaterThan(0);
    expect(r.conviction).toBeGreaterThan(0);
  });
  it("flags CHEAP vol (long-vol) when IV << forecast RV", () => {
    const r = vrpEngine(atmChain(0.14), 100, bars(Array(80).fill(0.32)));
    expect(r.side).toBe("long-vol");
    expect(r.vrpRatio!).toBeLessThan(0.95);
  });
  it("is neutral when IV ≈ forecast RV, and degrades gracefully with no bars", () => {
    expect(vrpEngine(atmChain(0.2), 100, bars(Array(80).fill(0.2))).side).toBe("neutral");
    const none = vrpEngine(atmChain(0.2), 100, []);
    expect(none.rvForecast).toBeNull();
    expect(none.conviction).toBe(0);
  });
});

describe("carryEngine", () => {
  const twoTenor = (frontIv: number, backIv: number): OptionContract[] => [
    ...atmChain(frontIv, "2026-02-06", 7),
    ...atmChain(backIv, "2026-03-20", 49),
  ];
  it("contango → sell-vol; roll-down is a COST to long vega (VIX-roll logic)", () => {
    const r = carryEngine(twoTenor(0.15, 0.22), 100);
    expect(r.shape).toBe("contango");
    expect(r.side).toBe("sell-vol");
    expect(r.slopeVolPts!).toBeGreaterThan(0);
    // long-vega roll-down is negative in contango (the short harvests it)
    expect(r.rollDownVolPtsPerWeek!).toBeLessThan(0);
  });
  it("backwardation → sell-front (event crush)", () => {
    const r = carryEngine(twoTenor(0.32, 0.2), 100);
    expect(r.shape).toBe("backwardation");
    expect(r.side).toBe("sell-front");
    expect(r.slopeVolPts!).toBeLessThan(0);
  });
});

describe("volFactor", () => {
  it("ranks richest vol first and builds a dollar-neutral book", () => {
    const m: SymbolMetrics[] = [
      { symbol: "AAA", vrpRatio: 1.35, termSlope: 0.02, skew: 0.05 },
      { symbol: "BBB", vrpRatio: 1.05, termSlope: 0.03, skew: 0.03 },
      { symbol: "CCC", vrpRatio: 0.85, termSlope: 0.04, skew: 0.01 },
    ];
    const r = volFactor(m);
    expect(r.rows[0].symbol).toBe("AAA"); // richest vol
    expect(r.rows[0].side).toBe("short-vol");
    expect(r.rows[r.rows.length - 1].side).toBe("long-vol");
    // dollar-neutral: net ≈ 0, gross ≈ 1
    const net = r.rows.reduce((s, x) => s + x.weight, 0);
    const gross = r.rows.reduce((s, x) => s + Math.abs(x.weight), 0);
    expect(Math.abs(net)).toBeLessThan(1e-9);
    expect(gross).toBeGreaterThan(0.9);
    expect(gross).toBeLessThanOrEqual(1.000001);
  });
  it("needs ≥3 symbols", () => {
    expect(volFactor([{ symbol: "A", vrpRatio: 1.2, termSlope: null, skew: null }]).rows).toHaveLength(0);
  });
});
