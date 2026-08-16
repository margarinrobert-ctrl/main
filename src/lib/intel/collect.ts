import type { HistoryBar, OptionContract } from "../barchart/types";
import { getEquityOptions, getHistory } from "../barchart/endpoints";
import { atmIv, gammaFlip, gexByStrike, netDex, netGex, putCallRatio } from "../flow/analytics";
import { anomalyIntel } from "../flow/anomalyPro";
import { buildSignals } from "../flow/signals";
import { mmHedge } from "../flow/mmhedge";
import type { GexSample } from "../gex-history";
import { buildCandidates, shouldRecord, type PredictionRecord } from "./journal";
import { mergeHistory } from "./merge";
import { resolveForSymbol } from "./resolve";
import { buildSnapshot, mergeSnapshots } from "./snapshot";
import { loadServerHistory, loadServerJournal, loadServerSnapshots, saveServerHistory, saveServerJournal, saveServerSnapshots } from "./store";

// Server-side collection — the same collect+resolve loop the browser runs, but reading/writing the
// durable store so it works headless on a schedule (Vercel route, or the standalone scripts/collect
// runner that commits to git). `stepSymbol` is pure (no network/IO) so it's unit-tested; `fetchInputs`
// does the live network; `collectSymbol` wires them to the store.

export interface CollectInputs {
  chain: OptionContract[];
  spot: number | null;
  bars: HistoryBar[];
  source: string;
}

export interface CollectResult {
  symbol: string;
  source: string;
  spot: number | null;
  samples: number;
  added: number;
  resolved: number;
  open: number;
  error?: string;
}

/** Fetch the live chain (CBOE) + candles (Yahoo) for a symbol. */
export async function fetchInputs(symbol: string): Promise<CollectInputs> {
  const sym = symbol.toUpperCase();
  const { data: chain, source } = await getEquityOptions(sym);
  const spot = chain.find((c) => c.underlyingPrice != null)?.underlyingPrice ?? null;
  const { data: bars } = await getHistory(sym, { maxRecords: 60 }).catch(() => ({ data: [] as HistoryBar[] }));
  return { chain, spot, bars, source };
}

/** Pure: record a snapshot, journal each engine's call, resolve matured ones. No network/IO. */
export function stepSymbol(symbol: string, inputs: CollectInputs, prevJournal: PredictionRecord[], prevHistory: GexSample[], now = Date.now()): { journal: PredictionRecord[]; history: GexSample[]; result: CollectResult } {
  const sym = symbol.toUpperCase();
  const { chain, spot, bars, source } = inputs;
  const openOf = (j: PredictionRecord[]) => j.filter((r) => r.symbol === sym && r.outcome == null).length;
  if (!chain.length || spot == null) {
    return { journal: prevJournal, history: prevHistory, result: { symbol: sym, source, spot, samples: prevHistory.length, added: 0, resolved: 0, open: openOf(prevJournal), error: "no chain/spot" } };
  }

  // snapshot → append to the durable session series
  const by = gexByStrike(chain, spot);
  const flip = gammaFlip(by);
  const exps = [...new Set(chain.map((c) => c.expiration))].sort();
  const frontExp = exps.find((e) => (chain.find((c) => c.expiration === e)?.dte ?? -1) >= 0) ?? exps[0];
  const iv = frontExp ? atmIv(chain, spot, frontExp) : null;
  const sample: GexSample = { t: now, spot, gex: netGex(chain, spot), flip, iv, pcr: putCallRatio(chain).vol, dex: netDex(chain, spot) };
  const history = mergeHistory(prevHistory, [sample]);

  // engines → candidate predictions
  const intel = anomalyIntel(sym, chain, spot, bars, history);
  const board = buildSignals(chain, spot, bars);
  const mm = mmHedge(chain, spot, bars);

  let journal = prevJournal;
  const cands = buildCandidates(sym, now, chain, spot, bars, intel, board, mm);
  let added = 0;
  for (const cand of cands)
    if (shouldRecord(journal, cand)) {
      journal = [...journal, cand];
      added++;
    }
  const before = journal.filter((r) => r.symbol === sym && r.outcome != null).length;
  journal = resolveForSymbol(journal, sym, history, now);
  const after = journal.filter((r) => r.symbol === sym && r.outcome != null).length;

  return { journal, history, result: { symbol: sym, source, spot, samples: history.length, added, resolved: after - before, open: openOf(journal) } };
}

export async function collectSymbol(symbol: string): Promise<CollectResult> {
  const sym = symbol.toUpperCase();
  const inputs = await fetchInputs(sym);
  const prevJournal = await loadServerJournal();
  const prevHistory = await loadServerHistory(sym);
  const { journal, history, result } = stepSymbol(sym, inputs, prevJournal, prevHistory);
  await saveServerHistory(sym, history);
  await saveServerJournal(journal);
  // Per-strike snapshot for the day (expired chains can't be re-fetched, so record the shape as it happens).
  const snaps = mergeSnapshots(await loadServerSnapshots(sym).catch(() => []), buildSnapshot(inputs.chain, inputs.spot, Date.now()));
  await saveServerSnapshots(sym, snaps);
  return result;
}

/** Collect a list of symbols sequentially; one failure doesn't abort the rest. */
export async function collectAll(symbols: string[]): Promise<CollectResult[]> {
  const out: CollectResult[] = [];
  for (const s of symbols) {
    try {
      out.push(await collectSymbol(s));
    } catch (e) {
      out.push({ symbol: s.toUpperCase(), source: "error", spot: null, samples: 0, added: 0, resolved: 0, open: 0, error: e instanceof Error ? e.message : "collect failed" });
    }
  }
  return out;
}
