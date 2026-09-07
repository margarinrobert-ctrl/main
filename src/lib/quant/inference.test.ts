import { describe, expect, it } from "vitest";
import { returnAutocorrelation, varianceRatios } from "./alpha";
import { blockLength, bootstrapCI, realityCheck, stationaryIndices } from "./bootstrap";
import { combinations, probabilityOfBacktestOverfitting } from "./cpcv";
import { deflatedSharpe, probabilisticSharpe } from "./deflated";
import { correctMultiple } from "./multipletest";
import { buildPortfolio, correlationMatrix, riskParityWeights } from "./portfolio";
import { mulberry32, normal } from "./rng";
import { maxDrawdown, mean, neweyWestT, normalCdf, normalInv, sharpeRatio, std } from "./stats";
import type { Bar } from "./types";

const iid = (n: number, seed: number, mu = 0, sd = 1): number[] => {
  const r = mulberry32(seed);
  return Array.from({ length: n }, () => mu + sd * normal(r));
};

describe("normal distribution helpers", () => {
  it("inverts its own CDF", () => {
    for (const p of [0.001, 0.025, 0.1, 0.5, 0.9, 0.975, 0.999]) expect(normalCdf(normalInv(p))).toBeCloseTo(p, 5);
  });
  it("matches known quantiles", () => {
    expect(normalInv(0.975)).toBeCloseTo(1.959964, 4);
    expect(normalCdf(0)).toBeCloseTo(0.5, 6);
    expect(normalCdf(1.644854)).toBeCloseTo(0.95, 4);
  });
});

describe("neweyWestT", () => {
  it("agrees with the plain t-statistic on independent data", () => {
    const x = iid(4000, 11, 0.05, 1);
    const plain = mean(x) / (std(x) / Math.sqrt(x.length));
    expect(neweyWestT(x).t).toBeCloseTo(plain, 0);
  });

  it("reports a LARGER standard error on positively autocorrelated data", () => {
    const shocks = iid(4000, 12);
    const ar: number[] = [];
    let prev = 0;
    for (const s of shocks) ar.push((prev = 0.7 * prev + s));
    const naiveSe = std(ar) / Math.sqrt(ar.length);
    expect(neweyWestT(ar).se).toBeGreaterThan(naiveSe * 1.5);
  });
});

describe("drawdown and Sharpe", () => {
  it("measures peak-to-trough correctly", () => {
    const dd = maxDrawdown([100, 120, 90, 130, 60, 80]);
    expect(dd.abs).toBe(70);
    expect(dd.pct).toBeCloseTo(70 / 130, 6);
  });
  it("annualises by the square root of periods", () => {
    const x = iid(2000, 13, 0.1, 1);
    expect(sharpeRatio(x, 252)).toBeCloseTo(sharpeRatio(x, 1) * Math.sqrt(252), 6);
  });
});

describe("multiple testing", () => {
  it("reproduces a textbook Benjamini-Hochberg example", () => {
    const rows = [
      { label: "a", p: 0.001 },
      { label: "b", p: 0.008 },
      { label: "c", p: 0.039 },
      { label: "d", p: 0.041 },
      { label: "e", p: 0.042 },
    ];
    const out = correctMultiple(rows, 0.05);
    expect(out.map((r) => r.label)).toEqual(["a", "b", "c", "d", "e"]);
    // q_k = min over j >= k of p_j * m / j, enforced monotone from the largest p downwards.
    expect(out[0].qBH).toBeCloseTo(0.005, 6); // 0.001 * 5 / 1
    expect(out[1].qBH).toBeCloseTo(0.02, 6); // 0.008 * 5 / 2
    expect(out[2].qBH).toBeCloseTo(0.042, 6); // 0.065 clipped down to the q of the largest p
    expect(out[4].qBH).toBeCloseTo(0.042, 6); // 0.042 * 5 / 5
    expect(out.filter((r) => r.rejectBH).map((r) => r.label)).toEqual(["a", "b", "c", "d", "e"]);
    // Holm is stricter on the same data and stops after the first two.
    expect(out.filter((r) => r.rejectHolm).map((r) => r.label)).toEqual(["a", "b"]);
  });

  it("is at least as strict under Holm as under BH", () => {
    const rows = Array.from({ length: 20 }, (_, i) => ({ label: `t${i}`, p: (i + 1) / 40 }));
    for (const r of correctMultiple(rows)) expect(r.pHolm).toBeGreaterThanOrEqual(r.qBH - 1e-12);
  });
});

describe("stationary bootstrap", () => {
  it("produces index paths of the right length inside the series", () => {
    const idx = stationaryIndices(500, blockLength(500), mulberry32(3));
    expect(idx).toHaveLength(500);
    expect(Math.min(...idx)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...idx)).toBeLessThan(500);
  });

  it("builds a confidence interval that brackets the true mean", () => {
    const ci = bootstrapCI(iid(1500, 21, 0.3, 1), mean, { samples: 500, seed: 7 });
    expect(ci.lower).toBeLessThan(0.3);
    expect(ci.upper).toBeGreaterThan(0.3);
    expect(ci.pLessEqualZero).toBeLessThan(0.01);
  });
});

describe("reality check / SPA", () => {
  it("does NOT reject when every candidate is pure noise", () => {
    const series = Array.from({ length: 12 }, (_, k) => iid(500, 100 + k));
    const rc = realityCheck(series, series.map((_, k) => `c${k}`), { samples: 500, seed: 4 });
    expect(rc.pWhite).toBeGreaterThan(0.1);
    expect(rc.pSpa).toBeGreaterThan(0.1);
  });

  it("rejects when one candidate has a genuine edge", () => {
    const series = Array.from({ length: 12 }, (_, k) => iid(500, 200 + k, k === 3 ? 0.25 : 0));
    const rc = realityCheck(series, series.map((_, k) => `c${k}`), { samples: 500, seed: 4 });
    expect(rc.bestIndex).toBe(3);
    expect(rc.pWhite).toBeLessThan(0.05);
  });
});

