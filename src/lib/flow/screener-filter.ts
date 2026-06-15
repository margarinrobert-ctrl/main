import type { ScreenerParams } from "../barchart/endpoints";
import type { OptionContract } from "../barchart/types";

/**
 * Apply screener constraints to normalized contracts. Mirrors the getOptionsScreener
 * params so the UI controls work identically in fixtures mode (where the live API
 * can't pre-filter for us) and tightens live results client-side.
 */
export function applyScreenerFilter(rows: OptionContract[], p: ScreenerParams): OptionContract[] {
  return rows.filter((c) => {
    const vol = c.volume ?? 0;
    const oi = c.openInterest ?? 0;
    if (p.minVolume != null && vol < p.minVolume) return false;
    if (p.minOpenInterest != null && oi < p.minOpenInterest) return false;
    if (p.minDTE != null && (c.dte == null || c.dte < p.minDTE)) return false;
    if (p.maxDTE != null && (c.dte == null || c.dte > p.maxDTE)) return false;
    if (p.minVolumeOpenInterestRatio != null) {
      const voir = oi > 0 ? vol / oi : 0;
      if (voir < p.minVolumeOpenInterestRatio) return false;
    }
    if (p.minDelta != null && (c.delta == null || c.delta < p.minDelta)) return false;
    if (p.maxDelta != null && (c.delta == null || c.delta > p.maxDelta)) return false;
    return true;
  });
}
