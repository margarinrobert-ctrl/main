import { atr, closes, ema, sma } from "../series";
import type { Bar, EntryIntent, Instrument, Params, Strategy } from "../types";

/**
 * Moving-average systems, parameterised over the choices people actually argue about.
 *
 * Mechanism, stated honestly: a moving average is a low-pass filter on price. It contains no
 * information price does not already contain — it is a lagging transform of the same series. So a
 * moving-average rule cannot create an edge; it can only *express* one that exists in the
 * autocorrelation structure of returns. That is why the alpha-discovery stage matters more than
 * this file: on NQ 5-minute bars, lag-1 autocorrelation is +0.0107 and the variance ratio at 10
 * bars is 0.928. Those are the numbers that bound what any MA rule can extract.
 *
 * The parameterisation exists to answer three questions that get asserted rather than measured:
 *   1. Does EMA beat SMA? (`maType`)
 *   2. Does the crossover matter, or is it just "price on one side of a line"? (`mode`)
 *   3. Does holding to the opposite cross beat a fixed target? (`exitMode`)
 */
export const movingAverage: Strategy = {
  id: "moving-average",
  label: "Moving-average system (EMA/SMA, cross / filter / pullback)",
  family: "momentum",
  rationale:
    "A moving average is a lagging low-pass filter on price; it can only express serial dependence that already exists in returns, never create it.",
  defaults: { maType: 1, fast: 9, slow: 21, mode: 0, exitMode: 0, stopAtr: 1.5, rr: 2, maxBars: 60, sideMode: 0 },
  space: {
    /** 0 = SMA, 1 = EMA. */
    maType: { values: [0, 1] },
    fast: { values: [5, 9, 20, 50] },
    slow: { values: [21, 50, 100, 200] },
    /** 0 = fast/slow crossover, 1 = price crossing the slow MA, 2 = pullback to the slow MA in the fast MA's direction. */
    mode: { values: [0, 1, 2] },
    /** 0 = ATR stop with an R-multiple target, 1 = ATR stop and hold until the signal reverses. */
    exitMode: { values: [0, 1] },
    stopAtr: { values: [1.0, 1.5, 2.5] },
    rr: { values: [1.0, 2.0, 3.0] },
    maxBars: { values: [30, 60, 120] },
    sideMode: { values: [0, 1, -1] },
  },
  build(bars: Bar[], p: Params, inst: Instrument) {
    void inst;
    const c = closes(bars);
    const a = atr(bars, 14);
    const avg = p.maType === 1 ? ema : sma;
    const fastLen = Math.max(2, Math.round(p.fast));
    const slowLen = Math.max(fastLen + 1, Math.round(p.slow));
    const f = avg(c, fastLen);
    const s = avg(c, slowLen);

    /** Which side the system considers itself on at bar i, or 0 when it has no opinion. */
    const bias = (i: number): 0 | 1 | -1 => {
      if (!Number.isFinite(f[i]) || !Number.isFinite(s[i])) return 0;
      if (p.mode === 1) return c[i] > s[i] ? 1 : c[i] < s[i] ? -1 : 0;
      return f[i] > s[i] ? 1 : f[i] < s[i] ? -1 : 0;
    };

    return (i: number): EntryIntent | null => {
      if (i < 1) return null;
      const av = a[i];
      if (!Number.isFinite(av) || av <= 0) return null;

      const now = bias(i);
      const before = bias(i - 1);
      if (now === 0) return null;

      let fire = false;
      if (p.mode === 2) {
        // Pullback: the trend is established and price has come back to touch the slow average.
        if (!Number.isFinite(s[i])) return null;
        const touched = now === 1 ? bars[i].l <= s[i] && c[i] > s[i] : bars[i].h >= s[i] && c[i] < s[i];
        fire = touched && before === now;
      } else {
        // Crossover, or price crossing the line: act only on the bar the state changes.
        fire = now !== before && before !== 0;
      }
      if (!fire) return null;
      if (p.sideMode !== 0 && p.sideMode !== now) return null;

      const stop = p.stopAtr * av;
      const base: EntryIntent = {
        side: now,
        stopDist: stop,
        targetDist: stop * p.rr,
        maxBars: p.maxBars,
        tag: `${p.maType === 1 ? "ema" : "sma"}-${p.mode}-${now === 1 ? "long" : "short"}`,
      };
      if (p.exitMode === 0) return base;

      // Hold while the system still has the same opinion. The target is pushed far enough away that
      // the signal exit, not the target, is what ends the trade.
      return { ...base, targetDist: stop * 100, holdWhile: (j: number) => bias(j) === now };
    };
  },
};
