import { mergeHistory } from "./intel/merge";

export interface GexSample {
  t: number; // epoch ms
  spot: number | null;
  gex: number | null; // net dealer gamma ($/1%)
  flip: number | null; // zero-gamma level
  iv?: number | null; // front/0DTE ATM implied vol
  pcr?: number | null; // put/call volume ratio
  dex?: number | null; // net dealer delta ($ notional) — recorded from Aug 2026 on; older samples lack it
}

const CAP = 600;
const MIN_GAP_MS = 25_000;
const key = (sym: string) => `gexhist:${sym.toUpperCase()}`;

/** Read the locally-recorded intraday GEX/spot history for a symbol. */
export function readHistory(sym: string): GexSample[] {
  if (typeof window === "undefined") return [];
  try {
    const v = JSON.parse(localStorage.getItem(key(sym)) ?? "[]");
    return Array.isArray(v) ? (v as GexSample[]) : [];
  } catch {
    return [];
  }
}

/** Merge a server-collected series into the local one (dedupe by timestamp), persist, and return it. */
export function mergeServerHistory(sym: string, incoming: GexSample[]): GexSample[] {
  if (typeof window === "undefined") return [];
  const merged = mergeHistory(readHistory(sym), incoming, CAP);
  try {
    localStorage.setItem(key(sym), JSON.stringify(merged));
  } catch {
    /* storage full / disabled — ignore */
  }
  return merged;
}

/** Append a sample (collapsing points closer than MIN_GAP_MS), persist, and return the series. */
export function appendSample(sym: string, s: GexSample): GexSample[] {
  if (typeof window === "undefined") return [];
  const prev = readHistory(sym);
  const last = prev[prev.length - 1];
  const next = last && s.t - last.t < MIN_GAP_MS ? [...prev.slice(0, -1), s] : [...prev, s];
  const capped = next.slice(-CAP);
  try {
    localStorage.setItem(key(sym), JSON.stringify(capped));
  } catch {
    /* storage full / disabled — ignore */
  }
  return capped;
}
