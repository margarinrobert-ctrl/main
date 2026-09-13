import { describe, expect, it } from "vitest";
import { bsBounds, bsImpliedVol, bsQuote, valueCurve } from "./bs";

describe("bsQuote — verified against published textbook values", () => {
  // Hull, "Options, Futures and Other Derivatives": S=42, K=40, r=10%, σ=20%, T=0.5
  it("reproduces Hull's classic example (call 4.76, put 0.81)", () => {
    const call = bsQuote({ type: "call", spot: 42, strike: 40, tYears: 0.5, sigma: 0.2, r: 0.1 })!;
    const put = bsQuote({ type: "put", spot: 42, strike: 40, tYears: 0.5, sigma: 0.2, r: 0.1 })!;
    expect(call.price).toBeCloseTo(4.759, 2);
    expect(put.price).toBeCloseTo(0.808, 2);
    expect(call.d1).toBeCloseTo(0.7693, 3);
    expect(call.d2).toBeCloseTo(0.6278, 3);
  });

  it("reproduces the standard S=K=100, T=1, σ=20%, r=5% call ≈ 10.45", () => {
    const c = bsQuote({ type: "call", spot: 100, strike: 100, tYears: 1, sigma: 0.2, r: 0.05 })!;
    expect(c.price).toBeCloseTo(10.4506, 3);
    expect(c.delta).toBeCloseTo(0.6368, 3);
    expect(c.gamma).toBeCloseTo(0.01876, 4);
    expect(c.vega).toBeCloseTo(0.3752, 3); // per vol point
    expect(c.rho).toBeCloseTo(0.5323, 3); // per rate point
    expect(c.thetaDay).toBeLessThan(0);
  });

  it("satisfies put-call parity with rates and dividends: C − P = S·e^{−qT} − K·e^{−rT}", () => {
    const i = { spot: 105, strike: 95, tYears: 0.75, sigma: 0.33, r: 0.04, q: 0.015 };
    const c = bsQuote({ ...i, type: "call" })!.price;
    const p = bsQuote({ ...i, type: "put" })!.price;
    expect(c - p).toBeCloseTo(105 * Math.exp(-0.015 * 0.75) - 95 * Math.exp(-0.04 * 0.75), 8);
  });

  it("dividend yield lowers the call and its delta (Merton)", () => {
    const base = bsQuote({ type: "call", spot: 100, strike: 100, tYears: 1, sigma: 0.2, r: 0.05 })!;
    const withQ = bsQuote({ type: "call", spot: 100, strike: 100, tYears: 1, sigma: 0.2, r: 0.05, q: 0.03 })!;
    expect(withQ.price).toBeLessThan(base.price);
    expect(withQ.delta).toBeLessThan(base.delta);
  });

  it("rejects degenerate inputs", () => {
    expect(bsQuote({ type: "call", spot: 0, strike: 100, tYears: 1, sigma: 0.2 })).toBeNull();
    expect(bsQuote({ type: "call", spot: 100, strike: 100, tYears: 0, sigma: 0.2 })).toBeNull();
    expect(bsQuote({ type: "call", spot: 100, strike: 100, tYears: 1, sigma: 0 })).toBeNull();
  });
});

describe("bsImpliedVol", () => {
  it("round-trips: price at σ → solve → σ (with r and q)", () => {
    for (const sigma of [0.08, 0.2, 0.55, 1.2]) {
      const i = { type: "put" as const, spot: 98, strike: 105, tYears: 0.3, r: 0.045, q: 0.012 };
      const price = bsQuote({ ...i, sigma })!.price;
      expect(bsImpliedVol(i, price)!).toBeCloseTo(sigma, 5);
    }
  });

  it("returns null outside the no-arbitrage bounds", () => {
    const i = { type: "call" as const, spot: 100, strike: 100, tYears: 0.5, r: 0.05 };
    const { lo, hi } = bsBounds(i);
    expect(bsImpliedVol(i, Math.max(0.001, lo - 0.5))).toBeNull(); // below intrinsic bound (≤ lo)
    expect(bsImpliedVol(i, hi + 1)).toBeNull(); // above S
    expect(bsImpliedVol(i, 0)).toBeNull();
  });
});

describe("valueCurve", () => {
  it("value dominates payoff for a call before expiry, and both rise with spot", () => {
    const rows = valueCurve({ type: "call", spot: 100, strike: 100, tYears: 0.25, sigma: 0.25, r: 0.03 });
    expect(rows.length).toBeGreaterThan(50);
    for (const r of rows) expect(r.value).toBeGreaterThanOrEqual(r.payoff - 1e-9);
    expect(rows[rows.length - 1].value).toBeGreaterThan(rows[0].value);
    // payoff kink at the strike
    const atK = rows.reduce((p, c) => (Math.abs(c.spot - 100) < Math.abs(p.spot - 100) ? c : p));
    expect(atK.payoff).toBeCloseTo(0, 1);
  });
});
