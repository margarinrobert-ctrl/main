import { cached } from "../cache/store";
import { avOptions } from "../providers/alphavantage";
import { stooqHistory, stooqQuote } from "../providers/stooq";
import { barchartRequest, readFixtureParsed } from "./client";
import { config } from "./config";
import { parseHistoryResponse, parseOptionsResponse, parseQuoteResponse } from "./normalize";
import type { OptionContract } from "./types";

const useStooq = () => config.dataSource === "live" && config.marketDataProvider === "stooq";
const useAvOptions = () =>
  config.dataSource === "live" && config.optionsProvider === "alphavantage" && !!config.alphaVantageApiKey;

export async function getQuote(symbol: string) {
  const sym = symbol.toUpperCase();
  const fixtures = [`quote.${sym}.json`, "quote.AAPL.json"];

  if (useStooq()) {
    try {
      const data = await cached(`stooq:quote:${sym}`, config.cacheTtlSeconds, () => stooqQuote(sym));
      return { data, source: "live" as const };
    } catch (err) {
      console.warn(`[stooq] quote failed for ${sym}; falling back to fixtures:`, err instanceof Error ? err.message : err);
      return { data: await readFixtureParsed(fixtures, parseQuoteResponse), source: "fixtures" as const };
    }
  }

  return barchartRequest({ endpoint: "getQuote.json", params: { symbols: sym }, fixtureCandidates: fixtures }, parseQuoteResponse);
}

export async function getHistory(symbol: string, params: { type?: string; maxRecords?: number } = {}) {
  const sym = symbol.toUpperCase();
  const fixtures = [`history.${sym}.json`, "history.AAPL.json"];
  const maxRecords = params.maxRecords ?? 60;

  if (useStooq()) {
    try {
      const data = await cached(`stooq:history:${sym}:${maxRecords}`, config.cacheTtlSeconds, () =>
        stooqHistory(sym, maxRecords),
      );
      return { data, source: "live" as const };
    } catch (err) {
      console.warn(`[stooq] history failed for ${sym}; falling back to fixtures:`, err instanceof Error ? err.message : err);
      return { data: await readFixtureParsed(fixtures, parseHistoryResponse), source: "fixtures" as const };
    }
  }

  return barchartRequest(
    {
      endpoint: "getHistory.json",
      params: { symbol: sym, type: params.type ?? "daily", maxRecords },
      fixtureCandidates: fixtures,
    },
    parseHistoryResponse,
  );
}

export async function getEquityOptions(symbol: string) {
  const sym = symbol.toUpperCase();
  const fixtures = [`options.${sym}.json`, "options.AAPL.json"];

  if (useAvOptions()) {
    try {
      const data = await cached(`av:options:${sym}`, config.optionsCacheTtlSeconds, () => avOptions(sym));
      return { data, source: "live" as const };
    } catch (err) {
      console.warn(`[alphavantage] options failed for ${sym}; falling back to fixtures:`, err instanceof Error ? err.message : err);
      return { data: await readFixtureParsed(fixtures, parseOptionsResponse), source: "fixtures" as const };
    }
  }

  return barchartRequest(
    {
      endpoint: "getEquityOptions.json",
      params: { symbol: sym, fields: "volatility,delta,gamma,theta,vega,openInterest,volume" },
      fixtureCandidates: fixtures,
    },
    parseOptionsResponse,
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
  if (useAvOptions()) {
    try {
      // Free Alpha Vantage has no multi-symbol scan, so synthesize flow from a cached
      // watchlist of per-symbol chains (each cached for OPTIONS_CACHE_TTL_SECONDS).
      const lists = await Promise.all(
        config.optionsWatchlist.map((s) =>
          cached(`av:options:${s}`, config.optionsCacheTtlSeconds, () => avOptions(s)).catch(() => [] as OptionContract[]),
        ),
      );
      const data = lists.flat();
      if (data.length === 0) throw new Error("no Alpha Vantage options data");
      return { data, source: "live" as const };
    } catch (err) {
      console.warn(`[alphavantage] screener failed; falling back to fixtures:`, err instanceof Error ? err.message : err);
      return { data: await readFixtureParsed(["screener.json"], parseOptionsResponse), source: "fixtures" as const };
    }
  }

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
    parseOptionsResponse,
  );
}
