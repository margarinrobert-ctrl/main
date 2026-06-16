import { describe, expect, it } from "vitest";
import { bsCharm, bsVanna, d1d2, pdf } from "./greeks";

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
});