describe("probability of backtest overfitting", () => {
  it("enumerates balanced splits correctly", () => {
    expect(combinations(10, 5)).toHaveLength(252);
    expect(combinations(4, 2)).toEqual([[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]]);
  });

  it("is near a coin flip when all candidates are noise", () => {
    const series = Array.from({ length: 30 }, (_, k) => iid(400, 300 + k));
    const pbo = probabilityOfBacktestOverfitting(series, 10);
    expect(pbo.pbo).toBeGreaterThan(0.25);
    expect(pbo.pbo).toBeLessThan(0.75);
  });

  it("is low when one candidate genuinely dominates", () => {
    const series = Array.from({ length: 30 }, (_, k) => iid(400, 400 + k, k === 7 ? 0.4 : 0));
    const pbo = probabilityOfBacktestOverfitting(series, 10);
    expect(pbo.pbo).toBeLessThan(0.15);
  });
});

describe("deflated Sharpe", () => {
  const x = iid(1000, 55, 0.06, 1);

  it("is monotonically decreasing in the number of trials", () => {
    const dispersion = 0.03;
    const a = deflatedSharpe(x, 5, dispersion).dsr;
    const b = deflatedSharpe(x, 500, dispersion).dsr;
    const c = deflatedSharpe(x, 50_000, dispersion).dsr;
    expect(a).toBeGreaterThan(b);
    expect(b).toBeGreaterThan(c);
  });

  it("equals the probabilistic Sharpe against zero when nothing was searched over", () => {
    expect(deflatedSharpe(x, 2, 0).dsr).toBeCloseTo(probabilisticSharpe(x, 0).psr, 6);
  });

  it("demands a longer track record for a weaker Sharpe", () => {
    const weak = probabilisticSharpe(iid(1000, 56, 0.02, 1)).minTrackRecord;
    const strong = probabilisticSharpe(iid(1000, 56, 0.2, 1)).minTrackRecord;
    expect(weak).toBeGreaterThan(strong);
  });
});

describe("variance ratio and autocorrelation", () => {
  const toBars = (prices: number[]): Bar[] =>
    prices.map((p, i) => ({ t: Date.UTC(2024, 0, 2, 0, 0) + i * 300_000, o: p, h: p, l: p, c: p, v: 1 }));

  it("finds VR near 1 and no autocorrelation on a random walk", () => {
    const r = mulberry32(77);
    const prices: number[] = [100];
    for (let i = 1; i < 6000; i++) prices.push(prices[i - 1] * Math.exp(0.001 * normal(r)));
    const vr = varianceRatios(toBars(prices), "UTC", [2, 5]);
    for (const v of vr) expect(Math.abs(v.vr - 1)).toBeLessThan(0.12);
    const ac = returnAutocorrelation(toBars(prices), "UTC", 3);
    for (const row of ac) expect(Math.abs(row.t)).toBeLessThan(3);
  });

  it("detects injected mean reversion as VR < 1", () => {
    const r = mulberry32(78);
    const prices: number[] = [100];
    let prev = 0;
    for (let i = 1; i < 6000; i++) {
      const shock = 0.001 * normal(r);
      const ret = shock - 0.4 * prev; // negative serial dependence
      prices.push(prices[i - 1] * Math.exp(ret));
      prev = ret;
    }
    const vr = varianceRatios(toBars(prices), "UTC", [2, 5]);
    expect(vr[0].vr).toBeLessThan(0.9);
    expect(vr[0].reading).toBe("mean reversion");
  });
});

describe("portfolio construction", () => {
  it("computes a correlation matrix with a unit diagonal and correct sign", () => {
    const a = iid(500, 61);
    const b = a.map((v) => -v + 0.01);
    const c = correlationMatrix([a, b]);
    expect(c[0][0]).toBeCloseTo(1, 9);
    expect(c[0][1]).toBeCloseTo(-1, 3);
  });

  it("equalises risk contributions under risk parity", () => {
    const cov = [
      [0.04, 0.006, 0.0],
      [0.006, 0.01, 0.0],
      [0.0, 0.0, 0.0025],
    ];
    const w = riskParityWeights(cov);
    const mrc = w.map((_, i) => w.reduce((acc, wj, j) => acc + cov[i][j] * wj, 0));
    const portVar = w.reduce((acc, wi, i) => acc + wi * mrc[i], 0);
    const rc = w.map((wi, i) => (wi * mrc[i]) / portVar);
    for (const share of rc) expect(share).toBeCloseTo(1 / 3, 2);
    expect(w[0]).toBeLessThan(w[2]); // the most volatile asset gets the smallest weight
  });

  it("shows diversification when combining uncorrelated streams", () => {
    const streams = Array.from({ length: 4 }, (_, k) => ({
      label: `s${k}`,
      dailyPnl: new Map(iid(400, 70 + k, 0.05, 1).map((v, i) => [i, v] as const)),
    }));
    const aligned = { days: Array.from({ length: 400 }, (_, i) => i), labels: streams.map((s) => s.label), matrix: streams.map((s) => Array.from({ length: 400 }, (_, i) => s.dailyPnl.get(i) ?? 0)) };
    const p = buildPortfolio(aligned, "risk-parity");
    expect(p.diversificationRatio).toBeGreaterThan(1.5);
    expect(p.sharpe).toBeGreaterThan(Math.max(...p.standaloneSharpes));
    expect(p.riskContribution.reduce((a, b) => a + b, 0)).toBeCloseTo(1, 6);
  });
});
