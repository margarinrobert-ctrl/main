import { clockFor, type ExchangeTz } from "./clock";
import type { Bar } from "./types";

// Bar ingestion + data integrity. Research is only as honest as its input series, so every load
// runs an audit and the audit is printed in the report. Silent bad data (duplicate stamps, a
// zero-volume synthetic weekend, a decimal-shifted print) is the single most expensive failure mode
// in a scalping study, because it manufactures edge that no live account will ever see.

export interface DataAudit {
  bars: number;
  first: string;
  last: string;
  /** Modal bar spacing in minutes — the study's timeframe. */
  timeframeMinutes: number;
  duplicateStamps: number;
  outOfOrder: number;
  /** Gaps > 3 bar-widths that recur at the same local time — exchange session breaks, expected. */
  structuralGaps: number;
  /** Gaps > 3 bar-widths that do NOT recur — genuinely missing data. */
  missingDataGaps: number;
  zeroVolumeBars: number;
  invalidOhlc: number;
  /**
   * Bar returns that are both > 10 ROBUST sigma (median absolute deviation, so fat tails do not
   * set the scale) and > 3% — the profile of a decimal shift or a bad print rather than a news bar.
   */
  suspectPrints: number;
  /** Returns beyond 10 robust sigma. Expected to be non-zero: intraday index futures are fat-tailed. */
  fatTailBars: number;
  tradingDays: number;
  ok: boolean;
  notes: string[];
}

/** Parse OHLCV CSV. Header is required; column order is free; timestamps may be ISO or epoch. */
export function parseCsv(text: string): Bar[] {
  const lines = text.trim().split(/\r?\n/).filter((l) => l.trim().length);
  if (lines.length < 2) return [];
  const header = lines[0].split(",").map((h) => h.trim().toLowerCase());
  const col = (...names: string[]) => {
    for (const n of names) {
      const i = header.indexOf(n);
      if (i >= 0) return i;
    }
    return -1;
  };
  const iT = col("timestamp", "time", "date", "datetime", "t");
  const iO = col("open", "o");
  const iH = col("high", "h");
  const iL = col("low", "l");
  const iC = col("close", "c", "last");
  const iV = col("volume", "vol", "v");
  if (iT < 0 || iO < 0 || iH < 0 || iL < 0 || iC < 0) throw new Error(`CSV needs timestamp,open,high,low,close columns; saw: ${header.join(",")}`);

  const bars: Bar[] = [];
  for (let li = 1; li < lines.length; li++) {
    const f = lines[li].split(",");
    const raw = (f[iT] ?? "").trim();
    let t = /^\d+$/.test(raw) ? Number(raw) : Date.parse(raw.includes(" ") && !raw.includes("T") ? raw.replace(" ", "T") + (/[zZ+]/.test(raw) ? "" : "Z") : raw);
    if (/^\d{10}$/.test(raw)) t *= 1000; // seconds -> ms
    const o = Number(f[iO]);
    const h = Number(f[iH]);
    const l = Number(f[iL]);
    const c = Number(f[iC]);
    const v = iV >= 0 ? Number(f[iV]) : 0;
    if (!Number.isFinite(t) || !Number.isFinite(o) || !Number.isFinite(h) || !Number.isFinite(l) || !Number.isFinite(c)) continue;
    bars.push({ t, o, h, l, c, v: Number.isFinite(v) ? v : 0 });
  }
  bars.sort((a, b) => a.t - b.t);
  return bars;
}

