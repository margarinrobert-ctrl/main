import { describe, expect, it } from "vitest";
import type { GexSample } from "../gex-history";
import type { PredictionRecord } from "./journal";
import { open, resolved, resolveForSymbol, resolveOne } from "./resolve";

function rec(p: Partial<PredictionRecord>): PredictionRecord {
  return {
    id: p.id ?? Math.random().toString(36).slice(2),
    t: p.t ?? 0,
    symbol: p.symbol ?? "SPY",
    source: p.source ?? "anomaly",
    model: p.model ?? "Anomaly",
    label: p.label ?? "x",
    direction: p.direction ?? "bullish",
    confidence: p.confidence ?? 70,
    strength: p.strength ?? 50,
    entry: p.entry ?? 100,
    target: p.target ?? null,
    stop: p.stop ?? null,
    horizonMs: p.horizonMs ?? 100,
    regime: p.regime ?? "long",
    volRegime: p.volRegime ?? "normal",
    features: p.features ?? {},
    conditions: p.conditions ?? { netGex: null, flip: null, iv: null, pcr: null, relVol: null },
    outcome: p.outcome ?? null,
  };
}
const series = (spots: number[], gap = 20): { t: number; spot: number }[] => spots.map((spot, i) => ({ t: i * gap, spot }));
const samples = (spots: number[], gap = 20): GexSample[] => spots.map((spot, i) => ({ t: i * gap, spot, gex: null, flip: null }));

describe("resolveOne", () => {
  it("scores a correct bullish call that reaches its target", () => {
    const r = rec({ direction: "bullish", entry: 100, target: 102, stop: 98, horizonMs: 100, confidence: 80 });
    const o = resolveOne(r, series([100, 101, 103, 104]), 1000); // matureAt=100 → exit at t=100 (index 5? gap20 → idx5=t100)
    expect(o).not.toBeNull();
    expect(o!.correct).toBe(true);
    expect(o!.dirReturn).toBeGreaterThan(0);
    expect(o!.hitTarget).toBe(true);
    expect(o!.brier).toBeCloseTo((0.8 - 1) ** 2, 6);
  });

  it("scores an incorrect bearish call when price rises", () => {
    const r = rec({ direction: "bearish", entry: 100, target: 98, horizonMs: 60 });
    const o = resolveOne(r, series([100, 101, 102, 103, 104]), 1000);
    expect(o!.correct).toBe(false);
    expect(o!.dirReturn).toBeLessThan(0);
    expect(o!.mae).toBeGreaterThan(0); // adverse excursion (price went up against the short)
  });

  it("returns null until the horizon matures", () => {
    const r = rec({ direction: "bullish", entry: 100, horizonMs: 10_000 });
    expect(resolveOne(r, series([100, 100.5, 101]), 50)).toBeNull();
  });

  it("tracks max favourable / adverse excursion over the path", () => {
    const r = rec({ direction: "bullish", entry: 100, horizonMs: 80 });
    const o = resolveOne(r, series([100, 97, 105, 101]), 1000);
    expect(o!.mfe).toBeCloseTo(0.05, 6); // hit 105
    expect(o!.mae).toBeCloseTo(0.03, 6); // dipped to 97
  });
});

describe("resolveForSymbol", () => {
  it("resolves matured records for the symbol, leaves others open and untouched", () => {
    const recs: PredictionRecord[] = [
      rec({ symbol: "SPY", direction: "bullish", entry: 100, horizonMs: 40 }),
      rec({ symbol: "SPY", direction: "bullish", entry: 100, horizonMs: 10_000_000 }), // not matured
      rec({ symbol: "QQQ", direction: "bullish", entry: 100, horizonMs: 40 }), // other symbol — untouched
    ];
    const out = resolveForSymbol(recs, "SPY", samples([100, 101, 102, 103, 104]), 1000);
    expect(resolved(out.filter((r) => r.symbol === "SPY"))).toHaveLength(1);
    expect(open(out.filter((r) => r.symbol === "SPY"))).toHaveLength(1);
    expect(out.find((r) => r.symbol === "QQQ")!.outcome).toBeNull();
  });

  it("is a no-op without enough price samples", () => {
    const recs = [rec({ symbol: "SPY", horizonMs: 40 })];
    expect(resolveForSymbol(recs, "SPY", samples([100]), 1000)).toBe(recs);
  });
});
