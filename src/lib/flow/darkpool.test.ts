import { describe, expect, it } from "vitest";
import { darkPoolLevels, darkPoolStats, type DarkPoolDay } from "./darkpool";

function day(date: string, short: number, total: number, consolidated: number | null = null): DarkPoolDay {
  return { date, shortVolume: short, shortExemptVolume: 0, offExchangeVolume: total, consolidatedVolume: consolidated };
}

function priced(date: string, off: number, low: number, high: number): DarkPoolDay {
  return { date, shortVolume: off / 2, shortExemptVolume: 0, offExchangeVolume: off, consolidatedVolume: null, low, high, close: (low + high) / 2, open: (low + high) / 2 };
}

describe("darkPoolStats", () => {
  it("returns an unavailable result for an empty series", () => {
    const s = darkPoolStats([]);
    expect(s.available).toBe(false);
    expect(s.dpr).toBeNull();
    expect(s.series).toHaveLength(0);
  });

  it("computes the dark-pool ratio and off-exchange % for the latest day", () => {
    const s = darkPoolStats([
      day("2026-06-17", 40, 100, 250),
      day("2026-06-18", 45, 100, 200),
      day("2026-06-19", 60, 100, 200), // latest: DPR 0.6, off-exch 50%
    ]);
    expect(s.available).toBe(true);
    expect(s.days).toBe(3);
    expect(s.dpr).toBeCloseTo(0.6, 6);
    expect(s.offExchPct).toBeCloseTo(0.5, 6);
    expect(s.latest?.date).toBe("2026-06-19");
  });

  it("sorts by date and reads the most recent day as latest regardless of input order", () => {
    const s = darkPoolStats([day("2026-06-19", 60, 100), day("2026-06-17", 40, 100), day("2026-06-18", 50, 100)]);
    expect(s.series.map((p) => p.date)).toEqual(["2026-06-17", "2026-06-18", "2026-06-19"]);
    expect(s.dpr).toBeCloseTo(0.6, 6);
  });

  it("flags an elevated dark-pool short ratio as accumulation (DIX thesis) via the z-score", () => {
    // a flat ~0.40 baseline, then a spike to 0.65 → high positive z → accumulation
    const rows = [
      ...["2026-06-10", "2026-06-11", "2026-06-12", "2026-06-15", "2026-06-16"].map((d) => day(d, 40, 100)),
      day("2026-06-17", 65, 100),
    ];
    const s = darkPoolStats(rows);
    expect(s.dprZ!).toBeGreaterThan(0.5);
    expect(s.bias).toBe("accumulation");
    expect(s.dprPctile).toBeCloseTo(1, 6); // latest is the highest in the window
  });

  it("flags a depressed ratio as distribution", () => {
    const rows = [
      ...["2026-06-10", "2026-06-11", "2026-06-12", "2026-06-15", "2026-06-16"].map((d) => day(d, 50, 100)),
      day("2026-06-17", 30, 100),
    ];
    const s = darkPoolStats(rows);
    expect(s.dprZ!).toBeLessThan(-0.5);
    expect(s.bias).toBe("distribution");
  });

  it("detects a rising off-exchange-ratio trend", () => {
    const rows = ["2026-06-10", "2026-06-11", "2026-06-12", "2026-06-15", "2026-06-16"].map((d, i) => day(d, 35 + i * 4, 100));
    const s = darkPoolStats(rows);
    expect(s.trend).toBe("rising");
  });

  it("leaves off-exchange % null when consolidated volume is unknown", () => {
    const s = darkPoolStats([day("2026-06-18", 40, 100, null), day("2026-06-19", 50, 100, null)]);
    expect(s.offExchPct).toBeNull();
    expect(s.offExchPctAvg).toBeNull();
    expect(s.dpr).toBeCloseTo(0.5, 6);
  });

  it("ignores days with zero off-exchange volume", () => {
    const s = darkPoolStats([day("2026-06-18", 0, 0), day("2026-06-19", 50, 100)]);
    expect(s.days).toBe(1);
    expect(s.dpr).toBeCloseTo(0.5, 6);
  });
});

describe("darkPoolLevels", () => {
  it("is unavailable without priced days", () => {
    expect(darkPoolLevels([]).available).toBe(false);
    expect(darkPoolLevels([day("2026-06-19", 50, 100)]).available).toBe(false); // no OHLC
  });

  it("puts the point-of-control where the most off-exchange volume traded", () => {
    // heavy dark volume clustered around 100, lighter wings at 95 and 105
    const p = darkPoolLevels([
      priced("2026-06-15", 10_000_000, 99, 101),
      priced("2026-06-16", 10_000_000, 99.5, 100.5),
      priced("2026-06-17", 2_000_000, 104, 106),
      priced("2026-06-18", 2_000_000, 94, 96),
    ]);
    expect(p.available).toBe(true);
    expect(p.poc!).toBeGreaterThan(99);
    expect(p.poc!).toBeLessThan(101);
    expect(p.priceLo!).toBeCloseTo(94, 6);
    expect(p.priceHi!).toBeCloseTo(106, 6);
    // value area brackets the POC and stays within the traded range
    expect(p.val!).toBeLessThanOrEqual(p.poc!);
    expect(p.vah!).toBeGreaterThanOrEqual(p.poc!);
    expect(p.val!).toBeGreaterThanOrEqual(94);
    expect(p.vah!).toBeLessThanOrEqual(106);
    // heaviest level is rank 1, near the POC, and ranks are volume-ordered
    expect(p.levels[0].rank).toBe(1);
    expect(Math.abs(p.levels[0].price - 100)).toBeLessThan(2);
    expect(p.levels[0].volume).toBeGreaterThanOrEqual(p.levels[p.levels.length - 1].volume);
    expect(p.levels[0].share).toBeGreaterThan(0);
  });

  it("keeps extracted levels distinct (min gap apart)", () => {
    const p = darkPoolLevels(
      [priced("2026-06-15", 8_000_000, 90, 110), priced("2026-06-16", 8_000_000, 95, 105)],
      { topN: 5 },
    );
    const prices = p.levels.map((l) => l.price).sort((a, b) => a - b);
    for (let i = 1; i < prices.length; i++) expect(prices[i] - prices[i - 1]).toBeGreaterThan(0);
  });

  it("falls back to close-as-point when a day has no high/low", () => {
    const p = darkPoolLevels([
      { date: "2026-06-18", shortVolume: 5e6, shortExemptVolume: 0, offExchangeVolume: 1e7, consolidatedVolume: null, close: 100 },
      { date: "2026-06-19", shortVolume: 5e6, shortExemptVolume: 0, offExchangeVolume: 1e7, consolidatedVolume: null, close: 100 },
    ]);
    expect(p.available).toBe(true);
    expect(p.poc!).toBeCloseTo(100, 6);
  });
});
