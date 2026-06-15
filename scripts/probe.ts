/**
 * Standalone Barchart OnDemand endpoint probe.
 *
 *   npm run probe                          # probe every endpoint
 *   npm run probe -- --only quote,history  # probe a subset
 *
 * Reads BARCHART_API_KEY from .env.local (or the environment). Makes exactly ONE
 * minimal request per endpoint, classifies the result, and on success saves the raw
 * JSON into /fixtures/<name>.live.json so you can seed real fixtures from whatever
 * your plan actually returns. Spends at most one request per endpoint.
 *
 * This script is intentionally self-contained (no app imports) so it works even if
 * the rest of the build is broken.
 */
import { config as loadEnv } from "dotenv";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

loadEnv({ path: ".env.local" });
loadEnv(); // also pick up .env if present

const API_KEY = process.env.BARCHART_API_KEY ?? "";
const BASE = (process.env.BARCHART_BASE_URL ?? "https://ondemand.websol.barchart.com/").replace(/\/+$/, "") + "/";
const FIXTURES = path.join(process.cwd(), "fixtures");

type Verdict = "OK" | "EMPTY" | "AUTH/PLAN" | "RATE-LIMIT" | "ERROR";

interface ProbeDef {
  name: string;
  endpoint: string;
  params: Record<string, string>;
  saveAs?: string;
  tier: string;
}

const PROBES: ProbeDef[] = [
  { name: "getQuote", endpoint: "getQuote.json", params: { symbols: "AAPL" }, saveAs: "quote.AAPL.live.json", tier: "free (expected)" },
  { name: "getHistory", endpoint: "getHistory.json", params: { symbol: "AAPL", type: "daily", maxRecords: "30" }, saveAs: "history.AAPL.live.json", tier: "free (expected)" },
  { name: "getEquityOptions", endpoint: "getEquityOptions.json", params: { symbol: "AAPL" }, saveAs: "options.AAPL.live.json", tier: "subscription (may be locked)" },
  { name: "getOptionsScreener", endpoint: "getOptionsScreener.json", params: { volumeMinimum: "500" }, saveAs: "screener.live.json", tier: "subscription (may be locked)" },
  { name: "getEquityOptionsHistory", endpoint: "getEquityOptionsHistory.json", params: { symbol: "AAPL", expirationDate: "2026-06-19" }, tier: "subscription (may be locked)" },
];

function pickOnly(): Set<string> | null {
  const idx = process.argv.indexOf("--only");
  if (idx >= 0 && process.argv[idx + 1]) {
    return new Set(process.argv[idx + 1].split(",").map((s) => s.trim().toLowerCase()));
  }
  return null;
}

function classify(httpStatus: number, body: unknown): { verdict: Verdict; detail: string } {
  if (httpStatus === 401 || httpStatus === 403) return { verdict: "AUTH/PLAN", detail: `HTTP ${httpStatus}` };
  if (httpStatus === 429) return { verdict: "RATE-LIMIT", detail: `HTTP ${httpStatus}` };
  if (httpStatus === 204) return { verdict: "EMPTY", detail: "HTTP 204" };
  if (httpStatus >= 400) return { verdict: "ERROR", detail: `HTTP ${httpStatus}` };

  const b = body as { status?: { code?: number; message?: string }; results?: unknown } | null;
  const code = b?.status?.code;
  const msg = String(b?.status?.message ?? "");
  if (code === 200) {
    const n = Array.isArray(b?.results) ? b!.results!.length : 0;
    return n > 0 ? { verdict: "OK", detail: `${n} result(s)` } : { verdict: "EMPTY", detail: "0 results" };
  }
  if (code === 204) return { verdict: "EMPTY", detail: msg || "no data" };
  if (code === 401 || code === 403 || /not authorized|not subscribed|permission/i.test(msg)) {
    return { verdict: "AUTH/PLAN", detail: `${code}: ${msg}` };
  }
  if (code === 429 || /max queries|rate limit/i.test(msg)) return { verdict: "RATE-LIMIT", detail: `${code}: ${msg}` };
  return { verdict: "ERROR", detail: `${code ?? "?"}: ${msg}` };
}

function inferDelay(body: unknown): string {
  const r = (body as { results?: Array<{ mode?: string; tradeTimestamp?: string }> } | null)?.results?.[0];
  if (!r) return "unknown";
  const mode = String(r.mode ?? "").toLowerCase();
  if (mode.startsWith("r")) return "real-time (mode=r)";
  if (mode.startsWith("d")) return "delayed (mode=d)";
  if (r.tradeTimestamp) {
    const ageMin = Math.round((Date.now() - new Date(r.tradeTimestamp).getTime()) / 60000);
    if (Number.isFinite(ageMin)) return `last trade ~${ageMin} min ago`;
  }
  return "unknown";
}

const ICON: Record<Verdict, string> = {
  OK: "✅",
  EMPTY: "⚠️ ",
  "AUTH/PLAN": "🔒",
  "RATE-LIMIT": "⏳",
  ERROR: "❌",
};

async function main() {
  const only = pickOnly();
  console.log("Barchart OnDemand probe");
  console.log("base:", BASE);

  if (!API_KEY) {
    console.log("\n⚠️  No BARCHART_API_KEY found in .env.local or the environment.");
    console.log("   → Cannot probe LIVE endpoints. The app still runs fully in FIXTURES mode.");
    console.log("   → Add BARCHART_API_KEY and re-run `npm run probe` to test live access.\n");
    return;
  }
  console.log("key: present (len=" + API_KEY.length + ")");
  await mkdir(FIXTURES, { recursive: true });

  const lines: string[] = [];
  for (const p of PROBES) {
    const key = p.name.toLowerCase();
    if (only && !only.has(key) && !only.has(key.replace(/^get/, ""))) continue;

    const url = new URL(p.endpoint, BASE);
    url.searchParams.set("apikey", API_KEY);
    for (const [k, v] of Object.entries(p.params)) url.searchParams.set(k, v);

    let verdict: Verdict = "ERROR";
    let detail = "";
    let body: unknown = null;
    try {
      const res = await fetch(url.toString(), { headers: { accept: "application/json" } });
      const text = await res.text();
      try {
        body = JSON.parse(text);
      } catch {
        body = null;
      }
      ({ verdict, detail } = classify(res.status, body));
      if (verdict === "OK" && p.saveAs && body) {
        await writeFile(path.join(FIXTURES, p.saveAs), JSON.stringify(body, null, 2));
        detail += ` → saved ${p.saveAs}`;
      }
    } catch (e) {
      verdict = "ERROR";
      detail = e instanceof Error ? e.message : String(e);
    }

    lines.push(`${ICON[verdict]} ${p.name.padEnd(24)} ${verdict.padEnd(11)} ${detail}   [${p.tier}]`);
    if (p.name === "getQuote" && verdict === "OK") {
      lines.push(`   ↳ data timeliness: ${inferDelay(body)}`);
    }
  }

  console.log("\nResults:\n");
  console.log(lines.join("\n"));
  console.log("\nLegend: ✅ usable   ⚠️ empty   🔒 not on your plan   ⏳ rate-limited   ❌ error");
}

main().catch((e) => {
  console.error("probe failed:", e);
  process.exit(1);
});
