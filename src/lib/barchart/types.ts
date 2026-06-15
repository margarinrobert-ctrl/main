export type OptionType = "call" | "put";

export type DataOrigin = "live" | "fixtures";

export interface NormalizedQuote {
  symbol: string;
  name: string | null;
  last: number | null;
  netChange: number | null;
  percentChange: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  previousClose: number | null;
  volume: number | null;
  tradeTimestamp: string | null;
  mode: string | null;
  delayed: boolean | null;
}

export interface HistoryBar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface OptionContract {
  symbol: string;
  underlying: string;
  type: OptionType;
  strike: number;
  expiration: string;
  dte: number | null;
  bid: number | null;
  ask: number | null;
  last: number | null;
  volume: number | null;
  openInterest: number | null;
  impliedVolatility: number | null;
  delta: number | null;
  gamma: number | null;
  theta: number | null;
  vega: number | null;
  underlyingPrice: number | null;
}
