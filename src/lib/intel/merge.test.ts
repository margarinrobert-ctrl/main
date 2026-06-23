import { describe, expect, it } from "vitest";
import type { GexSample } from "../gex-history";
import type { Outcome, PredictionRecord } from "./journal";
import { mergeHistory, mergeJournal } from "./merge";

const s = (t: number, spot: number): GexSample => ({ t, spot, gex: null, flip: null });
function rec(id: string, t: number, outcome: Outcome | null = null): PredictionRecord {
  return {
    id,
    t,
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
    horizonMs: 100,
    regime: "long",
    volRegime: "normal",
    features: {},
    conditions: { netGex: null, flip: null, iv: null, pcr: null, relVol: null },
    outcome,
  };
}
const outcome: Outcome = { resolvedAt: 5, exit: 101, realizedReturn: 0.01, dirReturn: 0.01, correct: true, hitTarget: null, hitStop: null, mfe: 0.01, mae: 0, brier: 0.09, bars: 3 };

describe("mergeHistory", () => {
  it("unions, dedupes by timestamp, sorts ascending and caps", () => {
    const a = [s(30, 100), s(10, 99), s(20, 98)];
    const b = [s(20, 200), s(40, 101)]; // t=20 collides → incoming wins
    const out = mergeHistory(a, b);
    expect(out.map((x) => x.t)).toEqual([10, 20, 30, 40]);
    expect(out.find((x) => x.t === 20)!.spot).toBe(200);
  });

  it("respects the cap, keeping the most recent", () => {
    const many = Array.from({ length: 50 }, (_, i) => s(i, 100 + i));
    const out = mergeHistory(many, [], 10);
    expect(out).toHaveLength(10);
    expect(out[0].t).toBe(40);
    expect(out[9].t).toBe(49);
  });
});

describe("mergeJournal", () => {
  it("dedupes by id and prefers the resolved copy of a duplicate", () => {
    const local = [rec("a", 1), rec("b", 2)];
    const server = [rec("a", 1, outcome), rec("c", 3)]; // a resolved on the server
    const out = mergeJournal(local, server);
    expect(out.map((r) => r.id).sort()).toEqual(["a", "b", "c"]);
    expect(out.find((r) => r.id === "a")!.outcome).not.toBeNull();
  });

  it("keeps distinct client + server streams (different ids) and sorts by time", () => {
    const out = mergeJournal([rec("x1", 5)], [rec("y1", 1), rec("y2", 9)]);
    expect(out.map((r) => r.id)).toEqual(["y1", "x1", "y2"]);
  });
});
