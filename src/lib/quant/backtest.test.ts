import { describe, expect, it } from "vitest";
import { runBacktest } from "./backtest";
import { fillFrictionPoints } from "./costs";
import { instrument, roundTurnCostPoints } from "./instruments";
import { neweyWestT } from "./stats";
import { STRATEGIES } from "./strategies";
import { syntheticSeries } from "./synth";
import type { Bar, EntryIntent, Instrument } from "./types";

const inst: Instrument = {
  ...instrument("NQ"),
  spreadTicks: 0,
  slippageTicks: 0,
  commissionRoundTurn: 0,
  tz: "UTC",
  session: [0, 1440],
};

/** Bars one minute apart starting at a fixed UTC instant, so session logic is trivial. */
const mk = (rows: [number, number, number, number][], startMs = Date.UTC(2024, 0, 2, 10, 0)): Bar[] =>
  rows.map(([o, h, l, c], i) => ({ t: startMs + i * 300_000, o, h, l, c, v: 100 }));

const always = (side: 1 | -1, stopDist: number, targetDist: number, maxBars = 50) =>
  (i: number): EntryIntent | null => (i === 0 ? { side, stopDist, targetDist, maxBars } : null);

describe("execution model", () => {
  it("fills at the NEXT bar's open, never on the signal bar", () => {
    const bars = mk([
      [100, 101, 99, 100],
      [105, 106, 104, 105],
      [110, 111, 109, 110],
    ]);
    const r = runBacktest(bars, always(1, 50, 50), { inst, sessionOnly: false });
    expect(r.trades).toHaveLength(1);
    expect(r.trades[0].entryIndex).toBe(1);
    expect(r.trades[0].entryPx).toBe(105); // the open of bar 1, not the close of bar 0
  });

  it("books the STOP when one bar contains both the stop and the target", () => {
    const bars = mk([
      [100, 100, 100, 100],
      [100, 110, 90, 100], // reaches +10 and -10 in the same bar
      [100, 100, 100, 100],
    ]);
    const r = runBacktest(bars, always(1, 5, 5), { inst, sessionOnly: false });
    expect(r.trades[0].reason).toBe("stop");
    expect(r.trades[0].pnl).toBeLessThan(0);
    expect(r.ambiguousExits).toBe(1);
  });

  it("fills at the OPEN when the market gaps through the stop", () => {
    const bars = mk([
      [100, 100, 100, 100],
      [100, 100, 100, 100],
      [80, 81, 79, 80], // gapped far below the 95 stop
    ]);
    const r = runBacktest(bars, always(1, 5, 100), { inst, sessionOnly: false });
    expect(r.trades[0].reason).toBe("stop");
    expect(r.trades[0].exitPx).toBe(80); // not the 95 stop level — that fill was never available
  });

  it("exits on the time stop when neither level is touched", () => {
    const bars = mk([[100, 100, 100, 100], [100, 100, 100, 100], [100, 100, 100, 100], [100, 100, 100, 100]]);
    const r = runBacktest(bars, always(1, 50, 50, 2), { inst, sessionOnly: false });
    expect(r.trades[0].reason).toBe("time");
    expect(r.trades[0].barsHeld).toBe(2);
  });

  it("charges the full round-turn cost on every trade", () => {
    const costed = { ...inst, spreadTicks: 1, slippageTicks: 1, commissionRoundTurn: 4 };
    const bars = mk([[100, 100, 100, 100], [100, 100, 100, 100], [100, 100, 100, 100]]);
    const r = runBacktest(bars, always(1, 50, 50, 1), { inst: costed, sessionOnly: false });
    expect(r.costPoints).toBeCloseTo(roundTurnCostPoints(costed), 10);
    expect(r.trades[0].grossPoints).toBe(0);
    expect(r.trades[0].pnl).toBeCloseTo(-19, 6); // 3.8 ticks x $5 per tick
  });

  it("goes flat at the end of the session rather than carrying overnight", () => {
    const sessioned: Instrument = { ...inst, session: [600, 660] };
    const bars = mk(
      [[100, 100, 100, 100], [100, 100, 100, 100], [100, 100, 100, 100], [100, 100, 100, 100]],
      Date.UTC(2024, 0, 2, 10, 0),
    );
    const r = runBacktest(bars, always(1, 50, 50, 99), { inst: sessioned, sessionOnly: true });
    expect(r.trades[0].reason).toBe("session");
  });

  it("respects the per-day entry cap", () => {
    const bars = mk(Array.from({ length: 40 }, () => [100, 101, 99, 100] as [number, number, number, number]));
    const r = runBacktest(bars, () => ({ side: 1, stopDist: 5, targetDist: 5, maxBars: 1 }), {
      inst,
      sessionOnly: false,
      maxTradesPerDay: 3,
    });
    expect(r.trades.length).toBeLessThanOrEqual(3);
  });
});

