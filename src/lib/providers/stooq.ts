import { config } from "../barchart/config";
import type { HistoryBar, NormalizedQuote } from "../barchart/types";

/**
 * Stooq is a free, keyless market-data source (EOD / delayed). It exposes plain CSV
 * endpoints intended for programmatic use, so it's a legitimate way to show live-ish
 * underlying data with no account. US symbols use the ".us" suffix.
 *
 * Used only for quote + price history when DATA_SOURCE=live and MARKET_DATA_PROVIDER=stooq.
 * (Stooq has no options data — chain/screener remain Barchart-only.)
 */

// Futures/indices have no ".us" ticker — map to Stooq's cash-index symbols so the
// underlying quote+chart stay live and consistent with the CBOE options mapping (ES→SPX, NQ→NDX).
const STOOQ_SYMBOL_MAP: Record<string, string> = {
  ES: "^spx",
  NQ: "^ndx",
  SPX: "^spx",
  NDX: "^ndx",
  VIX: "^vix",
  RUT: "^rut",
  YM: "^dji",
  DJX: "^dji",
};

function stooqSymbol(symbol: string): string {
  const u = symbol.toUpperCase();
  if (STOOQ_SYMBOL_MAP[u]) return STOOQ_SYMBOL_MAP[u];
  const s = symbol.toLowerCase();
  return s.includes(".") ? s : `${s}.us`;
}

function num(v: string | undefined): number | null {
  if (v === undefined) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

async function fetchCsv(url: string): Promise<string[][]> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), config.requestTimeoutMs);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      headers: {
        accept: "text/csv",
        // Stooq rejects requests that lack a browser-like User-Agent.
        "user-agent": "Mozilla/5.0 (compatible; OptionsFlow/0.1; +https://stooq.com)",
      },
    });
    if (!res.ok) throw new Error(`Stooq HTTP ${res.status}`);
    const text = await res.text();
    return text
      .trim()
      .split(/\r?\n/)
      .map((line) => line.split(","));
  } finally {
    clearTimeout(timer);
  }
}

export async function stooqQuote(symbol: string): Promise<NormalizedQuote[]> {
  const sym = stooqSymbol(symbol);
  const url = `${config.stooqBaseUrl}/q/l/?s=${encodeURIComponent(sym)}&f=sd2t2ohlcv&h&e=csv`;
  const rows = await fetchCsv(url);
  const data = rows[1]; // rows[0] is the header
  if (!data || data.length < 8 || data.join(",").includes("N/D")) {
    throw new Error(`Stooq: no quote for ${sym}`);
  }
  const [, date, time, open, high, low, close, volume] = data;
  return [
    {
      symbol: symbol.toUpperCase(),
      name: null,
      last: num(close),
      netChange: null,
      percentChange: null,
      open: num(open),
      high: num(high),
      low: num(low),
      previousClose: null,
      volume: num(volume),
      tradeTimestamp: date ? (time ? `${date}T${time}` : date) : null,
      mode: "stooq-eod",
      delayed: true,
    },
  ];
}

export async function stooqHistory(symbol: string, maxBars = 120): Promise<HistoryBar[]> {
  const sym = stooqSymbol(symbol);
  const url = `${config.stooqBaseUrl}/q/d/l/?s=${encodeURIComponent(sym)}&i=d`;
  const rows = await fetchCsv(url);
  if (rows.length < 2 || !rows[0].map((h) => h.toLowerCase()).includes("close")) {
    throw new Error(`Stooq: no/unexpected history for ${sym}`);
  }
  const out: HistoryBar[] = [];
  for (let i = 1; i < rows.length; i++) {
    const [date, open, high, low, close, volume] = rows[i];
    const c = Number(close);
    if (!date || !Number.isFinite(c)) continue;
    out.push({
      timestamp: `${date}T00:00:00`,
      open: Number(open),
      high: Number(high),
      low: Number(low),
      close: c,
      volume: Number(volume) || 0,
    });
  }
  if (out.length === 0) throw new Error(`Stooq: empty history for ${sym}`);
  return out.slice(-maxBars);
}
