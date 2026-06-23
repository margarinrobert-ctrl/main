import type { GexSample } from "../gex-history";
import type { PredictionRecord } from "./journal";

// Pure merge helpers shared by the server store and the client sync — no env/fetch/DOM deps, so they
// are safe to import into either bundle. Dedupe is deterministic so client-recorded and server-
// collected streams converge to the same union regardless of merge order.

export const HIST_CAP = 600;
export const JOURNAL_CAP = 2500;

/** Union two GexSample series, dedupe by timestamp (latest wins), sort ascending, cap. */
export function mergeHistory(a: GexSample[], b: GexSample[], cap = HIST_CAP): GexSample[] {
  const m = new Map<number, GexSample>();
  for (const s of a) if (s && typeof s.t === "number") m.set(s.t, s);
  for (const s of b) if (s && typeof s.t === "number") m.set(s.t, s); // b (incoming) wins ties
  return [...m.values()].sort((x, y) => x.t - y.t).slice(-cap);
}

/** Union two journals, dedupe by id (prefer the RESOLVED copy of a duplicate id), sort by time, cap. */
export function mergeJournal(a: PredictionRecord[], b: PredictionRecord[], cap = JOURNAL_CAP): PredictionRecord[] {
  const m = new Map<string, PredictionRecord>();
  for (const r of [...a, ...b]) {
    if (!r || !r.id) continue;
    const ex = m.get(r.id);
    if (!ex || (!ex.outcome && r.outcome)) m.set(r.id, r);
  }
  return [...m.values()].sort((x, y) => x.t - y.t).slice(-cap);
}
