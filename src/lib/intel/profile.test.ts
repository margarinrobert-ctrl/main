import { describe, expect, it } from "vitest";
import type { IntelSource, Outcome, PredictionRecord } from "./journal";
import { calibrateConfidence, learnedProfile, sourceStat } from "./profile";

let seq = 0;
function rec(dirReturn: number, confidence: number, source: IntelSource = "anomaly"): PredictionRecord {
  const correct = dirReturn > 0;
  const t = seq++;
  const outcome: Outcome = {
    resolvedAt: t,
    exit: 100 * (1 + dirReturn),
    realizedReturn: dirReturn,
    dirReturn,
    correct,
    hitTarget: null,
    hitStop: null,
    mfe: Math.max(0, dirReturn),
    mae: Math.max(0, -dirReturn),
    brier: (confidence / 100 - (correct ? 1 : 0)) ** 2,
    bars: 5,
  };
  return {
    id: String(t),
    t,
    symbol: "SPY",
    source,
    model: source,
    label: "x",
    direction: dirReturn >= 0 ? "bullish" : "bearish",
    confidence,
    strength: 50,
    entry: 100,
    target: null,
    stop: null,
    horizonMs: 100,
    regime: "long",
    volRegime: "normal",
    features: {},
    conditions: { netGex: null, flip: null, iv: null, pcr: null, relVol: null },
    outcome,
  };
}

describe("learnedProfile", () => {
  it("is not ready and weights sources near-equally with no history", () => {
    const p = learnedProfile([]);
    expect(p.ready).toBe(false);
    expect(p.sources).toHaveLength(3);
    expect(p.sources.reduce((s, x) => s + x.weight, 0)).toBeCloseTo(1, 6);
  });

  it("weights the higher-performing source above the worse one", () => {
    const recs = [
      ...Array.from({ length: 12 }, () => rec(0.004, 70, "anomaly")), // good edge
      ...Array.from({ length: 12 }, () => rec(-0.004, 70, "mmhedge")), // bad edge
    ];
    const p = learnedProfile(recs);
    expect(p.ready).toBe(true);
    const a = sourceStat(p, "anomaly")!;
    const m = sourceStat(p, "mmhedge")!;
    expect(a.weight).toBeGreaterThan(m.weight);
    expect(a.edge!).toBeGreaterThan(0);
    expect(m.edge!).toBeLessThan(0);
  });
});

describe("calibrateConfidence", () => {
  it("returns the stated confidence unchanged until the journal is mature", () => {
    const p = learnedProfile([rec(0.01, 80), rec(-0.01, 80)]); // n=2, not ready
    expect(calibrateConfidence(80, p)).toBe(80);
  });

  it("shrinks an overconfident band toward its realised hit-rate", () => {
    // 60-band realises ~60% (well-calibrated); 85-band realises only 50% (overconfident)
    const recs = [
      ...Array.from({ length: 10 }, (_, i) => rec(i < 6 ? 0.01 : -0.01, 60)),
      ...Array.from({ length: 10 }, (_, i) => rec(i < 5 ? 0.01 : -0.01, 85)),
    ];
    const p = learnedProfile(recs);
    expect(p.ready).toBe(true);
    const cal85 = calibrateConfidence(85, p);
    expect(cal85).toBeLessThan(85); // pulled down toward the realised ~50%
    expect(calibrateConfidence(60, p)).toBeGreaterThanOrEqual(55); // well-calibrated band ~unchanged
  });
});
