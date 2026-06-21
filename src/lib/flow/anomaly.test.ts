import { describe, expect, it } from "vitest";
import type { HistoryBar, OptionContract } from "../barchart/types";
import { detectAnomalies } from "./anomaly";

function bars(rets: number[], vol = 1e6): HistoryBar[] {
  let px = 100;
  const out: HistoryBar[] = [];
  for (const r of rets) {
    const open = px;
    px = px * Math.exp(r);
    out.push({ timestamp: "d", open, high: Math.max(open, px) * 1.001, low: Math.min(open, px) * 0.999, close: px, volume: vol });
  }
  return out;
}
const calm = (n: number) => Array.from({ length: n }, (_, i) => (i % 2 === 0 ? 0.003 : -0.003));

function opt(p: Partial<OptionContract>): OptionContract {
  return {
    symbol: "X", underlying: "X", type: "call", strike: 100, expiration: "2026-07-16", dte: 30,
    bid: 1, ask: 1.2, last: 1.1, volume: 100, openInterest: 1000, impliedVolatility: 0.3,
    delta: 0.5, gamma: 0.02, theta: -0.05, vega: 0.1, underlyingPrice: 100, ...p,
  };
}

describe("detectAnomalies", () => {
  it("reports calm when behaviour is within normal ranges", () => {
    const r = detectAnomalies(bars(calm(40)), [], null);
    expect(r.state).toBe("calm");
    expect(r.anomalies.length).toBe(0);
  });

  it("flags an outlier down day as an anomaly", () => {
    const r = detectAnomalies(bars([...calm(30), -0.05]), [], null);
    const ret = r.anomalies.find((a) => a.metric === "Daily return");
    expect(ret).toBeTruthy();
    expect(ret!.direction).toBe("down");
    expect(Math.abs(ret!.z!)).toBeGreaterThan(3);
    expect(r.state).toBe("anomalous");
  });

  it("flags a rich volatility risk premium from the chain", () => {
    const chain = [opt({ type: "call", impliedVolatility: 0.35 }), opt({ type: "put", impliedVolatility: 0.35, delta: -0.5 })];
    const r = detectAnomalies(bars(calm(40)), chain, 100); // calm RV → IV >> RV
    expect(r.anomalies.some((a) => a.metric === "VRP")).toBe(true);
  });

  it("needs enough history", () => {
    const r = detectAnomalies(bars(calm(10)), [], null);
    expect(r.score).toBe(0);
    expect(r.notes.join(" ")).toMatch(/history/i);
  });
});
