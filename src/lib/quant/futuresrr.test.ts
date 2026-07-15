import { describe, expect, it } from "vitest";
import { computeTradeRR, FUTURES, normCdf, pointValue, roundToTick, type RRInput } from "./futuresrr";

const ES = { tickSize: 0.25, tickValue: 12.5 }; // $50 / point

function base(p: Partial<RRInput> = {}): RRInput {
  return { side: "long", entry: 5000, stop: 4990, target: 5020, ...ES, ...p };
}

describe("normCdf", () => {
  it("matches known standard-normal values", () => {
    expect(normCdf(0)).toBeCloseTo(0.5, 6);
    expect(normCdf(1.96)).toBeCloseTo(0.975, 3);
    expect(normCdf(-1.96)).toBeCloseTo(0.025, 3);
    expect(normCdf(1000)).toBe(1);
    expect(normCdf(-1000)).toBeCloseTo(0, 6);
  });
});

describe("contract economics", () => {
  it("point value = tickValue / tickSize", () => {
    expect(pointValue(ES)).toBe(50);
    expect(pointValue({ tickSize: 0.01, tickValue: 10 })).toBe(1000); // CL
  });
  it("every preset yields a sane, positive point multiplier", () => {
    for (const c of FUTURES) expect(pointValue(c)).toBeGreaterThan(0);
    expect(FUTURES.find((c) => c.symbol === "NQ")).toMatchObject({ tickSize: 0.25, tickValue: 5 });
  });
  it("rounds prices to the tick grid", () => {
    expect(roundToTick(5000.31, 0.25)).toBe(5000.25);
    expect(roundToTick(5000.4, 0.25)).toBe(5000.5);
  });
});

describe("computeTradeRR — validation", () => {
  it("rejects a long whose target/stop are on the wrong side", () => {
    expect(computeTradeRR(base({ target: 4990 })).valid).toBe(false);
    expect(computeTradeRR(base({ stop: 5010 })).valid).toBe(false);
  });
  it("rejects a short whose target/stop are on the wrong side", () => {
    const short = base({ side: "short", entry: 5000, target: 4980, stop: 5010 });
    expect(computeTradeRR(short).valid).toBe(true);
    expect(computeTradeRR({ ...short, target: 5020 }).valid).toBe(false);
    expect(computeTradeRR({ ...short, stop: 4990 }).valid).toBe(false);
  });
  it("rejects degenerate specs", () => {
    expect(computeTradeRR(base({ tickSize: 0 })).valid).toBe(false);
    expect(computeTradeRR(base({ tickValue: 0 })).valid).toBe(false);
    expect(computeTradeRR(base({ contracts: 0 })).valid).toBe(false);
    expect(computeTradeRR(base({ entry: Number.NaN })).valid).toBe(false);
  });
});

describe("computeTradeRR — R:R and dollar economics", () => {
  it("computes points, ticks, dollars and RR for a 2:1 long", () => {
    const r = computeTradeRR(base()); // risk 10pt, reward 20pt
    expect(r.riskPoints).toBe(10);
    expect(r.rewardPoints).toBe(20);
    expect(r.riskTicks).toBe(40);
    expect(r.rewardTicks).toBe(80);
    expect(r.pointValue).toBe(50);
    expect(r.grossRR).toBe(2);
    // no costs → net == gross
    expect(r.riskDollars).toBe(10 * 50);
    expect(r.rewardDollars).toBe(20 * 50);
    expect(r.netRR).toBe(2);
  });

  it("scales dollars by contract count", () => {
    const r = computeTradeRR(base({ contracts: 3 }));
    expect(r.riskDollars).toBe(10 * 50 * 3);
    expect(r.rewardDollars).toBe(20 * 50 * 3);
  });

  it("costs erode net reward, inflate net risk and lift the break-even", () => {
    const free = computeTradeRR(base());
    const withCost = computeTradeRR(base({ costPerContract: 5, slippageTicks: 1 }));
    // friction = 5 + 2*1*12.5 = 30 per contract
    expect(withCost.costTotal).toBe(30);
    expect(withCost.rewardDollars).toBe(1000 - 30);
    expect(withCost.riskDollars).toBe(500 + 30);
    expect(withCost.netRR).toBeLessThan(free.netRR);
    expect(withCost.breakevenWinRate).toBeGreaterThan(free.breakevenWinRate);
  });
});

describe("computeTradeRR — the fair (driftless) probability", () => {
  it("P(target first) = risk / (risk + reward)", () => {
    const r = computeTradeRR(base()); // 10 risk, 20 reward
    expect(r.pTargetDriftless).toBeCloseTo(10 / 30, 12);
  });

  it("is symmetric with the gross break-even — R:R alone is a zero-edge fair game", () => {
    for (const target of [5010, 5020, 5050, 5005]) {
      const r = computeTradeRR(base({ target }));
      // with no costs the fair hit-rate equals the break-even hit-rate exactly
      const grossBreakeven = r.riskPoints / (r.riskPoints + r.rewardPoints);
      expect(r.pTargetDriftless).toBeCloseTo(grossBreakeven, 12);
      // and driftless expectancy is ~0
      const free = computeTradeRR(base({ target }));
      expect(free.expectancyDollars).toBeCloseTo(0, 6);
      expect(free.verdict).toBe("fair");
    }
  });

  it("a 1:1 bracket is a coin flip", () => {
    const r = computeTradeRR(base({ target: 5010, stop: 4990 }));
    expect(r.pTargetDriftless).toBeCloseTo(0.5, 12);
    expect(r.breakevenWinRate).toBeCloseTo(0.5, 12);
  });

  it("stretching the target lowers the fair hit-rate one-for-one", () => {
    const rr2 = computeTradeRR(base({ target: 5020 })); // 2:1
    const rr4 = computeTradeRR(base({ target: 5040 })); // 4:1
    expect(rr4.pTargetDriftless).toBeLessThan(rr2.pTargetDriftless);
    expect(rr4.pTargetDriftless).toBeCloseTo(10 / 50, 12);
  });
});

