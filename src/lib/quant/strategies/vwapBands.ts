import { clockFor } from "../clock";
import { atr, closes, percentRank, rollingVwapBands, sessionVwapBands } from "../series";
import type { Bar, EntryIntent, Instrument, Params, Strategy } from "../types";

/**
 * VWAP band mean reversion, parameterised over the band construction itself.
 *
 * Mechanism: VWAP is the benchmark execution price for anyone working size, so flow is mechanically
 * attracted back toward it — a desk that has bought above VWAP is losing against its own benchmark
 * and has an incentive to wait rather than chase. A stretch away from VWAP is therefore a temporary
 * imbalance that the same flow tends to correct, and the natural TARGET of the trade is VWAP itself
 * rather than an arbitrary reward multiple.
 *
 * The parameterisation exists because "VWAP bands" means two different things and people rarely say
 * which:
 *   - bandType 0: volume-weighted sigma. Dispersion of typical price around VWAP so far this
 *     session, weighted by volume. This is the classical construction.
 *   - bandType 1: ATR. VWAP plus a multiple of average true range — knows about bar size, knows
 *     nothing about where volume traded.
 *   - bandType 2: the wider of the two, so a stretch has to be extreme on both measures.
 *
 * And because the entry has a second choice that matters more than the band:
 *   - confirm 0: act as soon as price closes beyond the band (catching a knife).
 *   - confirm 1: wait for a close back INSIDE the band (the stretch is already failing).
 */
export const vwapBands: Strategy = {
  id: "vwap-bands",
  label: "VWAP band mean reversion (sigma / ATR bands)",
  family: "mean-reversion",
  rationale:
    "VWAP is the execution benchmark for size, so flow is drawn back to it; a stretch away is a temporary imbalance whose natural target is VWAP itself.",
  defaults: { bandType: 0, bandK: 2, confirm: 1, stopMode: 0, stopK: 1, targetMode: 0, targetFrac: 100, maxVolPct: 100, maxBars: 24, sideMode: 0, minMinutes: 0, anchorBars: 0 },
  space: {
    /** 0 = volume-weighted sigma, 1 = ATR, 2 = the wider of the two. */
    bandType: { values: [0, 1, 2] },
    /** Band distance from VWAP, in units of the chosen measure. */
    bandK: { values: [1.5, 2, 2.5, 3] },
    /** 0 = enter on the close beyond the band, 1 = wait for a close back inside it. */
    confirm: { values: [0, 1] },
    /** 0 = stop at the band `stopK` further out, 1 = stop at `stopK` x ATR from entry. */
    stopMode: { values: [0, 1] },
    stopK: { values: [0.75, 1, 1.5, 2] },
    /** 0 = target VWAP itself, 1 = a fraction of the distance to VWAP. */
    targetMode: { values: [0, 1] },
    targetFrac: { values: [50, 75, 100] },
    /** Skip when realised volatility is in the upper percentiles — do not fade a trend day. */
    maxVolPct: { values: [60, 80, 100] },
    maxBars: { values: [12, 24, 48] },
    sideMode: { values: [0, 1, -1] },
    /** Minutes into the session before the bands are trusted; VWAP is meaningless on bar one. */
    minMinutes: { values: [0, 30, 60] },
    /** 0 = session-anchored VWAP; N = rolling N-bar VWAP, so the anchor matches the reversion horizon. */
    anchorBars: { values: [0, 12, 20, 40] },
  },
  build(bars: Bar[], p: Params, inst: Instrument) {
    const clock = clockFor(bars, inst.tz);
    const c = closes(bars);
    const a = atr(bars, 14);
    const { vwap, sigma } = p.anchorBars > 0 ? rollingVwapBands(bars, Math.round(p.anchorBars)) : sessionVwapBands(bars, clock.dayIndex);
    const volPct = percentRank(a, 100);
    const sessionStart = inst.session[0];

    return (i: number): EntryIntent | null => {
      const av = a[i];
      const vw = vwap[i];
      if (!Number.isFinite(av) || av <= 0 || !Number.isFinite(vw)) return null;
      if (clock.minuteOfDay[i] - sessionStart < p.minMinutes) return null;
      if (p.maxVolPct < 100 && Number.isFinite(volPct[i]) && volPct[i] * 100 > p.maxVolPct) return null;

      // The band width, in price units, under whichever construction is selected.
      const bySigma = sigma[i] * p.bandK;
      const byAtr = av * p.bandK;
      const width = p.bandType === 0 ? bySigma : p.bandType === 1 ? byAtr : Math.max(bySigma, byAtr);
      if (!(width > 0)) return null;

      const upper = vw + width;
      const lower = vw - width;

      let side: 1 | -1 | 0 = 0;
      if (p.confirm === 0) {
        // Fade the stretch the moment it happens.
        if (c[i] > upper) side = -1;
        else if (c[i] < lower) side = 1;
      } else {
        // Wait for the stretch to fail: the previous bar closed beyond the band, this one closed back inside.
        if (i < 1) return null;
        const prevUpper = vwap[i - 1] + (p.bandType === 0 ? sigma[i - 1] * p.bandK : p.bandType === 1 ? a[i - 1] * p.bandK : Math.max(sigma[i - 1] * p.bandK, a[i - 1] * p.bandK));
        const prevLower = vwap[i - 1] - (p.bandType === 0 ? sigma[i - 1] * p.bandK : p.bandType === 1 ? a[i - 1] * p.bandK : Math.max(sigma[i - 1] * p.bandK, a[i - 1] * p.bandK));
        if (!Number.isFinite(prevUpper)) return null;
        if (c[i - 1] > prevUpper && c[i] <= upper) side = -1;
        else if (c[i - 1] < prevLower && c[i] >= lower) side = 1;
      }
      if (side === 0) return null;
      if (p.sideMode !== 0 && p.sideMode !== side) return null;

      const entry = c[i];
      const distanceToVwap = Math.abs(entry - vw);
      if (distanceToVwap < inst.tickSize) return null;

      // The band-based stop sits beyond the band — but on a knife-catch entry price has already
      // closed well past the band, so the band-derived level can land on the WRONG SIDE of the
      // entry and stop the trade out instantly. Clamp it to always be at least half an ATR beyond
      // the fill. Without this the variant reports a 1-4% win rate, which is a bug reading as a
      // finding.
      const bandStop = side === 1 ? lower - width * (p.stopK - 1) - av * 0.25 : upper + width * (p.stopK - 1) + av * 0.25;
      const clamped = side === 1 ? Math.min(bandStop, entry - av * 0.5) : Math.max(bandStop, entry + av * 0.5);
      const stopPrice = p.stopMode === 0 ? clamped : entry - side * av * p.stopK;
      const targetPrice = p.targetMode === 0 ? vw : entry + side * distanceToVwap * (p.targetFrac / 100);

      const stopDist = Math.abs(entry - stopPrice);
      const targetDist = Math.abs(targetPrice - entry);
      if (stopDist < inst.tickSize || targetDist < inst.tickSize) return null;

      return {
        side,
        stopPrice,
        targetPrice,
        stopDist,
        targetDist,
        maxBars: p.maxBars,
        tag: `vwap-${p.bandType}-${side === 1 ? "long" : "short"}`,
      };
    };
  },
};
