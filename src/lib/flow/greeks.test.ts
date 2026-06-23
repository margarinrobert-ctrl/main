import { describe, expect, it } from "vitest";
import { bsCharm, bsGamma, bsVanna, d1d2, ncdf, pdf, probAbove, probTouch } from "./greeks";

describe("black-scholes second-order greeks", () => {
  it("pdf peaks at 0 and is symmetric", () => {
    expect(pdf(0)).toBeCloseTo(0.39894, 5);
    expect(pdf(1)).toBeCloseTo(pdf(-1), 12);
  });

  it("guards degenerate d1/d2 inputs", () => {
    expect(d1d2(0, 100, 0.3, 0.05)).toBeNull();
    expect(d1d2(100, 100, 0.3, 0)).toBeNull();
    expect(d1d2(100, 100, 0, 0.05)).toBeNull();
  });

  it("OTM call: raising IV lifts delta (vanna > 0), delta bleeds to 0 into expiry (charm < 0)", () => {
    expect(bsVanna(100, 110, 0.3, 0.05)).toBeCloseTo(0.7387, 3);
    expect(bsCharm(100, 110, 0.3, 0.05)).toBeCloseTo(-2.2162, 3);
  });

  it("ITM call: raising IV lowers delta (vanna < 0), delta builds toward 1 (charm > 0)", () => {
    expect(bsVanna(100, 90, 0.3, 0.05)).toBeCloseTo(-0.5644, 3);
    expect(bsCharm(100, 90, 0.3, 0.05)).toBeCloseTo(1.6936, 3);
  });

  it("gamma is positive and peaks at the money", () => {
    const atm = bsGamma(100, 100, 0.3, 0.05)!;
    const otm = bsGamma(100, 130, 0.3, 0.05)!;
    expect(atm).toBeGreaterThan(0);
    expect(atm).toBeGreaterThan(otm);
    expect(bsGamma(100, 100, 0, 0.05)).toBeNull();
  });

  it("normal CDF and probabilities behave", () => {
    expect(ncdf(0)).toBeCloseTo(0.5, 5);
    expect(ncdf(1.6448536)).toBeCloseTo(0.95, 3);
    expect(probAbove(100, 100, 0.2, 0.25)).toBeLessThan(0.5); // driftless: slightly below 0.5
  });

  it("probability-of-touch: 1 at spot, higher for closer levels, ≥ prob of finishing past", () => {
    expect(probTouch(100, 100, 0.2, 0.1)).toBe(1);
    const near = probTouch(100, 102, 0.2, 0.1)!;
    const far = probTouch(100, 110, 0.2, 0.1)!;
    expect(near).toBeGreaterThan(far);
    expect(near).toBeGreaterThan(0);
    expect(near).toBeLessThanOrEqual(1);
    // touching a barrier is at least as likely as finishing beyond it
    expect(probTouch(100, 108, 0.2, 0.1)!).toBeGreaterThanOrEqual(probAbove(100, 108, 0.2, 0.1)!);
    expect(probTouch(100, 110, 0, 0.1)).toBeNull();
  });
});
