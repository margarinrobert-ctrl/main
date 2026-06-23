import { describe, expect, it } from "vitest";
import type { GexSample } from "../gex-history";
import type { HistoryBar, OptionContract } from "../barchart/types";
import { anomalyIntel } from "./anomalyPro";

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
    volume: 1000,
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

const SQ = (x: number) => x * x;
// long-gamma book: ATM-peaked positive net gamma, balanced put/call volume, walls either side of spot.
function longGammaChain(): OptionContract[] {
  const out: OptionContract[] = [];
  for (const k of [88, 92, 96, 100, 104, 108, 112]) {
    const g = 0.05 * Math.exp(-SQ(k - 100) / 70);
    out.push(c({ type: "call", strike: k, gamma: g, openInterest: Math.round(1500 + 260 * (k - 88)), volume: 7000, delta: 0.4 }));
    out.push(c({ type: "put", strike: k, gamma: g, openInterest: Math.round(1500 + 260 * (112 - k)), volume: 7000, delta: -0.4 }));
  }
  return out;
}

function bar(close: number, volume = 1_000_000): HistoryBar {
  return { timestamp: "2026-06-01", open: close, high: close * 1.001, low: close * 0.999, close, volume };
}
// a quiet daily series with a sharp move tacked on as the final bar.
function dailyWithSpike(n: number, jump: number): HistoryBar[] {
  const bars: HistoryBar[] = [];
  let px = 100;
  for (let i = 0; i < n; i++) {
    px *= i % 2 === 0 ? 1.0006 : 0.9994;
    bars.push(bar(px));
  }
  bars.push(bar(px * (1 + jump), 3_000_000));
  return bars;
}
function sampleSeries(n: number, jump = 0): GexSample[] {
  const out: GexSample[] = [];
  let px = 100;
  for (let i = 0; i < n; i++) {
    px *= i % 2 === 0 ? 1.0004 : 0.9996;
    out.push({ t: i * 30000, spot: px, gex: 1e9, flip: 99.5, iv: 0.2, pcr: 1 });
  }
  if (jump) {
    const last = out[out.length - 1];
    out.push({ t: last.t + 30000, spot: (last.spot as number) * (1 + jump), gex: 1e9, flip: 99.5, iv: 0.21, pcr: 1 });
  }
  return out;
}

describe("anomalyIntel", () => {
  it("produces a structured, well-formed institutional read from daily history", () => {
    const r = anomalyIntel("TEST", longGammaChain(), 100, dailyWithSpike(30, 0.06), []);
    expect(r.symbol).toBe("TEST");
    expect(r.source).toBe("daily");
    expect(r.strength).toBeGreaterThanOrEqual(0);
    expect(r.strength).toBeLessThanOrEqual(100);
    // band must agree with the strength score
    const expectBand = r.strength >= 80 ? "Extreme" : r.strength >= 60 ? "Institutional" : r.strength >= 40 ? "Strong" : r.strength >= 20 ? "Moderate" : "Weak";
    expect(r.band).toBe(expectBand);
    // classification is a proper split
    expect(r.bullish + r.bearish).toBe(100);
    expect(r.confidence).toBeGreaterThanOrEqual(0);
    expect(r.confidence).toBeLessThanOrEqual(100);
    // full ensemble of five detectors
    expect(r.models.map((m) => m.name)).toEqual(["Z-score", "Modified-Z (MAD)", "EWMA / Kalman", "CUSUM change-pt", "EVT tail"]);
    // quant factor grid is populated
    expect(Object.keys(r.quant)).toContain("GEX (net γ/1%)");
    expect(Object.keys(r.quant)).toContain("DEX (net Δ)");
    // structured JSON output round-trips
    expect(() => JSON.parse(r.json)).not.toThrow();
    expect(JSON.parse(r.json).symbol).toBe("TEST");
  });

  it("labels free-data limits honestly (proxies, session IV, modeled forecast)", () => {
    const r = anomalyIntel("HON", longGammaChain(), 100, dailyWithSpike(30, 0.04), []);
    const text = r.methodology.join(" ");
    expect(text).toContain("PROXIES");
    expect(text).toContain("session-window");
    expect(text).toContain("MODEL estimates");
    expect(r.quant["Order flow (proxy)"]).toBeDefined();
    expect(r.quant["IV %ile (session)"]).toBeDefined();
  });

  it("prefers intraday session samples when enough are recorded", () => {
    const r = anomalyIntel("INTRA", longGammaChain(), 100, dailyWithSpike(30, 0.02), sampleSeries(18));
    expect(r.source).toBe("intraday");
  });

  it("falls back to daily when samples are sparse", () => {
    const r = anomalyIntel("FALL", longGammaChain(), 100, dailyWithSpike(30, 0.02), sampleSeries(4));
    expect(r.source).toBe("daily");
  });

  it("degrades gracefully when there is no usable data", () => {
    const r = anomalyIntel("NONE", [], null, [], []);
    expect(r.source).toBe("none");
    expect(r.strength).toBe(0);
    expect(r.band).toBe("Weak");
    expect(r.neutral).toBe(true);
    expect(r.models).toHaveLength(0);
    expect(r.targets).toHaveLength(0);
  });

  it("reads a long-gamma up-spike as a fade (bearish) with downside targets", () => {
    const r = anomalyIntel("FADE", longGammaChain(), 100, dailyWithSpike(30, 0.06), []);
    expect(r.strength).toBeGreaterThan(20);
    expect(r.neutral).toBe(false);
    expect(r.bearish).toBeGreaterThanOrEqual(r.bullish);
    expect(r.targets.length).toBeGreaterThan(0);
    expect(r.targets[0].price).toBeLessThan(100);
  });

  it("returns a time-forecast whose horizon probabilities form a distribution", () => {
    const r = anomalyIntel("TIME", longGammaChain(), 100, dailyWithSpike(30, 0.05), []);
    expect(r.timeForecast.probs.map((p) => p.h)).toEqual(["5m", "15m", "30m", "1h", "4h", "1d"]);
    const total = r.timeForecast.probs.reduce((s, p) => s + p.p, 0);
    expect(total).toBeGreaterThanOrEqual(99);
    expect(total).toBeLessThanOrEqual(101);
    expect(r.timeForecast.probs).toContainEqual(expect.objectContaining({ h: r.timeForecast.window }));
  });
});
