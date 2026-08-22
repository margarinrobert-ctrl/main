import { describe, expect, it } from "vitest";
import { runBacktest, runStrategy } from "./backtest";
import { instrument } from "./instruments";
import { ibDays } from "./ibFeatures";
import { initialBalance } from "./strategies";
import type { Bar, EntryIntent, Instrument } from "./types";

const inst: Instrument = {
  ...instrument("NQ"),
  spreadTicks: 0, slippageTicks: 0, commissionRoundTurn: 0,
  tz: "UTC", session: [0, 1440],
};

const mk = (rows: [number, number, number, number][], startMs = Date.UTC(2024, 0, 2, 10, 0)): Bar[] =>
  rows.map(([o, h, l, c], i) => ({ t: startMs + i * 300_000, o, h, l, c, v: 100 }));

/** Rest a buy limit at `px` on bar 0 only. */
const restLimit = (px: number, side: 1 | -1, stopPx: number, targetPx: number, validBars = 100) =>
  (i: number): EntryIntent | null =>
    i === 0
      ? { side, limitPrice: px, stopPrice: stopPx, targetPrice: targetPx, stopDist: Math.abs(px - stopPx), targetDist: Math.abs(targetPx - px), maxBars: 999, validBars }
      : null;

describe("resting limit orders", () => {
  it("does not fill while price stays away from the order", () => {
    const bars = mk([
      [100, 101, 100, 100],
      [100, 102, 100, 101],
      [101, 103, 101, 102],
    ]);
    const r = runBacktest(bars, restLimit(95, 1, 90, 110), { inst, sessionOnly: false });
    expect(r.trades).toHaveLength(0);
    expect(r.cancelledOrders).toBeGreaterThanOrEqual(0);
  });

  it("fills hours later when price finally trades through it", () => {
    const bars = mk([
      [100, 101, 100, 100],
      [100, 101, 99, 100],
      [100, 100, 94, 96], // trades through 95
      [96, 112, 96, 110],
    ]);
    const r = runBacktest(bars, restLimit(95, 1, 90, 110), { inst, sessionOnly: false });
    expect(r.trades).toHaveLength(1);
    expect(r.trades[0].entryIndex).toBe(2); // filled on the bar that reached it, not bar 1
    expect(r.trades[0].entryPx).toBeCloseTo(95, 9);
  });

  it("requires a trade THROUGH the price, not merely a touch", () => {
    const touch = mk([[100, 101, 100, 100], [100, 101, 95, 100], [100, 101, 100, 100]]);
    const through = mk([[100, 101, 100, 100], [100, 101, 94.75, 100], [100, 101, 100, 100]]);
    expect(runBacktest(touch, restLimit(95, 1, 90, 110), { inst, sessionOnly: false }).trades).toHaveLength(0);
    expect(runBacktest(through, restLimit(95, 1, 90, 110), { inst, sessionOnly: false }).trades).toHaveLength(1);
  });

  it("fills at the better price when the bar gaps past the order", () => {
    const bars = mk([[100, 101, 100, 100], [92, 93, 90, 92], [92, 112, 92, 110]]);
    const r = runBacktest(bars, restLimit(95, 1, 85, 110), { inst, sessionOnly: false });
    expect(r.trades[0].entryPx).toBeCloseTo(92, 9); // the open, which is better than the 95 limit
  });

  it("expires after validBars without filling", () => {
    const bars = mk([
      [100, 101, 100, 100],
      [100, 101, 100, 100],
      [100, 101, 100, 100],
      [100, 101, 94, 95], // would have filled, but the order is already gone
      [95, 112, 95, 110],
    ]);
    const r = runBacktest(bars, restLimit(95, 1, 90, 110, 2), { inst, sessionOnly: false });
    expect(r.trades).toHaveLength(0);
    expect(r.cancelledOrders).toBe(1);
  });

  it("cancels an unfilled order at the session boundary rather than carrying it overnight", () => {
    const day1 = mk([[100, 101, 100, 100], [100, 101, 100, 100]], Date.UTC(2024, 0, 2, 10, 0));
    const day2 = mk([[100, 101, 94, 95], [95, 112, 95, 110]], Date.UTC(2024, 0, 3, 10, 0));
    const r = runBacktest([...day1, ...day2], restLimit(95, 1, 90, 110), { inst, sessionOnly: false });
    expect(r.trades).toHaveLength(0);
    expect(r.cancelledOrders).toBe(1);
  });

  it("honours absolute stop and target prices rather than re-deriving them from the fill", () => {
    const bars = mk([[100, 101, 100, 100], [100, 101, 94, 96], [96, 96, 88, 89]]);
    const r = runBacktest(bars, restLimit(95, 1, 90, 120), { inst, sessionOnly: false });
    expect(r.trades[0].reason).toBe("stop");
    expect(r.trades[0].exitPx).toBeCloseTo(90, 9); // the absolute level, not entry - stopDist
  });
});