describe("computeTradeRR — drift-adjusted probability", () => {
  it("with zero drift the drift model reproduces the driftless probability", () => {
    const r = computeTradeRR(base({ horizonSigma: 15, horizonDrift: 0 }));
    expect(r.pTargetDrift).not.toBeNull();
    expect(r.pTargetDrift as number).toBeCloseTo(r.pTargetDriftless, 6);
    // zero drift is not "meaningful" → expectancy still uses the driftless probability
    expect(r.winProbSource).toBe("driftless");
  });

  it("favourable drift raises P(target first) for a long", () => {
    const flat = computeTradeRR(base({ target: 5010, stop: 4990, horizonSigma: 15, horizonDrift: 0 }));
    const up = computeTradeRR(base({ target: 5010, stop: 4990, horizonSigma: 15, horizonDrift: 6 }));
    expect(up.pTargetDrift as number).toBeGreaterThan(flat.pTargetDrift as number);
    expect(up.pTargetDrift as number).toBeGreaterThan(0.5); // up drift on a symmetric bracket
    expect(up.winProbSource).toBe("drift");
  });

  it("the same up-drift HURTS a short (favourable frame flips)", () => {
    const short = base({ side: "short", entry: 5000, target: 4990, stop: 5010, horizonSigma: 15, horizonDrift: 6 });
    const r = computeTradeRR(short);
    expect(r.pTargetDrift as number).toBeLessThan(0.5);
  });

  it("stays in [0,1] under extreme drift/vol", () => {
    for (const d of [-500, -50, 50, 500]) {
      const r = computeTradeRR(base({ horizonSigma: 0.5, horizonDrift: d }));
      const p = r.pTargetDrift as number;
      expect(p).toBeGreaterThanOrEqual(0);
      expect(p).toBeLessThanOrEqual(1);
      expect(Number.isFinite(p)).toBe(true);
    }
  });
});

describe("computeTradeRR — finite-horizon touch odds", () => {
  it("are null without a volatility input, present with one", () => {
    expect(computeTradeRR(base()).pTouchTarget).toBeNull();
    const r = computeTradeRR(base({ horizonSigma: 15 }));
    expect(r.pTouchTarget).not.toBeNull();
    expect(r.pTouchStop).not.toBeNull();
    expect(r.pCloseBeyondTarget).not.toBeNull();
  });

  it("touching a barrier is at least as likely as closing beyond it", () => {
    const r = computeTradeRR(base({ horizonSigma: 15 }));
    expect(r.pTouchTarget as number).toBeGreaterThanOrEqual(r.pCloseBeyondTarget as number);
  });

  it("the nearer barrier (stop) is touched more often than the farther (target)", () => {
    const r = computeTradeRR(base({ horizonSigma: 15 })); // stop 10pt away, target 20pt away
    expect(r.pTouchStop as number).toBeGreaterThan(r.pTouchTarget as number);
  });

  it("more volatility raises the odds of reaching the target", () => {
    const lo = computeTradeRR(base({ horizonSigma: 5 }));
    const hi = computeTradeRR(base({ horizonSigma: 25 }));
    expect(hi.pTouchTarget as number).toBeGreaterThan(lo.pTouchTarget as number);
  });
});

describe("computeTradeRR — expectancy, edge, Kelly, verdict", () => {
  it("an assumed win-rate above break-even yields positive expectancy and a Kelly stake", () => {
    const r = computeTradeRR(base({ assumedWinRate: 0.5 })); // 2:1, need only 33% to break even
    expect(r.winProbSource).toBe("assumed");
    expect(r.edge).toBeCloseTo(0.5 - 1 / 3, 6);
    expect(r.expectancyDollars).toBeGreaterThan(0);
    expect(r.verdict).toBe("positive");
    expect(r.kelly).toBeGreaterThan(0);
    // Kelly on 2:1 net odds at p=0.5:  p − q/b = 0.5 − 0.5/2 = 0.25
    expect(r.kelly).toBeCloseTo(0.25, 6);
  });

  it("an assumed win-rate below break-even is a negative-expectancy trade", () => {
    const r = computeTradeRR(base({ assumedWinRate: 0.25 })); // below the 33% break-even
    expect(r.expectancyDollars).toBeLessThan(0);
    expect(r.verdict).toBe("negative");
    expect(r.kelly).toBe(0);
  });

  it("expectancy in dollars and in R agree (1R = net risk)", () => {
    const r = computeTradeRR(base({ assumedWinRate: 0.45 }));
    expect(r.expectancyDollars).toBeCloseTo(r.expectancyR * r.riskDollars, 6);
  });

  it("costs alone push a fair bracket negative", () => {
    const r = computeTradeRR(base({ costPerContract: 20, slippageTicks: 1 }));
    // no directional edge, but friction makes the driftless game a loser
    expect(r.winProbSource).toBe("driftless");
    expect(r.expectancyDollars).toBeLessThan(0);
    expect(r.verdict).toBe("negative");
  });
});
