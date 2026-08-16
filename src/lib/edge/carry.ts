import type { OptionContract } from "../barchart/types";
import { ivTermStructure } from "../flow/analytics";

/**
 * Volatility term-structure carry engine.
 *
 * The IV term structure is usually upward-sloping (contango): near-dated vol is cheaper than far-dated,
 * because most days are quiet and the far tenor carries more event/uncertainty. Two documented edges live
 * here:
 *   1. Carry / roll-down — a long vega position further out the curve "rolls down" to cheaper vol as time
 *      passes (you sell what decays slower, hedge with what decays faster). Steeper contango = more carry.
 *   2. Backwardation as a signal — when the front is RICHER than the back (inverted), the market is pricing
 *      a near-term event (earnings, macro). Selling the front / calendars harvests the crush — but a gap
 *      through the strike is the risk.
 *
 * Slope is measured in annualized vol points between the front usable tenor and a ~1–3 month back tenor.
 * Pure — unit-tested. Educational — not advice.
 */

export type CarrySide = "sell-front" | "sell-vol" | "neutral";

export interface CarryRead {
  front: { dte: number; iv: number } | null;
  back: { dte: number; iv: number } | null;
  slopeVolPts: number | null; // back IV − front IV (annualized vol points)
  slopePctPerMonth: number | null; // normalized slope per 30 DTE
  shape: "contango" | "backwardation" | "flat" | "n/a";
  rollDownVolPtsPerWeek: number | null; // roll-down P&L to a LONG-vega back-tenor position per week, static curve (<0 in contango: long vol pays the carry; the short earns it)
  side: CarrySide;
  conviction: number; // 0..100
  notes: string[];
}

const clamp = (x: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, x));
const pct = (n: number | null) => (n == null ? "—" : `${(n * 100).toFixed(1)}%`);

export function carryEngine(chain: OptionContract[], spot: number | null): CarryRead {
  const base: CarryRead = { front: null, back: null, slopeVolPts: null, slopePctPerMonth: null, shape: "n/a", rollDownVolPtsPerWeek: null, side: "neutral", conviction: 0, notes: [] };
  if (!chain.length) {
    base.notes.push("No chain for a term structure.");
    return base;
  }

  const term = ivTermStructure(chain, spot)
    .filter((x): x is { expiration: string; dte: number; iv: number } => x.iv != null && x.dte != null && x.dte >= 0 && x.iv > 0)
    .sort((a, b) => a.dte - b.dte);

  if (term.length < 2) {
    base.notes.push("Need ≥2 expirations with IV to measure the curve.");
    return base;
  }

  const front = term[0];
  // pick a back tenor ~30–90 DTE for a stable slope; else the furthest available
  const back = term.find((x) => x.dte >= 25 && x.dte <= 100) ?? term[term.length - 1];
  if (back.dte <= front.dte) {
    base.front = { dte: front.dte, iv: front.iv };
    base.notes.push("Only a single usable tenor — no slope.");
    return base;
  }

  const slope = back.iv - front.iv; // annualized vol points
  const dteGap = back.dte - front.dte;
  const slopePerMonth = (slope / dteGap) * 30;
  const shape: CarryRead["shape"] = slope > 0.01 ? "contango" : slope < -0.01 ? "backwardation" : "flat";

  // Roll-down to a LONG-vega back-tenor position on a static curve: as the option ages its DTE falls and
  // it re-marks toward the FRONT IV. In contango (front < back) that is a mark-DOWN → a cost to long vega,
  // so the favorable roll-down accrues to the SHORT (the VIX-futures-roll logic). In backwardation the
  // long earns it. Signed for the long-vega owner.
  const rollDownLongVega = -(slope / dteGap) * 7;

  let side: CarrySide = "neutral";
  const notes: string[] = [];
  if (shape === "backwardation") {
    side = "sell-front";
    notes.push(`Backwardated: front ${pct(front.iv)} > back ${pct(back.iv)} — the market is pricing a near-term event. Selling the ${front.dte}d premium or a calendar (short front / long back) harvests the crush; a binary gap through the strike is the risk.`);
  } else if (shape === "contango") {
    side = "sell-vol";
    notes.push(`Contango: back ${pct(back.iv)} ≥ front ${pct(front.iv)} (slope +${(slope * 100).toFixed(1)}vp over ${dteGap}d). Normal regime — vol carry favors SELLERS: a short-the-curve position harvests ~${(Math.abs(rollDownLongVega) * 100).toFixed(2)}vp/week of roll-down as options age down the upward curve, while a long-vega position PAYS that carry.`);
  } else {
    notes.push("Flat term structure — no carry edge; the vol trade is level (VRP), not slope.");
  }

  // Conviction from |slope per month|, capped; steep curves are higher-confidence carry.
  const conviction = Math.round(clamp(Math.abs(slopePerMonth) / 0.06, 0, 1) * 100);

  return {
    front: { dte: front.dte, iv: front.iv },
    back: { dte: back.dte, iv: back.iv },
    slopeVolPts: slope,
    slopePctPerMonth: slopePerMonth,
    shape,
    rollDownVolPtsPerWeek: rollDownLongVega,
    side,
    conviction,
    notes,
  };
}
