import { CALM, feePoints, feesRoundTurn, fillCostPoints, REALISTIC_SLIPPAGE, scheduleFor } from "./costs";
import type { Instrument } from "./types";

// Instrument specs. Tick sizes and tick values are exchange FACTS; spreads, slippage and
// commissions are retail-realistic *assumptions* and are the single most important input to a
// scalping study — at a 5-minute horizon the cost line is usually larger than the raw edge.
//
// Fees are no longer one lumped number. Each instrument carries an itemised `FeeSchedule` —
// broker, exchange, clearing, regulatory, each per side — built by `scheduleFor` from the
// discount-broker preset and the CME schedule in `costs.ts`, and `commissionRoundTurn` is DERIVED
// from it so the two cannot drift apart. Slippage is a model rather than a constant, because the
// flat tick is charged in the calm bars where it is not paid and understated in the fast ones
// where it is.
//
// Every number is overridable per study, and `costSensitivity()` reports how much of a result
// survives if these are wrong by 2x — which, given they are assumptions, is the number to trust.

const DEFAULTS = { barsPerDay: 78, daysPerYear: 252 };

/**
 * Slippage for one instrument, keyed on its own quiet-market cost in ticks.
 *
 * `slippageTicks` is DERIVED from the model's base rather than set alongside it, so the headline
 * and the detail cannot drift apart -- the same relationship `commissionRoundTurn` has to `fees`.
 * `effectiveSlippage` relies on that equality to tell a deliberate override from a stale field.
 */
function slip(base: number) {
  return { slippage: { ...REALISTIC_SLIPPAGE, base }, slippageTicks: base };
}

/** Build the fee block and the derived round-turn commission for one instrument id. */
function costed(id: string, broker = "discount") {
  const fees = scheduleFor(id, broker);
  return { fees, commissionRoundTurn: feesRoundTurn(fees) };
}

export const INSTRUMENTS: Record<string, Instrument> = {
  XAUUSD: {
    id: "XAUUSD",
    label: "Spot gold (100 oz lot)",
    tickSize: 0.01,
    tickValue: 1.0, // $0.01 x 100 oz
    spreadTicks: 20, // 20c typical retail spread; tightens to ~12c in the London/NY overlap
    ...slip(5),
    commissionRoundTurn: 7.0, // ECN-style; 0 on spread-only accounts, but then widen spreadTicks
    tz: "America/New_York", session: [180, 1020], // 03:00-17:00 ET: London open through the NY afternoon
    ...DEFAULTS,
  },
  GC: {
    id: "GC",
    label: "COMEX gold future (100 oz)",
    tickSize: 0.1,
    tickValue: 10.0,
    spreadTicks: 1,
    ...slip(0.5),
    ...costed("GC"),
    tz: "America/New_York", session: [180, 1020],
    ...DEFAULTS,
  },
  MGC: {
    id: "MGC",
    label: "Micro gold future (10 oz)",
    tickSize: 0.1,
    tickValue: 1.0,
    spreadTicks: 1,
    ...slip(1),
    ...costed("MGC"),
    tz: "America/New_York", session: [180, 1020],
    ...DEFAULTS,
  },
  CL: {
    id: "CL",
    label: "WTI crude future (1,000 bbl)",
    tickSize: 0.01,
    tickValue: 10.0,
    spreadTicks: 1,
    ...slip(1),
    ...costed("CL"),
    tz: "America/New_York", session: [540, 870], // 09:00-14:30 ET pit hours; CL liquidity dies outside them
    ...DEFAULTS,
  },
  MCL: {
    id: "MCL",
    label: "Micro WTI crude future (100 bbl)",
    tickSize: 0.01,
    tickValue: 1.0,
    spreadTicks: 1,
    ...slip(1.5),
    ...costed("MCL"),
    tz: "America/New_York", session: [540, 870],
    ...DEFAULTS,
  },
  ES: {
    id: "ES",
    label: "E-mini S&P 500",
    tickSize: 0.25,
    tickValue: 12.5,
    spreadTicks: 1,
    ...slip(0.25),
    ...costed("ES"),
    tz: "America/New_York", session: [570, 960], // 09:30-16:00 ET regular trading hours
    ...DEFAULTS,
  },
  NQ: {
    id: "NQ",
    label: "E-mini Nasdaq 100",
    tickSize: 0.25,
    tickValue: 5.0,
    spreadTicks: 1,
    ...slip(1),
    ...costed("NQ"),
    tz: "America/New_York", session: [570, 960], // 09:30-16:00 ET regular trading hours
    ...DEFAULTS,
  },
  // The micro. Same tick size and the same one-tick spread, but a tenth of the tick value against a
  // commission that only falls by a factor of three — so the round turn costs 1.42 points instead of
  // NQ's 0.95, half as much edge again. Prop-firm evaluations at $50k are usually traded here, which
  // is exactly where that 50% cost premium does the most damage.
  MNQ: {
    id: "MNQ",
    label: "Micro E-mini Nasdaq 100",
    tickSize: 0.25,
    tickValue: 0.5,
    spreadTicks: 1,
    ...slip(1),
    ...costed("MNQ"),
    tz: "America/New_York", session: [570, 960],
    ...DEFAULTS,
  },
};

export function instrument(id: string): Instrument {
  const inst = INSTRUMENTS[id.toUpperCase()];
  if (!inst) throw new Error(`unknown instrument ${id} (known: ${Object.keys(INSTRUMENTS).join(", ")})`);
  return { ...inst };
}

/** Cost of TAKING liquidity on one side, in price units: fees, half the spread, and slippage. */
export function takerSideCostPoints(inst: Instrument): number {
  return fillCostPoints(inst, "taker", CALM);
}

/** Per-side fees for a round turn, expressed in price units. */
export function commissionPoints(inst: Instrument): number {
  return 2 * feePoints(inst);
}

/**
 * The REFERENCE round turn, in price units: market in, market out, on a median bar, in session.
 *
 * This is the headline "what does it cost to trade" number, and it is deliberately the calm
 * taker/taker case rather than the worst case — it is what a study quotes when it asks whether an
 * edge can clear costs at all, and quoting a worst case there would understate what is possible
 * just as badly as a best case overstates it. What a trade ACTUALLY pays is computed per fill from
 * the bar it landed on, and for a stopped-out trade in a fast market it is materially more than
 * this. Both numbers are real; they answer different questions.
 */
export function roundTurnCostPoints(inst: Instrument): number {
  return 2 * fillCostPoints(inst, "taker", CALM);
}

/** The pessimistic round turn: market in, STOPPED out, in a bar running at the model's cap. */
export function worstRoundTurnCostPoints(inst: Instrument): number {
  const fast = { volRatio: 1e9, inSession: false };
  return fillCostPoints(inst, "taker", fast) + fillCostPoints(inst, "stop", fast);
}

/** Same cost expressed in ticks — the number that decides whether a scalp can exist at all. */
export function roundTurnCostTicks(inst: Instrument): number {
  return roundTurnCostPoints(inst) / inst.tickSize;
}

export function pointsToUsd(inst: Instrument, points: number): number {
  return (points / inst.tickSize) * inst.tickValue;
}

/** Snap a price to the instrument's tick grid, away from the trader (conservative). */
export function snap(inst: Instrument, px: number, dir: -1 | 1): number {
  const n = px / inst.tickSize;
  const k = dir > 0 ? Math.ceil(n - 1e-9) : Math.floor(n + 1e-9);
  return Number((k * inst.tickSize).toFixed(10));
}
