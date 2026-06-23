import { describe, expect, it } from "vitest";
import type { HistoryBar, OptionContract } from "../barchart/types";
import { stepSymbol, type CollectInputs } from "./collect";

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
function chain(): OptionContract[] {
  const out: OptionContract[] = [];
  for (const k of [88, 92, 96, 100, 104, 108, 112]) {
    const g = 0.05 * Math.exp(-SQ(k - 100) / 70);
    out.push(c({ type: "call", strike: k, gamma: g, openInterest: Math.round(1500 + 260 * (k - 88)), volume: 7000, delta: 0.4 }));
    out.push(c({ type: "put", strike: k, gamma: g, openInterest: Math.round(1500 + 260 * (112 - k)), volume: 7000, delta: -0.4 }));
  }
  return out;
}
function dailyWithSpike(n: number, jump: number): HistoryBar[] {
  const bars: HistoryBar[] = [];
  let px = 100;
  for (let i = 0; i < n; i++) {
    px *= i % 2 === 0 ? 1.0006 : 0.9994;
    bars.push({ timestamp: "2026-06-01", open: px, high: px * 1.001, low: px * 0.999, close: px, volume: 1_000_000 });
  }
  bars.push({ timestamp: "2026-06-02", open: px, high: px * (1 + jump), low: px, close: px * (1 + jump), volume: 3_000_000 });
  return bars;
}

describe("stepSymbol", () => {
  it("records a snapshot and journals at least one directional call", () => {
    const inputs: CollectInputs = { chain: chain(), spot: 100, bars: dailyWithSpike(30, 0.06), source: "live" };
    const { journal, history, result } = stepSymbol("SPY", inputs, [], [], 1_000_000);
    expect(history).toHaveLength(1);
    expect(history[0].spot).toBe(100);
    expect(result.source).toBe("live");
    expect(result.added).toBeGreaterThanOrEqual(1);
    expect(journal.length).toBe(result.added);
    expect(journal.every((r) => r.symbol === "SPY")).toBe(true);
    expect(result.open).toBe(result.added); // nothing resolved on the first step
  });

  it("appends to existing history and gates near-duplicate calls", () => {
    const inputs: CollectInputs = { chain: chain(), spot: 100, bars: dailyWithSpike(30, 0.06), source: "live" };
    const first = stepSymbol("SPY", inputs, [], [], 1_000_000);
    // a second snapshot 1 minute later (inside the dedupe window, same direction) → no new records
    const second = stepSymbol("SPY", { ...inputs, spot: 100.2 }, first.journal, first.history, 1_060_000);
    expect(second.history).toHaveLength(2);
    expect(second.result.added).toBe(0);
  });

  it("no-ops without a chain/spot", () => {
    const prevJ = [{ id: "x" }] as never[];
    const prevH = [{ t: 1, spot: 100 }] as never[];
    const r = stepSymbol("SPY", { chain: [], spot: null, bars: [], source: "fixtures" }, prevJ, prevH);
    expect(r.journal).toBe(prevJ);
    expect(r.history).toBe(prevH);
    expect(r.result.error).toBeTruthy();
  });
});
