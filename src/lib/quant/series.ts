import type { Bar } from "./types";

// Causal indicator primitives. Every function returns an array the same length as its input where
// element i uses ONLY elements 0..i. Warm-up positions are NaN, never silently zero — a zero would
// masquerade as a real reading and quietly create look-ahead-shaped bugs.

export const nan = (n: number): number[] => new Array(n).fill(NaN);

export function sma(x: number[], n: number): number[] {
  const out = nan(x.length);
  if (n <= 0) return out;
  let sum = 0;
  for (let i = 0; i < x.length; i++) {
    sum += x[i];
    if (i >= n) sum -= x[i - n];
    if (i >= n - 1) out[i] = sum / n;
  }
  return out;
}

export function ema(x: number[], n: number): number[] {
  const out = nan(x.length);
  if (n <= 0 || x.length === 0) return out;
  const k = 2 / (n + 1);
  let prev = NaN;
  for (let i = 0; i < x.length; i++) {
    if (i === n - 1) {
      let s = 0;
      for (let j = 0; j <= i; j++) s += x[j];
      prev = s / n;
      out[i] = prev;
    } else if (i >= n) {
      prev = x[i] * k + prev * (1 - k);
      out[i] = prev;
    }
  }
  return out;
}

/** Rolling sample standard deviation. */
export function rollingStd(x: number[], n: number): number[] {
  const out = nan(x.length);
  if (n < 2) return out;
  let s = 0;
  let s2 = 0;
  for (let i = 0; i < x.length; i++) {
    s += x[i];
    s2 += x[i] * x[i];
    if (i >= n) {
      s -= x[i - n];
      s2 -= x[i - n] * x[i - n];
    }
    if (i >= n - 1) {
      const v = (s2 - (s * s) / n) / (n - 1);
      out[i] = v > 0 ? Math.sqrt(v) : 0;
    }
  }
  return out;
}

export function trueRange(bars: Bar[]): number[] {
  const out = nan(bars.length);
  for (let i = 0; i < bars.length; i++) {
    const b = bars[i];
    out[i] = i === 0 ? b.h - b.l : Math.max(b.h - b.l, Math.abs(b.h - bars[i - 1].c), Math.abs(b.l - bars[i - 1].c));
  }
  return out;
}

/** Wilder's ATR — the volatility unit every stop and target in this stack is quoted in. */
export function atr(bars: Bar[], n: number): number[] {
  const tr = trueRange(bars);
  const out = nan(bars.length);
  if (bars.length < n || n <= 0) return out;
  let sum = 0;
  for (let i = 0; i < n; i++) sum += tr[i];
  let prev = sum / n;
  out[n - 1] = prev;
  for (let i = n; i < bars.length; i++) {
    prev = (prev * (n - 1) + tr[i]) / n;
    out[i] = prev;
  }
  return out;
}

export function rsi(x: number[], n: number): number[] {
  const out = nan(x.length);
  if (x.length <= n || n <= 0) return out;
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= n; i++) {
    const d = x[i] - x[i - 1];
    if (d >= 0) gain += d;
    else loss -= d;
  }
  let ag = gain / n;
  let al = loss / n;
  out[n] = al === 0 ? 100 : 100 - 100 / (1 + ag / al);
  for (let i = n + 1; i < x.length; i++) {
    const d = x[i] - x[i - 1];
    ag = (ag * (n - 1) + Math.max(d, 0)) / n;
    al = (al * (n - 1) + Math.max(-d, 0)) / n;
    out[i] = al === 0 ? 100 : 100 - 100 / (1 + ag / al);
  }
  return out;
}

/** Highest high / lowest low of the n bars ENDING at i-1 (excludes the current bar). */
export function priorExtreme(bars: Bar[], n: number, kind: "high" | "low"): number[] {
  const out = nan(bars.length);
  for (let i = n; i < bars.length; i++) {
    let best = kind === "high" ? -Infinity : Infinity;
    for (let j = i - n; j < i; j++) {
      const v = kind === "high" ? bars[j].h : bars[j].l;
      best = kind === "high" ? Math.max(best, v) : Math.min(best, v);
    }
    out[i] = best;
  }
  return out;
}

