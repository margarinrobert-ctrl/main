import { cached } from "../cache/store";
import { avOptions } from "../providers/alphavantage";
import { cboeOptions } from "../providers/cboe";
import { stooqHistory, stooqQuote } from "../providers/stooq";
import { barchartRequest, readFixtureParsed } from "./client";
import { config } from "./config";
import { parseHistoryResponse, parseOptionsResponse, parseQuoteResponse } from "./normalize";
import type { OptionContract } from "./types";

const useStooq = () => config.dataSource === "live" && config.marketDataProvider === "stooq";

// Options: 'cboe' (public, keyless) and 'alphavantage' (free key) fetch per-symbol chains;
// 'barchart' (paid) goes through the shared barchartRequest path below.
const liveOptionsEnabled = () =>
  config.dataSource === "live" &&
  (config.optionsProvider === "cboe" || (config.optionsProvider === "alphavantage" && !!config.alphaVantageApiKey));
const fetchLiveOptions = (sym: string) => (config.optionsProvider === "alphavantage" ? avOptions(sym) : cboeOptions(sym));
const optionsTtl = () => (config.optionsProvider === "cboe" ? config.cboeCacheTtlSeconds : config.optionsCacheTtlSeconds);

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

  if (liveOptionsEnabled()) {
    try {
      const data = await cached(`opt:${config.optionsProvider}:${sym}`, optionsTtl(), () => fetchLiveOptions(sym));
      return { data, source: "live" as const };
    } catch (err) {
      console.warn(`[${config.optionsProvider}] options failed for ${sym}; falling back to fixtures:`, err instanceof Error ? err.message : err);
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
  if (liveOptionsEnabled()) {
    try {
      // No free multi-symbol scan, so synthesize flow from a cached watchlist of per-symbol chains.
      const lists = await Promise.all(
        config.optionsWatchlist.map((s) =>
          cached(`opt:${config.optionsProvider}:${s}`, optionsTtl(), () => fetchLiveOptions(s)).catch(
            () => [] as OptionContract[],
          ),
        ),
      );
      const data = lists.flat();
      if (data.length === 0) throw new Error("no live options data");
      return { data, source: "live" as const };
    } catch (err) {
      console.warn(`[${config.optionsProvider}] screener failed; falling back to fixtures:`, err instanceof Error ? err.message : err);
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
