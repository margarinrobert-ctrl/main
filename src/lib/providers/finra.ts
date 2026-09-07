import { config } from "../barchart/config";
import { cache } from "../cache/store";
import type { DarkPoolDay } from "../flow/darkpool";

/**
 * FINRA consolidated daily short-sale volume — the public, keyless OFF-EXCHANGE (dark-pool) feed.
 *
 *   {base}/equity/regsho/daily/CNMSshvol{YYYYMMDD}.txt   (pipe-delimited, one row per symbol)
 *   Header:  Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market
 *
 * `TotalVolume` here is the volume reported to FINRA's Trade Reporting Facilities (off-exchange:
 * ATS/dark pools + wholesaler internalization), NOT the consolidated tape — which is exactly why it
 * isolates the "dark" prints. Files exist only for trading days and publish after the close (T+0
 * evening / T+1), so weekends/holidays/not-yet-published days simply 404 and are skipped.
 *
 * Only reachable from servers with open egress (Vercel / GitHub Actions). Locally the host is usually
 * blocked, so the caller falls back to the sample fixture.
 */

interface FinraRow {
  short: number;
  shortExempt: number;
  total: number;
}

function fmtDate(d: Date): string {
  return `${d.getUTCFullYear()}${String(d.getUTCMonth() + 1).padStart(2, "0")}${String(d.getUTCDate()).padStart(2, "0")}`;
}

function isoDate(yyyymmdd: string): string {
  return `${yyyymmdd.slice(0, 4)}-${yyyymmdd.slice(4, 6)}-${yyyymmdd.slice(6, 8)}`;
}

/** Parse a CNMS short-sale file into a per-symbol map. Tolerant of the trailing record-count footer. */
export function parseFinraDaily(text: string): Map<string, FinraRow> {
  const out = new Map<string, FinraRow>();
  const lines = text.split(/\r?\n/);
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (!line || !line.includes("|")) continue;
    const p = line.split("|");
    if (p.length < 5) continue;
    const sym = p[1]?.trim().toUpperCase();
    if (!sym || sym === "SYMBOL") continue;
    const total = Number(p[4]);
    if (!Number.isFinite(total)) continue; // skips the "Records:" footer
    out.set(sym, { short: Number(p[2]) || 0, shortExempt: Number(p[3]) || 0, total });
  }
  return out;
}

async function fetchDaily(yyyymmdd: string): Promise<Map<string, FinraRow> | null> {
  const url = `${config.finraBaseUrl}/equity/regsho/daily/CNMSshvol${yyyymmdd}.txt`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), config.requestTimeoutMs);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      headers: { accept: "text/plain", "user-agent": "Mozilla/5.0 (compatible; OptionsFlow/0.1; +https://finra.org)" },
    });
    if (!res.ok) return null; // 404 = weekend/holiday/not yet published
    const map = parseFinraDaily(await res.text());
    return map.size ? map : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Cached per-day map, shared across all symbols. Successful days are cached for the configured TTL
 * (the data is immutable once published); misses get a short negative cache so a not-yet-published
 * day is retried later the same session.
 */
async function dailyMap(yyyymmdd: string): Promise<Map<string, FinraRow> | null> {
  const key = `finra:cnms:${yyyymmdd}`;
  const hit = await cache.get<Record<string, FinraRow> | "MISS">(key);
  if (hit === "MISS") return null;
  if (hit) return new Map(Object.entries(hit));
  const map = await fetchDaily(yyyymmdd);
  if (map) {
    await cache.set(key, Object.fromEntries(map), config.darkPoolCacheTtlSeconds);
    return map;
  }
  await cache.set(key, "MISS", 1800); // 30-min negative cache
  return null;
}

async function pool<T, R>(items: T[], limit: number, fn: (t: T) => Promise<R>): Promise<R[]> {
  const out: R[] = new Array(items.length);
  let i = 0;
  const worker = async () => {
    while (i < items.length) {
      const idx = i++;
      out[idx] = await fn(items[idx]);
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return out;
}

/** Off-exchange (dark-pool) daily series for a symbol over the last `lookback` trading days. */
export async function finraDarkPool(symbol: string, lookback = config.darkPoolLookbackDays): Promise<DarkPoolDay[]> {
  const sym = symbol.toUpperCase();
  // Candidate weekdays, newest first; over-fetch a little to absorb holidays.
  const candidates: string[] = [];
  const today = new Date();
  for (let k = 0; candidates.length < lookback + 6 && k < lookback + 24; k++) {
    const d = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() - k));
    const wd = d.getUTCDay();
    if (wd === 0 || wd === 6) continue; // skip Sat/Sun
    candidates.push(fmtDate(d));
  }
  const maps = await pool(candidates, 4, dailyMap);
  const rows: DarkPoolDay[] = [];
  for (let idx = 0; idx < candidates.length && rows.length < lookback; idx++) {
    const r = maps[idx]?.get(sym);
    if (!r) continue;
    rows.push({
      date: isoDate(candidates[idx]),
      shortVolume: r.short,
      shortExemptVolume: r.shortExempt,
      offExchangeVolume: r.total,
      consolidatedVolume: null,
    });
  }
  return rows.sort((a, b) => a.date.localeCompare(b.date));
}
