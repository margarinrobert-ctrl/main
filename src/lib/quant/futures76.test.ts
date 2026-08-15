import { describe, expect, it } from "vitest";
import { bsQuote } from "./bs";
import { black76, evalSetup, gridLevels, probNoTouchBand, probTouch, sessionSigma } from "./futures76";

describe("black76 — the futures conversion of Black-Scholes", () => {
  it("equals BSM when the future is the forward: F = S·e^{(r−q)T}", () => {
    const S = 5000, K = 5050, T = 0.25, sigma = 0.18, r = 0.05, q = 0.015;
    const F = S * Math.exp((r - q) * T);
    for (const type of ["call", "put"] as const) {
      const bsm = bsQuote({ type, spot: S, strike: K, tYears: T, sigma, r, q })!.price;
      const b76 = black76({ type, fut: F, strike: K, tYears: T, sigma, r })!.price;
      expect(b76).toBeCloseTo(bsm, 8);
    }
  });

  it("satisfies futures put-call parity: C − P = e^{−rT}(F − K)", () => {
    const i = { fut: 21000, strike: 20800, tYears: 0.1, sigma: 0.22, r: 0.04 };
    const c = black76({ ...i, type: "call" })!.price;
    const p = black76({ ...i, type: "put" })!.price;
    expect(c - p).toBeCloseTo(Math.exp(-0.04 * 0.1) * (21000 - 20800), 8);
  });

  it("ATM-forward call and put are equal (F = K), and greeks are sane", () => {
    const i = { fut: 21000, strike: 21000, tYears: 1 / 365, sigma: 0.2, r: 0 };
    const c = black76({ ...i, type: "call" })!;
    const p = black76({ ...i, type: "put" })!;
    expect(c.price).toBeCloseTo(p.price, 10);
    expect(c.delta).toBeGreaterThan(0);
    expect(p.delta).toBeLessThan(0);
    expect(c.gamma).toBeGreaterThan(0);
    expect(c.thetaDay).toBeLessThan(0);
  });

  it("rejects degenerate inputs", () => {
    expect(black76({ type: "call", fut: 0, strike: 100, tYears: 1, sigma: 0.2 })).toBeNull();
    expect(black76({ type: "call", fut: 100, strike: 100, tYears: 0, sigma: 0.2 })).toBeNull();
  });
});

describe("session vol & touch probability", () => {
  it("scales IV to the remaining slice of the session", () => {
    const full = sessionSigma(0.2, 1);
    expect(full).toBeCloseTo(0.2 / Math.sqrt(252), 10);
    expect(sessionSigma(0.2, 0.25)).toBeCloseTo(full * 0.5, 10); // √¼ = ½
    expect(sessionSigma(0.2, 0)).toBe(0);
  });

  it("probTouch: certain at the money, decays with distance, ~68% at 1σ", () => {
    const F = 21000;
    const sig = sessionSigma(0.2, 1); // ≈1.26% of price
    expect(probTouch(F, F, sig)).toBe(1);
    const near = probTouch(F, F * 1.005, sig);
    const far = probTouch(F, F * 1.03, sig);
    expect(near).toBeGreaterThan(far);
    // reflection principle: P(touch 1σ) = 2·N(−1) ≈ 0.317... for log-distance 1σ
    expect(probTouch(F, F * Math.exp(sig), sig)).toBeCloseTo(2 * 0.158655, 3);
  });

  it("probNoTouchBand: →1 for a wide band, →0 for a vanishing one", () => {
    expect(probNoTouchBand(0.5, 0.01)).toBeCloseTo(1, 6);
    expect(probNoTouchBand(0.0001, 0.05)).toBeLessThan(0.05);
    expect(probNoTouchBand(0.01, 0)).toBe(1); // no time left ⇒ cannot touch
  });
});

describe("evalSetup — the 1:1 bracket", () => {
  const F = 21000;
  const sig = sessionSigma(0.22, 1);

  it("EXACT 50% win rate at zero drift — the martingale null, for any level/risk/vol", () => {
    for (const level of [20800, 21000, 21240]) {
      for (const risk of [10, 40, 120]) {
        for (const side of ["long", "short"] as const) {
          const s = evalSetup(F, level, risk, sig, side)!;
          expect(s.winRate).toBeCloseTo(0.5, 12);
          expect(s.expR).toBeCloseTo(0, 12); // zero expected R before costs
        }
      }
    }
  });

  it("a supplied drift tilts the win rate in the traded direction, and long/short mirror", () => {
    const up = evalSetup(F, F, 40, sig, "long", 60)!;
    const dn = evalSetup(F, F, 40, sig, "short", 60)!;
    expect(up.winRate).toBeGreaterThan(0.5);
    expect(dn.winRate).toBeCloseTo(1 - up.winRate, 10);
    expect(up.expR).toBeGreaterThan(0);
    expect(dn.expR).toBeLessThan(0);
    // a downward drift flips it
    expect(evalSetup(F, F, 40, sig, "long", -60)!.winRate).toBeLessThan(0.5);
  });

  it("bracket geometry is correct for both sides", () => {
    const long = evalSetup(F, 20960, 40, sig, "long")!;
    expect(long.entry).toBe(20960);
    expect(long.target).toBe(21000);
    expect(long.stop).toBe(20920);
    const short = evalSetup(F, 20960, 40, sig, "short")!;
    expect(short.target).toBe(20920);
    expect(short.stop).toBe(21000);
    expect(long.risk).toBe(40);
  });

  it("far levels are less likely to fill, and outcome probabilities are a partition", () => {
    const near = evalSetup(F, F + 20, 40, sig, "long")!;
    const far = evalSetup(F, F + 900, 40, sig, "long")!;
    expect(far.probTouchLevel).toBeLessThan(near.probTouchLevel);
    for (const s of [near, far]) {
      expect(s.pWinSession + s.pLossSession + s.pUnresolved).toBeCloseTo(s.probTouchLevel, 10);
      expect(s.probResolve).toBeGreaterThanOrEqual(0);
      expect(s.probResolve).toBeLessThanOrEqual(1);
    }
  });

  it("less session time left ⇒ more brackets finish unresolved", () => {
    const early = evalSetup(F, F, 40, sessionSigma(0.22, 1), "long")!;
    const late = evalSetup(F, F, 40, sessionSigma(0.22, 0.05), "long")!;
    expect(late.probResolve).toBeLessThan(early.probResolve);
  });
});

describe("gridLevels", () => {
  it("builds a round-number ladder straddling price (NQ 40 / ES 10)", () => {
    const nq = gridLevels(21013, 40, 2); // nearest multiple of 40 is 21000
    expect(nq).toEqual([20920, 20960, 21000, 21040, 21080]);
    const es = gridLevels(5783, 10, 2);
    expect(es).toEqual([5760, 5770, 5780, 5790, 5800]);
    expect(gridLevels(0, 40)).toEqual([]);
  });
});
