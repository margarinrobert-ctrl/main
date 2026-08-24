import { describe, expect, it } from "vitest";
import { auditBars, cleanBars, parseCsv, splitAt } from "./data";
import { atr, ema, percentRank, priorExtreme, rollingStd, rsi, sessionVwap, sma, zscore } from "./series";
import { expandGrid, plateauReport, gridSearch } from "./optimize";
import { instrument } from "./instruments";
import { syntheticSeries } from "./synth";
import { volBreakout } from "./strategies";
import type { Bar } from "./types";

const bars = (closes: number[]): Bar[] =>
  closes.map((c, i) => ({ t: Date.UTC(2024, 0, 2, 14, 0) + i * 300_000, o: c, h: c + 1, l: c - 1, c, v: 100 }));

describe("indicator causality", () => {
  const series = Array.from({ length: 200 }, (_, i) => 100 + Math.sin(i / 7) * 5 + i * 0.01);
  const b = bars(series);

  // Every indicator must give the same value at index i whether or not later data exists. This is
  // the property that makes a backtest meaningful, so it is asserted directly rather than assumed.
  const causal: [string, (x: Bar[]) => number[]][] = [
    ["sma", (x) => sma(x.map((v) => v.c), 20)],
    ["ema", (x) => ema(x.map((v) => v.c), 20)],
    ["rollingStd", (x) => rollingStd(x.map((v) => v.c), 20)],
    ["rsi", (x) => rsi(x.map((v) => v.c), 14)],
    ["atr", (x) => atr(x, 14)],
    ["zscore", (x) => zscore(x.map((v) => v.c), 30)],
    ["percentRank", (x) => percentRank(x.map((v) => v.c), 30)],
    ["priorExtreme", (x) => priorExtreme(x, 10, "high")],
    ["sessionVwap", (x) => sessionVwap(x, x.map(() => 0))],
  ];

  for (const [name, fn] of causal) {
    it(`${name} at index i does not depend on data after i`, () => {
      const full = fn(b);
      for (const cut of [60, 120, 180]) {
        const truncated = fn(b.slice(0, cut + 1));
        expect(truncated[cut], name).toBeCloseTo(full[cut], 9);
      }
    });
  }

  it("leaves the warm-up as NaN rather than zero", () => {
    const s = sma([1, 2, 3, 4, 5], 3);
    expect(Number.isNaN(s[0])).toBe(true);
    expect(Number.isNaN(s[1])).toBe(true);
    expect(s[2]).toBeCloseTo(2, 9);
  });

  it("computes a known ATR by hand", () => {
    const b2: Bar[] = [
      { t: 0, o: 10, h: 12, l: 8, c: 11, v: 1 },
      { t: 1, o: 11, h: 13, l: 10, c: 12, v: 1 },
      { t: 2, o: 12, h: 14, l: 11, c: 13, v: 1 },
    ];
    // TR = [4, 3, 3]; ATR(2) seeds at (4+3)/2 = 3.5 then Wilder-smooths to (3.5 + 3)/2 = 3.25.
    const a = atr(b2, 2);
    expect(a[1]).toBeCloseTo(3.5, 9);
    expect(a[2]).toBeCloseTo(3.25, 9);
  });

  it("resets VWAP on a session change", () => {
    const b3 = bars([10, 20, 30, 40]);
    const v = sessionVwap(b3, [0, 0, 1, 1]);
    expect(v[1]).toBeCloseTo(15, 6);
    expect(v[2]).toBeCloseTo(30, 6); // first bar of the new session -> its own typical price
  });
});