describe("fill models", () => {
  const costed: Instrument = { ...inst, spreadTicks: 1, slippageTicks: 1, commissionRoundTurn: 4 };

  it("taker charges the full round turn regardless of how the trade exited", () => {
    const bars = mk([[100, 100, 100, 100], [100, 100, 100, 100], [100, 110, 100, 110]]);
    const r = runBacktest(bars, always(1, 50, 5), { inst: costed, sessionOnly: false, fillModel: "taker" });
    expect(r.trades[0].reason).toBe("target");
    expect(r.trades[0].costPoints).toBeCloseTo(roundTurnCostPoints(costed), 9);
  });

  it("realistic charges no spread on a target exit but full taker cost on a stop", () => {
    const win = mk([[100, 100, 100, 100], [100, 100, 100, 100], [100, 110, 100, 110]]);
    const lose = mk([[100, 100, 100, 100], [100, 100, 100, 100], [100, 100, 90, 90]]);
    const onTarget = runBacktest(win, always(1, 50, 5), { inst: costed, sessionOnly: false, fillModel: "realistic" });
    const onStop = runBacktest(lose, always(1, 5, 50), { inst: costed, sessionOnly: false, fillModel: "realistic" });
    expect(onTarget.trades[0].reason).toBe("target");
    expect(onStop.trades[0].reason).toBe("stop");
    expect(onTarget.trades[0].costPoints).toBeLessThan(onStop.trades[0].costPoints);
    // A target rests, so it pays fees only. A stop takes liquidity AND pays the stop premium on
    // top, because it becomes a market order exactly when the book is thinnest. The gap between
    // them is therefore one taker side PLUS that premium -- under the old flat model it was one
    // taker side, and the missing premium is the specific way a flat tick flatters a stop system.
    // Fees are paid on both, so the gap is pure friction: one taker side of spread and slippage,
    // plus the stop premium.
    expect(onStop.trades[0].costPoints - onTarget.trades[0].costPoints).toBeCloseTo(fillFrictionPoints(costed, "stop"), 9);
  });

  it("passive only fills when price trades THROUGH the resting order", () => {
    // Signal closes at 100, so a long limit rests at 99.75. The next bar's low never reaches it.
    const noFill = mk([[100, 100, 100, 100], [100, 101, 99.75, 100]]);
    const r1 = runBacktest(noFill, always(1, 5, 5), { inst: costed, sessionOnly: false, fillModel: "passive", limitOffsetTicks: 1 });
    expect(r1.trades).toHaveLength(0);
    expect(r1.unfilledLimits).toBe(1);

    // Same setup, but the bar trades below the limit — now it fills, at the limit price.
    const fill = mk([[100, 100, 100, 100], [100, 101, 99.0, 100], [100, 100, 100, 100]]);
    const r2 = runBacktest(fill, always(1, 5, 5), { inst: costed, sessionOnly: false, fillModel: "passive", limitOffsetTicks: 1 });
    expect(r2.trades).toHaveLength(1);
    expect(r2.trades[0].entryPx).toBeCloseTo(99.75, 9);
  });

  it("orders the three models by cost, cheapest last", () => {
    // Bar 1 dips to 99 so the passive limit at 99.75 genuinely trades through; bar 2 reaches the
    // target under all three models, so only the charged cost differs.
    const bars = mk([[100, 100, 100, 100], [100, 101, 99, 100], [100, 110, 100, 110]]);
    const taker = runBacktest(bars, always(1, 50, 5), { inst: costed, sessionOnly: false, fillModel: "taker" });
    const realistic = runBacktest(bars, always(1, 50, 5), { inst: costed, sessionOnly: false, fillModel: "realistic" });
    const passive = runBacktest(bars, always(1, 50, 5), { inst: costed, sessionOnly: false, fillModel: "passive" });
    expect(taker.trades[0].costPoints).toBeGreaterThan(realistic.trades[0].costPoints);
    expect(realistic.trades[0].costPoints).toBeGreaterThan(passive.trades[0].costPoints);
  });
});

