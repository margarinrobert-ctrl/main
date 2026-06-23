import { z } from "zod";

/**
 * Barchart returns numbers as numbers OR strings depending on plan/endpoint, and
 * uses "" / "NA" for missing values. `numish` coerces all of that to number | null.
 */
export const numish = z.preprocess((v) => {
  if (v === null || v === undefined || v === "" || v === "NA") return null;
  if (typeof v === "string") {
    const n = Number(v.replace(/,/g, ""));
    return Number.isFinite(n) ? n : null;
  }
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  return null;
}, z.number().nullable());

export const statusSchema = z.object({
  code: z.number(),
  message: z.string(),
});

export const rawQuoteSchema = z
  .object({
    symbol: z.string(),
    name: z.string().nullish(),
    mode: z.string().nullish(),
    lastPrice: numish,
    tradeTimestamp: z.string().nullish(),
    netChange: numish,
    percentChange: numish,
    open: numish,
    high: numish,
    low: numish,
    previousClose: numish,
    volume: numish,
  })
  .passthrough();

export const quoteResponseSchema = z
  .object({
    status: statusSchema,
    results: z.array(rawQuoteSchema).nullish(),
  })
  .passthrough();

export const rawHistoryBarSchema = z
  .object({
    timestamp: z.string(),
    open: numish,
    high: numish,
    low: numish,
    close: numish,
    volume: numish,
  })
  .passthrough();

export const historyResponseSchema = z
  .object({
    status: statusSchema,
    results: z.array(rawHistoryBarSchema).nullish(),
  })
  .passthrough();

export const rawOptionSchema = z
  .object({
    symbol: z.string().nullish(),
    underlying_symbol: z.string().nullish(),
    optionType: z.string().nullish(), // "Call" | "Put"
    strike: numish,
    expirationDate: z.string().nullish(),
    daysToExpiration: numish,
    bid: numish,
    ask: numish,
    lastPrice: numish,
    volume: numish,
    openInterest: numish,
    volatility: numish, // implied vol (field name varies by plan)
    impliedVolatility: numish,
    delta: numish,
    gamma: numish,
    theta: numish,
    vega: numish,
    underlyingLastPrice: numish,
  })
  .passthrough();

export const optionsResponseSchema = z
  .object({
    status: statusSchema,
    results: z.array(rawOptionSchema).nullish(),
  })
  .passthrough();

export const screenerResponseSchema = optionsResponseSchema;

export type RawQuote = z.infer<typeof rawQuoteSchema>;
export type RawHistoryBar = z.infer<typeof rawHistoryBarSchema>;
export type RawOption = z.infer<typeof rawOptionSchema>;
