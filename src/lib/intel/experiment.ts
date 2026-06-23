import type { PredictionRecord } from "./journal";
import { resolved } from "./resolve";

// Statistically-honest optimisation: walk-forward (out-of-sample) threshold tuning and what-if rule
// evaluation on the resolved journal. Walk-forward picks the confidence cut-off on a TRAIN slice and
// reports its expectancy on a later, unseen TEST slice vs taking everything — so an improvement isn't
// just in-sample overfit. These are evaluations, not auto-deploying changes.

const mean = (a: number[]) => (a.length ? a.reduce((s, x) => s + x, 0) / a.length : 0);
const ret = (r: PredictionRecord) => r.outcome!.dirReturn * 100;

export interface WalkForward {
  ok: boolean;
  field: string;
  bestThreshold: number | null;
  trainExpectancy: number | null;
  testExpectancy: number | null; // filtered, out-of-sample
  baselineTestExpectancy: number | null; // take-all, out-of-sample
  improvement: number | null;
  nTrain: number;
  nTest: number;
  nTestKept: number;
  note: string;
}

/** Tune a minimum-confidence cut-off on the train slice, evaluate it on the held-out test slice. */
export function walkForwardThreshold(records: PredictionRecord[], splitFrac = 0.7, minTotal = 20): WalkForward {
  const recs = resolved(records).sort((a, b) => a.outcome!.resolvedAt - b.outcome!.resolvedAt);
  const base: WalkForward = { ok: false, field: "confidence", bestThreshold: null, trainExpectancy: null, testExpectancy: null, baselineTestExpectancy: null, improvement: null, nTrain: 0, nTest: 0, nTestKept: 0, note: "" };
  if (recs.length < minTotal) return { ...base, nTrain: recs.length, note: `Need ≥${minTotal} resolved calls for a walk-forward split (have ${recs.length}).` };

  const cut = Math.floor(recs.length * splitFrac);
  const train = recs.slice(0, cut);
  const test = recs.slice(cut);
  if (test.length < 4) return { ...base, nTrain: train.length, nTest: test.length, note: "Test slice too small to be meaningful yet." };

  const grid = [0, 50, 55, 60, 65, 70, 75, 80, 85];
  let bestT = 0;
  let bestExp = -Infinity;
  for (const t of grid) {
    const kept = train.filter((r) => r.confidence >= t).map(ret);
    if (kept.length < Math.max(4, Math.floor(train.length * 0.15))) continue; // need enough to trust
    const e = mean(kept);
    if (e > bestExp) {
      bestExp = e;
      bestT = t;
    }
  }
  const testKept = test.filter((r) => r.confidence >= bestT).map(ret);
  const testExp = testKept.length ? mean(testKept) : null;
  const baseExp = mean(test.map(ret));
  return {
    ok: true,
    field: "confidence",
    bestThreshold: bestT,
    trainExpectancy: Number.isFinite(bestExp) ? bestExp : null,
    testExpectancy: testExp,
    baselineTestExpectancy: baseExp,
    improvement: testExp != null ? testExp - baseExp : null,
    nTrain: train.length,
    nTest: test.length,
    nTestKept: testKept.length,
    note: bestT === 0 ? "No confidence filter beat taking all calls in-sample." : `Confidence ≥ ${bestT} maximised train expectancy; the test column is its out-of-sample result.`,
  };
}

export interface WhatIf {
  rule: string;
  n: number;
  expectancy: number | null;
  hitRate: number | null;
  deltaVsAll: number | null;
}

/** Evaluate simple decision filters on the resolved journal vs taking every call. */
export function whatIfRules(records: PredictionRecord[]): WhatIf[] {
  const recs = resolved(records);
  if (recs.length < 10) return [];
  const allExp = mean(recs.map(ret));
  const rules: { rule: string; pred: (r: PredictionRecord) => boolean }[] = [
    { rule: "Confidence ≥ 60", pred: (r) => r.confidence >= 60 },
    { rule: "Confidence ≥ 75", pred: (r) => r.confidence >= 75 },
    { rule: "Long-γ only", pred: (r) => r.regime === "long" },
    { rule: "Short-γ only", pred: (r) => r.regime === "short" },
    { rule: "Vol expansion only", pred: (r) => /expansion/i.test(r.volRegime) },
    { rule: "Anomaly source only", pred: (r) => r.source === "anomaly" },
    { rule: "Bullish calls only", pred: (r) => r.direction === "bullish" },
    { rule: "Bearish calls only", pred: (r) => r.direction === "bearish" },
  ];
  return rules
    .map(({ rule, pred }) => {
      const g = recs.filter(pred);
      const e = g.length ? mean(g.map(ret)) : null;
      return { rule, n: g.length, expectancy: e, hitRate: g.length ? g.filter((r) => r.outcome!.correct).length / g.length : null, deltaVsAll: e != null ? e - allExp : null };
    })
    .filter((w) => w.n >= 4)
    .sort((a, b) => (b.expectancy ?? -1e9) - (a.expectancy ?? -1e9));
}