describe("look-ahead contract", () => {
  // The decisive structural test: a decision made at bar i must not change when the bars AFTER i
  // are removed. Any indicator that peeks forward — a centred average, a full-sample normalisation,
  // an opening range built from the completed day — fails here rather than silently inflating a
  // result.
  //
  // The comparison REPLAYS the signal closure over every bar from 0 to the cut, rather than calling
  // it once at the cut. That matters: several strategies carry per-session state (one trade per day,
  // whether a side has been used, how long price has held inside a level) which only exists if the
  // closure has been called on every prior bar, which is how the backtester calls it. Calling it
  // out of sequence compares two different states and reports differences that are an artefact of
  // the test rather than a leak in the strategy. Replaying also makes the test far stricter, since
  // it compares every decision up to the cut instead of one.
  const bars = syntheticSeries("NQ", { days: 40, seed: 5, barsPerDay: 78, minutesPerBar: 5, sessionStartUtc: 0 });

  const replay = (strategy: (typeof STRATEGIES)[number], data: typeof bars, upTo: number): string[] => {
    const fn = strategy.build(data, strategy.defaults, inst);
    const out: string[] = [];
    for (let i = 0; i <= upTo; i++) out.push(JSON.stringify(fn(i)));
    return out;
  };

  for (const strategy of STRATEGIES) {
    it(`${strategy.id} makes identical decisions on a truncated series`, () => {
      for (const cut of [900, 1500, 2100, 2600]) {
        expect(replay(strategy, bars.slice(0, cut + 1), cut), strategy.id).toEqual(replay(strategy, bars, cut));
      }
    });
  }
});

describe("null calibration", () => {
  // The engine is run over a simulated martingale with costs switched off. There is no edge in that
  // series, so gross P&L per trade must be statistically indistinguishable from zero. A tick
  // threshold would be arbitrary and instrument-dependent; a t-statistic is the real test. The
  // bound is 3.5 rather than 2 because six strategies are checked at once, so the family-wise
  // critical value is what matters (Bonferroni at 5% over six tests is z = 2.64).
  it("shows no significant gross edge on a costless martingale", () => {
    const bars = syntheticSeries("NQ", { days: 300, seed: 99, barsPerDay: 78, minutesPerBar: 5, sessionStartUtc: 0 });
    for (const s of STRATEGIES) {
      const r = runBacktest(bars, s.build(bars, s.defaults, inst), { inst, sessionOnly: false });
      if (r.trades.length < 100) continue;
      const gross = r.trades.map((t) => t.grossPoints / inst.tickSize);
      const { t } = neweyWestT(gross);
      expect(Math.abs(t), `${s.id} leaked edge on a martingale`).toBeLessThan(3.5);
    }
  });

  it("charges the modelled cost, so the same martingale is a guaranteed loser once costs are on", () => {
    const costed = { ...inst, spreadTicks: 1, slippageTicks: 1, commissionRoundTurn: 4 };
    const bars = syntheticSeries("NQ", { days: 300, seed: 99, barsPerDay: 78, minutesPerBar: 5, sessionStartUtc: 0 });
    for (const s of STRATEGIES) {
      const free = runBacktest(bars, s.build(bars, s.defaults, inst), { inst, sessionOnly: false });
      const paid = runBacktest(bars, s.build(bars, s.defaults, costed), { inst: costed, sessionOnly: false });
      if (paid.trades.length < 100) continue;
      const freePerTrade = free.trades.reduce((a, t) => a + t.pnl, 0) / free.trades.length;
      const paidPerTrade = paid.trades.reduce((a, t) => a + t.pnl, 0) / paid.trades.length;
      // The REALISED cost per trade now sits ABOVE the calm-bar reference and never below it.
      // That is the point of the model: stops trigger preferentially in fast bars -- that is why
      // they trigger -- so charging every bar the same tick understates what a stop system pays.
      // The band is wide because how far above depends on the strategy's own exit mix.
      const calmReference = 19; // 3.8 ticks x $5, market in, market out, median bar
      const realised = freePerTrade - paidPerTrade;
      expect(realised, `${s.id} realised cost fell below the calm-bar reference`).toBeGreaterThanOrEqual(calmReference - 0.5);
      expect(realised, `${s.id} realised cost is implausibly far above the reference`).toBeLessThan(2 * calmReference);
    }
  });
});
