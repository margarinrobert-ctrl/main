import { describe, expect, it } from "vitest";
import type { HistoryBar, OptionContract } from "../barchart/types";
import { buildHarvestReport, chooseHarvestExpiration } from "./harvest";

const STRIKES = [80, 85, 90, 95, 100, 105, 110, 115, 120];
const PUT_D: Record<number, number> = { 80: -0.04, 85: -0.09, 90: -0.18, 95: -0.32, 100: -0.5, 105: -0.6, 110: -0.75, 115: -0.88, 120: -0.95 };
const CALL_D: Record<number, number> = { 80: 0.96, 85: 0.9, 90: 0.8, 95: 0.66, 100: 0.5, 105: 0.34, 110: 0.18, 115: 0.09, 120: 0.04 };
const PUT_M: Record<number, number> = { 80: 0.2, 85: 0.5, 90: 1, 95: 2, 100: 3.5, 105: 5.5, 110: 9, 115: 13, 120: 18 };
const CALL_M: Record<number, number> = { 80: 18, 85: 13, 90: 9, 95: 5.5, 100: 3.5, 105: 2, 110: 1, 115: 0.5, 120: 0.2 };

function mkChain(iv: number, expiration: string, dte: number): OptionContract[] {
  const out: OptionContract[] = [];
  for (const k of STRIKES) {
    for (const type of ["call", "put"] as const) {
      const mid = type === "call" ? CALL_M[k] : PUT_M[k];
      out.push({
        symbol: `X${k}${type}`,
        underlying: "X",
        type,
        strike: k,
        expiration,
        dte,
        bid: Math.max(0.01, mid - 0.05),
        ask: mid + 0.05,
        last: mid,
        volume: 100,
        openInterest: 1000,
        impliedVolatility: iv,
        delta: type === "call" ? CALL_D[k] : PUT_D[k],
        gamma: 0.02,
        theta: -0.05,
        vega: 0.1,
        underlyingPrice: 100,
      });
    }
  }
  return out;
}

// ~18% annualized realized vol via alternating ±daily returns.
function mkBars(n = 30): HistoryBar[] {
  const r = 0.18 / Math.sqrt(252);
  let px = 100;
  const bars: HistoryBar[] = [];
  for (let i = 0; i < n; i++) {
    px *= Math.exp(i % 2 === 0 ? r : -r);
    bars.push({ timestamp: `2026-05-${(i % 28) + 1}`, open: px, high: px, low: px, close: px, volume: 1e6 });
  }
  return bars;
}

describe("premium harvesting", () => {
  it("flags a harvest regime when IV is rich vs realized and emits sized credit structures", () => {
    const rep = buildHarvestReport(mkChain(0.3, "2026-07-16", 30), 100, mkBars());
    expect(rep.regime).toBe("harvest");
    expect(rep.vrpRatio!).toBeGreaterThan(1.1);
    const names = rep.signals.map((s) => s.name);
    expect(names).toContain("Cash-Secured Put");
    expect(names).toContain("Iron Condor");
    expect(names).toContain("Bull Put Spread");
    expect(rep.signals.every((s) => s.score >= 0 && s.score <= 100)).toBe(true);
    // sorted by score desc
    for (let i = 1; i < rep.signals.length; i++) expect(rep.signals[i - 1].score).toBeGreaterThanOrEqual(rep.signals[i].score);
  });

  it("prices the cash-secured put: credit, breakeven, POP and positive theta harvest", () => {
    const rep = buildHarvestReport(mkChain(0.3, "2026-07-16", 30), 100, mkBars());
    const csp = rep.signals.find((s) => s.name === "Cash-Secured Put")!;
    expect(csp.credit).toBeCloseTo(2, 1); // 95P mid ≈ 2
    expect(csp.breakevens[0]).toBeCloseTo(93, 1);
    expect(csp.pop!).toBeCloseTo(0.68, 2); // 1 − 0.32
    expect(csp.thetaDay!).toBeGreaterThan(0); // seller harvests decay
    expect(csp.legs[0]).toMatchObject({ action: "sell", type: "put", strike: 95 });
  });

  it("builds a defined-risk iron condor with a bounded max loss", () => {
    const rep = buildHarvestReport(mkChain(0.3, "2026-07-16", 30), 100, mkBars());
    const ic = rep.signals.find((s) => s.name === "Iron Condor")!;
    expect(ic.legs).toHaveLength(4);
    expect(ic.maxLoss!).toBeGreaterThan(0);
    expect(ic.breakevens).toHaveLength(2);
    expect(ic.pop!).toBeGreaterThan(0.5);
  });

  it("says AVOID when IV is cheap vs realized", () => {
    const rep = buildHarvestReport(mkChain(0.12, "2026-07-16", 30), 100, mkBars());
    expect(rep.regime).toBe("avoid");
  });

  it("chooses the ~30 DTE expiration for harvesting", () => {
    const chain = [
      ...mkChain(0.3, "2026-06-19", 3),
      ...mkChain(0.3, "2026-07-16", 30),
      ...mkChain(0.3, "2026-08-21", 66),
    ];
    expect(chooseHarvestExpiration(chain)).toBe("2026-07-16");
    expect(buildHarvestReport(chain, 100, mkBars(), "2026-06-19").expiration).toBe("2026-06-19"); // forced
  });
});
