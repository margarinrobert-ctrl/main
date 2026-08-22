import type { Instrument } from "./types";

// Instrument specs. Tick sizes and tick values are exchange facts; spreads, slippage and
// commissions are retail-realistic *assumptions* and are the single most important input to a
// scalping study — at a 5-minute horizon the cost line is usually larger than the raw edge.
// Every number here is overridable per study, and `costSensitivity()` reports how much of the
// result survives if these are wrong by 2x.

const DEFAULTS = { barsPerDay: 78, daysPerYear: 252 };

export const INSTRUMENTS: Record<string, Instrument> = {
  XAUUSD: {
    id: "XAUUSD",
    label: "Spot gold (100 oz lot)",
    tickSize: 0.01,
    tickValue: 1.0, // $0.01 x 100 oz
    spreadTicks: 20, // 20c typical retail spread; tightens to ~12c in the London/NY overlap
    slippageTicks: 5,
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
    slippageTicks: 0.5,
    commissionRoundTurn: 4.5,
    tz: "America/New_York", session: [180, 1020],
    ...DEFAULTS,
  },
  MGC: {
    id: "MGC",
    label: "Micro gold future (10 oz)",
    tickSize: 0.1,
    tickValue: 1.0,
    spreadTicks: 1,
    slippageTicks: 1,
    commissionRoundTurn: 1.5,
    tz: "America/New_York", session: [180, 1020],
    ...DEFAULTS,
  },
  CL: {
    id: "CL",
    label: "WTI crude future (1,000 bbl)",
    tickSize: 0.01,
    tickValue: 10.0,
    spreadTicks: 1,
    slippageTicks: 1,
    commissionRoundTurn: 4.5,
    tz: "America/New_York", session: [540, 870], // 09:00-14:30 ET pit hours; CL liquidity dies outside them
    ...DEFAULTS,
  },
  MCL: {
    id: "MCL",
    label: "Micro WTI crude future (100 bbl)",
    tickSize: 0.01,
    tickValue: 1.0,
    spreadTicks: 1,
    slippageTicks: 1.5,
    commissionRoundTurn: 1.5,
    tz: "America/New_York", session: [540, 870],
    ...DEFAULTS,
  },
  ES: {
    id: "ES",
    label: "E-mini S&P 500",
    tickSize: 0.25,
    tickValue: 12.5,
    spreadTicks: 1,
    slippageTicks: 0.25,
    commissionRoundTurn: 4.0,
    tz: "America/New_York", session: [570, 960], // 09:30-16:00 ET regular trading hours
    ...DEFAULTS,
  },
  NQ: {
    id: "NQ",
    label: "E-mini Nasdaq 100",
    tickSize: 0.25,
    tickValue: 5.0,
    spreadTicks: 1,
    slippageTicks: 1,
    commissionRoundTurn: 4.0,
    tz: "America/New_York", session: [570, 960], // 09:30-16:00 ET regular trading hours
    ...DEFAULTS,
  },
};

export function instrument(id: string): Instrument {
  const inst = INSTRUMENTS[id.toUpperCase()];
  if (!inst) throw new Error(`unknown instrument ${id} (known: ${Object.keys(INSTRUMENTS).join(", ")})`);
  return { ...inst };
}

/** Round-turn cost for one unit, in PRICE units — spread crossed once, slippage both sides. */
export function roundTurnCostPoints(inst: Instrument): number {
  const spread = inst.spreadTicks * inst.tickSize;
  const slip = 2 * inst.slippageTicks * inst.tickSize;
  const commission = inst.commissionRoundTurn / (inst.tickValue / inst.tickSize);
  return spread + slip + commission;
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
