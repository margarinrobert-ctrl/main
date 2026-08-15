import { describe, expect, it } from "vitest";
import { buildFuturesPine } from "./futuresPine";

describe("buildFuturesPine", () => {
  it("emits a v6 indicator for NQ1! with a 40-point 1:1 grid", () => {
    const r = buildFuturesPine({ contract: "NQ1!", step: 40, ivPct: 22.4, proxy: "QQQ" });
    expect(r.code).toContain("//@version=6");
    expect(r.code).toContain('indicator("OptionsFlow 0DTE 1:1 • NQ1!"');
    expect(r.code).toContain('input.float(40, "Level spacing / bracket size R (pts)"');
    expect(r.code).toContain('input.float(22.4, "Annualized IV (%)"');
    expect(r.code).toContain("step * 20"); // NQ $20/pt in the risk tooltip
    expect(r.contract).toBe("NQ1!");
    expect(r.step).toBe(40);
  });

  it("emits a separate ES1! script with a 10-point grid and $50/pt", () => {
    const r = buildFuturesPine({ contract: "ES1!", step: 10, ivPct: 16.1, proxy: "SPY" });
    expect(r.code).toContain('indicator("OptionsFlow 0DTE 1:1 • ES1!"');
    expect(r.code).toContain('input.float(10, "Level spacing / bracket size R (pts)"');
    expect(r.code).toContain("step * 50"); // ES $50/pt
    expect(r.code).not.toContain("NQ1!");
  });

  it("states the Black-76 futures conversion and the exact-50% martingale result", () => {
    const r = buildFuturesPine({ contract: "NQ1!", step: 40, ivPct: 20, proxy: "QQQ" });
    expect(r.code).toContain("Black-76");
    expect(r.code).toContain("MARTINGALE");
    expect(r.code).toContain("p = 1/2 EXACTLY");
    expect(r.code).toContain("NO"); // "NO edge from geometry"
    expect(r.code).toContain("martingale null");
  });

  it("computes probabilities live in Pine (not baked): touch, no-touch band, drift tilt", () => {
    const r = buildFuturesPine({ contract: "ES1!", step: 10, ivPct: 18, proxy: "SPY" });
    expect(r.code).toContain("pTouch(lvl)");
    expect(r.code).toContain("pNoTouchBand(h)");
    expect(r.code).toContain("pUpFirst(h)");
    expect(r.code).toContain("ncdf(x)"); // normal CDF implemented in-script
    expect(r.code).toContain("2.0 * ncdf(-math.abs(math.log(lvl / close)) / sigRem)"); // reflection principle
    expect(r.code).toContain("(math.exp(theta * h) - 1.0)"); // corrected scale function
    expect(r.code).toContain("sigDay   = ivUse / math.sqrt(252)");
  });

  it("is 0DTE-scoped: session clock, time-decayed vol, and a fill-weighted best setup", () => {
    const r = buildFuturesPine({ contract: "NQ1!", step: 40, ivPct: 20, proxy: "QQQ" });
    expect(r.code).toContain("0DTE clock");
    expect(r.code).toContain("fracLeft");
    expect(r.code).toContain("math.sqrt(math.max(fracLeft, 0.0001))");
    expect(r.code).toContain("input.session(");
    expect(r.code).toContain("BEST ");
    expect(r.code).toContain("score = pt * expR");
  });

  it("guarantees at least 10 marked levels regardless of touch probability", () => {
    const r = buildFuturesPine({ contract: "NQ1!", step: 40, ivPct: 20, proxy: "QQQ" });
    expect(r.code).toContain('input.int(10, "Always mark at least N levels"');
    expect(r.code).toContain("distCut"); // Nth-nearest distance threshold
    expect(r.code).toContain("keep = math.abs(lvl - close) <= distCut + 0.0001 or pt * 100 >= minTouch");
    expect(r.code).toContain("array.sort(dists, order.ascending)");
    // grid is wide enough to satisfy the floor: 8 each side = 17 levels
    expect(r.code).toContain('input.int(8, "Levels each side"');
  });

  it("defaults the drift to zero so the honest 50% baseline is what ships", () => {
    const r = buildFuturesPine({ contract: "ES1!", step: 10, ivPct: 15, proxy: "SPY" });
    expect(r.code).toContain('input.float(0.0, "Session drift (pts, your bias)"');
    expect(r.code).toContain("drift 0 => win rate 50%");
  });

  it("falls back to a 20% vol seed when no IV is available", () => {
    const r = buildFuturesPine({ contract: "NQ1!", step: 40, ivPct: null, proxy: "QQQ" });
    expect(r.code).toContain('input.float(20, "Annualized IV (%)"');
    expect(r.ivPct).toBeNull();
  });
});
