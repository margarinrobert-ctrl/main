/**
 * Headless intelligence collector — runs in CI (GitHub Actions) so the journal accrues even when no
 * browser is open. Reads the previous data from the git store (the `intel-data` branch), fetches the
 * live chain (CBOE) + candles (Yahoo) for the watchlist, records a snapshot, journals each engine's
 * directional call, resolves matured ones against the accumulated series, and writes the FULL updated
 * dataset to ./out-data/data/intel/*.json. The workflow then commits that folder to `intel-data`.
 *
 *   npm run collect-intel
 *
 * Env (set by the workflow): INTEL_DATA_REPO=owner/repo, INTEL_DATA_REF=intel-data,
 * GH_DATA_TOKEN=<token for private repos>. Network failures are tolerated per-symbol.
 */
import { config as loadEnv } from "dotenv";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { config } from "../src/lib/barchart/config";
import { fetchInputs, stepSymbol, type CollectResult } from "../src/lib/intel/collect";
import { loadServerHistory, loadServerJournal, storeMode } from "../src/lib/intel/store";
import type { PredictionRecord } from "../src/lib/intel/journal";

loadEnv({ path: ".env.local" });
loadEnv();

const OUT = path.join(process.cwd(), process.env.INTEL_OUT_DIR ?? "out-data", "data", "intel");

async function main() {
  await mkdir(OUT, { recursive: true });
  const symbols = config.optionsWatchlist;
  let journal: PredictionRecord[] = await loadServerJournal().catch(() => []);
  const results: CollectResult[] = [];

  for (const sym of symbols) {
    let hist = await loadServerHistory(sym).catch(() => []);
    try {
      const inputs = await fetchInputs(sym);
      const r = stepSymbol(sym, inputs, journal, hist, Date.now());
      journal = r.journal;
      hist = r.history;
      results.push(r.result);
    } catch (e) {
      results.push({ symbol: sym, source: "error", spot: null, samples: hist.length, added: 0, resolved: 0, open: 0, error: e instanceof Error ? e.message : "failed" });
    }
    await writeFile(path.join(OUT, `history-${sym}.json`), JSON.stringify(hist));
  }

  await writeFile(path.join(OUT, "journal.json"), JSON.stringify(journal));
  console.log(JSON.stringify({ ok: true, storeMode: storeMode(), at: new Date().toISOString(), out: OUT, results }, null, 2));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
