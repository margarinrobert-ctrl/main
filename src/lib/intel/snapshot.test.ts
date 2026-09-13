import { describe, expect, it } from "vitest";
import type { OptionContract } from "../barchart/types";
import { buildSnapshot, mergeSnapshots, utcDay, type DaySnapshot } from "./snapshot";

function c(p: Partial<OptionContract>): OptionContract {
  return {
    symbol: "X", underlying: "X", type: "call", strike: 100, expiration: "2026-08-21", dte: 19,
    bid: 1, ask: 1.2, last: 1.1, volume: 100, openInterest: 1000, impliedVolatility: 0.2,
    delta: 0.5, gamma: 0.03, theta: -0.05, vega: 0.1, underlyingPrice: 100, ...p,
  };
}

const chain = (): OptionContract[] => [
  c({ type: "call", strike: 95, gamma: 0.02, delta: 0.8, openInterest: 2000 }),
  c({ type: "put", strike: 95, gamma: 0.02, delta: -0.2, openInterest: 5000 }),
  c({ type: "call", strike: 100, gamma: 0.05, delta: 0.5, openInterest: 3000 }),
  c({ type: "put", strike: 100, gamma: 0.05, delta: -0.5, openInterest: 4000 }),
  c({ type: "call", strike: 105, gamma: 0.02, delta: 0.2, openInterest: 1500 }),
];

const T = new Date("2026-08-01T19:30:00Z").getTime();

describe("buildSnapshot", () => {
  it("captures per-strike GEX/DEX/OI plus the day's headline metrics", () => {
    const s = buildSnapshot(chain(), 100, T)!;
    expect(s).not.toBeNull();
    expect(s.day).toBe("2026-08-01");
    expect(s.t).toBe(T);
    expect(s.spot).toBe(100);
    expect(s.strikes.map((x) => x.k)).toEqual([95, 100, 105]);
    // OI is split call/put per strike
    const k95 = s.strikes.find((x) => x.k === 95)!;
    expect(k95.co).toBe(2000);
    expect(k95.po).toBe(5000);
    // net aggregates present
    expect(s.gex).not.toBeNull();
    expect(s.dex).not.toBeNull();
    expect(typeof s.strikes[0].g).toBe("number");
    expect(typeof s.strikes[0].d).toBe("number");
  });

  it("returns null without a usable chain/spot", () => {
    expect(buildSnapshot([], 100, T)).toBeNull();
    expect(buildSnapshot(chain(), null, T)).toBeNull();
    expect(buildSnapshot(chain(), 0, T)).toBeNull();
  });

  it("keys the day in UTC", () => {
    expect(utcDay(new Date("2026-08-01T23:59:00Z").getTime())).toBe("2026-08-01");
    expect(utcDay(new Date("2026-08-02T00:01:00Z").getTime())).toBe("2026-08-02");
  });
});

describe("mergeSnapshots", () => {
  const snap = (day: string, t: number, spot: number): DaySnapshot => ({ day, t, spot, gex: 1, dex: 1, flip: 1, iv: 0.2, pcr: 1, strikes: [] });

  it("keeps one entry per day, latest write of the day winning", () => {
    const prev = [snap("2026-08-01", 10, 100)];
    const out = mergeSnapshots(prev, snap("2026-08-01", 20, 105));
    expect(out.length).toBe(1);
    expect(out[0].spot).toBe(105); // later snapshot replaced the earlier one
  });

  it("never rewinds a day with an out-of-order (older) write", () => {
    const prev = [snap("2026-08-01", 20, 105)];
    const out = mergeSnapshots(prev, snap("2026-08-01", 10, 100));
    expect(out[0].spot).toBe(105);
  });

  it("accumulates distinct days, sorted, and caps to the most recent", () => {
    let acc: DaySnapshot[] = [];
    for (let i = 1; i <= 5; i++) acc = mergeSnapshots(acc, snap(`2026-08-0${i}`, i, 100 + i), 3);
    expect(acc.map((s) => s.day)).toEqual(["2026-08-03", "2026-08-04", "2026-08-05"]);
  });

  it("passes prev through unchanged when there's nothing new", () => {
    const prev = [snap("2026-08-01", 10, 100)];
    expect(mergeSnapshots(prev, null)).toEqual(prev);
  });
});
