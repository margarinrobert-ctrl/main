import { z } from "zod";
import { cached } from "../cache/store";
import { config } from "../barchart/config";
import { numish } from "../barchart/schemas";
import type { NormalizedQuote, OptionContract, OptionType } from "../barchart/types";

/**
 * CBOE delayed quotes — a public, keyless feed (~15-min delayed) powering cboe.com's free pages.
 * One fetch per symbol (cached) serves both the options chain and the underlying quote.
 *
 * Futures (ES/NQ) have no public options feed, so we map them to the matching CBOE cash index
 * (ES→SPX, NQ→NDX) as a free stand-in for S&P / Nasdaq index-options flow.
 */
const FUTURES_TO_INDEX: Record<string, string> = { ES: "SPX", NQ: "NDX", RTY: "RUT", YM: "DJX" };
const CBOE_INDICES = new Set(["SPX", "NDX", "VIX", "RUT", "DJX", "XSP"]);

const cboeOption = z
  .object({
    option: z.string(),
    bid: numish,
    ask: numish,
    last_trade_price: numish,
    volume: numish,
    open_interest: numish,
    iv: numish,
    delta: numish,
    gamma: numish,
    theta: numish,
    vega: numish,
  })
  .passthrough();

const cboeResponse = z
  .object({
    // CBOE stamps its own delayed-quote time at the top level — use it instead of fetch time.
    timestamp: z.string().nullish(),
    data: z
      .object({
        current_price: numish,
        close: numish,
        prev_day_close: numish,
        open: numish,
        high: numish,
        low: numish,
        last_trade_time: z.string().nullish(),
        options: z.array(cboeOption).nullish(),
      })
      .passthrough()
      .nullish(),
  })
  .passthrough();

function cboePath(symbol: string): string {
  let s = symbol.toUpperCase();
  if (FUTURES_TO_INDEX[s]) s = FUTURES_TO_INDEX[s];
  return CBOE_INDICES.has(s) ? `_${s}.json` : `${s}.json`;
}

function parseOcc(opt: string): { strike: number; type: OptionType; expiration: string } {
  const strike = Number(opt.slice(-8)) / 1000;
  const type: OptionType = opt.slice(-9, -8) === "P" ? "put" : "call";
  const ymd = opt.slice(-15, -9);
  const expiration = `20${ymd.slice(0, 2)}-${ymd.slice(2, 4)}-${ymd.slice(4, 6)}`;
  return { strike, type, expiration };
}

function dteFrom(exp: string): number | null {
  const t = new Date(`${exp}T00:00:00Z`).getTime();
  return Number.isFinite(t) ? Math.round((t - Date.now()) / 86_400_000) : null;
}

const round2 = (n: number) => Math.round(n * 100) / 100;

export interface CboeRaw {
  options: OptionContract[];
  spot: number | null;
  prevClose: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  asOf: string | null; // CBOE's own data timestamp (delayed)
}

async function fetchCboeRaw(symbol: string): Promise<CboeRaw> {
  const sym = symbol.toUpperCase();
  const url = `${config.cboeBaseUrl}/${cboePath(sym)}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), config.requestTimeoutMs);
  let json: unknown;
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      headers: { accept: "application/json", "user-agent": "Mozilla/5.0 (compatible; OptionsFlow/0.1)" },
    });
    if (!res.ok) throw new Error(`CBOE HTTP ${res.status}`);
    json = await res.json();
  } finally {
    clearTimeout(timer);
  }

  const parsed = cboeResponse.parse(json);
  const d = parsed.data;
  const asOf = parsed.timestamp ?? d?.last_trade_time ?? null;
  const options = (d?.options ?? [])
    .map((r): OptionContract | null => {
      if (!/^.+\d{6}[CP]\d{8}$/.test(r.option)) return null;
      const { strike, type, expiration } = parseOcc(r.option);
      if (!Number.isFinite(strike)) return null;
      return {
        symbol: r.option,
        underlying: sym,
        type,
        strike,
        expiration,
        dte: dteFrom(expiration),
        bid: r.bid,
        ask: r.ask,
        last: r.last_trade_price,
        volume: r.volume,
        openInterest: r.open_interest,
        impliedVolatility: r.iv,
        delta: r.delta,
        gamma: r.gamma,
        theta: r.theta,
        vega: r.vega,
        underlyingPrice: d?.current_price ?? d?.close ?? null,
      };
    })
    .filter((x): x is OptionContract => x !== null);

  return {
    options,
    spot: d?.current_price ?? d?.close ?? null,
    prevClose: d?.prev_day_close ?? d?.close ?? null,
    open: d?.open ?? null,
    high: d?.high ?? null,
    low: d?.low ?? null,
    asOf,
  };
}

/** Single cached CBOE fetch per symbol (shared by chain + quote). */
export function cboeRaw(symbol: string): Promise<CboeRaw> {
  return cached(`cboe:${symbol.toUpperCase()}`, config.cboeCacheTtlSeconds, () => fetchCboeRaw(symbol));
}

export async function cboeOptions(symbol: string): Promise<OptionContract[]> {
  const raw = await cboeRaw(symbol);
  if (raw.options.length === 0) throw new Error(`CBOE: no options for ${symbol}`);
  return raw.options;
}

/** Chain plus CBOE's own data timestamp + spot, for accurate freshness reporting. */
export async function cboeChain(symbol: string): Promise<{ options: OptionContract[]; asOf: string | null; spot: number | null }> {
  const raw = await cboeRaw(symbol);
  if (raw.options.length === 0) throw new Error(`CBOE: no options for ${symbol}`);
  return { options: raw.options, asOf: raw.asOf, spot: raw.spot };
}

export async function cboeQuote(symbol: string): Promise<NormalizedQuote[]> {
  const raw = await cboeRaw(symbol);
  if (raw.spot == null) throw new Error(`CBOE: no quote for ${symbol}`);
  const last = raw.spot;
  const prev = raw.prevClose;
  return [
    {
      symbol: symbol.toUpperCase(),
      name: null,
      last,
      netChange: prev != null ? round2(last - prev) : null,
      percentChange: prev ? round2(((last - prev) / prev) * 100) : null,
      open: raw.open,
      high: raw.high,
      low: raw.low,
      previousClose: prev,
      volume: null,
      tradeTimestamp: raw.asOf, // CBOE's stamped time (delayed), not fetch time
      mode: "cboe-delayed",
      delayed: true,
    },
  ];
}
