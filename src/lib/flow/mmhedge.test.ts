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
    expect(r.trade?.target).toBe(110);
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
    expect(r.trade?.target).toBe(90);
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
