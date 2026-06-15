export type DataSource = "fixtures" | "live";
export type MarketDataProvider = "barchart" | "stooq";
export type OptionsProvider = "barchart" | "alphavantage";

function toInt(v: string | undefined, fallback: number): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function pickOptionsProvider(): OptionsProvider {
  const v = process.env.OPTIONS_PROVIDER;
  if (v === "alphavantage" || v === "barchart") return v;
  // Auto-select Alpha Vantage (free EOD options) when a key is present.
  return process.env.ALPHAVANTAGE_API_KEY ? "alphavantage" : "barchart";
}

/** Central runtime config. Read once from the environment (server-side only). */
export const config = {
  // Default to LIVE so deployed instances pull fresh data. Set DATA_SOURCE=fixtures for
  // offline/dev. Any live failure still falls back to fixtures so the UI never breaks.
  dataSource: (process.env.DATA_SOURCE === "fixtures" ? "fixtures" : "live") as DataSource,
  apiKey: process.env.BARCHART_API_KEY ?? "",
  baseUrl: (process.env.BARCHART_BASE_URL ?? "https://ondemand.websol.barchart.com/").replace(/\/+$/, "") + "/",
  // Underlying quote + price history. 'stooq' is free + keyless (EOD, ~1 day old).
  marketDataProvider: (process.env.MARKET_DATA_PROVIDER === "barchart" ? "barchart" : "stooq") as MarketDataProvider,
  stooqBaseUrl: (process.env.STOOQ_BASE_URL ?? "https://stooq.com").replace(/\/+$/, ""),
  // Options chain/heatmap/flow. 'alphavantage' = fresh EOD chains with a FREE key
  // (auto-selected when ALPHAVANTAGE_API_KEY is set); 'barchart' needs a paid key.
  optionsProvider: pickOptionsProvider(),
  alphaVantageApiKey: process.env.ALPHAVANTAGE_API_KEY ?? "",
  alphaVantageBaseUrl: process.env.ALPHAVANTAGE_BASE_URL ?? "https://www.alphavantage.co/query",
  optionsWatchlist: (process.env.OPTIONS_WATCHLIST ?? "SPY,QQQ,AAPL,NVDA,TSLA,AMD")
    .split(",")
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean),
  cacheTtlSeconds: toInt(process.env.CACHE_TTL_SECONDS, 60),
  optionsCacheTtlSeconds: toInt(process.env.OPTIONS_CACHE_TTL_SECONDS, 21600), // 6h (EOD data)
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
