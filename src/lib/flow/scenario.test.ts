import { describe, expect, it } from "vitest";
import type { OptionContract } from "../barchart/types";
import { scenarioMatrix } from "./scenario";

function c(p: Partial<OptionContract>): OptionContract {
  return {
    symbol: "X", underlying: "X", type: "call", strike: 100, expiration: "2026-06-19", dte: 20,
    bid: 1, ask: 1.2, last: 1.1, volume: 100, openInterest: 5000, impliedVolatility: 0.25,
    delta: 0.5, gamma: 0.03, theta: -0.05, vega: 0.1, underlyingPrice: 100, ...p,
  };
}

// Short-gamma book: puts carry the gamma (dealers short puts), so net GEX < 0 → amplifying regime.
function shortGammaChain(): OptionContract[] {
  return [
    c({ type: "put", strike: 100, gamma: 0.06, openInterest: 20000 }),
    c({ type: "put", strike: 95, gamma: 0.04, openInterest: 12000 }),
    c({ type: "call", strike: 105, gamma: 0.01, openInterest: 3000 }),
  ];
}
// Long-gamma book: calls carry the gamma (dealers long calls) → net GEX > 0 → dampening regime.
function longGammaChain(): OptionContract[] {
  return [
    c({ type: "call", strike: 100, gamma: 0.06, openInterest: 20000 }),
    c({ type: "call", strike: 105, gamma: 0.04, openInterest: 12000 }),
    c({ type: "put", strike: 95, gamma: 0.01, openInterest: 3000 }),
  ];
}

describe("scenarioMatrix", () => {
  it("returns not-ok on empty/invalid input", () => {
    expect(scenarioMatrix([], 100).ok).toBe(false);
    expect(scenarioMatrix(shortGammaChain(), null).ok).toBe(false);
    expect(scenarioMatrix(shortGammaChain(), 0).ok).toBe(false);
  });

  it("builds a full grid matching the axes", () => {
    const r = scenarioMatrix(shortGammaChain(), 100);
    expect(r.ok).toBe(true);
    expect(r.cells.length).toBe(r.volAxis.length);
    for (const row of r.cells) expect(row.length).toBe(r.spotAxis.length);
    // zero-shock cell (x=0, Δσ=0) has zero flow and never amplifies
    const zRow = r.volAxis.indexOf(0);
    const zCol = r.spotAxis.indexOf(0);
    expect(r.cells[zRow][zCol].flow).toBe(0);
    expect(r.cells[zRow][zCol].amplifies).toBe(false);
  });

  it("short-gamma book: dealers SELL into down-moves (amplifying) at Δσ=0", () => {
    const r = scenarioMatrix(shortGammaChain(), 100);
    expect(r.regime).toBe("short");
    expect(r.netGex! < 0).toBe(true);
    const zRow = r.volAxis.indexOf(0);
    const downCol = r.spotAxis.indexOf(-4);
    const cell = r.cells[zRow][downCol];
    // short gamma + spot down → dealers sell (flow < 0), same direction as the move → amplifies
    expect(cell.flow < 0).toBe(true);
    expect(cell.amplifies).toBe(true);
    expect(r.worst).not.toBeNull();
  });

  it("long-gamma book: dealers BUY into down-moves (dampening), never amplifies at Δσ=0", () => {
    const r = scenarioMatrix(longGammaChain(), 100);
    expect(r.regime).toBe("long");
    expect(r.netGex! > 0).toBe(true);
    const zRow = r.volAxis.indexOf(0);
    for (const x of [-4, -2, 2, 4]) {
      const cell = r.cells[zRow][r.spotAxis.indexOf(x)];
      // long gamma dampens: dealers trade AGAINST the move, so no amplification on the Δσ=0 row
      expect(cell.amplifies).toBe(false);
    }
  });

  it("flow scales with the spot move and reports a realistic down/up-vol stress corner", () => {
    const r = scenarioMatrix(shortGammaChain(), 100);
    const zRow = r.volAxis.indexOf(0);
    const f1 = Math.abs(r.cells[zRow][r.spotAxis.indexOf(-1)].flow);
    const f4 = Math.abs(r.cells[zRow][r.spotAxis.indexOf(-4)].flow);
    expect(f4).toBeGreaterThan(f1); // bigger move → bigger hedging flow (linear in GEX)
    expect(r.stress).not.toBeNull();
    expect(r.stress!.spotPct).toBe(-4);
    expect(r.stress!.volPts).toBe(10);
    expect(r.maxAbsFlow).toBeGreaterThan(0);
  });
});
