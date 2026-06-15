import { z } from "zod";
import { config } from "../barchart/config";
import { numish } from "../barchart/schemas";
import type { OptionContract, OptionType } from "../barchart/types";

/**
 * CBOE delayed quotes — a public, keyless options feed (~15-min delayed) that powers
 * cboe.com's free quote pages. Returns full chains with volume, OI, IV and greeks.
 *
 * Futures (ES/NQ) have no public options feed, so we map them to the matching CBOE
 * cash index (ES→SPX, NQ→NDX) as a free stand-in for S&P / Nasdaq index-options flow.
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
    data: z
      .object({
        current_price: numish,
        close: numish,
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

/** Parse an OCC option symbol, e.g. "AAPL250117C00150000" -> {strike, type, expiration}. */
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

export async function cboeOptions(symbol: string): Promise<OptionContract[]> {
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
  const rows = parsed.data?.options ?? [];
  if (rows.length === 0) throw new Error(`CBOE: no options for ${sym}`);
  const underlying = parsed.data?.current_price ?? parsed.data?.close ?? null;

  return rows
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
        underlyingPrice: underlying,
      };
    })
    .filter((x): x is OptionContract => x !== null);
}
