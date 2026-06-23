import { getEquityOptions, getHistory } from "../barchart/endpoints";
import { atmIv, gammaFlip, gexByStrike, netGex, putCallRatio } from "../flow/analytics";
import { anomalyIntel } from "../flow/anomalyPro";
import { buildSignals } from "../flow/signals";
import { mmHedge } from "../flow/mmhedge";
import type { GexSample } from "../gex-history";
import { buildCandidates, shouldRecord } from "./journal";
import { mergeHistory } from "./merge";
import { resolveForSymbol } from "./resolve";
import { loadServerHistory, loadServerJournal, saveServerHistory, saveServerJournal } from "./store";

// Server-side collection — the same collect+resolve loop the browser runs, but reading/writing the
// durable store so it works headless on a schedule. Fetches the live chain (CBOE) + candles (Yahoo),
// records a snapshot, journals each engine's directional call, and resolves matured ones against the
// accumulated server price series. No DOM/localStorage — safe in a route handler / cron.

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

export async function collectSymbol(symbol: string): Promise<CollectResult> {
  const sym = symbol.toUpperCase();
  const { data: chain, source } = await getEquityOptions(sym);
  const spot = chain.find((c) => c.underlyingPrice != null)?.underlyingPrice ?? null;
  if (!chain.length || spot == null) return { symbol: sym, source, spot, samples: 0, added: 0, resolved: 0, open: 0, error: "no chain/spot" };
  const { data: bars } = await getHistory(sym, { maxRecords: 60 }).catch(() => ({ data: [] }));

  // snapshot → append to the durable session series
  const by = gexByStrike(chain, spot);
  const flip = gammaFlip(by);
  const exps = [...new Set(chain.map((c) => c.expiration))].sort();
  const frontExp = exps.find((e) => (chain.find((c) => c.expiration === e)?.dte ?? -1) >= 0) ?? exps[0];
  const iv = frontExp ? atmIv(chain, spot, frontExp) : null;
  const sample: GexSample = { t: Date.now(), spot, gex: netGex(chain, spot), flip, iv, pcr: putCallRatio(chain).vol };
  const hist = mergeHistory(await loadServerHistory(sym), [sample]);

  // engines → candidate predictions
  const intel = anomalyIntel(sym, chain, spot, bars, hist);
  const board = buildSignals(chain, spot, bars);
  const mm = mmHedge(chain, spot, bars);

  let journal = await loadServerJournal();
  const cands = buildCandidates(sym, Date.now(), chain, spot, bars, intel, board, mm);
  let added = 0;
  for (const cand of cands)
    if (shouldRecord(journal, cand)) {
      journal = [...journal, cand];
      added++;
    }
  const before = journal.filter((r) => r.symbol === sym && r.outcome != null).length;
  journal = resolveForSymbol(journal, sym, hist, Date.now());
  const after = journal.filter((r) => r.symbol === sym && r.outcome != null).length;

  await saveServerHistory(sym, hist);
  await saveServerJournal(journal);
  return { symbol: sym, source, spot, samples: hist.length, added, resolved: after - before, open: journal.filter((r) => r.symbol === sym && r.outcome == null).length };
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