describe("CSV ingestion and audit", () => {
  it("parses ISO and epoch stamps and any column order", () => {
    const csv = ["close,timestamp,open,volume,high,low", "101,2024-01-02T14:30:00Z,100,500,102,99", "103,1704205800000,101,600,104,100"].join("\n");
    const out = parseCsv(csv);
    expect(out).toHaveLength(2);
    expect(out[0].c).toBe(101);
    expect(out[0].o).toBe(100);
    expect(new Date(out[0].t).toISOString()).toBe("2024-01-02T14:30:00.000Z");
  });

  it("separates recurring session breaks from genuinely missing data", () => {
    const rows: Bar[] = [];
    // Ten days of six 5-minute bars with a one-hour break in the middle of each day.
    for (let d = 0; d < 10; d++) {
      const base = Date.UTC(2024, 0, 2 + d, 14, 0);
      for (const off of [0, 5, 10, 70, 75, 80]) rows.push({ t: base + off * 60_000, o: 1, h: 1, l: 1, c: 1, v: 1 });
    }
    const a = auditBars(rows, "UTC");
    // 10 mid-session breaks plus 9 overnight breaks: both recur at a fixed local minute, so both
    // are structural. Nothing here is missing data.
    expect(a.structuralGaps).toBe(19);
    expect(a.missingDataGaps).toBe(0);
    expect(a.duplicateStamps).toBe(0);
  });

  it("counts a one-off hole as missing data, not as a session break", () => {
    const rows: Bar[] = [];
    for (let d = 0; d < 10; d++) {
      const base = Date.UTC(2024, 0, 2 + d, 14, 0);
      const offsets = d === 4 ? [0, 5, 40, 45] : [0, 5, 10, 15]; // day 4 loses its middle
      for (const off of offsets) rows.push({ t: base + off * 60_000, o: 1, h: 1, l: 1, c: 1, v: 1 });
    }
    const a = auditBars(rows, "UTC");
    expect(a.missingDataGaps).toBe(1);
  });

  it("flags duplicates and repairs impossible OHLC", () => {
    const dupes: Bar[] = [
      { t: 1000, o: 1, h: 2, l: 0.5, c: 1.5, v: 1 },
      { t: 1000, o: 1, h: 2, l: 0.5, c: 1.5, v: 1 },
      { t: 2000, o: 5, h: 1, l: 9, c: 5, v: 1 },
    ];
    expect(auditBars(dupes, "UTC").duplicateStamps).toBe(1);
    const cleaned = cleanBars(dupes);
    expect(cleaned).toHaveLength(2);
    expect(cleaned[1].h).toBeGreaterThanOrEqual(cleaned[1].l);
  });

  it("splits chronologically", () => {
    const b = bars(Array.from({ length: 100 }, (_, i) => i));
    const { train, test } = splitAt(b, 0.7);
    expect(train).toHaveLength(70);
    expect(test).toHaveLength(30);
    expect(train[train.length - 1].t).toBeLessThan(test[0].t);
  });
});

describe("parameter search", () => {
  it("enumerates a small grid exhaustively and samples a large one deterministically", () => {
    const space = { a: { values: [1, 2, 3] }, b: { values: [10, 20] } };
    expect(expandGrid(space, 100)).toHaveLength(6);
    const sampled = expandGrid({ a: { values: [1, 2, 3, 4, 5] }, b: { values: [1, 2, 3, 4, 5] } }, 7, 42);
    expect(sampled).toHaveLength(7);
    expect(expandGrid({ a: { values: [1, 2, 3, 4, 5] }, b: { values: [1, 2, 3, 4, 5] } }, 7, 42)).toEqual(sampled);
  });

  // plateauReport is the cheapest overfit detector in the toolkit, so it is tested directly against
  // two hand-built surfaces rather than against whatever a noise run happens to produce.
  const surface = (score: (a: number, b: number) => number) => {
    const space = { a: { values: [1, 2, 3, 4, 5] }, b: { values: [1, 2, 3, 4, 5] } };
    const trials = space.a.values.flatMap((a) =>
      space.b.values.map((b) => ({
        params: { a, b },
        objective: score(a, b),
        dailySharpe: 0,
        summary: {} as never,
      })),
    );
    const best = [...trials].sort((x, y) => y.objective - x.objective)[0];
    return { search: { strategyId: "t", trials, best, trialCount: trials.length }, space };
  };

  it("calls a single mined peak a spike", () => {
    const { search, space } = surface((a, b) => (a === 3 && b === 3 ? 2 : -1));
    expect(plateauReport(search, space).verdict).toBe("spike");
  });

  it("calls a broad region a plateau", () => {
    const { search, space } = surface((a, b) => 2 - 0.05 * (Math.abs(a - 3) + Math.abs(b - 3)));
    const r = plateauReport(search, space);
    expect(r.verdict).toBe("plateau");
    expect(r.stability).toBeGreaterThan(0.9);
    expect(r.neighbourHitRate).toBe(1);
  });

  it("runs end to end on a real search", () => {
    const inst = { ...instrument("NQ"), tz: "UTC" as const, session: [0, 1440] as [number, number] };
    const b = syntheticSeries("NQ", { days: 120, seed: 31, barsPerDay: 78, minutesPerBar: 5, sessionStartUtc: 0 });
    const search = gridSearch(volBreakout, b, { inst, sessionOnly: false }, { minTrades: 20, maxCombos: 200, seed: 5 });
    expect(search.trialCount).toBe(200);
    expect(["plateau", "ridge", "spike"]).toContain(plateauReport(search, volBreakout.space).verdict);
  });
});
