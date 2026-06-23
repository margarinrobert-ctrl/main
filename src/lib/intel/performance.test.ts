import { describe, expect, it } from "vitest";
import type { Outcome, PredictionRecord } from "./journal";
import { breakdown, calibration, edgeDecay, featureImportance, healthState, rankModels, rollingEdge, summarize, wilson } from "./performance";

let seq = 0;
function res(dirReturn: number, confidence: number, extra: Partial<PredictionRecord> = {}, resolvedAt = seq++): PredictionRecord {
  const correct = dirReturn > 0;
  const outcome: Outcome = {
    resolvedAt,
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
    id: Math.random().toString(36).slice(2),
    t: resolvedAt,
    symbol: "SPY",
    source: "anomaly",
    model: "Anomaly",
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
    ...extra,
  };
}

describe("wilson", () => {
  it("brackets the point estimate and is wider at small n", () => {
    const wide = wilson(8, 10);
    const tight = wilson(80, 100);
    expect(wide.lo).toBeLessThan(0.8);
    expect(wide.hi).toBeGreaterThan(0.8);
    expect(tight.hi - tight.lo).toBeLessThan(wide.hi - wide.lo);
    expect(wilson(0, 0)).toEqual({ lo: 0, hi: 0 });
  });
});

describe("summarize", () => {
  it("computes hit-rate, expectancy, profit factor and Brier from outcomes", () => {
    const recs = [res(0.02, 80), res(0.01, 70), res(-0.01, 60), res(0.03, 90)];
    const s = summarize(recs);
    expect(s.n).toBe(4);
    expect(s.hitRate).toBeCloseTo(0.75, 6);
    expect(s.expectancy).toBeCloseTo(((2 + 1 - 1 + 3) / 4), 6); // in %
    expect(s.profitFactor).toBeCloseTo(6 / 1, 6);
    expect(s.brier).toBeGreaterThan(0);
    expect(s.ci!.lo).toBeLessThan(0.75);
  });
  it("returns an empty summary with no resolved records", () => {
    expect(summarize([]).n).toBe(0);
    expect(summarize([]).hitRate).toBeNull();
  });
});

describe("breakdown / rankModels", () => {
  it("groups by key and ranks models, filtering by min sample", () => {
    const recs = [res(0.02, 70, { model: "Anomaly" }), res(0.03, 70, { model: "Anomaly" }), res(-0.02, 70, { model: "MM:short-γ" })];
    const byModel = breakdown(recs, (r) => r.model);
    expect(byModel.map((g) => g.key)).toContain("Anomaly");
    expect(byModel[0].summary.expectancy!).toBeGreaterThan(byModel[byModel.length - 1].summary.expectancy!);
    expect(rankModels(recs, 5)).toHaveLength(0); // none reach n=5
    expect(rankModels(recs, 1).length).toBeGreaterThan(0);
  });
});

describe("rollingEdge / edgeDecay / healthState", () => {
  it("produces a rolling series and flags a decaying edge", () => {
    // strong winners first, losers later → recent expectancy below baseline
    const recs = [...Array(10)].map((_, i) => res(0.03, 70, {}, i)).concat([...Array(10)].map((_, i) => res(-0.03, 70, {}, 10 + i)));
    const roll = rollingEdge(recs, 5);
    expect(roll).toHaveLength(20);
    const decay = edgeDecay(recs);
    expect(decay.decaying).toBe(true);
    expect(decay.recent!).toBeLessThan(decay.baseline!);
    expect(healthState(recs)).toBe("degrading");
  });
  it("reports insufficient with too few resolved", () => {
    expect(healthState([res(0.01, 70)])).toBe("insufficient");
  });
});

describe("calibration", () => {
  it("detects overconfidence (high stated confidence, low realised hit-rate)", () => {
    // 90% confidence but only half correct
    const recs = [...Array(6)].map((_, i) => res(i % 2 === 0 ? 0.01 : -0.01, 90));
    const cal = calibration(recs);
    expect(cal.error!).toBeGreaterThan(0.2);
    const hi = cal.bins.find((b) => b.label === "80–100")!;
    expect(hi.predicted).toBeGreaterThan(hi.realized);
  });
});

describe("featureImportance", () => {
  it("ranks a feature that aligns with outcomes highest", () => {
    // feature "edge" equals the sign/size of the return → strong positive correlation
    const recs = [...Array(12)].map((_, i) => {
      const dr = (i % 2 === 0 ? 1 : -1) * 0.02;
      return res(dr, 70, { features: { edge: dr * 100, noise: Math.sin(i) } });
    });
    const fi = featureImportance(recs);
    expect(fi[0].feature).toBe("edge");
    expect(Math.abs(fi[0].corr)).toBeGreaterThan(0.9);
  });
});
