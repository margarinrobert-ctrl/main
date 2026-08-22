import { describe, expect, it } from "vitest";
import {
  breakEvenWinRate, criticalCumulativeR, expectancy, expectedMaxZ, minTrackRecordLength,
  normalQuantile, nullVariance, pathBenchmarks, postSelectionCriticalR, validateRRecord, zStatistic,
} from "./rmultiple";
import { mulberry32 } from "./rng";

describe("R-multiple null model", () => {
  it("break-even win rate is 1/(b+1)", () => {
    expect(breakEvenWinRate(1)).toBeCloseTo(0.5, 12);
    expect(breakEvenWinRate(2)).toBeCloseTo(1 / 3, 12);
    expect(breakEvenWinRate(3)).toBeCloseTo(0.25, 12);
  });

  it("expectancy is exactly zero at the break-even win rate", () => {
    for (const b of [0.5, 1, 1.5, 2, 3, 4]) {
      expect(expectancy(breakEvenWinRate(b), b)).toBeCloseTo(0, 12);
    }
  });

  it("null variance equals the reward multiple — the result the framework turns on", () => {
    // Var(X) = E[X^2] under the null. p*b^2 + (1-p) with p = 1/(b+1) collapses to exactly b.
    for (const b of [0.5, 1, 1.5, 2, 3, 4, 10]) {
      const p = breakEvenWinRate(b);
      const brute = p * b * b + (1 - p) * 1 - expectancy(p, b) ** 2;
      expect(nullVariance(b)).toBeCloseTo(brute, 10);
      expect(nullVariance(b)).toBeCloseTo(b, 12);
    }
  });

  it("simulated trades reproduce the analytic null variance", () => {
    const rnd = mulberry32(3);
    for (const b of [1, 2, 4]) {
      const p = breakEvenWinRate(b);
      const xs = Array.from({ length: 200_000 }, () => (rnd() < p ? b : -1));
      const m = xs.reduce((a, x) => a + x, 0) / xs.length;
      const v = xs.reduce((a, x) => a + (x - m) ** 2, 0) / (xs.length - 1);
      expect(m).toBeCloseTo(0, 1);
      expect(v).toBeCloseTo(b, 1);
    }
  });
});

describe("normalQuantile", () => {
  it("matches known critical values", () => {
    expect(normalQuantile(0.5)).toBeCloseTo(0, 8);
    expect(normalQuantile(0.95)).toBeCloseTo(1.6448536, 5);
    expect(normalQuantile(0.975)).toBeCloseTo(1.959964, 5);
    expect(normalQuantile(0.99)).toBeCloseTo(2.326348, 5);
  });
  it("is symmetric", () => {
    for (const p of [0.01, 0.1, 0.3]) expect(normalQuantile(p)).toBeCloseTo(-normalQuantile(1 - p), 6);
  });
});

describe("thresholds", () => {
  it("critical cumulative R grows with sqrt(n) and sqrt(b)", () => {
    const a = criticalCumulativeR(100, 1);
    expect(criticalCumulativeR(400, 1) / a).toBeCloseTo(2, 6);   // 4x trades -> 2x threshold
    expect(criticalCumulativeR(100, 4) / a).toBeCloseTo(2, 6);   // 4x reward -> 2x threshold
  });

  it("a higher reward multiple makes an edge HARDER to validate, not easier", () => {
    // The paper's central practical claim. Same edge, bigger b, more trades required.
    const e = 0.1;
    expect(minTrackRecordLength(3, e)).toBeCloseTo(3 * minTrackRecordLength(1, e), 6);
    expect(minTrackRecordLength(3, e)).toBeGreaterThan(minTrackRecordLength(1, e));
  });

  it("required trades grow quadratically as the edge shrinks", () => {
    expect(minTrackRecordLength(2, 0.05) / minTrackRecordLength(2, 0.1)).toBeCloseTo(4, 6);
  });

  it("returns Infinity for a non-positive edge", () => {
    expect(minTrackRecordLength(2, 0)).toBe(Infinity);
    expect(minTrackRecordLength(2, -0.1)).toBe(Infinity);
  });

  it("the z statistic is calibrated: 5% of zero-edge records clear the 5% threshold", () => {
    const rnd = mulberry32(11);
    const b = 2, n = 300, p = breakEvenWinRate(b);
    let rejects = 0;
    const runs = 4000;
    for (let k = 0; k < runs; k++) {
      let s = 0;
      for (let i = 0; i < n; i++) s += rnd() < p ? b : -1;
      if (s > criticalCumulativeR(n, b, 0.05)) rejects++;
    }
    expect(rejects / runs).toBeGreaterThan(0.03);
    expect(rejects / runs).toBeLessThan(0.07);
  });
});

