import { describe, expect, it } from "vitest";
import type { Outcome, PredictionRecord } from "./journal";
import { recommend } from "./recommend";
import { walkForwardThreshold, whatIfRules } from "./experiment";

let seq = 0;
function res(dirReturn: number, confidence: number, extra: Partial<PredictionRecord> = {}): PredictionRecord {
  const correct = dirReturn > 0;
  const resolvedAt = seq++;
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

describe("walkForwardThreshold", () => {
  it("needs a minimum sample before it will split", () => {
    const wf = walkForwardThreshold([res(0.01, 70)]);
    expect(wf.ok).toBe(false);
    expect(wf.note).toMatch(/walk-forward/i);
  });

  it("finds that filtering by confidence helps out-of-sample when high-confidence calls win", () => {
    // high-confidence (>=70) calls win; low-confidence calls lose — consistent across train & test
    const recs: PredictionRecord[] = [];
    for (let i = 0; i < 40; i++) recs.push(i % 2 === 0 ? res(0.02, 80) : res(-0.02, 55));
    const wf = walkForwardThreshold(recs);
    expect(wf.ok).toBe(true);
    expect(wf.bestThreshold!).toBeGreaterThanOrEqual(60);
    expect(wf.testExpectancy!).toBeGreaterThan(wf.baselineTestExpectancy!);
    expect(wf.improvement!).toBeGreaterThan(0);
  });
});

describe("whatIfRules", () => {
  it("ranks decision filters by expectancy and computes delta vs taking all", () => {
    const recs: PredictionRecord[] = [];
    for (let i = 0; i < 20; i++) recs.push(res(i % 2 === 0 ? 0.03 : -0.01, i % 2 === 0 ? 80 : 55));
    const rules = whatIfRules(recs);
    expect(rules.length).toBeGreaterThan(0);
    const hiConf = rules.find((r) => r.rule === "Confidence ≥ 75");
    expect(hiConf).toBeTruthy();
    expect(hiConf!.deltaVsAll!).toBeGreaterThan(0); // high-confidence subset beats the blend
  });

  it("returns nothing with too few resolved records", () => {
    expect(whatIfRules([res(0.01, 70)])).toHaveLength(0);
  });
});

describe("recommend", () => {
  it("emits a collecting note while the sample is small", () => {
    const recs = [res(0.01, 70), res(-0.01, 60)];
    const r = recommend(recs);
    expect(r.some((x) => x.id === "collecting")).toBe(true);
  });

  it("flags a negative overall edge as critical with enough samples", () => {
    const recs = [...Array(16)].map(() => res(-0.02, 70));
    const r = recommend(recs);
    expect(r.some((x) => x.id === "neg-overall" && x.severity === "critical")).toBe(true);
  });
});