/** Session-anchored VWAP, reset whenever `sessionId` changes. */
export function sessionVwap(bars: Bar[], sessionId: ArrayLike<number>): number[] {
  const out = nan(bars.length);
  let pv = 0;
  let vv = 0;
  let cur = NaN;
  for (let i = 0; i < bars.length; i++) {
    if (sessionId[i] !== cur) {
      cur = sessionId[i];
      pv = 0;
      vv = 0;
    }
    const typical = (bars[i].h + bars[i].l + bars[i].c) / 3;
    const vol = bars[i].v > 0 ? bars[i].v : 1;
    pv += typical * vol;
    vv += vol;
    out[i] = pv / vv;
  }
  return out;
}

/**
 * Session-anchored VWAP together with its volume-weighted standard deviation.
 *
 * This is the construction "VWAP bands" actually refers to: sigma is the volume-weighted dispersion
 * of typical price around VWAP so far this session, so the bands widen when heavy volume trades away
 * from the average and stay tight when it does not. That is a different object from VWAP plus an
 * ATR multiple — ATR measures bar range and knows nothing about where the volume traded — and the
 * two disagree most exactly when it matters, on a heavy directional open.
 */
export function sessionVwapBands(bars: Bar[], sessionId: ArrayLike<number>): { vwap: number[]; sigma: number[] } {
  const vwap = nan(bars.length);
  const sigma = nan(bars.length);
  let pv = 0;
  let vv = 0;
  let pv2 = 0;
  let cur = NaN;
  for (let i = 0; i < bars.length; i++) {
    if (sessionId[i] !== cur) {
      cur = sessionId[i];
      pv = 0;
      vv = 0;
      pv2 = 0;
    }
    const typical = (bars[i].h + bars[i].l + bars[i].c) / 3;
    const vol = bars[i].v > 0 ? bars[i].v : 1;
    pv += typical * vol;
    vv += vol;
    pv2 += typical * typical * vol;
    const mean = pv / vv;
    vwap[i] = mean;
    const variance = pv2 / vv - mean * mean;
    sigma[i] = variance > 0 ? Math.sqrt(variance) : 0;
  }
  return { vwap, sigma };
}

/**
 * ROLLING volume-weighted mean and dispersion over the last `n` bars.
 *
 * The session-anchored version aggregates everything since the open, so by mid-afternoon it
 * describes six hours of trade. If the reversion that actually exists in the data lives at a
 * 10-20 bar horizon — which is what the variance ratios say — then the session anchor is measuring
 * a stretch away from the wrong timescale. This is the same statistic computed over a window that
 * matches the horizon, so the two can be compared directly.
 */
export function rollingVwapBands(bars: Bar[], n: number): { vwap: number[]; sigma: number[] } {
  const vwap = nan(bars.length);
  const sigma = nan(bars.length);
  if (n < 2) return { vwap, sigma };
  let pv = 0;
  let vv = 0;
  let pv2 = 0;
  const typicalOf = (i: number) => (bars[i].h + bars[i].l + bars[i].c) / 3;
  const volOf = (i: number) => (bars[i].v > 0 ? bars[i].v : 1);
  for (let i = 0; i < bars.length; i++) {
    const t = typicalOf(i);
    const v = volOf(i);
    pv += t * v;
    vv += v;
    pv2 += t * t * v;
    if (i >= n) {
      const to = typicalOf(i - n);
      const vo = volOf(i - n);
      pv -= to * vo;
      vv -= vo;
      pv2 -= to * to * vo;
    }
    if (i >= n - 1 && vv > 0) {
      const mean = pv / vv;
      vwap[i] = mean;
      const variance = pv2 / vv - mean * mean;
      sigma[i] = variance > 0 ? Math.sqrt(variance) : 0;
    }
  }
  return { vwap, sigma };
}

/** Rolling z-score of x against its own trailing window (current value included). */
export function zscore(x: number[], n: number): number[] {
  const m = sma(x, n);
  const s = rollingStd(x, n);
  return x.map((v, i) => (Number.isFinite(m[i]) && s[i] > 0 ? (v - m[i]) / s[i] : NaN));
}

/** Percentile rank (0..1) of the current value within its trailing window. */
export function percentRank(x: number[], n: number): number[] {
  const out = nan(x.length);
  for (let i = n - 1; i < x.length; i++) {
    let below = 0;
    for (let j = i - n + 1; j <= i; j++) if (x[j] < x[i]) below++;
    out[i] = below / (n - 1);
  }
  return out;
}

export const closes = (bars: Bar[]): number[] => bars.map((b) => b.c);

