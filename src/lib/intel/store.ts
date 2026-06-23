import { cached } from "../cache/store";
import type { GexSample } from "../gex-history";
import type { PredictionRecord } from "./journal";
import { HIST_CAP, JOURNAL_CAP } from "./merge";

// Durable server-side store for the intelligence layer, so history accrues even when no browser is
// open. Three backends, in priority order:
//   1. KV    — Vercel KV / Upstash Redis REST (read + write) when KV_REST_API_* / UPSTASH_* are set.
//   2. git   — READ-ONLY from a GitHub branch (default `intel-data`): a scheduled GitHub Action runs
//              the collector and commits the JSON there (see scripts/collect-intel.ts + the workflow).
//              On Vercel the repo is auto-detected from VERCEL_GIT_REPO_OWNER/SLUG; public repos need
//              no token, private repos read via the API with GH_DATA_TOKEN.
//   3. memory — per-instance fallback (resets on cold start) for local dev.
// See COLLECTION.md.

const JOURNAL_KEY = "intel:journal";
const histKey = (sym: string) => `intel:hist:${sym.toUpperCase()}`;
const histFile = (sym: string) => `history-${sym.toUpperCase()}.json`;

function kvEnv(): { url: string; token: string } | null {
  const url = process.env.KV_REST_API_URL ?? process.env.UPSTASH_REDIS_REST_URL ?? "";
  const token = process.env.KV_REST_API_TOKEN ?? process.env.UPSTASH_REDIS_REST_TOKEN ?? "";
  return url && token ? { url: url.replace(/\/+$/, ""), token } : null;
}

function gitCfg(): { owner: string; repo: string; ref: string; token: string } | null {
  const ref = process.env.INTEL_DATA_REF ?? "intel-data";
  const token = process.env.GH_DATA_TOKEN ?? "";
  const combined = process.env.INTEL_DATA_REPO ?? "";
  if (combined.includes("/")) {
    const [owner, repo] = combined.split("/");
    return owner && repo ? { owner, repo, ref, token } : null;
  }
  const owner = process.env.INTEL_DATA_OWNER ?? process.env.VERCEL_GIT_REPO_OWNER ?? "";
  const repo = combined || process.env.VERCEL_GIT_REPO_SLUG || "";
  return owner && repo ? { owner, repo, ref, token } : null;
}

export const storeMode = (): "kv" | "git" | "memory" => (kvEnv() ? "kv" : gitCfg() ? "git" : "memory");

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

/** Read a JSON data file from the git branch — raw CDN for public repos, contents API for private. */
async function gitReadJson<T>(file: string): Promise<T | null> {
  const g = gitCfg();
  if (!g) return null;
  return cached<T | null>(`git:${g.ref}:${file}`, 30, async () => {
    const raw = `https://raw.githubusercontent.com/${g.owner}/${g.repo}/${g.ref}/data/intel/${file}`;
    try {
      const res = await fetch(raw, { cache: "no-store" });
      if (res.ok) return (await res.json()) as T;
    } catch {
      /* fall through to API */
    }
    if (g.token) {
      try {
        const api = `https://api.github.com/repos/${g.owner}/${g.repo}/contents/data/intel/${encodeURIComponent(file)}?ref=${g.ref}`;
        const res = await fetch(api, { headers: { Accept: "application/vnd.github.raw", Authorization: `Bearer ${g.token}`, "User-Agent": "optionsflow-intel" }, cache: "no-store" });
        if (res.ok) return (await res.json()) as T;
      } catch {
        /* ignore */
      }
    }
    return null;
  });
}

export async function loadServerHistory(sym: string): Promise<GexSample[]> {
  if (kvEnv()) return (await kvGet<GexSample[]>(histKey(sym))) ?? [];
  const git = await gitReadJson<GexSample[]>(histFile(sym));
  if (git) return git;
  return (mem.get(histKey(sym)) as GexSample[]) ?? [];
}
export async function saveServerHistory(sym: string, hist: GexSample[]): Promise<void> {
  await kvSet(histKey(sym), hist.slice(-HIST_CAP));
}
export async function loadServerJournal(): Promise<PredictionRecord[]> {
  if (kvEnv()) return (await kvGet<PredictionRecord[]>(JOURNAL_KEY)) ?? [];
  const git = await gitReadJson<PredictionRecord[]>("journal.json");
  if (git) return git;
  return (mem.get(JOURNAL_KEY) as PredictionRecord[]) ?? [];
}
export async function saveServerJournal(journal: PredictionRecord[]): Promise<void> {
  await kvSet(JOURNAL_KEY, journal.slice(-JOURNAL_CAP));
}