describe("initial balance strategy", () => {
  // A synthetic session: a 60-minute IB, then a break, then a retracement into the range.
  const session = (dayOffset: number): Bar[] => {
    const base = Date.UTC(2024, 0, 2 + dayOffset, 0, 0);
    const rows: Bar[] = [];
    for (let k = 0; k < 12; k++) rows.push({ t: base + k * 300_000, o: 100, h: 110, l: 90, c: 100, v: 1 }); // IB 90-110
    rows.push({ t: base + 12 * 300_000, o: 100, h: 115, l: 100, c: 114, v: 1 }); // breaks the high
    rows.push({ t: base + 13 * 300_000, o: 114, h: 114, l: 103, c: 104, v: 1 }); // retraces through 105
    rows.push({ t: base + 14 * 300_000, o: 104, h: 122, l: 104, c: 121, v: 1 }); // runs to target
    for (let k = 15; k < 24; k++) rows.push({ t: base + k * 300_000, o: 120, h: 121, l: 119, c: 120, v: 1 });
    return rows;
  };

  const bars = [0, 1, 2, 3, 4].flatMap(session);
  const ibInst: Instrument = { ...inst, session: [0, 120] };

  it("enters on the retracement, not on the break", () => {
    const r = runStrategy(initialBalance, bars, initialBalance.defaults, { inst: ibInst });
    expect(r.trades.length).toBeGreaterThan(0);
    const t = r.trades[0];
    // IB is 90-110, range 20. Entry = 110 - 25% x 20 = 105, target = 110 + 50% x 20 = 120.
    expect(t.entryPx).toBeCloseTo(105, 6);
    expect(t.side).toBe(1);
    expect(t.reason).toBe("target");
    expect(t.exitPx).toBeCloseTo(120, 6);
  });

  it("targets a fixed multiple of the actual risk when rrMode is on", () => {
    // IB 90-110, range 20. Entry = 110 - 25% x 20 = 105. Stop at 80% = 110 - 16 = 94, so the risk
    // is 11 points. A 1:1 target is 105 + 11 = 116 — NOT 110 + some fraction of the range, which is
    // what the percent-of-range target would give. The two orders are genuinely different.
    const p = { ...initialBalance.defaults, stopPct: 80, rrMode: 1, rrMult: 1 };
    const r = runStrategy(initialBalance, bars, p, { inst: ibInst });
    expect(r.trades.length).toBeGreaterThan(0);
    const t = r.trades[0];
    expect(t.entryPx).toBeCloseTo(105, 6);
    expect(t.reason).toBe("target");
    expect(t.exitPx).toBeCloseTo(116, 6);
  });

  it("scales the fixed target by rrMult", () => {
    const p = { ...initialBalance.defaults, stopPct: 80, rrMode: 1, rrMult: 1.5 };
    const r = runStrategy(initialBalance, bars, p, { inst: ibInst });
    // Same 11-point risk, so 1.5R is 105 + 16.5 = 121.5.
    expect(r.trades[0].exitPx).toBeCloseTo(121.5, 6);
  });

  it("leaves the percent-of-range target untouched when rrMode is off", () => {
    // rrMult is set to something that would be obvious if it leaked through, and must be ignored.
    const p = { ...initialBalance.defaults, rrMode: 0, rrMult: 3 };
    const r = runStrategy(initialBalance, bars, p, { inst: ibInst });
    expect(r.trades[0].exitPx).toBeCloseTo(120, 6); // 110 + 50% x 20
  });

  it("stopMode 2 puts the stop a fixed number of points from the ENTRY, not the edge", () => {
    // Entry 105, fixed 6-point stop -> 99. The percent-of-range stop would be measured from 110.
    const p = { ...initialBalance.defaults, stopMode: 2, stopPts: 6, rrMode: 1, rrMult: 1 };
    const r = runStrategy(initialBalance, bars, p, { inst: ibInst });
    expect(r.trades.length).toBeGreaterThan(0);
    const t = r.trades[0];
    expect(t.entryPx).toBeCloseTo(105, 6);
    expect(t.exitPx).toBeCloseTo(111, 6); // 1R above entry on a 6-point risk
  });

  it("stopMode 3 uses the opposite edge of the range", () => {
    // IB 90-110, long entry 105, stop at the LOW = 90, so risk is 15 and a 1:1 target is 120.
    const p = { ...initialBalance.defaults, stopMode: 3, rrMode: 1, rrMult: 1 };
    const r = runStrategy(initialBalance, bars, p, { inst: ibInst });
    expect(r.trades.length).toBeGreaterThan(0);
    expect(r.trades[0].exitPx).toBeCloseTo(120, 6);
  });

  it("stopMode 1 scales the stop with ATR", () => {
    // The synthetic IB bars have a 20-point true range, so ATR is ~20. Multiples are kept small
    // enough that both 1:1 targets sit inside the day's move — otherwise the wider one exits on
    // the session flat and the comparison measures the synthetic data, not the stop rule.
    const near = runStrategy(initialBalance, bars, { ...initialBalance.defaults, stopMode: 1, atrLen: 5, atrMult: 0.25, rrMode: 1, rrMult: 1 }, { inst: ibInst });
    const far = runStrategy(initialBalance, bars, { ...initialBalance.defaults, stopMode: 1, atrLen: 5, atrMult: 0.5, rrMode: 1, rrMult: 1 }, { inst: ibInst });
    expect(near.trades[0].reason).toBe("target");
    expect(far.trades[0].reason).toBe("target");
    expect(near.trades.length).toBeGreaterThan(0);
    expect(far.trades.length).toBeGreaterThan(0);
    // At 1:1 the target sits exactly 1R above the entry, so the target distance IS the risk.
    const risk = (t: { entryPx: number; exitPx: number }) => t.exitPx - t.entryPx;
    expect(risk(far.trades[0])).toBeGreaterThan(risk(near.trades[0]));
    expect(risk(far.trades[0]) / risk(near.trades[0])).toBeCloseTo(2, 1);
  });

  it("refuses a trade whose stop would land on the wrong side of the entry", () => {
    // Entry is 105 and a zero-distance fixed stop is not a stop. No trade, rather than a trade
    // with a negative or zero risk that would produce an infinite R.
    const r = runStrategy(initialBalance, bars, { ...initialBalance.defaults, stopMode: 2, stopPts: 0 }, { inst: ibInst });
    expect(r.trades.length).toBe(0);
  });

  it("still refuses when the percent stop sits inside the retracement", () => {
    const r = runStrategy(initialBalance, bars, { ...initialBalance.defaults, retrPct: 50, stopPct: 40 }, { inst: ibInst });
    expect(r.trades.length).toBe(0);
  });

  it("takes at most one trade per session", () => {
    const r = runStrategy(initialBalance, bars, initialBalance.defaults, { inst: ibInst });
    const perDay = new Map<number, number>();
    for (const t of r.trades) {
      const d = Math.floor(t.entryTime / 86_400_000);
      perDay.set(d, (perDay.get(d) ?? 0) + 1);
    }
    for (const n of perDay.values()) expect(n).toBeLessThanOrEqual(1);
  });

  it("computes day features only from information available when the window closes", () => {
    const days = ibDays(bars, ibInst, 60);
    expect(days.length).toBe(5);
    for (const d of days) {
      expect(d.high).toBeCloseTo(110, 6);
      expect(d.low).toBeCloseTo(90, 6);
      expect(d.range).toBeCloseTo(20, 6);
      expect(d.closePosition).toBeCloseTo(0.5, 6); // the IB window's last close was 100, mid-range
    }
  });
});

