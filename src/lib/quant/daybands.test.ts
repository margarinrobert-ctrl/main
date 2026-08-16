import { describe, expect, it } from "vitest";
import { bsPrice } from "../flow/greeks";
import { STRADDLE_TO_SIGMA, Z_618, coverageOf, dayBands, sigmaFromIv, sigmaFromStraddle } from "./daybands";

describe("constants and coverage", () => {
  it("Z_618 really is the 61.8% two-sided band", () => {
    expect(coverageOf(Z_618)).toBeCloseTo(0.618, 4);
  });

  it("1σ = 68.27%, 2σ = 95.45% (sanity on the normal law)", () => {
    expect(coverageOf(1)).toBeCloseTo(0.6827, 3);
    expect(coverageOf(2)).toBeCloseTo(0.9545, 3);
  });

  it("the straddle↔σ factor is √(π/2), i.e. a straddle is only ~0.798σ", () => {
    expect(STRADDLE_TO_SIGMA).toBeCloseTo(1.25331, 5);
    expect(1 / STRADDLE_TO_SIGMA).toBeCloseTo(0.79788, 5);
    // ±straddle therefore covers ~57.5%, NOT the ~68% a 1σ band implies — the bug this module fixes
    expect(coverageOf(1 / STRADDLE_TO_SIGMA)).toBeCloseTo(0.575, 3);
  });
});

describe("sigmaFromStraddle — inverts a real Black-Scholes straddle", () => {
  it("recovers σS√T from an ATM straddle priced by Black-Scholes", () => {
    const S = 500;
    for (const sigma of [0.12, 0.25, 0.6]) {
      for (const dte of [1, 7, 30]) {
        const T = dte / 365;
        const straddle = bsPrice("call", S, S, sigma, T)! + bsPrice("put", S, S, sigma, T)!;
        const recovered = sigmaFromStraddle(straddle)!;
        const truth = S * sigma * Math.sqrt(T);
        expect(recovered / truth).toBeCloseTo(1, 2); // exact up to the r=q=0 ATM approximation
      }
    }
  });

  it("rejects non-positive input", () => {
    expect(sigmaFromStraddle(0)).toBeNull();
    expect(sigmaFromStraddle(null)).toBeNull();
  });
});

describe("sigmaFromIv", () => {
  it("scales an annual IV to one session", () => {
    expect(sigmaFromIv(100, 0.16)!).toBeCloseTo((100 * 0.16) / Math.sqrt(252), 10);
    expect(sigmaFromIv(null, 0.16)).toBeNull();
    expect(sigmaFromIv(100, 0)).toBeNull();
  });
});

describe("dayBands", () => {
  it("centres on the anchor and orders the bands 61.8% < 1σ < 2σ", () => {
    const b = dayBands(600, null, 0.2)!;
    expect(b.mean).toBe(600);
    expect(b.source).toBe("iv");
    const [p618, sd1, sd2] = b.bands;
    expect(p618.hi).toBeLessThan(sd1.hi);
    expect(sd1.hi).toBeLessThan(sd2.hi);
    expect(p618.lo).toBeGreaterThan(sd1.lo);
    // symmetric about the mean
    for (const x of b.bands) expect(x.hi - 600).toBeCloseTo(600 - x.lo, 10);
    expect(sd1.hi - 600).toBeCloseTo(b.sigmaAbs, 10);
    expect(p618.coverage).toBeCloseTo(0.618, 4);
  });

  it("prefers the straddle and reports the source, but both paths mean the SAME σ", () => {
    const S = 500;
    const sigma = 0.2;
    const T = 1 / 252;
    const straddle = bsPrice("call", S, S, sigma, T)! + bsPrice("put", S, S, sigma, T)!;
    const fromStraddle = dayBands(S, straddle, null)!;
    const fromIv = dayBands(S, null, sigma)!;
    expect(fromStraddle.source).toBe("straddle");
    expect(fromIv.source).toBe("iv");
    // the whole point: consistent quantities, not a ~25% silent mismatch
    expect(fromStraddle.sigmaAbs / fromIv.sigmaAbs).toBeCloseTo(1, 2);
  });

  it("a raw straddle band would be materially tighter than the true 1σ (the old bug, quantified)", () => {
    const S = 500;
    const T = 1 / 252;
    const straddle = bsPrice("call", S, S, 0.2, T)! + bsPrice("put", S, S, 0.2, T)!;
    const trueSd1 = dayBands(S, straddle, null)!.bands.find((x) => x.key === "sd1")!;
    expect(trueSd1.hi - S).toBeGreaterThan(straddle * 1.2); // ~1.25× wider than ±straddle
  });

  it("degrades cleanly with no usable inputs", () => {
    expect(dayBands(null, 5, 0.2)).toBeNull();
    expect(dayBands(100, null, null)).toBeNull();
    expect(dayBands(100, 0, 0)).toBeNull();
  });
});