describe("post-selection", () => {
  it("no adjustment for a single pre-specified test", () => {
    expect(expectedMaxZ(1)).toBe(0);
    expect(postSelectionCriticalR(100, 1, 1)).toBeCloseTo(criticalCumulativeR(100, 1), 10);
  });

  it("the bar rises with the size of the search", () => {
    expect(expectedMaxZ(10)).toBeGreaterThan(0);
    expect(expectedMaxZ(1000)).toBeGreaterThan(expectedMaxZ(10));
    expect(expectedMaxZ(100_000)).toBeGreaterThan(expectedMaxZ(1000));
    // Grows like sqrt(2 ln K): slow, but by 100k it is worth more than a full extra sigma.
    expect(expectedMaxZ(100_000)).toBeGreaterThan(1);
  });

  it("tracks the true expected maximum of K normals", () => {
    // Compare against a simulated max of K standard normals.
    const rnd = mulberry32(5);
    const norm = () => {
      const u = Math.max(rnd(), 1e-12), v = rnd();
      return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
    };
    for (const K of [10, 100]) {
      let acc = 0;
      const runs = 6000;
      for (let r = 0; r < runs; r++) {
        let mx = -Infinity;
        for (let i = 0; i < K; i++) mx = Math.max(mx, norm());
        acc += mx;
      }
      expect(expectedMaxZ(K)).toBeCloseTo(acc / runs, 0);
    }
  });
});

describe("path benchmarks under zero edge", () => {
  it("a no-edge system still produces drawdowns and losing streaks", () => {
    const bm = pathBenchmarks(200, 2, 4000, 1);
    expect(bm.maxDrawdown.p50).toBeGreaterThan(0);
    expect(bm.longestLosingStreak.p50).toBeGreaterThanOrEqual(3);
    expect(bm.equityMFE.p50).toBeGreaterThan(0);   // temporary profit with no edge at all
    expect(bm.equityMAE.p50).toBeLessThan(0);
  });

  it("path drama scales up with the reward multiple", () => {
    const low = pathBenchmarks(200, 1, 3000, 2);
    const high = pathBenchmarks(200, 4, 3000, 2);
    expect(high.maxDrawdown.p50).toBeGreaterThan(low.maxDrawdown.p50);
    expect(high.longestLosingStreak.p50).toBeGreaterThan(low.longestLosingStreak.p50);
  });
});

describe("validateRRecord", () => {
  it("flags a strong pre-specified record as significant", () => {
    // 200 trades, 60% wins at +2R: a large, obvious edge.
    const rnd = mulberry32(9);
    const rs = Array.from({ length: 200 }, () => (rnd() < 0.6 ? 2 : -1));
    const v = validateRRecord(rs, 1);
    expect(v.expectancy).toBeGreaterThan(0.5);
    expect(v.significant).toBe(true);
    expect(v.p).toBeLessThan(0.01);
  });

  it("does not flag a zero-edge record", () => {
    const rnd = mulberry32(4);
    const rs = Array.from({ length: 300 }, () => (rnd() < 1 / 3 ? 2 : -1));
    expect(validateRRecord(rs, 1).significant).toBe(false);
  });

  it("a record that passes as a single test can fail once the search is priced in", () => {
    const rnd = mulberry32(21);
    // A marginal edge — enough to clear the single-test bar, not a 10,000-config search.
    let rs: number[] = [];
    for (let attempt = 0; attempt < 60; attempt++) {
      rs = Array.from({ length: 150 }, () => (rnd() < 0.40 ? 2 : -1));
      const v = validateRRecord(rs, 1);
      if (v.significant && !validateRRecord(rs, 10_000).survivesSelection) break;
    }
    const single = validateRRecord(rs, 1);
    const searched = validateRRecord(rs, 10_000);
    expect(single.significant).toBe(true);
    expect(searched.survivesSelection).toBe(false);
    expect(searched.postSelectionCriticalR).toBeGreaterThan(single.criticalR);
  });

  it("reports observed variance next to the model's, so a non-binary record is visible", () => {
    // A record with partial exits: outcomes strictly between -1 and +b. The binary model does not
    // describe it, and the two variances diverge — here the small partial wins drag the implied b
    // down to 1.15 while the surviving +2 outcomes keep the real spread at 1.34. Which way it
    // breaks depends on the mix, so the test asserts DISAGREEMENT, not a direction: that is the
    // signal that the analytic thresholds are being applied to the wrong process.
    const rs = [2, -1, 0.3, -0.4, 2, -1, 0.1, -0.2, 2, -1, 0.5, -0.6, 2, -1, 0.2, -0.3, 2, -1, 0.4, -0.5];
    const v = validateRRecord(rs, 1);
    expect(v.nullVar).toBeCloseTo(v.impliedB, 10);
    expect(Math.abs(v.observedVar - v.nullVar) / v.nullVar).toBeGreaterThan(0.10);
  });

  it("the two variances agree when the record really is binary", () => {
    // The control for the test above: a clean +2 / -1 record, where the model is correct.
    const rnd = mulberry32(17);
    const rs = Array.from({ length: 4000 }, () => (rnd() < 1 / 3 ? 2 : -1));
    const v = validateRRecord(rs, 1);
    expect(v.observedVar).toBeCloseTo(v.nullVar, 1);
  });

  it("throws on an empty record rather than returning a verdict", () => {
    expect(() => validateRRecord([], 1)).toThrow();
  });
});
