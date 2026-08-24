import type { ExchangeTz } from "./clock";
import type { FeeSchedule, SlippageModel } from "./costs";

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
  /**
   * USD commission for a round turn of one unit.
   *
   * Retained as the headline figure and as the fallback for instruments that have not been given a
   * `fees` breakdown, but `fees` is the authority when present. Keep the two consistent:
   * `commissionRoundTurn` should equal `feesRoundTurn(fees)`, and `instruments.test.ts` asserts it.
   */
  commissionRoundTurn: number;
  /**
   * The itemised per-side charges behind `commissionRoundTurn`. Present on every instrument that
   * has been costed properly; absent means the lumped number is all that is known, and
   * `legacyFees` reads it as broker commission with no exchange or regulatory line — which
   * understates the truth. See `costs.ts`.
   */
  fees?: FeeSchedule;
  /**
   * How slippage behaves. Omitted means a flat `slippageTicks` on every fill, which is the
   * assumption that most flatters a stop-loss strategy. See `costs.ts`.
   */
  slippage?: SlippageModel;
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
  /** Protective stop distance in price units (must be > 0). Ignored when `stopPrice` is set. */
  stopDist: number;
  /** Profit target distance in price units (must be > 0). Ignored when `targetPrice` is set. */
  targetDist: number;
  /** Hard time stop, in bars held. */
  maxBars: number;
  /**
   * Rest a LIMIT order at this absolute price instead of taking the next open.
   *
   * Some strategies are defined by a price that has to come to you — a retracement entry after a
   * breakout, for instance — and modelling that as a market order at the next open measures a
   * completely different trade. The order works until it fills, `validBars` elapses, or the
   * session ends.
   */
  limitPrice?: number;
  /** Bars a resting limit stays working before it is cancelled. Defaults to the rest of the session. */
  validBars?: number;
  /** Absolute stop price. Takes precedence over `stopDist` — used when the level is structural. */
  stopPrice?: number;
  /** Absolute target price. Takes precedence over `targetDist`. */
  targetPrice?: number;
  /**
   * Optional per-bar hold predicate. While it returns true the position stays open; the first bar
   * it returns false, the position is closed at that bar's close with reason `signal`.
   *
   * This exists because a whole family of strategies is defined by its EXIT rather than by a target
   * — a moving-average system is "long while fast is above slow", and forcing it into a fixed
   * stop-and-target measures a different strategy that happens to share an entry. Like the entry
   * signal, the predicate may only read bars up to `i`.
   */
  holdWhile?: (i: number) => boolean;
  tag?: string;
}

export type ExitReason = "stop" | "target" | "time" | "session" | "eod" | "signal";

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
