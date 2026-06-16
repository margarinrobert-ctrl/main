import { describe, expect, it } from "vitest";
import type { HistoryBar, OptionContract } from "../barchart/types";
import { buildSignals, scanRow } from "./signals";

function c(p: Partial<OptionContract>): OptionContract {
  return {
    symbol: "X",
    underlying: "X",
    type: "call",
    strike: 100,
    expiration: "2026-07-16",
    dte: 30,
    bid: 1,
    ask: 1.2,
    last: 1.1,
    volume: 100,
    openInterest: 1000,
    impliedVolatility: 0.3,
    delta: 0.5,
    gamma: 0.05,
    theta: -0.05,
    vega: 0.1,
    underlyingPrice: 100,
    ...p,
  };
}

function bars(dir: "up" | "down" | "flat", n = 30): HistoryBar[] {
  let px = 100;
  const out: HistoryBar[] = [];
  for (let i = 0; i < n; i++) {
    if (dir === "up") px *= 1.004;
    else if (dir === "down") px *= 0.996;
    else px *= Math.exp((i % 2 === 0 ? 1 : -1) * (0.18 / Math.sqrt(252)));
    out.push({ timestamp: `2026-05-${(i % 28) + 1}`, open: px, high: px, low: px, close: px, volume: 1e6 });
  }
  return out;
}

// rich 9-strike chain (≈30% IV) for the volatility branch
const ST = [80, 85, 90, 95, 100, 105, 110, 115, 120];
const PD: Record<number, number> = { 80: -0.04, 85: -0.09, 90: -0.18, 95: -0.32, 100: -0.5, 105: -0.6, 110: -0.75, 115: -0.88, 120: -0.95 };
const CD: Record<number, number> = { 80: 0.96, 85: 0.9, 90: 0.8, 95: 0.66, 100: 0.5, 105: 0.34, 110: 0.18, 115: 0.09, 120: 0.04 };
const PM: Record<number, number> = { 80: 0.2, 85: 0.5, 90: 1, 95: 2, 100: 3.5, 105: 5.5, 110: 9, 115: 13, 120: 18 };
const CM: Record<number, number> = { 80: 18, 85: 13, 90: 9, 95: 5.5, 100: 3.5, 105: 2, 110: 1, 115: 0.5, 120: 0.2 };
function richChain(iv: number): OptionContract[] {
  const out: OptionContract[] = [];
  for (const k of ST)
    for (const t of ["call", "put"] as const) {
      const mid = t === "call" ? CM[k] : PM[k];
      out.push(
        c({
          type: t,
          strike: k,
          bid: Math.max(0.01, mid - 0.05),
          ask: mid + 0.05,
          last: mid,
          impliedVolatility: iv,
          delta: t === "call" ? CD[k] : PD[k],
          gamma: 0.02,
          openInterest: 1000,
          volume: t === "call" ? 200 : 100,
        }),
      );
    }
  return out;
}

describe("buildSignals", () => {
  it("turns a long-gamma, call-leaning, uptrending tape into a bullish board", () => {
    const chain = [
      c({ type: "put", strike: 95, gamma: 0.05, openInterest: 2000, delta: -0.3, volume: 100 }),
      c({ type: "call", strike: 105, gamma: 0.05, openInterest: 8000, delta: 0.3, volume: 1500 }),
    ];
    const board = buildSignals(chain, 120, bars("up"));
    expect(board.biasScore).toBeGreaterThan(15);
    expect(board.bias).toBe("bullish");
    expect(board.regime).toBe("long");
    expect(board.signals.some((s) => s.id === "dir-bull")).toBe(true);
    expect(board.signals.some((s) => s.id === "regime-mr")).toBe(true);
    // each directional signal carries levels + horizon
    const dir = board.signals.find((s) => s.id === "dir-bull")!;
    expect(dir.entry).not.toBeNull();
    expect(dir.targets.length).toBeGreaterThan(0);
    expect(dir.horizon).toBeTruthy();
  });

  it("flags a short-gamma momentum regime when puts dominate", () => {
    const chain = [
      c({ type: "put", strike: 95, gamma: 0.05, openInterest: 9000, delta: -0.4, volume: 1500 }),
      c({ type: "call", strike: 105, gamma: 0.05, openInterest: 1000, delta: 0.3, volume: 100 }),
    ];
    const board = buildSignals(chain, 90, bars("down"));
    expect(board.regime).toBe("short");
    expect(board.signals.some((s) => s.id === "regime-mom")).toBe(true);
  });

  it("adds a sell-premium volatility signal when IV is rich vs realized", () => {
    const board = buildSignals(richChain(0.3), 100, bars("flat"));
    expect(board.signals.some((s) => s.id === "vol-sell")).toBe(true);
    // board is ranked by score
    for (let i = 1; i < board.signals.length; i++) expect(board.signals[i - 1].score).toBeGreaterThanOrEqual(board.signals[i].score);
  });

  it("adds a buy-gamma signal when IV is cheap vs realized", () => {
    const board = buildSignals(richChain(0.12), 100, bars("flat"));
    expect(board.signals.some((s) => s.id === "vol-buy")).toBe(true);
  });

  it("returns an empty board without spot or chain", () => {
    expect(buildSignals([], 100, []).signals).toHaveLength(0);
    expect(buildSignals([c({})], null, []).signals).toHaveLength(0);
  });

  it("summarizes a symbol for the cross-ticker scanner", () => {
    const row = scanRow("SPY", richChain(0.3), 100, bars("flat"));
    expect(row.symbol).toBe("SPY");
    expect(row.spot).toBe(100);
    expect(["long", "short", "unknown"]).toContain(row.regime);
    expect(row.vrp).not.toBeNull();
    expect(row.top).not.toBeNull();
    expect(typeof row.biasScore).toBe("number");
  });
});