export function auditBars(bars: Bar[], tz: ExchangeTz = "America/New_York"): DataAudit {
  const notes: string[] = [];
  if (!bars.length) {
    return {
      bars: 0, first: "", last: "", timeframeMinutes: 0, duplicateStamps: 0, outOfOrder: 0, structuralGaps: 0,
      missingDataGaps: 0, zeroVolumeBars: 0, invalidOhlc: 0, suspectPrints: 0, fatTailBars: 0, tradingDays: 0,
      ok: false, notes: ["empty series"],
    };
  }
  const diffs = new Map<number, number>();
  let dupes = 0;
  let outOfOrder = 0;
  for (let i = 1; i < bars.length; i++) {
    const d = bars[i].t - bars[i - 1].t;
    if (d === 0) dupes++;
    else if (d < 0) outOfOrder++;
    else diffs.set(d, (diffs.get(d) ?? 0) + 1);
  }
  let modal = 60_000;
  let best = 0;
  for (const [d, n] of diffs) if (n > best) { best = n; modal = d; }

  // A gap that shows up at the same local minute on many days is the exchange's own session
  // structure (the CME maintenance break, a pit close). A gap that happens once is missing data.
  // Conflating the two produces an alarming audit on a perfectly good file.
  const clock = clockFor(bars, tz);
  const gapAt = new Map<number, number>();
  const gapIdx: number[] = [];
  for (let i = 1; i < bars.length; i++) {
    if (bars[i].t - bars[i - 1].t > 3 * modal) {
      gapIdx.push(i);
      gapAt.set(clock.minuteOfDay[i], (gapAt.get(clock.minuteOfDay[i]) ?? 0) + 1);
    }
  }
  let structuralGaps = 0;
  let missingDataGaps = 0;
  for (const i of gapIdx) {
    if ((gapAt.get(clock.minuteOfDay[i]) ?? 0) >= 5) structuralGaps++;
    else missingDataGaps++;
  }

  let invalid = 0;
  let zeroVol = 0;
  const rets: number[] = [];
  for (const b of bars) {
    if (b.h < b.l || b.o > b.h || b.o < b.l || b.c > b.h || b.c < b.l || b.o <= 0 || b.c <= 0) invalid++;
    if (b.v <= 0) zeroVol++;
  }
  // Only contiguous bar-to-bar returns: a move across a session break is a gap, not a bad print,
  // and mixing the two makes every overnight gap look like a data error.
  for (let i = 1; i < bars.length; i++) if (bars[i].t - bars[i - 1].t <= modal * 1.5) rets.push(Math.log(bars[i].c / bars[i - 1].c));
  // Robust scale: the standard deviation of a fat-tailed intraday series is set by the very
  // outliers we are trying to detect, so use the MAD instead (0.6745 makes it Gaussian-comparable).
  const absSorted = rets.map(Math.abs).sort((x, y) => x - y);
  const mad = absSorted.length ? absSorted[Math.floor(absSorted.length / 2)] : 0;
  const robustSd = mad / 0.6745;
  const fatTailBars = robustSd > 0 ? rets.filter((r) => Math.abs(r) > 10 * robustSd).length : 0;
  const suspectPrints = robustSd > 0 ? rets.filter((r) => Math.abs(r) > 10 * robustSd && Math.abs(r) > 0.03).length : 0;

  const days = new Set(bars.map((b) => Math.floor(b.t / 86_400_000))).size;
  if (dupes) notes.push(`${dupes} duplicate timestamps — dedupe before trusting any result`);
  if (outOfOrder) notes.push(`${outOfOrder} out-of-order bars`);
  if (invalid) notes.push(`${invalid} bars violate low <= open/close <= high`);
  if (suspectPrints) notes.push(`${suspectPrints} returns beyond 10 robust sigma AND > 3% — likely bad prints, inspect before trusting`);
  if (missingDataGaps) notes.push(`${missingDataGaps} non-recurring gaps > 3 bars — genuinely missing data`);
  if (structuralGaps) notes.push(`${structuralGaps} gaps at recurring local times — exchange session breaks, expected`);
  if (zeroVol > bars.length * 0.5) notes.push("more than half the bars have zero volume — volume-based rules are unusable");

  return {
    bars: bars.length,
    first: new Date(bars[0].t).toISOString(),
    last: new Date(bars[bars.length - 1].t).toISOString(),
    timeframeMinutes: modal / 60_000,
    duplicateStamps: dupes,
    outOfOrder,
    structuralGaps,
    missingDataGaps,
    zeroVolumeBars: zeroVol,
    invalidOhlc: invalid,
    suspectPrints,
    fatTailBars,
    tradingDays: days,
    ok: dupes === 0 && outOfOrder === 0 && invalid === 0,
    notes,
  };
}

/** Drop duplicates, re-sort, and repair bars whose OHLC ordering is impossible. */
export function cleanBars(bars: Bar[]): Bar[] {
  const seen = new Set<number>();
  const out: Bar[] = [];
  for (const b of [...bars].sort((a, z) => a.t - z.t)) {
    if (seen.has(b.t)) continue;
    seen.add(b.t);
    const h = Math.max(b.o, b.h, b.l, b.c);
    const l = Math.min(b.o, b.h, b.l, b.c);
    out.push({ ...b, h, l });
  }
  return out;
}

/** Restrict to a UTC hour window — used to keep CL research inside pit liquidity. */
export function filterSession(bars: Bar[], startUtcHour: number, endUtcHour: number): Bar[] {
  return bars.filter((b) => {
    const h = new Date(b.t).getUTCHours();
    return startUtcHour <= endUtcHour ? h >= startUtcHour && h < endUtcHour : h >= startUtcHour || h < endUtcHour;
  });
}

/** Chronological split — the only split allowed for time-series validation. */
export function splitAt(bars: Bar[], fraction: number): { train: Bar[]; test: Bar[] } {
  const k = Math.floor(bars.length * fraction);
  return { train: bars.slice(0, k), test: bars.slice(k) };
}
