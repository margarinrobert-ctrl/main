import { ncdf } from "./bs";

/**
 * Standard-deviation day bands for 0DTE — the session's expected mean, maximum and minimum.
 *
 * THE ERROR THIS EXISTS TO FIX. Desks quote the ATM straddle as "the expected move", and it is often
 * then drawn as if it were a 1σ band. It is not. For an ATM-forward option the straddle price is the
 * MEAN ABSOLUTE deviation of the terminal price:
 *
 *     straddle = E|S_T − K| = σ·S·√T·√(2/π) ≈ 0.7979·σ·S·√T
 *
 * so ±straddle is a ±0.798σ band, which contains only ~57.5% of outcomes — not the ~68.2% a 1σ band
 * implies. Mixing the two (straddle when quotes exist, IV·√T otherwise) silently changes the meaning of
 * the level by ~25%. Everything here derives from ONE σ, and each band is labeled with the coverage it
 * actually has.
 *
 * Bands provided:
 *   mean   — E[S_T] = the anchor. Under the driftless/martingale convention used throughout this app the
 *            expected close IS the current price; it is the distribution's centre, not a target.
 *   ±61.8% — z = 0.8742, the Fibonacci-flavoured band traders ask for (2Φ(z) − 1 = 0.618).
 *   ±1σ    — z = 1, the day max/min (68.27%).
 *   ±2σ    — z = 2 (95.45%), the tail envelope.
 *
 * Pure — unit-tested.
 */

/** straddle = σS√T·√(2/π); multiply a straddle by this to recover σS√T. */
export const STRADDLE_TO_SIGMA = Math.sqrt(Math.PI / 2); // 1.25331…
/** z with 2Φ(z) − 1 = 0.618 (the 61.8% two-sided band). */
export const Z_618 = 0.8742;

export type BandKey = "p618" | "sd1" | "sd2";

export interface DayBands {
  anchor: number;
  sigmaAbs: number; // σ in price units for the horizon (i.e. σ·S·√T)
  sigmaPct: number;
  source: "straddle" | "iv";
  mean: number;
  bands: { key: BandKey; z: number; coverage: number; hi: number; lo: number; label: string }[];
}

/** Coverage of a two-sided ±z band under the normal law. */
export const coverageOf = (z: number): number => 2 * ncdf(z) - 1;

/**
 * σ (in price units) implied by an ATM straddle price. Inverts straddle = 0.7979·σS√T, so the result
 * is directly comparable to IV·S·√T — which is the whole point.
 */
export function sigmaFromStraddle(straddle: number | null): number | null {
  if (straddle == null || !(straddle > 0)) return null;
  return straddle * STRADDLE_TO_SIGMA;
}

/** σ (price units) for one session from an annualized IV. */
export function sigmaFromIv(spot: number | null, annualIv: number | null, tradingDays = 252): number | null {
  if (spot == null || !(spot > 0) || annualIv == null || !(annualIv > 0)) return null;
  return spot * (annualIv / Math.sqrt(tradingDays));
}

/**
 * Build the day's bands around an anchor. Prefer the straddle (market-implied, converted to a true σ)
 * and fall back to IV — either way the returned σ means the same thing.
 */
export function dayBands(anchor: number | null, straddle: number | null, annualIv: number | null, tradingDays = 252): DayBands | null {
  if (anchor == null || !(anchor > 0)) return null;
  const fromStraddle = sigmaFromStraddle(straddle);
  const sigmaAbs = fromStraddle ?? sigmaFromIv(anchor, annualIv, tradingDays);
  if (sigmaAbs == null || !(sigmaAbs > 0)) return null;
  const source: "straddle" | "iv" = fromStraddle != null ? "straddle" : "iv";

  const spec: { key: BandKey; z: number }[] = [
    { key: "p618", z: Z_618 },
    { key: "sd1", z: 1 },
    { key: "sd2", z: 2 },
  ];

  return {
    anchor,
    sigmaAbs,
    sigmaPct: sigmaAbs / anchor,
    source,
    mean: anchor,
    bands: spec.map(({ key, z }) => {
      const cov = coverageOf(z);
      return {
        key,
        z,
        coverage: cov,
        hi: anchor + z * sigmaAbs,
        lo: anchor - z * sigmaAbs,
        label: key === "p618" ? "61.8%" : key === "sd1" ? "1σ" : "2σ",
      };
    }),
  };
}
