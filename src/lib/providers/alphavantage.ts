import { z } from "zod";
import { config } from "../barchart/config";
import { numish } from "../barchart/schemas";
import type { OptionContract, OptionType } from "../barchart/types";
import { stooqQuote } from "./stooq";

/**
 * Alpha Vantage HISTORICAL_OPTIONS — full options chain for the most recent trading day
 * (≈1 day old) on the FREE tier. Numeric fields arrive as strings, so `numish` coerces them.
 * Get a free key at https://www.alphavantage.co/support/#api-key
 */
const avRow = z
  .object({
    contractID: z.string().optional(),
    symbol: z.string().optional(),
    expiration: z.string(),
    strike: numish,
    type: z.string(), // "call" | "put"
    last: numish,
    mark: numish,
    bid: numish,
    ask: numish,
    volume: numish,
    open_interest: numish,
    implied_volatility: numish,
    delta: numish,
    gamma: numish,
    theta: numish,
    vega: numish,
  })
  .passthrough();

const avResponse = z
  .object({
    data: z.array(avRow).nullish(),
    message: z.string().optional(),
    // Alpha Vantage surfaces rate-limit / key problems in these fields with HTTP 200.
    Information: z.string().optional(),
    Note: z.string().optional(),
    "Error Message": z.string().optional(),
  })
  .passthrough();

function dteFrom(exp: string): number | null {
  const t = new Date(`${exp}T00:00:00Z`).getTime();
  if (!Number.isFinite(t)) return null;
  return Math.round((t - Date.now()) / 86_400_000);
}

export async function avOptions(symbol: string): Promise<OptionContract[]> {
  const sym = symbol.toUpperCase();
  if (!config.alphaVantageApiKey) throw new Error("ALPHAVANTAGE_API_KEY is not set");

  const url = new URL(config.alphaVantageBaseUrl);
  url.searchParams.set("function", "HISTORICAL_OPTIONS");
  url.searchParams.set("symbol", sym);
  url.searchParams.set("apikey", config.alphaVantageApiKey);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), config.requestTimeoutMs);
  let json: unknown;
  try {
    const res = await fetch(url.toString(), { signal: controller.signal, headers: { accept: "application/json" } });
    if (!res.ok) throw new Error(`Alpha Vantage HTTP ${res.status}`);
    json = await res.json();
  } finally {
    clearTimeout(timer);
  }

  const parsed = avResponse.parse(json);
  const problem = parsed.Information ?? parsed.Note ?? parsed["Error Message"];
  if (problem) throw new Error(`Alpha Vantage: ${problem}`);
  const rows = parsed.data ?? [];
  if (rows.length === 0) throw new Error(`Alpha Vantage: no options for ${sym}`);

  // Underlying last (for ATM marker + moneyness). Best-effort; degrade to null.
  let underlying: number | null = null;
  try {
    underlying = (await stooqQuote(sym))[0]?.last ?? null;
  } catch {
    underlying = null;
  }

  return rows
    .map((r): OptionContract | null => {
      if (r.strike === null) return null;
      const type: OptionType = r.type.toLowerCase().startsWith("p") ? "put" : "call";
      return {
        symbol: r.contractID ?? `${sym}|${r.expiration}|${r.strike}${type[0]}`,
        underlying: sym,
        type,
        strike: r.strike,
        expiration: r.expiration,
        dte: dteFrom(r.expiration),
        bid: r.bid,
        ask: r.ask,
        last: r.last ?? r.mark,
        volume: r.volume,
        openInterest: r.open_interest,
        impliedVolatility: r.implied_volatility,
        delta: r.delta,
        gamma: r.gamma,
        theta: r.theta,
        vega: r.vega,
        underlyingPrice: underlying,
      };
    })
    .filter((x): x is OptionContract => x !== null);
}
