import { describe, expect, it } from "vitest";
import { ensembleForecast } from "./ensemble";
import type { Outcome, PredictionRecord } from "./journal";

const DAY = 24 * 60 * 60_000;

function rec(p: Partial<PredictionRecord>): PredictionRecord {
  return {
    id: Math.random().toString(36).slice(2),
    t: 0,
    symbol: "SPY",
    source: "anomaly",
    model: "Anomaly",
    label: "x",
    direction: "bullish",
    confidence: 70,
    strength: 50,
    entry: 100,
    target: null,
    stop: null,
    horizonMs: 60 * 60_000,
    regime: "long",
    volRegime: "normal",
    features: {},
    conditions: { netGex: null, flip: null, iv: null, pcr: null, relVol: null },
    outcome: null,
    ...p,
  };
}

function resv(dirReturn: number, p: Partial<PredictionRecord> = {}): PredictionRecord {
  const correct = dirReturn > 0;
  const outcome: Outcome = {
    resolvedAt: p.t ?? 0,
    exit: 100 * (1 + dirReturn),
    realizedReturn: dirReturn,
    dirReturn,
    correct,
    hitTarget: null,
    hitStop: null,
    mfe: Math.max(0, dirReturn),
    mae: Math.max(0, -dirReturn),
    brier: 0.25,
    bars: 5,
  };
  return rec({ ...p, outcome });
}

describe("ensembleForecast", () => {
  it("is unavailable with no records or only neutral calls", () => {
    expect(ensembleForecast([]).available).toBe(false);
    expect(ensembleForecast([rec({ direction: "neutral" })]).available).toBe(false);
  });

  it("blends toward the higher-performing source even when sources disagree", () => {
    const now = 1_000_000;
    const recs: PredictionRecord[] = [];
    // anomaly has a positive realised edge and is calling bullish
    for (let i = 0; i < 12; i++) recs.push(resv(0.004, { source: "anomaly", model: "Anomaly", t: i * 1000 }));
    // mmhedge has a negative realised edge and is calling bearish
    for (let i = 0; i < 12; i++) recs.push(resv(-0.004, { source: "mmhedge", model: "MM:long-γ", t: i * 1000, direction: "bearish" }));
    // freshest live calls from each
    recs.push(rec({ source: "anomaly", model: "Anomaly", t: now - 1000, direction: "bullish" }));
    recs.push(rec({ source: "mmhedge", model: "MM:long-γ", t: now - 1000, direction: "bearish" }));

    const e = ensembleForecast(recs, now);
    expect(e.available).toBe(true);
    expect(e.direction).toBe("bullish"); // good (bullish) source outweighs the bad (bearish) one
    expect(e.pUp).toBeGreaterThan(0.5);
    expect(e.score).toBeGreaterThan(0);
    const anomaly = e.votes.find((v) => v.source === "Anomaly")!;
    const mm = e.votes.find((v) => v.source.startsWith("MM"))!;
    expect(anomaly.weight).toBeGreaterThan(mm.weight);
    // weights are normalised
    expect(e.votes.reduce((s, v) => s + v.weight, 0)).toBeCloseTo(1, 6);
    // positive-edge book with a directional call → a capped fractional-Kelly suggestion
    expect(e.kelly).not.toBeNull();
    expect(e.kelly!).toBeGreaterThanOrEqual(0);
    expect(e.kelly!).toBeLessThanOrEqual(0.25);
  });

  it("downweights stale calls relative to fresh ones", () => {
    const now = 1_000_000;
    const e = ensembleForecast(
      [
        rec({ source: "anomaly", model: "Anomaly", t: now - 1000, direction: "bullish" }), // fresh
        rec({ source: "signals", model: "Signal:x", t: now - 5 * DAY, direction: "bullish" }), // stale
      ],
      now,
    );
    const fresh = e.votes.find((v) => v.source === "Anomaly")!;
    const stale = e.votes.find((v) => v.source === "Signal:x")!;
    expect(fresh.weight).toBeGreaterThan(stale.weight);
  });

  it("agrees and gains confidence when all fresh sources align", () => {
    const now = 1_000_000;
    const e = ensembleForecast(
      [
        rec({ source: "anomaly", model: "Anomaly", t: now - 1000, direction: "bearish", confidence: 75 }),
        rec({ source: "signals", model: "Signal:x", t: now - 1000, direction: "bearish", confidence: 70 }),
        rec({ source: "mmhedge", model: "MM:short-γ", t: now - 1000, direction: "bearish", confidence: 65 }),
      ],
      now,
    );
    expect(e.direction).toBe("bearish");
    expect(e.pUp).toBeLessThan(0.5);
    expect(e.agreement).toBeCloseTo(1, 6); // unanimous
  });
});
