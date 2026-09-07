import { clockFor } from "./clock";
import type { Bar, Instrument } from "./types";

// Volume features, built so that every value at bar i is computable from bars[0..i] only.
//
// The reason this module exists at all: every earlier study in this repo is OHLC-only, and an
// OHLC-only rule competes with everyone who has the same OHLC. Volume is the one column in the file
// that carries information price does not, and the naive way to use it — comparing a bar's volume to
// a trailing average — is nearly worthless intraday, because the session volume profile is a deep U.
// A 15:55 bar is "high volume" against a 20-bar trailing mean essentially every day, and an 11:30
// bar almost never is, so a trailing-mean surge filter is largely a clock in disguise.
//
// The fix is to compare a bar to the SAME MINUTE OF DAY on prior sessions. Both normalisations are
// computed here so the difference between them can be measured rather than assumed.

/** Median of a numeric array (copy-sorted; empty -> NaN). */
function median(xs: number[]): number {
  if (!xs.length) return NaN;
  const s = [...xs].sort((a, b) => a - b);
  const mid = s.length >> 1;
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

export interface VolumeContext {
  /**
   * Bar volume divided by the median volume of the SAME minute-of-day over the prior completed
   * sessions. This is the time-of-day-neutral "is this bar busy?" measure. NaN during warm-up.
   */
  rvolTod: number[];
  /**
   * Bar volume divided by the mean of the trailing 20 bars, ignoring session boundaries — the naive
   * normalisation used by essentially every "volume surge" filter, kept here as the control.
   * NaN during warm-up.
   */
  rvolTrailing: number[];
  /**
   * Close location inside the bar's own range, mapped to [-1, +1]: +1 closed on the high, -1 on the
   * low. The crudest possible buy/sell-pressure proxy that uses only OHLC — it is a *proxy*, not
   * delta: a bar can close on its high on passive buying or on a short squeeze, and this cannot tell
   * them apart. NaN when high == low.
   */
  pressure: number[];
  /** Cumulative session volume up to and including bar i. */
  sessionVolume: number[];
  /**
   * Cumulative session volume divided by the median cumulative session volume at the same
   * minute-of-day over prior sessions — "is today unusually busy so far?". NaN during warm-up.
   */
  sessionPace: number[];
  /** Session sum of v * pressure divided by session volume: a volume-weighted session delta proxy. */
  sessionDelta: number[];
}

export interface VolumeContextOptions {
  /** How many prior sessions of the same minute-of-day to keep in the reference window. */
  priorSessions?: number;
  /** Minimum prior observations before a normalised value is emitted rather than NaN. */
  minSessions?: number;
  /** Trailing window for the (deliberately naive) rolling volume mean. */
  trailingBars?: number;
}

/**
 * Build the per-bar volume context. Every reference distribution is drawn from COMPLETED prior
 * sessions only, so nothing here can see its own day, let alone the future.
 */
export function volumeContext(bars: Bar[], inst: Instrument, opts: VolumeContextOptions = {}): VolumeContext {
  const priorSessions = opts.priorSessions ?? 20;
  const minSessions = opts.minSessions ?? 10;
  const trailingBars = opts.trailingBars ?? 20;
  const n = bars.length;
  const clock = clockFor(bars, inst.tz);

  const rvolTod = new Array<number>(n).fill(NaN);
  const rvolTrailing = new Array<number>(n).fill(NaN);
  const pressure = new Array<number>(n).fill(NaN);
  const sessionVolume = new Array<number>(n).fill(0);
  const sessionPace = new Array<number>(n).fill(NaN);
  const sessionDelta = new Array<number>(n).fill(NaN);

  const barHistory = new Map<number, number[]>();
  const cumHistory = new Map<number, number[]>();
  /** This session's (minuteOfDay, volume, cumulative) rows, flushed into history at the session end. */
  let pending: { m: number; v: number; cum: number }[] = [];

  const flush = () => {
    for (const row of pending) {
      for (const [map, value] of [[barHistory, row.v], [cumHistory, row.cum]] as const) {
        let arr = map.get(row.m);
        if (!arr) map.set(row.m, (arr = []));
        arr.push(value);
        if (arr.length > priorSessions) arr.shift();
      }
    }
    pending = [];
  };

  let day = -1;
  let cum = 0;
  let cumDelta = 0;

  for (let i = 0; i < n; i++) {
    if (clock.dayIndex[i] !== day) {
      flush();
      day = clock.dayIndex[i];
      cum = 0;
      cumDelta = 0;
    }
    const b = bars[i];
    const m = clock.minuteOfDay[i];
    cum += b.v;
    sessionVolume[i] = cum;

    const range = b.h - b.l;
    const p = range > 0 ? (2 * (b.c - b.l)) / range - 1 : NaN;
    pressure[i] = p;
    if (Number.isFinite(p)) cumDelta += p * b.v;
    sessionDelta[i] = cum > 0 ? cumDelta / cum : NaN;

    const hb = barHistory.get(m);
    if (hb && hb.length >= minSessions) {
      const med = median(hb);
      if (med > 0) rvolTod[i] = b.v / med;
    }
    const hc = cumHistory.get(m);
    if (hc && hc.length >= minSessions) {
      const med = median(hc);
      if (med > 0) sessionPace[i] = cum / med;
    }

    if (i >= trailingBars) {
      let s = 0;
      for (let j = i - trailingBars; j < i; j++) s += bars[j].v;
      const avg = s / trailingBars;
      if (avg > 0) rvolTrailing[i] = b.v / avg;
    }

    pending.push({ m, v: b.v, cum });
  }
  return { rvolTod, rvolTrailing, pressure, sessionVolume, sessionPace, sessionDelta };
}

/** Mean of the finite values of `xs` over the window [i-k+1, i]; NaN if any is missing. */
export function windowMean(xs: number[], i: number, k: number): number {
  if (i - k + 1 < 0) return NaN;
  let s = 0;
  for (let j = i - k + 1; j <= i; j++) {
    if (!Number.isFinite(xs[j])) return NaN;
    s += xs[j];
  }
  return s / k;
}

/**
 * Volume-weighted mean pressure over the trailing k bars — the crude cumulative-delta proxy in
 * rolling form. Returns NaN if any bar in the window lacks a defined pressure.
 */
export function weightedPressure(bars: Bar[], pressure: number[], i: number, k: number): number {
  if (i - k + 1 < 0) return NaN;
  let num = 0;
  let den = 0;
  for (let j = i - k + 1; j <= i; j++) {
    if (!Number.isFinite(pressure[j])) return NaN;
    num += pressure[j] * bars[j].v;
    den += bars[j].v;
  }
  return den > 0 ? num / den : NaN;
}
