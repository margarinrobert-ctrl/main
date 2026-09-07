import { clockFor } from "../clock";
import { atr, closes, ema, rsi } from "../series";
import type { Bar, EntryIntent, Instrument, Params, Strategy } from "../types";

/**
 * Trend pullback continuation.
 *
 * Mechanism: within an established intraday trend, pullbacks are inventory rebalancing by
 * short-horizon participants rather than a change in the auction's direction. Entering on the reset
 * (RSI cooling while the EMA stack holds) buys the same direction at a better price, which is what
 * makes the trade survivable at scalping cost levels — chasing the same trend at the extension does
 * not.
 */
export const trendPullback: Strategy = {
  id: "trend-pullback",
  label: "EMA-stack pullback continuation",
  family: "momentum",
  rationale: "Pullbacks inside an intraday trend are inventory rebalancing, not a change in the auction's direction.",
  defaults: { fast: 9, slow: 30, rsiLen: 5, resetLevel: 40, stopAtr: 1.0, rr: 1.5, maxBars: 20 },
  space: {
    fast: { values: [5, 9, 15] },
    slow: { values: [20, 30, 50] },
    rsiLen: { values: [3, 5, 9] },
    resetLevel: { values: [30, 40, 50] },
    stopAtr: { values: [0.75, 1.0, 1.5] },
    rr: { values: [1.0, 1.5, 2.0] },
    maxBars: { values: [10, 20, 40] },
  },
  build(bars: Bar[], p: Params) {
    const c = closes(bars);
    const f = ema(c, p.fast);
    const s = ema(c, p.slow);
    const a = atr(bars, 14);
    const r = rsi(c, p.rsiLen);
    return (i: number): EntryIntent | null => {
      if (i < 1) return null;
      const av = a[i];
      if (!Number.isFinite(av) || av <= 0 || !Number.isFinite(f[i]) || !Number.isFinite(s[i]) || !Number.isFinite(r[i]) || !Number.isFinite(r[i - 1]))
        return null;
      const stop = p.stopAtr * av;
      const up = f[i] > s[i] && c[i] > s[i];
      const down = f[i] < s[i] && c[i] < s[i];
      // Enter as the reset completes: RSI crosses back up out of the pullback zone (mirrored short).
      if (up && r[i - 1] < p.resetLevel && r[i] >= p.resetLevel)
        return { side: 1, stopDist: stop, targetDist: stop * p.rr, maxBars: p.maxBars, tag: "pb-long" };
      if (down && r[i - 1] > 100 - p.resetLevel && r[i] <= 100 - p.resetLevel)
        return { side: -1, stopDist: stop, targetDist: stop * p.rr, maxBars: p.maxBars, tag: "pb-short" };
      return null;
    };
  },
};

/**
 * Time-of-day control strategy.
 *
 * This one exists to be a NULL BENCHMARK, not a trade idea: it enters in a fixed direction at a
 * fixed hour with an ATR stop and target. Run through the same statistical pipeline as the real
 * candidates, it shows what "no information, only exposure and costs" scores — and any real
 * candidate that cannot clearly beat it has not demonstrated anything.
 */
export const timeOfDayControl: Strategy = {
  id: "tod-control",
  label: "Time-of-day control (null benchmark)",
  family: "seasonality",
  rationale: "Deliberate null: fixed-hour entry with no predictive content, used to calibrate the rest of the pipeline.",
  defaults: { hourLocal: 10, side: 1, stopAtr: 1.0, rr: 1.5, maxBars: 20 },
  space: {
    hourLocal: { values: [9, 10, 11, 13, 14] },
    side: { values: [1, -1] },
    stopAtr: { values: [1.0] },
    rr: { values: [1.0, 1.5] },
    maxBars: { values: [20] },
  },
  build(bars: Bar[], p: Params, inst: Instrument) {
    const a = atr(bars, 14);
    const clock = clockFor(bars, inst.tz);
    return (i: number): EntryIntent | null => {
      const av = a[i];
      if (!Number.isFinite(av) || av <= 0) return null;
      if (clock.hour[i] !== p.hourLocal || clock.minute[i] >= 15) return null;
      const stop = p.stopAtr * av;
      return { side: p.side >= 0 ? 1 : -1, stopDist: stop, targetDist: stop * p.rr, maxBars: p.maxBars, tag: "control" };
    };
  },
};
