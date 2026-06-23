import type { GexSample } from "../gex-history";
import type { PredictionRecord } from "./journal";
import { HIST_CAP, JOURNAL_CAP } from "./merge";

// Durable server-side store for the intelligence layer, so history accrues even when no browser is
// open. Uses a KV REST API (Vercel KV or Upstash Redis — both expose the same REST shape) when the
// env vars are present; otherwise falls back to a per-instance in-memory map (works, but resets on a
// serverless cold start — that's why the UI reports the store mode and asks you to wire KV).
//
// Setup (free): provision Vercel KV or an Upstash Redis DB, then set KV_REST_API_URL +
// KV_REST_API_TOKEN (or UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN). See COLLECTION.md.

const JOURNAL_KEY = "intel:journal";
const histKey = (sym: string) => `intel:hist:${sym.toUpperCase()}`;

function kvEnv(): { url: string; token: string } | null {
  const url = process.env.KV_REST_API_URL ?? process.env.UPSTASH_REDIS_REST_URL ?? "";
  const token = process.env.KV_REST_API_TOKEN ?? process.env.UPSTASH_REDIS_REST_TOKEN ?? "";
  return url && token ? { url: url.replace(/\/+$/, ""), token } : null;
}

export const storeMode = (): "kv" | "memory" => (kvEnv() ? "kv" : "memory");

const mem = new Map<string, unknown>();

async function kvGet<T>(key: string): Promise<T | null> {
  const env = kvEnv();
  if (!env) return (mem.get(key) as T) ?? null;
  const res = await fetch(`${env.url}/get/${encodeURIComponent(key)}`, { headers: { Authorization: `Bearer ${env.token}` }, cache: "no-store" });
  if (!res.ok) throw new Error(`kv get ${res.status}`);
  const j = (await res.json()) as { result: string | null };
  if (j.result == null) return null;
  try {
    return JSON.parse(j.result) as T;
  } catch {
    return null;
  }
}

async function kvSet<T>(key: string, value: T): Promise<void> {
  const env = kvEnv();
  if (!env) {
    mem.set(key, value);
    return;
  }
  const res = await fetch(`${env.url}/set/${encodeURIComponent(key)}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${env.token}`, "Content-Type": "application/json" },
    body: JSON.stringify(value),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`kv set ${res.status}`);
}

export async function loadServerHistory(sym: string): Promise<GexSample[]> {
  return (await kvGet<GexSample[]>(histKey(sym))) ?? [];
}
export async function saveServerHistory(sym: string, hist: GexSample[]): Promise<void> {
  await kvSet(histKey(sym), hist.slice(-HIST_CAP));
}
export async function loadServerJournal(): Promise<PredictionRecord[]> {
  return (await kvGet<PredictionRecord[]>(JOURNAL_KEY)) ?? [];
}
export async function saveServerJournal(journal: PredictionRecord[]): Promise<void> {
  await kvSet(JOURNAL_KEY, journal.slice(-JOURNAL_CAP));
}
