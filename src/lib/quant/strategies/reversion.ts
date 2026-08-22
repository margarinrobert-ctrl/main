import { clockFor } from "../clock";
import { atr, closes, percentRank, rsi, sessionVwap } from "../series";
import type { Bar, EntryIntent, Instrument, Params, Strategy } from "../types";

/**
 * Session-VWAP band fade.
 *
 * Mechanism: VWAP is the benchmark execution price for size, so institutional flow is mechanically
 * attracted back to it — a stretch of N ATR away from session VWAP is a temporary imbalance that
 * the same flow tends to correct. The regime gate matters more than the entry: fading works in
 * balanced (low realised-vol percentile) tape and is a capital shredder in a trend day, so the
 * strategy refuses to trade when volatility is in its upper percentiles.
 */
export const vwapFade: Strategy = {
  id: "vwap-fade",
  label: "Session-VWAP band fade",
  family: "mean-reversion",
  rationale: "VWAP is the institutional execution benchmark; stretches away from it are corrected by the same flow.",
  defaults: { stretchAtr: 1.5, maxVolPct: 0.7, volLookback: 100, stopAtr: 1.0, rr: 1.0, maxBars: 16, rsiLen: 7, rsiEdge: 25 },
  space: {
    stretchAtr: { values: [1.0, 1.5, 2.0, 2.5] },
    maxVolPct: { values: [0.5, 0.7, 1.0] },
    volLookback: { values: [50, 100, 200] },
    stopAtr: { values: [0.75, 1.0, 1.5] },
    rr: { values: [0.75, 1.0, 1.5] },
    maxBars: { values: [8, 16, 32] },
    rsiLen: { values: [5, 7, 14] },
    rsiEdge: { values: [15, 25, 35] },
  },
  build(bars: Bar[], p: Params, inst: Instrument) {
    const a = atr(bars, 14);
    const c = closes(bars);
    const vwap = sessionVwap(bars, clockFor(bars, inst.tz).dayIndex);
    const volPct = percentRank(a, p.volLookback);
    const r = rsi(c, p.rsiLen);
    return (i: number): EntryIntent | null => {
      const av = a[i];
      if (!Number.isFinite(av) || av <= 0 || !Number.isFinite(vwap[i]) || !Number.isFinite(r[i])) return null;
      if (Number.isFinite(volPct[i]) && volPct[i] > p.maxVolPct) return null; // trend regime — do not fade
      const stretch = (c[i] - vwap[i]) / av;
      const stop = p.stopAtr * av;
      if (stretch > p.stretchAtr && r[i] > 100 - p.rsiEdge)
        return { side: -1, stopDist: stop, targetDist: stop * p.rr, maxBars: p.maxBars, tag: "fade-short" };
      if (stretch < -p.stretchAtr && r[i] < p.rsiEdge)
        return { side: 1, stopDist: stop, targetDist: stop * p.rr, maxBars: p.maxBars, tag: "fade-long" };
      return null;
    };
  },
};

/**
 * Liquidity-sweep reversal ("stop run").
 *
 * Mechanism: resting stops cluster just beyond obvious swing extremes. A bar that pierces the prior
 * N-bar extreme and closes back INSIDE the range is the signature of those stops being filled
 * against passive size rather than a genuine repricing — the fill itself removes the fuel for
 * continuation. Requires the sweep to be a real excursion (`minPierceAtr`), otherwise every noisy
 * bar qualifies and the rule degenerates into random entries.
 */
export const sweepReversal: Strategy = {
  id: "sweep-reversal",
  label: "Liquidity-sweep reversal",
  family: "liquidity",
  rationale: "A pierce of a swing extreme that closes back inside is stop-run absorption, not repricing.",
  defaults: { lookback: 20, minPierceAtr: 0.25, stopAtr: 1.0, rr: 1.5, maxBars: 16, maxVolPct: 1.0, volLookback: 100 },
  space: {
    lookback: { values: [10, 20, 40] },
    minPierceAtr: { values: [0.1, 0.25, 0.5] },
    stopAtr: { values: [0.75, 1.0, 1.5] },
    rr: { values: [1.0, 1.5, 2.0] },
    maxBars: { values: [8, 16, 32] },
    maxVolPct: { values: [0.7, 1.0] },
    volLookback: { values: [100] },
  },
  build(bars: Bar[], p: Params) {
    const a = atr(bars, 14);
    const volPct = percentRank(a, p.volLookback);
    const n = p.lookback;
    return (i: number): EntryIntent | null => {
      if (i < n) return null;
      const av = a[i];
      if (!Number.isFinite(av) || av <= 0) return null;
      if (Number.isFinite(volPct[i]) && volPct[i] > p.maxVolPct) return null;
      let hi = -Infinity;
      let lo = Infinity;
      for (let j = i - n; j < i; j++) {
        hi = Math.max(hi, bars[j].h);
        lo = Math.min(lo, bars[j].l);
      }
      const b = bars[i];
      const stop = p.stopAtr * av;
      const minPierce = p.minPierceAtr * av;
      if (b.h > hi + minPierce && b.c < hi)
        return { side: -1, stopDist: stop, targetDist: stop * p.rr, maxBars: p.maxBars, tag: "sweep-short" };
      if (b.l < lo - minPierce && b.c > lo)
        return { side: 1, stopDist: stop, targetDist: stop * p.rr, maxBars: p.maxBars, tag: "sweep-long" };
      return null;
    };
  },
};
