import { barchartRequest } from "./client";
import {
  historyResponseSchema,
  optionsResponseSchema,
  quoteResponseSchema,
  screenerResponseSchema,
  type RawOption,
  type RawQuote,
} from "./schemas";
import type { HistoryBar, NormalizedQuote, OptionContract, OptionType } from "./types";

function isDelayed(mode: string | null | undefined): boolean | null {
  if (!mode) return null;
  const m = mode.toLowerCase();
  if (m.startsWith("d")) return true;
  if (m.startsWith("r") || m.startsWith("i")) return false;
  return null;
}

function normalizeQuote(r: RawQuote): NormalizedQuote {
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

function normalizeOption(r: RawOption): OptionContract | null {
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

export async function getQuote(symbol: string) {
  const sym = symbol.toUpperCase();
  return barchartRequest(
    { endpoint: "getQuote.json", params: { symbols: sym }, fixtureCandidates: [`quote.${sym}.json`, "quote.AAPL.json"] },
    (raw): NormalizedQuote[] => {
      const parsed = quoteResponseSchema.parse(raw);
      return (parsed.results ?? []).map(normalizeQuote);
    },
  );
}

export async function getHistory(symbol: string, params: { type?: string; maxRecords?: number } = {}) {
  const sym = symbol.toUpperCase();
  return barchartRequest(
    {
      endpoint: "getHistory.json",
      params: { symbol: sym, type: params.type ?? "daily", maxRecords: params.maxRecords ?? 60 },
      fixtureCandidates: [`history.${sym}.json`, "history.AAPL.json"],
    },
    (raw): HistoryBar[] => {
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
    },
  );
}

export async function getEquityOptions(symbol: string) {
  const sym = symbol.toUpperCase();
  return barchartRequest(
    {
      endpoint: "getEquityOptions.json",
      params: { symbol: sym, fields: "volatility,delta,gamma,theta,vega,openInterest,volume" },
      fixtureCandidates: [`options.${sym}.json`, "options.AAPL.json"],
    },
    (raw): OptionContract[] => {
      const parsed = optionsResponseSchema.parse(raw);
      return (parsed.results ?? []).map(normalizeOption).filter((x): x is OptionContract => x !== null);
    },
  );
}

export interface ScreenerParams {
  minVolume?: number;
  minOpenInterest?: number;
  minDTE?: number;
  maxDTE?: number;
  minVolumeOpenInterestRatio?: number;
  minDelta?: number;
  maxDelta?: number;
}

export async function getOptionsScreener(params: ScreenerParams = {}) {
  return barchartRequest(
    {
      endpoint: "getOptionsScreener.json",
      // Barchart's exact param names vary by plan; mapped here so the UI/API stays stable.
      params: {
        volumeMinimum: params.minVolume,
        openInterestMinimum: params.minOpenInterest,
        baseDataMinimumDaysToExpiration: params.minDTE,
        baseDataMaximumDaysToExpiration: params.maxDTE,
        volumeOpenInterestRatioMinimum: params.minVolumeOpenInterestRatio,
        deltaMinimum: params.minDelta,
        deltaMaximum: params.maxDelta,
      },
      fixtureCandidates: ["screener.json"],
    },
    (raw): OptionContract[] => {
      const parsed = screenerResponseSchema.parse(raw);
      return (parsed.results ?? []).map(normalizeOption).filter((x): x is OptionContract => x !== null);
    },
  );
}
