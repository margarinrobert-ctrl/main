import type { ScreenerParams } from "./barchart/endpoints";
import { parseHistoryResponse, parseOptionsResponse, parseQuoteResponse } from "./barchart/normalize";
import type { HistoryBar, NormalizedQuote, OptionContract } from "./barchart/types";
import { darkPoolStats, type DarkPoolDay, type DarkPoolStats } from "./flow/darkpool";
import { scoreContracts, type ScoredContract } from "./flow/heuristic";
import { applyScreenerFilter } from "./flow/screener-filter";
import { mergeServerHistory, type GexSample } from "./gex-history";
import { readJournal, writeJournal, type PredictionRecord } from "./intel/journal";
import { mergeJournal } from "./intel/merge";

/**
 * Browser data layer. In a normal (server) deploy it calls the /api proxy routes.
 * In a static export (GitHub Pages, NEXT_PUBLIC_STATIC=1) there is no server, so it
 * fetches the fixture JSON directly and runs the same parse/score in the browser.
 */
const STATIC = process.env.NEXT_PUBLIC_STATIC === "1";
const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

async function fetchFixture(candidates: string[]): Promise<unknown> {
  let lastErr: unknown;
  for (const name of candidates) {
    try {
      const res = await fetch(`${BASE}/fixtures/${name}`, { cache: "no-store" });
      if (res.ok) return await res.json();
      lastErr = new Error(`HTTP ${res.status}`);
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr ?? new Error(`fixture not found: ${candidates.join(", ")}`);
}

async function fetchJson(url: string): Promise<Record<string, unknown>> {
  const res = await fetch(url, { cache: "no-store" });
  const json = await res.json();
  if (!res.ok) throw new Error((json as { error?: string })?.error ?? "Request failed");
  return json as Record<string, unknown>;
}

export async function loadQuote(symbol: string): Promise<{ quotes: NormalizedQuote[]; source: string }> {
  const sym = symbol.toUpperCase();
  if (STATIC) {
    const raw = await fetchFixture([`quote.${sym}.json`, "quote.AAPL.json"]);
    return { quotes: parseQuoteResponse(raw), source: "fixtures" };
  }
  const json = await fetchJson(`/api/barchart/quote?symbol=${encodeURIComponent(sym)}`);
  return { quotes: (json.quotes as NormalizedQuote[]) ?? [], source: (json.source as string) ?? "" };
}

export async function loadHistory(symbol: string): Promise<{ bars: HistoryBar[]; source: string }> {
  const sym = symbol.toUpperCase();
  if (STATIC) {
    const raw = await fetchFixture([`history.${sym}.json`, "history.AAPL.json"]);
    return { bars: parseHistoryResponse(raw), source: "fixtures" };
  }
  const json = await fetchJson(`/api/barchart/history?symbol=${encodeURIComponent(sym)}`);
  return { bars: (json.bars as HistoryBar[]) ?? [], source: (json.source as string) ?? "" };
}

export async function loadCandles(symbol: string, interval: string, range: string): Promise<{ bars: HistoryBar[]; source: string }> {
  const sym = symbol.toUpperCase();
  if (STATIC) {
    const raw = await fetchFixture([`history.${sym}.json`, "history.AAPL.json"]);
    return { bars: parseHistoryResponse(raw), source: "fixtures" };
  }
  const json = await fetchJson(`/api/barchart/candles?symbol=${encodeURIComponent(sym)}&interval=${encodeURIComponent(interval)}&range=${encodeURIComponent(range)}`);
  return { bars: (json.bars as HistoryBar[]) ?? [], source: (json.source as string) ?? "" };
}

export async function loadChain(
  symbol: string,
): Promise<{ chain: OptionContract[]; source: string; spot: number | null; asOf: string | null }> {
  const sym = symbol.toUpperCase();
  if (STATIC) {
    const raw = await fetchFixture([`options.${sym}.json`, "options.AAPL.json"]);
    const chain = parseOptionsResponse(raw);
    const spot = chain.find((c) => c.underlyingPrice != null)?.underlyingPrice ?? null;
    return { chain, source: "fixtures", spot, asOf: null };
  }
  const json = await fetchJson(`/api/barchart/options?symbol=${encodeURIComponent(sym)}`);
  return {
    chain: (json.chain as OptionContract[]) ?? [],
    source: (json.source as string) ?? "",
    spot: (json.spot as number | null) ?? null,
    asOf: (json.asOf as string | null) ?? null,
  };
}

function parseScreenerQuery(qs: string): ScreenerParams {
  const p = new URLSearchParams(qs);
  const n = (k: string): number | undefined => {
    const v = p.get(k);
    if (!v) return undefined;
    const x = Number(v);
    return Number.isFinite(x) ? x : undefined;
  };
  return {
    minVolume: n("minVolume"),
    minOpenInterest: n("minOpenInterest"),
    minDTE: n("minDTE"),
    maxDTE: n("maxDTE"),
    minVolumeOpenInterestRatio: n("minVoir"),
  };
}

/**
 * Pull the durable server-collected history + journal and merge them into local storage, so the UI
 * shows everything gathered while the site was closed. Best-effort: a missing/empty server store just
 * leaves the local data untouched. Returns the store mode for the status banner.
 */
export async function pullServerData(symbol: string): Promise<{ storeMode: string; history: number; journal: number }> {
  if (typeof window === "undefined" || STATIC) return { storeMode: "memory", history: 0, journal: 0 };
  const sym = symbol.toUpperCase();
  const res = await fetch(`/api/intel?symbol=${encodeURIComponent(sym)}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const j = (await res.json()) as { storeMode: string; history?: GexSample[]; journal?: PredictionRecord[] };
  const history = j.history ?? [];
  const journal = j.journal ?? [];
  if (history.length) mergeServerHistory(sym, history);
  if (journal.length) writeJournal(mergeJournal(readJournal(), journal));
  return { storeMode: j.storeMode ?? "memory", history: history.length, journal: journal.length };
}

export async function loadDarkPool(symbol: string): Promise<{ stats: DarkPoolStats; source: string }> {
  const sym = symbol.toUpperCase();
  if (STATIC) {
    // No server in the static export — read the sample series and reduce it in the browser.
    const raw = await fetchFixture([`darkpool.${sym}.json`, "darkpool.SAMPLE.json"]).catch(() => []);
    return { stats: darkPoolStats((Array.isArray(raw) ? raw : []) as DarkPoolDay[]), source: "fixtures" };
  }
  const json = await fetchJson(`/api/darkpool?symbol=${encodeURIComponent(sym)}`);
  return { stats: json.stats as DarkPoolStats, source: (json.source as string) ?? "" };
}

export async function loadFlow(qs: string): Promise<{ rows: ScoredContract[]; source: string }> {
  if (STATIC) {
    const raw = await fetchFixture(["screener.json"]);
    const rows = scoreContracts(applyScreenerFilter(parseOptionsResponse(raw), parseScreenerQuery(qs)));
    return { rows, source: "fixtures" };
  }
  const json = await fetchJson(`/api/barchart/screener?${qs}`);
  return { rows: (json.rows as ScoredContract[]) ?? [], source: (json.source as string) ?? "" };
}