describe("initial balance — fixed point target", () => {
  const session = (dayOffset: number): Bar[] => {
    const base = Date.UTC(2024, 0, 2 + dayOffset, 0, 0);
    const rows: Bar[] = [];
    for (let k = 0; k < 12; k++) rows.push({ t: base + k * 300_000, o: 100, h: 110, l: 90, c: 100, v: 1 });
    rows.push({ t: base + 12 * 300_000, o: 100, h: 115, l: 100, c: 114, v: 1 });
    rows.push({ t: base + 13 * 300_000, o: 114, h: 114, l: 103, c: 104, v: 1 });
    rows.push({ t: base + 14 * 300_000, o: 104, h: 122, l: 104, c: 121, v: 1 });
    for (let k = 15; k < 24; k++) rows.push({ t: base + k * 300_000, o: 120, h: 121, l: 119, c: 120, v: 1 });
    return rows;
  };
  const bars = [0, 1, 2].flatMap(session);
  const ibInst: Instrument = { ...inst, session: [0, 120] };

  it("targets a fixed distance from the entry, ignoring both the range and the risk", () => {
    // Entry is 105. A 7-point target is 112 — not a fraction of the 20-point range, and not a
    // multiple of the risk, both of which would give something else.
    const p = { ...initialBalance.defaults, targetMode: 1, targetPts: 7 };
    const r = runStrategy(initialBalance, bars, p, { inst: ibInst });
    expect(r.trades.length).toBeGreaterThan(0);
    expect(r.trades[0].entryPx).toBeCloseTo(105, 6);
    expect(r.trades[0].exitPx).toBeCloseTo(112, 6);
    expect(r.trades[0].reason).toBe("target");
  });

  it("overrides the R:R target rather than combining with it", () => {
    // rrMult is set to something that would be obvious if it leaked through.
    const p = { ...initialBalance.defaults, targetMode: 1, targetPts: 7, rrMode: 1, rrMult: 9 };
    const r = runStrategy(initialBalance, bars, p, { inst: ibInst });
    expect(r.trades[0].exitPx).toBeCloseTo(112, 6);
  });

  it("pairs with a fixed point stop to give a flat 1:1 in points", () => {
    // Stop 6 points below 105 is 99; target 6 above is 111. Equal distances, so the R multiple on
    // a win is 1 before costs regardless of how wide the IB happened to be.
    const p = { ...initialBalance.defaults, stopMode: 2, stopPts: 6, targetMode: 1, targetPts: 6 };
    const r = runStrategy(initialBalance, bars, p, { inst: ibInst });
    expect(r.trades[0].exitPx).toBeCloseTo(111, 6);
    expect(r.trades[0].reason).toBe("target");
  });
});
