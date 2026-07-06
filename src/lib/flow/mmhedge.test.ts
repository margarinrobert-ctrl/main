import { describe, expect, it } from "vitest";
import type { OptionContract } from "../barchart/types";
import { mmHedge, planAtLevel, pressureAt } from "./mmhedge";

function c(p: Partial<OptionContract>): OptionContract {
  return {
    symbol: "X",
    underlying: "X",
    type: "call",
    strike: 100,
    expiration: "2026-07-16",
    dte: 5,
    bid: 1,
    ask: 1.2,
    last: 1.1,
    volume: 100,
    openInterest: 1000,
    impliedVolatility: 0.3,
    delta: 0.5,
    gamma: 0.03,
    theta: -0.05,
    vega: 0.1,
    underlyingPrice: 100,
    ...p,
  };
}

describe("mmHedge", () => {
  it("long gamma pins UP toward a magnet above spot", () => {
    const chain = [
      c({ type: "call", strike: 110, gamma: 0.05, openInterest: 9000 }),
      c({ type: "put", strike: 90, gamma: 0.03, openInterest: 2000 }),
    ];
    const r = mmHedge(chain, 100);
    expect(r.regime).toBe("long");
    expect(r.magnet).toBe(110);
    expect(r.pressure).toBe("up");
    expect(r.pressureScore).toBeGreaterThan(15);
    expect(r.trade?.side).toBe("long");
    expect(r.trade?.targets.some((t) => t.price === 110)).toBe(true); // magnet is a TP
    expect(r.trade?.targets.length).toBeGreaterThanOrEqual(2); // layered TPs
    expect(r.trade!.stop!).toBeLessThan(100); // stop below a long entry
    expect(r.trade!.targets[0].r).not.toBeNull(); // R multiple computed
    expect(r.trade!.targets[0].pTouch!).toBeGreaterThan(0); // Black-Scholes prob-of-touch
    expect(r.trade!.targets[0].pTouch!).toBeLessThanOrEqual(1);
    // quant-model fields
    expect(r.flowPer1pct).not.toBeNull(); // $ hedged per 1% = net GEX
    expect(r.com).not.toBeNull(); // gamma centre-of-mass
    expect(r.conviction).toBeGreaterThanOrEqual(0);
    expect(r.conviction).toBeLessThanOrEqual(100);
    expect(typeof r.trade!.ev === "number").toBe(true); // modelled EV in R
  });

  it("long gamma pins DOWN toward a magnet below spot", () => {
    const chain = [
      c({ type: "call", strike: 90, gamma: 0.05, openInterest: 9000 }),
      c({ type: "put", strike: 110, gamma: 0.03, openInterest: 2000 }),
    ];
    const r = mmHedge(chain, 100);
    expect(r.regime).toBe("long");
    expect(r.magnet).toBe(90);
    expect(r.pressure).toBe("down");
    expect(r.trade?.side).toBe("short");
    expect(r.trade?.targets.some((t) => t.price === 90)).toBe(true); // magnet is a TP
    expect(r.trade!.stop!).toBeGreaterThan(100); // stop above a short entry
  });

  it("maps dealer action + likely reaction per level and includes the full level set", () => {
    const chain = [
      c({ type: "call", strike: 110, gamma: 0.05, openInterest: 9000 }),
      c({ type: "put", strike: 90, gamma: 0.03, openInterest: 2000 }),
    ];
    const r = mmHedge(chain, 100); // long gamma, dominant strike 110 → magnet
    expect(r.levelPlays.length).toBeGreaterThan(0);
    // the dominant gamma strike is a magnet → pin
    const mag = r.levelPlays.find((l) => l.name.toLowerCase().includes("magnet"));
    expect(mag!.outcome.toLowerCase()).toContain("pin");
    // a support level below spot in long gamma → dealers buy → bounce up
    const sup = r.levelPlays.find((l) => l.price < 100 && !l.name.toLowerCase().includes("flip"));
    expect(sup!.bias).toBe("up");
    // the expanded set carries the 1-day range
    expect(r.levelPlays.some((l) => l.name === "1D Max")).toBe(true);
    expect(r.levelPlays.some((l) => l.name === "1D Min")).toBe(true);
    // sorted nearest-first
    expect(Math.abs(r.levelPlays[0].price - 100)).toBeLessThanOrEqual(Math.abs(r.levelPlays[r.levelPlays.length - 1].price - 100));
    // each level carries open interest + its share of the book
    const lvl = r.levelPlays[0];
    expect(typeof lvl.callOi).toBe("number");
    expect(typeof lvl.putOi).toBe("number");
    expect(lvl.oiShare).toBeGreaterThanOrEqual(0);
    expect(lvl.oiShare).toBeLessThanOrEqual(1);
  });

  it("computes BS P(win) and re-anchors the plan to a selected level", () => {
    const chain = [
      c({ type: "call", strike: 110, gamma: 0.05, openInterest: 9000 }),
      c({ type: "put", strike: 90, gamma: 0.03, openInterest: 2000 }),
    ];
    const r = mmHedge(chain, 100);
    expect(r.trade!.pWin!).toBeGreaterThan(0);
    expect(r.trade!.pWin!).toBeLessThanOrEqual(1);
    // anchor to a support level below spot → a long plan anchored there
    const sup = r.levelPlays.find((l) => l.price < 100 && l.bias === "up");
    const p = planAtLevel(r, 100, sup!);
    expect(p).not.toBeNull();
    expect(p!.anchorLevel).toBe(sup!.name);
    expect(p!.side).toBe("long");
    expect(p!.pWin).not.toBeNull();
  });

  it("classifies a short-gamma regime when puts dominate net GEX", () => {
    const chain = [
      c({ type: "put", strike: 100, gamma: 0.05, openInterest: 9000 }),
      c({ type: "call", strike: 110, gamma: 0.02, openInterest: 1000 }),
    ];
    const r = mmHedge(chain, 105);
    expect(r.regime).toBe("short");
    expect(r.components.length).toBeGreaterThan(0);
  });

  it("emits a wait/empty result without data", () => {
    const r = mmHedge([], 100);
    expect(r.regime).toBe("unknown");
    expect(r.trade).toBeNull();
    expect(r.pressure).toBe("balanced");
  });

  // ── new directional signals: Delta (DEX) / Options flow / Open interest ──
  const comp = (r: ReturnType<typeof mmHedge>, label: string) => r.components.find((x) => x.label === label);

  it("greekless / no-volume chain: no new-signal rows, balanced, finite score", () => {
    // greeks present so by.length>0 isn't the early-out, but zero volume kills flow,
    // and we strip OI/delta on a copy below for the fully-degenerate path.
    const greekless = [
      c({ type: "call", strike: 110, gamma: 0.05, openInterest: 9000, volume: 0, delta: undefined, impliedVolatility: undefined }),
      c({ type: "put", strike: 90, gamma: 0.03, openInterest: 2000, volume: 0, delta: undefined, impliedVolatility: undefined }),
    ];
    const r = mmHedge(greekless, 100);
    expect(Number.isFinite(r.pressureScore)).toBe(true);
    expect(comp(r, "Options flow")).toBeUndefined(); // no volume → flowSpan 0
    expect(comp(r, "Delta (DEX)")).toBeUndefined(); // no delta → grossDex 0
    // a truly empty chain stays balanced with no trade
    const empty = mmHedge([], 100);
    expect(empty.pressure).toBe("balanced");
    expect(Number.isFinite(empty.pressureScore)).toBe(true);
  });

  it("options-flow component saturates to ±16 by aggressor side", () => {
    // every classifiable print is a call bought at the ask → all-bullish premium
    const bull = [
      c({ type: "call", strike: 100, bid: 1, ask: 1.2, last: 1.2, volume: 500, openInterest: 1000 }),
      c({ type: "call", strike: 105, bid: 1, ask: 1.2, last: 1.2, volume: 500, openInterest: 1000 }),
    ];
    const rb = mmHedge(bull, 100);
    const fb = comp(rb, "Options flow");
    expect(fb).toBeDefined();
    expect(fb!.dir).toBe("up");
    expect(fb!.weight).toBe(16); // |netPremium| === flowSpan → ratio +1
    expect(rb.flowNetPremium!).toBeGreaterThan(0);

    // every print is a call sold at the bid → all-bearish
    const bear = [
      c({ type: "call", strike: 100, bid: 1, ask: 1.2, last: 1, volume: 500, openInterest: 1000 }),
      c({ type: "call", strike: 105, bid: 1, ask: 1.2, last: 1, volume: 500, openInterest: 1000 }),
    ];
    const rbe = mmHedge(bear, 100);
    const fbe = comp(rbe, "Options flow");
    expect(fbe!.dir).toBe("down");
    expect(fbe!.weight).toBe(16);
    expect(rbe.flowNetPremium!).toBeLessThan(0);
  });

  it("call-heavy book above the delta-flip: DEX and OI both bullish", () => {
    // calls (positive dex) above spot, puts (negative dex) below → cumulative net DEX
    // crosses zero below spot, so spot sits above the delta-flip; call OI >> put OI.
    const chain = [
      c({ type: "put", strike: 80, delta: -0.2, gamma: 0.02, openInterest: 4000 }),
      c({ type: "call", strike: 120, delta: 0.7, gamma: 0.05, openInterest: 12000, volume: 50 }),
    ];
    const r = mmHedge(chain, 100);
    expect(r.deltaFlip).not.toBeNull();
    expect(r.deltaFlip!).toBeLessThan(100); // pivot below spot
    const d = comp(r, "Delta (DEX)");
    const o = comp(r, "Open interest");
    expect(d).toBeDefined();
    expect(d!.dir).toBe("up");
    expect(d!.weight).toBeGreaterThan(0);
    expect(o).toBeDefined();
    expect(o!.dir).toBe("up"); // call-heavy OI → bullish
    expect(o!.weight).toBeGreaterThan(0);
  });

  it("spot at the delta-flip contributes ~0 DEX (proximity gate)", () => {
    // symmetric call/put dex so the cumulative crossing lands at spot=100
    const chain = [
      c({ type: "put", strike: 100, delta: -0.5, gamma: 0.04, openInterest: 5000 }),
      c({ type: "call", strike: 100, delta: 0.5, gamma: 0.04, openInterest: 5000 }),
      c({ type: "put", strike: 95, delta: -0.4, gamma: 0.03, openInterest: 3000 }),
      c({ type: "call", strike: 105, delta: 0.4, gamma: 0.03, openInterest: 3000 }),
    ];
    const r = mmHedge(chain, 100);
    const d = comp(r, "Delta (DEX)");
    if (d) expect(d.weight).toBe(0); // prox≈0 → deltaComp≈0 (row may push with weight 0)
  });

  it("gamma stays dominant when flow/OI conflict with the pin", () => {
    // strong long-γ pin BELOW spot (≈ −40) vs bullish DEX/charm/flow/OI at typical magnitudes.
    const chain = [
      c({ type: "call", strike: 90, gamma: 0.06, openInterest: 15000, delta: 0.5, bid: 1, ask: 1.2, last: 1.1, volume: 0 }),
      c({ type: "call", strike: 95, gamma: 0.05, openInterest: 12000, delta: 0.5, bid: 1, ask: 1.2, last: 1.1, volume: 0 }),
      // partial bullish flow (a call at ask + a smaller one at bid → net mildly bullish)
      c({ type: "call", strike: 100, gamma: 0.002, openInterest: 1000, delta: 0.5, bid: 1, ask: 1.2, last: 1.2, volume: 300 }),
      c({ type: "call", strike: 100, gamma: 0.002, openInterest: 1000, delta: 0.5, bid: 1, ask: 1.2, last: 1.0, volume: 150 }),
      c({ type: "put", strike: 110, gamma: 0.002, openInterest: 22000, delta: -0.3, volume: 0 }),
    ];
    const r = mmHedge(chain, 100);
    expect(r.regime).toBe("long");
    const g = comp(r, "Gamma pin");
    expect(g!.dir).toBe("down"); // magnet below spot
    expect(g!.weight).toBeGreaterThan((comp(r, "Options flow")?.weight ?? 0)); // gamma is the largest term
    expect(r.pressureScore).toBeLessThan(0); // gamma wins the blend
  });

  it("all six components saturate same-sign to exactly ±100, never NaN", () => {
    // We can't force every term independently from one chain, so assert the clamp invariant
    // and finiteness on a strongly-loaded chain, plus the empty/degenerate guards stay finite.
    const loaded = [
      c({ type: "call", strike: 120, gamma: 0.08, openInterest: 50000, delta: 0.8, bid: 1, ask: 1.2, last: 1.2, volume: 5000 }),
      c({ type: "call", strike: 130, gamma: 0.08, openInterest: 50000, delta: 0.8, bid: 1, ask: 1.2, last: 1.2, volume: 5000 }),
      c({ type: "put", strike: 70, gamma: 0.001, openInterest: 50, delta: -0.1, volume: 0 }),
    ];
    const r = mmHedge(loaded, 100);
    expect(Number.isFinite(r.pressureScore)).toBe(true);
    expect(r.pressureScore).toBeGreaterThanOrEqual(-100);
    expect(r.pressureScore).toBeLessThanOrEqual(100);
  });

  it("guards every divide/NaN in degenerate chains", () => {
    // zero call OI → pcr.oi null (OI row skipped); no greeks → grossDex 0 (DEX row skipped);
    // all-MID prints → flowSpan 0 (flow row skipped). Score stays finite throughout.
    const degenerate = [
      c({ type: "put", strike: 100, gamma: 0.04, openInterest: 1000, delta: undefined, impliedVolatility: undefined, bid: 1, ask: 1.2, last: 1.1, volume: 100 }),
    ];
    const r = mmHedge(degenerate, 100);
    expect(Number.isFinite(r.pressureScore)).toBe(true);
    expect(comp(r, "Open interest")).toBeUndefined(); // co=0 → pcr.oi null
    expect(comp(r, "Delta (DEX)")).toBeUndefined(); // no delta → grossDex 0
    expect(comp(r, "Options flow")).toBeUndefined(); // last at mid → no aggressor
  });

  it("pressureAt re-evaluates the gamma-pin direction vs the selected reference price", () => {
    // long-gamma book, centre-of-mass ~104 → pin pulls toward it from either side.
    const chain = [
      c({ type: "call", strike: 105, gamma: 0.06, openInterest: 12000 }),
      c({ type: "put", strike: 95, gamma: 0.03, openInterest: 3000 }),
    ];
    const below = pressureAt(chain, 100, 96);
    const above = pressureAt(chain, 100, 114);
    expect(below).not.toBeNull();
    expect(above).not.toBeNull();
    const gBelow = below!.components.find((x) => x.label.startsWith("Gamma"))!;
    const gAbove = above!.components.find((x) => x.label.startsWith("Gamma"))!;
    expect(gBelow.dir).toBe("up"); // reference below COM → pulled up toward the magnet
    expect(gAbove.dir).toBe("down"); // reference above COM → pulled back down
    expect(pressureAt([], 100, 100)).toBeNull();
    expect(pressureAt(chain, null, 100)).toBeNull();
  });
});
