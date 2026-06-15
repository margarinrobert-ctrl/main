export type DataSource = "fixtures" | "live";
export type MarketDataProvider = "barchart" | "stooq";

function toInt(v: string | undefined, fallback: number): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

/** Central runtime config. Read once from the environment (server-side only). */
export const config = {
  dataSource: (process.env.DATA_SOURCE === "live" ? "live" : "fixtures") as DataSource,
  apiKey: process.env.BARCHART_API_KEY ?? "",
  baseUrl: (process.env.BARCHART_BASE_URL ?? "https://ondemand.websol.barchart.com/").replace(/\/+$/, "") + "/",
  // Who serves underlying quote + price history when DATA_SOURCE=live.
  // 'stooq' is free + keyless (EOD/delayed) — see live underlying data with no account.
  // Options chain + screener are Barchart-only regardless of this setting.
  marketDataProvider: (process.env.MARKET_DATA_PROVIDER === "stooq" ? "stooq" : "barchart") as MarketDataProvider,
  stooqBaseUrl: (process.env.STOOQ_BASE_URL ?? "https://stooq.com").replace(/\/+$/, ""),
  cacheTtlSeconds: toInt(process.env.CACHE_TTL_SECONDS, 60),
  pollIntervalMs: toInt(process.env.POLL_INTERVAL_MS, 0),
  requestTimeoutMs: 10_000,
  maxRetries: 3,
} as const;

/**
 * Unusual-activity heuristic thresholds. All tunable in one place.
 * Each signal is normalized to 0..1 via a clamped ramp between floor and cap.
 */
export const flowThresholds = {
  // Gates: rows below these are excluded (score 0) to kill small-denominator noise.
  minVolume: 100,
  minOpenInterest: 50,

  // Signal 1: volume / open interest
  voirFloor: 1.0,
  voirCap: 5.0,
  voirWeight: 0.4,

  // Signal 2: volume / trailing-average volume (needs history; weight redistributed if absent)
  volSpikeFloor: 2.0,
  volSpikeCap: 10.0,
  volSpikeWeight: 0.2,

  // Signal 3: notional = volume * mid * 100 (USD)
  notionalFloor: 250_000,
  notionalCap: 5_000_000,
  notionalWeight: 0.3,

  // Signal 4: short-dated + far out-of-the-money
  shortDteDays: 7,
  farOtmPct: 0.05,
  shortDteOtmWeight: 0.1,
} as const;

export type FlowThresholds = typeof flowThresholds;
