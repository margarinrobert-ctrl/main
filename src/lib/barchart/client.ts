import fs from "node:fs/promises";
import path from "node:path";
import { cached } from "../cache/store";
import { config } from "./config";
import { BarchartError, isRetryable, type BarchartErrorKind } from "./errors";

export interface BarchartRequestArgs {
  /** e.g. "getQuote.json" */
  endpoint: string;
  params: Record<string, string | number | undefined>;
  /** Fixture filenames tried in order (first that exists wins). */
  fixtureCandidates: string[];
}

type DataOriginInternal = "live" | "fixtures";

const FIXTURES_DIR = path.join(process.cwd(), "fixtures");

async function readFixture(candidates: string[]): Promise<unknown> {
  let lastErr: unknown;
  for (const name of candidates) {
    try {
      const raw = await fs.readFile(path.join(FIXTURES_DIR, name), "utf8");
      return JSON.parse(raw);
    } catch (e) {
      lastErr = e;
    }
  }
  throw new BarchartError("UNKNOWN", `No fixture found (tried: ${candidates.join(", ")})`, { cause: lastErr });
}

/** Read + parse a fixture outside the standard request flow (used by non-Barchart providers). */
export async function readFixtureParsed<T>(candidates: string[], parse: (raw: unknown) => T): Promise<T> {
  return parse(await readFixture(candidates));
}

function classifyHttp(status: number): BarchartErrorKind | null {
  if (status === 401 || status === 403) return "AUTH";
  if (status === 429) return "RATE_LIMIT";
  if (status === 204) return "EMPTY";
  if (status >= 500) return "NETWORK";
  if (status >= 400) return "UNKNOWN";
  return null;
}

function classifyBarchartCode(code: number, message: string): BarchartErrorKind | null {
  if (code === 200) return null;
  if (code === 204) return "EMPTY";
  if (code === 401 || code === 403) return "AUTH";
  if (code === 429 || /max queries|rate limit/i.test(message)) return "RATE_LIMIT";
  if (/not authorized|not subscribed|permission/i.test(message)) return "AUTH";
  return "UNKNOWN";
}

function buildUrl(endpoint: string, params: Record<string, string | number | undefined>): string {
  const url = new URL(endpoint, config.baseUrl);
  url.searchParams.set("apikey", config.apiKey);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") url.searchParams.set(k, String(v));
  }
  return url.toString();
}

function cacheKey(endpoint: string, params: Record<string, string | number | undefined>): string {
  const entries = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== "")
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}=${v}`);
  return `bc:${endpoint}?${entries.join("&")}`;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function liveCall(endpoint: string, params: Record<string, string | number | undefined>): Promise<unknown> {
  if (!config.apiKey) throw new BarchartError("AUTH", "BARCHART_API_KEY is not set");

  const url = buildUrl(endpoint, params);
  let attempt = 0;

  for (;;) {
    attempt++;
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), config.requestTimeoutMs);
      let res: Response;
      try {
        res = await fetch(url, { signal: controller.signal, headers: { accept: "application/json" } });
      } finally {
        clearTimeout(timer);
      }

      const httpKind = classifyHttp(res.status);
      if (httpKind) throw new BarchartError(httpKind, `Barchart HTTP ${res.status}`, { status: res.status });

      const text = await res.text();
      let json: unknown;
      try {
        json = JSON.parse(text);
      } catch (e) {
        throw new BarchartError("PARSE", "Failed to parse Barchart JSON", { cause: e });
      }

      const status = (json as { status?: { code?: unknown; message?: unknown } }).status;
      if (status && typeof status.code === "number") {
        const codeKind = classifyBarchartCode(status.code, String(status.message ?? ""));
        if (codeKind) {
          throw new BarchartError(codeKind, `Barchart status ${status.code}: ${String(status.message ?? "")}`, {
            barchartCode: status.code,
          });
        }
      }
      return json;
    } catch (err) {
      const kind = err instanceof BarchartError ? err.kind : "NETWORK";
      if (attempt <= config.maxRetries && isRetryable(kind)) {
        await sleep(250 * 2 ** (attempt - 1));
        continue;
      }
      if (err instanceof BarchartError) throw err;
      throw new BarchartError("NETWORK", "Network error calling Barchart", { cause: err });
    }
  }
}

/**
 * The single entry point for every Barchart call. Honors DATA_SOURCE:
 *  - 'fixtures' -> read canned JSON
 *  - 'live'     -> call the API (cached by endpoint+params for CACHE_TTL_SECONDS);
 *                  on ANY failure, fall back to fixtures so the UI never breaks.
 */
export async function barchartRequest<T>(
  args: BarchartRequestArgs,
  parse: (raw: unknown) => T,
): Promise<{ data: T; source: DataOriginInternal }> {
  if (config.dataSource === "fixtures") {
    const raw = await readFixture(args.fixtureCandidates);
    return { data: parse(raw), source: "fixtures" };
  }

  try {
    const raw = await cached(cacheKey(args.endpoint, args.params), config.cacheTtlSeconds, () =>
      liveCall(args.endpoint, args.params),
    );
    return { data: parse(raw), source: "live" };
  } catch (err) {
    console.warn(
      `[barchart] live call failed (${args.endpoint}); falling back to fixtures:`,
      err instanceof Error ? err.message : err,
    );
    const raw = await readFixture(args.fixtureCandidates);
    return { data: parse(raw), source: "fixtures" };
  }
}
