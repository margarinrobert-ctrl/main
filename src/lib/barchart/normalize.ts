import {
  historyResponseSchema,
  optionsResponseSchema,
  quoteResponseSchema,
  type RawOption,
  type RawQuote,
} from "./schemas";
import type { HistoryBar, NormalizedQuote, OptionContract, OptionType } from "./types";

/**
 * Pure, browser-safe normalization (zod + plain objects, no node:fs).
 * Shared by the server endpoints and the client-side static data layer.
 */

export function isDelayed(mode: string | null | undefined): boolean | null {
  if (!mode) return null;
  const m = mode.toLowerCase();
  if (m.startsWith("d")) return true;
  if (m.startsWith("r") || m.startsWith("i")) return false;
  return null;
}

export function normalizeQuote(r: RawQuote): NormalizedQuote {
  return {
    symbol: r.symbol,
    name: r.name ?? null,
    last: r.lastPrice,
    netChange: r.netChange,
    percentChange: r.percentChange,
    open: r.open,
    high: r.high,
    low: r.low,
    previousClose: r.previousClose,
    volume: r.volume,
    tradeTimestamp: r.tradeTimestamp ?? null,
    mode: r.mode ?? null,
    delayed: isDelayed(r.mode),
  };
}

export function normalizeOption(r: RawOption): OptionContract | null {
  if (r.strike === null) return null;
  const type: OptionType = String(r.optionType ?? "").toLowerCase().startsWith("p") ? "put" : "call";
  return {
    symbol: r.symbol ?? "",
    underlying: r.underlying_symbol ?? "",
    type,
    strike: r.strike,
    expiration: r.expirationDate ?? "",
    dte: r.daysToExpiration,
    bid: r.bid,
    ask: r.ask,
    last: r.lastPrice,
    volume: r.volume,
    openInterest: r.openInterest,
    impliedVolatility: r.impliedVolatility ?? r.volatility,
    delta: r.delta,
    gamma: r.gamma,
    theta: r.theta,
    vega: r.vega,
    underlyingPrice: r.underlyingLastPrice,
  };
}

export function parseQuoteResponse(raw: unknown): NormalizedQuote[] {
  const parsed = quoteResponseSchema.parse(raw);
  return (parsed.results ?? []).map(normalizeQuote);
}

export function parseHistoryResponse(raw: unknown): HistoryBar[] {
  const parsed = historyResponseSchema.parse(raw);
  return (parsed.results ?? [])
    .filter((b) => b.open !== null && b.high !== null && b.low !== null && b.close !== null)
    .map((b) => ({
      timestamp: b.timestamp,
      open: b.open as number,
      high: b.high as number,
      low: b.low as number,
      close: b.close as number,
      volume: b.volume ?? 0,
    }));
}

export function parseOptionsResponse(raw: unknown): OptionContract[] {
  const parsed = optionsResponseSchema.parse(raw);
  return (parsed.results ?? []).map(normalizeOption).filter((x): x is OptionContract => x !== null);
}
