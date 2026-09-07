/**
 * Ingest raw intraday OHLCV into the canonical research format.
 *
 *   npx tsx scripts/quant-ingest.ts --in raw.csv --out data/NQ_5m.csv --tf 5 --tz America/New_York
 *
 * Input timestamps are read as EXCHANGE WALL CLOCK in `--tz` and converted to true UTC, so a
 * dataset stamped in US Eastern survives both DST transitions. Output is always UTC ISO-8601.
 *
 * Resampling is anchored to LOCAL midnight, which is what makes a 5-minute bucket line up with the
 * 09:30 ET open instead of straddling it.
 */
import { createReadStream, mkdirSync, writeFileSync } from "node:fs";
import { createInterface } from "node:readline";
import { dirname } from "node:path";
import { localToUtc, nyOffsetMinutes, type ExchangeTz } from "../src/lib/quant/clock";

interface Args {
  in: string;
  out: string;
  tf: number;
  tz: ExchangeTz;
}

function parseArgs(): Args {
  const a = process.argv.slice(2);
  const get = (k: string, d?: string) => {
    const i = a.indexOf(`--${k}`);
    return i >= 0 && a[i + 1] ? a[i + 1] : d;
  };
  const input = get("in");
  const out = get("out");
  if (!input || !out) {
    console.error("usage: quant-ingest --in <raw.csv> --out <data/SYM_5m.csv> [--tf 5] [--tz America/New_York]");
    process.exit(1);
  }
  return { in: input, out, tf: Number(get("tf", "5")), tz: (get("tz", "America/New_York") as ExchangeTz) };
}

/** Parse `M/D/YYYY H:MM[:SS]` or ISO-ish local stamps into local calendar fields. */
function parseLocalStamp(raw: string): { y: number; mo: number; d: number; h: number; mi: number } | null {
  const s = raw.trim();
  let m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})[ T](\d{1,2}):(\d{2})/.exec(s);
  if (m) return { y: +m[3], mo: +m[1], d: +m[2], h: +m[4], mi: +m[5] };
  m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})/.exec(s);
  if (m) return { y: +m[1], mo: +m[2], d: +m[3], h: +m[4], mi: +m[5] };
  return null;
}

/** Local wall-clock times that DST makes impossible (spring forward) or ambiguous (fall back). */
function dstAnomaly(y: number, mo: number, d: number, h: number, tz: ExchangeTz): "skipped" | "repeated" | null {
  if (tz !== "America/New_York") return null;
  const utcGuess = Date.UTC(y, mo - 1, d, h);
  const before = nyOffsetMinutes(utcGuess - 3 * 3_600_000);
  const after = nyOffsetMinutes(utcGuess + 3 * 3_600_000);
  if (before === after) return null;
  return before === -300 ? "skipped" : "repeated";
}

async function main() {
  const args = parseArgs();
  const bucketMs = args.tf * 60_000;

  const rl = createInterface({ input: createReadStream(args.in), crlfDelay: Infinity });
  let header: string[] | null = null;
  let iT = -1, iO = -1, iH = -1, iL = -1, iC = -1, iV = -1;

  const out: string[] = ["timestamp,open,high,low,close,volume"];
  let cur: { key: number; t: number; o: number; h: number; l: number; c: number; v: number } | null = null;
  let rows = 0;
  let skippedRows = 0;
  let dstSkipped = 0;
  let dstRepeated = 0;
  let outBars = 0;
  let lastT = -Infinity;
  let nonMonotonic = 0;

  const flush = () => {
    if (!cur) return;
    out.push(`${new Date(cur.t).toISOString()},${cur.o},${cur.h},${cur.l},${cur.c},${cur.v}`);
    outBars++;
  };

  for await (const line of rl) {
    if (!line.trim()) continue;
    const f = line.split(",");
    if (!header) {
      header = f.map((x) => x.trim().toLowerCase());
      const col = (...names: string[]) => {
        for (const n of names) {
          const i = header!.findIndex((h) => h === n || h.replace(/[^a-z]/g, "") === n);
          if (i >= 0) return i;
        }
        return -1;
      };
      iT = col("timestamp", "timestampet", "time", "datetime", "date");
      iO = col("open", "o");
      iH = col("high", "h");
      iL = col("low", "l");
      iC = col("close", "c");
      iV = col("volume", "vol", "v");
      if (iT < 0 || iO < 0 || iH < 0 || iL < 0 || iC < 0) throw new Error(`missing OHLC columns in header: ${header.join(",")}`);
      continue;
    }

    const parsed = parseLocalStamp(f[iT]);
    if (!parsed) {
      skippedRows++;
      continue;
    }
    const anomaly = dstAnomaly(parsed.y, parsed.mo, parsed.d, parsed.h, args.tz);
    if (anomaly === "skipped") dstSkipped++;
    if (anomaly === "repeated") dstRepeated++;

    const t = localToUtc(parsed.y, parsed.mo, parsed.d, parsed.h, parsed.mi, args.tz);
    const o = +f[iO], h = +f[iH], l = +f[iL], c = +f[iC];
    const v = iV >= 0 ? +f[iV] : 0;
    if (![o, h, l, c].every(Number.isFinite)) {
      skippedRows++;
      continue;
    }
    if (t < lastT) nonMonotonic++;
    lastT = t;
    rows++;

    // Bucket on the LOCAL clock so buckets align with the session, not with UTC midnight.
    const localMs = t + (args.tz === "UTC" ? 0 : nyOffsetMinutes(t)) * 60_000;
    const key = Math.floor(localMs / bucketMs);
    if (!cur || cur.key !== key) {
      flush();
      cur = { key, t: key * bucketMs - (args.tz === "UTC" ? 0 : nyOffsetMinutes(t)) * 60_000, o, h, l, c, v };
    } else {
      cur.h = Math.max(cur.h, h);
      cur.l = Math.min(cur.l, l);
      cur.c = c;
      cur.v += v;
    }
  }
  flush();

  mkdirSync(dirname(args.out), { recursive: true });
  writeFileSync(args.out, out.join("\n") + "\n");

  console.log(`read      ${rows.toLocaleString()} source rows (${skippedRows} unparseable)`);
  console.log(`wrote     ${outBars.toLocaleString()} ${args.tf}-minute bars -> ${args.out}`);
  console.log(`timezone  ${args.tz} -> UTC`);
  if (nonMonotonic) console.log(`WARNING   ${nonMonotonic} out-of-order source rows`);
  if (dstSkipped) console.log(`WARNING   ${dstSkipped} rows fall in the spring-forward hour that does not exist locally`);
  if (dstRepeated) console.log(`WARNING   ${dstRepeated} rows fall in the fall-back hour that occurs twice (assumed first pass)`);
  if (!dstSkipped && !dstRepeated) console.log(`DST       clean — no source timestamps land in an ambiguous or non-existent local hour`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
