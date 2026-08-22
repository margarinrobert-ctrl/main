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
