import type { OptionContract } from "../barchart/types";

// Barchart-style "Options Flow" model. Each chain contract becomes a flow row (sorted by $ premium),
// and the book rolls up into the two Barchart header gauges: Net Trade Sentiment (bullish vs bearish
// $ premium) and Delta Imbalance (call vs put delta-weighted volume).
//
// Honest note on granularity: Barchart's site shows a per-PRINT tape (single-trade price/size/exchange
// code/time) from a premium feed. The OnDemand API the app integrates returns the aggregate chain, so
// each row is one contract: Trade = last, Premium = volume × mid × 100 (the day's traded premium), and
// Side is inferred from where the last print sits in the bid/ask. With BARCHART_API_KEY the chain comes
// straight from Barchart; otherwise CBOE (~15-min delayed) / fixtures.

export type FlowSide = "ASK" | "BID" | "MID" | "—";

export interface FlowRow {
  contract: string;
  underlying: string;
  price: number | null; // underlying spot
  type: "call" | "put";
  strike: number;
  expiration: string;
  dte: number | null;
  bid: number | null;
  ask: number | null;
  trade: number | null; // last
  premium: number; // volume × mid × 100
  volume: number;
  openInterest: number;
  iv: number | null;
  delta: number | null;
  side: FlowSide; // last vs bid/ask
  bullish: boolean | null; // directional read of the trade (call-at-ask / put-at-bid = bullish)
}

export interface FlowSentiment {
  netPremium: number; // bullish − bearish $ premium
  bullPremium: number; // total bullish $ (≥0)
  bearPremium: number; // total bearish $ (≤0)
  deltaImbalance: number; // call + put delta-weighted volume (signed)
  callDelta: number; // Σ call delta × vol × 100 (≥0)
  putDelta: number; // Σ put delta × vol × 100 (≤0)
  callPremium: number;
  putPremium: number;
}

export interface OptionsFlow {
  rows: FlowRow[];
  sentiment: FlowSentiment;
}

const CONTRACT = 100;
function mid(c: OptionContract): number | null {
  if (c.bid != null && c.ask != null && c.ask > 0) return (c.bid + c.ask) / 2;
  return c.last != null && c.last > 0 ? c.last : null;
}

/** Where the last print sits in the spread → AT ASK (aggressive buy) / AT BID (aggressive sell) / MID. */
function classifySide(c: OptionContract): FlowSide {
  if (c.last == null || c.bid == null || c.ask == null || c.ask <= 0 || c.ask < c.bid) return "—";
  const span = c.ask - c.bid;
  if (span <= 0) return "MID";
  if (c.last >= c.ask - span * 0.15) return "ASK";
  if (c.last <= c.bid + span * 0.15) return "BID";
  return "MID";
}

export interface OptionsFlowOpts {
  minPremium?: number; // drop rows below this $ premium
  limit?: number; // cap rows (sorted by premium desc)
}

/** Build the Barchart-style flow rows + sentiment gauges from an options chain. */
export function optionsFlow(chain: OptionContract[], spot: number | null, opts: OptionsFlowOpts = {}): OptionsFlow {
  const minPremium = opts.minPremium ?? 0;
  const rows: FlowRow[] = [];
  let bullPremium = 0;
  let bearPremium = 0;
  let callDelta = 0;
  let putDelta = 0;
  let callPremium = 0;
  let putPremium = 0;

  for (const c of chain) {
    const volume = c.volume ?? 0;
    if (volume <= 0) continue;
    const m = mid(c);
    const premium = m != null ? volume * m * CONTRACT : 0;
    if (premium < minPremium) continue;

    const side = classifySide(c);
    // directional read: buying calls / selling puts = bullish; buying puts / selling calls = bearish
    const aggr = side === "ASK" ? 1 : side === "BID" ? -1 : 0;
    const dir = c.type === "call" ? aggr : -aggr;
    const bullish = dir === 0 ? null : dir > 0;

    if (dir > 0) bullPremium += premium;
    else if (dir < 0) bearPremium -= premium; // accumulate as negative
    if (c.type === "call") callPremium += premium;
    else putPremium += premium;
    if (c.delta != null) {
      const dex = c.delta * volume * CONTRACT;
      if (c.type === "call") callDelta += dex;
      else putDelta += dex;
    }

    rows.push({
      contract: c.symbol,
      underlying: c.underlying,
      price: c.underlyingPrice ?? spot,
      type: c.type,
      strike: c.strike,
      expiration: c.expiration,
      dte: c.dte,
      bid: c.bid,
      ask: c.ask,
      trade: c.last,
      premium,
      volume,
      openInterest: c.openInterest ?? 0,
      iv: c.impliedVolatility,
      delta: c.delta,
      side,
      bullish,
    });
  }

  rows.sort((a, b) => b.premium - a.premium);
  const limited = opts.limit ? rows.slice(0, opts.limit) : rows;

  return {
    rows: limited,
    sentiment: {
      netPremium: bullPremium + bearPremium,
      bullPremium,
      bearPremium,
      deltaImbalance: callDelta + putDelta,
      callDelta,
      putDelta,
      callPremium,
      putPremium,
    },
  };
}
