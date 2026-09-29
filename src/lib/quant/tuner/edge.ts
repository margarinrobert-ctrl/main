/**
 * Edge diagnostics: the questions to ask BEFORE believing a backtest.
 *
 * A positive net P&L is the weakest evidence in this whole stack. Everything here exists because
 * a number that looks like an edge has, in this repository, repeatedly turned out to be one of
 * four other things — and each of those has a specific test that catches it.
 *
 *   1. NOT CLEARING COSTS. At scalping horizons the cost line is the same order as the signal, so
 *      the first question is how many ticks of forecast a rule needs before it earns anything at
 *      all. That is a property of the geometry and the broker, computable before any rule exists.
 *   2. A WIN RATE WITHOUT ITS BASE RATE. 70% sounds like an edge until you learn a random entry
 *      with the same barriers wins 68%. The driftless bound is 1/(1+R); the REAL base rate is not
 *      that, because costs push it down, a wider barrier pushes it back up, and drift lifts longs
 *      and sinks shorts. It has to be measured, per geometry, from a matched control.
 *   3. A DIRECTION BET WEARING BARRIER CLOTHES. A rule whose profit arrives at the TIME stop is
 *      not exploiting its stop and target at all — it is a bet on drift over a fixed horizon, and
 *      it should be evaluated as one. Splitting P&L by exit reason separates them.
 *   4. THE SEARCH ITSELF. Enough configurations and something wins. The count is carried
 *      everywhere and converted to the threshold a single claim would actually have to clear.
 *
 * Every number here is computed from the same walk that produced the result. Nothing is assumed,
 * and where a quantity cannot be known from OHLCV it is returned as null rather than estimated.
 */
import { pointsToUsd, roundTurnCostPoints, worstRoundTurnCostPoints } from "../instruments";
import type { Instrument } from "../types";
import { REASON, type ControlResult, type WalkStats } from "./tensor";

export interface CostHurdle {
  /** Round-turn cost in ticks, market in / market out, on a median bar. */
  ticks: number;
  usd: number;
  /** The same round turn when the exit is a stop in a fast bar out of session. */
  worstTicks: number;
  /**
   * Ticks the rule must forecast, on average, per trade, purely to break even — which is the
   * round turn. Quoted against the typical bar range so it is comparable across instruments.
   */
  breakEvenTicks: number;
  /** Break-even as a fraction of the median bar range, when a range is supplied. */
  shareOfBar: number | null;
}

export function costHurdle(inst: Instrument, medianBarTicks?: number): CostHurdle {
  const rt = roundTurnCostPoints(inst);
  const ticks = rt / inst.tickSize;
  return {
    ticks,
    usd: pointsToUsd(inst, rt),
    worstTicks: worstRoundTurnCostPoints(inst) / inst.tickSize,
    breakEvenTicks: ticks,
    shareOfBar: medianBarTicks && medianBarTicks > 0 ? ticks / medianBarTicks : null,
  };
}

export interface ExitSplit {
  reason: "stop" | "target" | "time" | "session";
  n: number;
  share: number;
}

/**
 * Where the money came from.
 *
 * `n` per reason is what the walk records. Note what this deliberately does NOT claim: the tensor
 * stores one net figure per trade, so this splits the COUNT of exits, not the dollars, and saying
 * otherwise would be inventing a decomposition the data does not carry. The count is still the
 * diagnostic that matters — a rule exiting mostly on the time stop is a direction bet whatever
 * its dollars say.
 */
export function exitSplit(s: WalkStats): ExitSplit[] {
  const names: ExitSplit["reason"][] = ["stop", "target", "time", "session"];
  const total = Math.max(s.n, 1);
  return names.map((reason, i) => ({ reason, n: s.byReason[i], share: s.byReason[i] / total }));
}

export interface EdgeVerdict {
  /** The measured win rate, and what a matched random entry achieves under the same geometry. */
  winPct: number;
  baseRatePct: number | null;
  /** Measured minus base. This, not the raw win rate, is the quantity with any information in it. */
  excessWinPct: number | null;
  perTrade: number;
  controlPerTrade: number | null;
  excessPerTrade: number | null;
  /** Share of exits at the time/session stop — high means a direction bet, not a barrier edge. */
  timeStopShare: number;
  /** Configurations evaluated, and the Bonferroni threshold one claim would have to clear. */
  searched: number;
  bonferroni: number;
  /** Plain-language flags. Empty means nothing objectionable was found, NOT that it is an edge. */
  warnings: string[];
}

export function verdict(
  s: WalkStats,
  control: ControlResult | null,
  searched: number,
  hurdle: CostHurdle,
): EdgeVerdict {
  const winPct = s.n ? (100 * s.wins) / s.n : 0;
  const perTrade = s.n ? s.netUsd / s.n : 0;
  const split = exitSplit(s);
  const timeStopShare = (split[2].share ?? 0) + (split[3].share ?? 0);
  const baseRatePct = control && Number.isFinite(control.meanWinPct) ? control.meanWinPct : null;
  const controlPerTrade = control ? control.meanAll : null;

  const warnings: string[] = [];
  if (s.n < 30) {
    warnings.push(`${s.n} trades is too few to distinguish from noise at any threshold.`);
  }
  if (baseRatePct !== null && winPct - baseRatePct < 2) {
    warnings.push(
      `Win rate ${winPct.toFixed(1)}% against a base rate of ${baseRatePct.toFixed(1)}% for this exact geometry — ` +
        `the headline number is mostly the barrier placement, not the rule.`,
    );
  }
  if (timeStopShare > 0.5) {
    warnings.push(
      `${Math.round(100 * timeStopShare)}% of exits are at the time or session stop, so this is a bet on drift over a ` +
        `fixed horizon rather than an edge in the stop and target. Evaluate it as one.`,
    );
  }
  if (controlPerTrade !== null && perTrade - controlPerTrade < hurdle.usd * 0.1) {
    warnings.push(
      `Per-trade edge over a matched random entry is $${(perTrade - controlPerTrade).toFixed(2)} against a ` +
        `$${hurdle.usd.toFixed(2)} round turn — thin enough that a wrong cost assumption erases it.`,
    );
  }
  if (searched > 1) {
    warnings.push(
      `${searched.toLocaleString()} configurations were evaluated, so a single claim needs p < ${(0.05 / searched).toExponential(1)} ` +
        `to mean what p < 0.05 usually means. ${(searched * 0.05).toFixed(1)} are expected to clear 0.05 by chance.`,
    );
  }
  return {
    winPct,
    baseRatePct,
    excessWinPct: baseRatePct === null ? null : winPct - baseRatePct,
    perTrade,
    controlPerTrade,
    excessPerTrade: controlPerTrade === null ? null : perTrade - controlPerTrade,
    timeStopShare,
    searched,
    bonferroni: 0.05 / Math.max(searched, 1),
    warnings,
  };
}

/** Median bar range in ticks — the scale the cost hurdle is meaningful against. */
export function medianBarTicks(highs: ArrayLike<number>, lows: ArrayLike<number>, tickSize: number): number {
  const r: number[] = [];
  for (let i = 0; i < highs.length; i++) {
    const v = (highs[i] - lows[i]) / tickSize;
    if (Number.isFinite(v) && v > 0) r.push(v);
  }
  if (!r.length) return 0;
  r.sort((a, b) => a - b);
  return r[Math.floor(r.length / 2)];
}

export { REASON };
