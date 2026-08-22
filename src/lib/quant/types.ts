import type { ExchangeTz } from "./clock";

// Core types for the systematic futures research stack.
//
// Everything downstream — strategies, backtester, statistics, portfolio — speaks these types.
// Bars are UTC-epoch-millisecond stamped; prices are in the instrument's quote units.

export interface Bar {
  /** Bar OPEN time, epoch ms, UTC. Bars are left-labelled and non-overlapping. */
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

/** Contract / CFD specification. Costs are the honest, retail-realistic defaults. */
export interface Instrument {
  id: string;
  label: string;
  /** Minimum price increment. */
  tickSize: number;
  /** USD P&L of one tick for one unit (contract / lot). */
  tickValue: number;
  /** Typical quoted bid-ask in ticks during the strategy's session. */
  spreadTicks: number;
  /** Extra adverse fill, in ticks, per side — the market-order tax beyond half-spread. */
  slippageTicks: number;
  /** USD commission for a round turn of one unit. */
  commissionRoundTurn: number;
  /** Exchange wall clock the session is defined in. */
  tz: ExchangeTz;
  /** Local trading window as [startMinuteOfDay, endMinuteOfDay) — e.g. [570, 960] is 09:30-16:00. */
  session: [number, number];
  /** Bars per trading day at the research timeframe — set by the loader. */
  barsPerDay: number;
  /** Trading days per year for annualisation. */
  daysPerYear: number;
}

export type Side = 1 | -1;

/** What a strategy wants to do at the close of bar `i`, executed at the open of `i+1`. */
export interface EntryIntent {
  side: Side;
  /** Protective stop distance in price units (must be > 0). */
  stopDist: number;
  /** Profit target distance in price units (must be > 0). */
  targetDist: number;
  /** Hard time stop, in bars held. */
  maxBars: number;
  tag?: string;
}

export type ExitReason = "stop" | "target" | "time" | "session" | "eod";

export interface Trade {
  side: Side;
  entryIndex: number;
  exitIndex: number;
  entryTime: number;
  exitTime: number;
  entryPx: number;
  exitPx: number;
  /** Gross price move in the trade's favour, in price units. */
  grossPoints: number;
  /** Round-turn cost charged to this trade, in price units. */
  costPoints: number;
  /** Net USD P&L for one unit. */
  pnl: number;
  /** Net P&L expressed in units of the initial risk (stop distance) — the R multiple. */
  r: number;
  barsHeld: number;
  reason: ExitReason;
  tag?: string;
}

export interface ParamRange {
  /** Inclusive grid of values this parameter is searched over. */
  values: number[];
}

export type Params = Record<string, number>;
export type ParamSpace = Record<string, ParamRange>;

export interface Strategy {
  id: string;
  label: string;
  /** Economic family — used to keep a portfolio from stacking near-duplicates. */
  family: "breakout" | "mean-reversion" | "momentum" | "liquidity" | "seasonality";
  /** One-line statement of the economic mechanism the edge is supposed to come from. */
  rationale: string;
  defaults: Params;
  space: ParamSpace;
  /**
   * Precompute indicators once, then answer "what do you want at bar i?".
   * The returned closure MUST NOT read bars beyond `i` — that is the look-ahead contract,
   * and it is enforced by a test that truncates the series and re-checks decisions.
   */
  build(bars: Bar[], params: Params, inst: Instrument): (i: number) => EntryIntent | null;
}
