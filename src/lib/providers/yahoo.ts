import { config } from "../barchart/config";
import type { HistoryBar, NormalizedQuote } from "../barchart/types";

/**
 * Yahoo Finance public chart endpoint (v8) — keyless JSON the Yahoo Finance site itself serves.
 * Reliable from servers (unlike Stooq's CSV, which blocks datacenter IPs) and real-time-ish for
 * liquid ETFs/indices, so it's the primary free source for the underlying quote + price history.
 * Used for quote + history when DATA_SOURCE=live; options stay on CBOE.
 */

// Plain tickers for ETFs/equities; futures map to Yahoo continuous-future symbols.
const YAHOO_SYMBOL_MAP: Record<string, string> = { ES: "ES=F", NQ: "NQ=F", RTY: "RTY=F", YM: "YM=F", SPX: "^GSPC", NDX: "^NDX", VIX: "^VIX", RUT: "^RUT" };
const ySymbol = (s: string) => YAHOO_SYMBOL_MAP[s.toUpperCase()] ?? s.toUpperCase();

interface YResult {
  timestamp?: number[];
  indicators?: { quote?: { open?: (number | null)[]; high?: (number | null)[]; low?: (number | null)[]; close?: (number | null)[]; volume?: (number | null)[] }[] };
  meta?: { regularMarketPrice?: number; chartPreviousClose?: number; previousClose?: number; regularMarketTime?: number; regularMarketVolume?: number };
}

async function fetchChart(symbol: string, range: string, interval: string): Promise<YResult> {
  const url = `${config.yahooBaseUrl}/v8/finance/chart/${encodeURIComponent(ySymbol(symbol))}?range=${range}&interval=${interval}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), config.requestTimeoutMs);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      headers: { accept: "application/json", "user-agent": "Mozilla/5.0 (compatible; OptionsFlow/0.1)" },
    });
    if (!res.ok) throw new Error(`Yahoo HTTP ${res.status}`);
    const json = (await res.json()) as { chart?: { result?: YResult[]; error?: { description?: string } } };
    if (json.chart?.error) throw new Error(`Yahoo: ${json.chart.error.description ?? "error"}`);
    const r = json.chart?.result?.[0];
    if (!r) throw new Error(`Yahoo: no result for ${symbol}`);
    return r;
  } finally {
    clearTimeout(timer);
  }
}

function barsFrom(r: YResult, symbol: string): HistoryBar[] {
  const ts = r.timestamp ?? [];
  const q = r.indicators?.quote?.[0];
  if (!ts.length || !q?.close) throw new Error(`Yahoo: empty history for ${symbol}`);
  const out: HistoryBar[] = [];
  for (let i = 0; i < ts.length; i++) {
    const close = q.close[i];
    if (close == null || !Number.isFinite(close)) continue;
    out.push({
      timestamp: new Date(ts[i] * 1000).toISOString(),
      open: q.open?.[i] ?? close,
      high: q.high?.[i] ?? close,
      low: q.low?.[i] ?? close,
      close,
      volume: q.volume?.[i] ?? 0,
    });
  }
  if (!out.length) throw new Error(`Yahoo: no usable bars for ${symbol}`);
  return out;
}

export async function yahooHistory(symbol: string, maxBars = 120): Promise<HistoryBar[]> {
  return barsFrom(await fetchChart(symbol, "6mo", "1d"), symbol).slice(-maxBars);
}

/** OHLC candles at an arbitrary interval/range (e.g. 1m/1d, 5m/5d, 60m/3mo, 1d/6mo). */
export async function yahooCandles(symbol: string, interval: string, range: string): Promise<HistoryBar[]> {
  return barsFrom(await fetchChart(symbol, range, interval), symbol);
}

export async function yahooQuote(symbol: string): Promise<NormalizedQuote[]> {
  const r = await fetchChart(symbol, "1d", "1d");
  const m = r.meta ?? {};
  const last = m.regularMarketPrice;
  if (last == null || !Number.isFinite(last)) throw new Error(`Yahoo: no quote for ${symbol}`);
  const prev = m.chartPreviousClose ?? m.previousClose ?? null;
  const round2 = (n: number) => Math.round(n * 100) / 100;
  return [
    {
      symbol: symbol.toUpperCase(),
      name: null,
      last,
      netChange: prev != null ? round2(last - prev) : null,
      percentChange: prev ? round2(((last - prev) / prev) * 100) : null,
      open: null,
      high: null,
      low: null,
      previousClose: prev,
      volume: m.regularMarketVolume ?? null,
      tradeTimestamp: m.regularMarketTime ? new Date(m.regularMarketTime * 1000).toISOString() : null,
      mode: "yahoo",
      delayed: true,
    },
  ];
}
