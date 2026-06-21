import { describe, expect, it } from "vitest";
import type { OptionContract } from "../barchart/types";
import { mmHedge } from "./mmhedge";

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
});
