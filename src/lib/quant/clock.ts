import type { Bar } from "./types";

// Exchange-local time.
//
// Intraday futures research MUST run on the exchange's wall clock, not UTC. The 09:30 ET open is
// the same event every day; 13:30 UTC is only the same event for eight months of the year. Anchoring
// sessions, opening ranges and time-of-day studies to UTC smears every DST-crossing sample across
// two different points in the trading day — which quietly destroys exactly the intraday structure a
// scalping study is trying to measure.
//
// The DST rule for America/New_York is implemented directly (US federal rule since 2007: forward on
// the second Sunday in March at 02:00 local, back on the first Sunday in November at 02:00 local).
// It is verified against Intl.DateTimeFormat in clock.test.ts across the whole sample period —
// the arithmetic version is used because it is ~100x faster over a million bars.

export type ExchangeTz = "America/New_York" | "UTC";

const MS_DAY = 86_400_000;

/** UTC ms of 02:00 local on the nth `weekday` of `month` (0-based) in `year`. */
function nthWeekdayUtc(year: number, month: number, weekday: number, n: number, localHour: number, stdOffsetMin: number): number {
  const first = Date.UTC(year, month, 1);
  const firstDow = new Date(first).getUTCDay();
  const day = 1 + ((weekday - firstDow + 7) % 7) + (n - 1) * 7;
  return Date.UTC(year, month, day, localHour) + stdOffsetMin * 60_000;
}

/**
 * Offset of America/New_York from UTC, in minutes (EST = -300, EDT = -240).
 * Valid for 2007 onward, which covers every dataset this stack is aimed at.
 */
export function nyOffsetMinutes(utcMs: number): number {
  const year = new Date(utcMs).getUTCFullYear();
  // Spring forward: 2nd Sunday of March, 02:00 EST (= 07:00 UTC).
  const start = nthWeekdayUtc(year, 2, 0, 2, 2, 300);
  // Fall back: 1st Sunday of November, 02:00 EDT (= 06:00 UTC).
  const end = nthWeekdayUtc(year, 10, 0, 1, 2, 240);
  return utcMs >= start && utcMs < end ? -240 : -300;
}

export function offsetMinutes(utcMs: number, tz: ExchangeTz): number {
  return tz === "UTC" ? 0 : nyOffsetMinutes(utcMs);
}

/** Convert an exchange-local wall clock to true UTC ms. Used at ingest. */
export function localToUtc(year: number, month1: number, day: number, hour: number, minute: number, tz: ExchangeTz): number {
  const naive = Date.UTC(year, month1 - 1, day, hour, minute);
  if (tz === "UTC") return naive;
  // Two-pass fixed point: guess with the offset at the naive instant, then correct.
  const guess = naive - nyOffsetMinutes(naive) * 60_000;
  return naive - nyOffsetMinutes(guess) * 60_000;
}

/** Local wall-clock fields a strategy is allowed to condition on. */
export interface Clock {
  /** Local hour 0..23. */
  hour: Int8Array;
  /** Local minute 0..59. */
  minute: Int8Array;
  /** Minutes since local midnight. */
  minuteOfDay: Int16Array;
  /** Local day-of-week, 0 = Sunday. */
  weekday: Int8Array;
  /** Local calendar date as days-since-epoch — the session id for VWAP and opening ranges. */
  dayIndex: Int32Array;
  tz: ExchangeTz;
}

const cache = new WeakMap<Bar[], Map<string, Clock>>();

/** Local-time fields for a bar series, computed once and memoised per (series, timezone). */
export function clockFor(bars: Bar[], tz: ExchangeTz = "America/New_York"): Clock {
  let perTz = cache.get(bars);
  if (!perTz) {
    perTz = new Map();
    cache.set(bars, perTz);
  }
  const hit = perTz.get(tz);
  if (hit) return hit;

  const n = bars.length;
  const clock: Clock = {
    hour: new Int8Array(n),
    minute: new Int8Array(n),
    minuteOfDay: new Int16Array(n),
    weekday: new Int8Array(n),
    dayIndex: new Int32Array(n),
    tz,
  };
  for (let i = 0; i < n; i++) {
    const local = bars[i].t + offsetMinutes(bars[i].t, tz) * 60_000;
    const d = new Date(local);
    const h = d.getUTCHours();
    const m = d.getUTCMinutes();
    clock.hour[i] = h;
    clock.minute[i] = m;
    clock.minuteOfDay[i] = h * 60 + m;
    clock.weekday[i] = d.getUTCDay();
    clock.dayIndex[i] = Math.floor(local / MS_DAY);
  }
  perTz.set(tz, clock);
  return clock;
}

/** Is a local minute-of-day inside [start, end)? Handles windows that wrap past local midnight. */
export function inWindow(minuteOfDay: number, startMin: number, endMin: number): boolean {
  return startMin <= endMin ? minuteOfDay >= startMin && minuteOfDay < endMin : minuteOfDay >= startMin || minuteOfDay < endMin;
}

export const hhmm = (minutes: number): string =>
  `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
