/**
 * Indicators with the PERIOD as an argument, memoised — the layer that makes a period a knob.
 *
 * Every strategy in `../strategies` takes its periods from a `Params` object baked into the
 * module. That is right for a shipped strategy and wrong for a tuner, where "what if it were
 * EMA 60" has to be answerable without a code change. This resolves `("ema", [60])` on demand and
 * caches it, so a period sweep costs one pass per distinct value and nothing per re-use.
 *
 * Primitives come from `../series` — there is one definition of EMA, ATR and RSI in this codebase
 * and it is that file. Two consequences worth stating out loud, because both have shipped broken
 * elsewhere in this repository:
 *
 *   * ATR here is WILDER's (an RMA of true range), matching `series.atr` and therefore matching
 *     what `runBacktest` and every TS strategy sizes a stop in. The Python research layer uses
 *     `ema(tr, n)` instead. They are close but not equal, so a number from this app and a number
 *     from `research/tune.py` should be compared on shape, not to the dollar.
 *   * CCI is on hlc3 and the ATR-normalised MACD histogram divides by ATR(14), both matching the
 *     Pine emitters.
 *
 * Causality is the contract: the value at bar i uses bars <= i and never i+1. `leakCheck` in
 * `tuner.test.ts` truncates the series and asserts every indicator is unchanged before the cut.
 */
import { ByteLru } from "./lru";
import type { Bar } from "../types";
import { atr as wilderAtr, ema, percentRank, priorExtreme, rollingStd, rsi, sessionVwap, sma, trueRange } from "../series";

export interface IndicatorContext {
  bars: Bar[];
  sessionId: ArrayLike<number>;
  minuteOfDay: ArrayLike<number>;
  /** Identifies the bar set, so the memo cannot serve one timeframe's array for another. */
  key: string;
  /**
   * Byte-budgeted, because a period sweep is exactly the thing that fills it: `ema{n}` over
   * n = 10..200 step 5 is 39 arrays, and each one is 8 bytes a bar. On a million-bar file that is
   * 312 MB of cache for a single knob, and the unbounded Map this replaced never gave any of it
   * back.
   */
  cache: ByteLru<Float64Array>;
}

export interface IndicatorSpec {
  /** How many numeric arguments it takes. 0 means it is written bare, e.g. `close`. */
  arity: number;
  doc: string;
  build: (ctx: IndicatorContext, args: number[]) => ArrayLike<number>;
}

const EPS = 1e-12;
const safe = (x: number): number => (Math.abs(x) > EPS ? x : EPS);

const closes = (ctx: IndicatorContext) => ctx.bars.map((b) => b.c);

/** Elementwise helper that keeps NaN propagating rather than silently becoming a number. */
function map1(n: number, f: (i: number) => number): Float64Array {
  const out = new Float64Array(n);
  for (let i = 0; i < n; i++) out[i] = f(i);
  return out;
}

function shift(x: ArrayLike<number>, k: number): Float64Array {
  const out = new Float64Array(x.length).fill(NaN);
  for (let i = k; i < x.length; i++) out[i] = x[i - k];
  return out;
}

/** Wilder smoothing, which is what RSI, ATR and ADX are defined on. */
function rma(x: ArrayLike<number>, n: number): Float64Array {
  const out = new Float64Array(x.length).fill(NaN);
  if (n <= 0 || x.length < n) return out;
  let sum = 0;
  for (let i = 0; i < n; i++) sum += x[i];
  let prev = sum / n;
  out[n - 1] = prev;
  for (let i = n; i < x.length; i++) {
    prev = (prev * (n - 1) + x[i]) / n;
    out[i] = prev;
  }
  return out;
}

function rollExtreme(x: ArrayLike<number>, n: number, max: boolean): Float64Array {
  const out = new Float64Array(x.length).fill(NaN);
  for (let i = n - 1; i < x.length; i++) {
    let best = max ? -Infinity : Infinity;
    for (let j = i - n + 1; j <= i; j++) best = max ? Math.max(best, x[j]) : Math.min(best, x[j]);
    out[i] = best;
  }
  return out;
}

function directional(ctx: IndicatorContext, n: number): { adx: Float64Array; pdi: Float64Array; ndi: Float64Array } {
  const b = ctx.bars;
  const tr = rma(trueRange(b), n);
  const pdm = new Float64Array(b.length);
  const ndm = new Float64Array(b.length);
  for (let i = 1; i < b.length; i++) {
    const up = b[i].h - b[i - 1].h;
    const dn = b[i - 1].l - b[i].l;
    pdm[i] = up > dn && up > 0 ? up : 0;
    ndm[i] = dn > up && dn > 0 ? dn : 0;
  }
  const sp = rma(pdm, n);
  const sn = rma(ndm, n);
  const pdi = map1(b.length, (i) => (100 * sp[i]) / safe(tr[i]));
  const ndi = map1(b.length, (i) => (100 * sn[i]) / safe(tr[i]));
  const dx = map1(b.length, (i) => (100 * Math.abs(pdi[i] - ndi[i])) / safe(pdi[i] + ndi[i]));
  return { adx: rma(dx, n), pdi, ndi };
}

/** ATR(14) is the scale-free denominator for every "distance" indicator below. */
const atr14 = (ctx: IndicatorContext): Float64Array => get(ctx, "atr", [14]);

export const REGISTRY: Record<string, IndicatorSpec> = {
  // ---- price and bar shape, no arguments -------------------------------------------------
  close: { arity: 0, doc: "close", build: (c) => c.bars.map((b) => b.c) },
  open: { arity: 0, doc: "open", build: (c) => c.bars.map((b) => b.o) },
  high: { arity: 0, doc: "high", build: (c) => c.bars.map((b) => b.h) },
  low: { arity: 0, doc: "low", build: (c) => c.bars.map((b) => b.l) },
  volume: { arity: 0, doc: "volume", build: (c) => c.bars.map((b) => b.v) },
  range: { arity: 0, doc: "high minus low", build: (c) => c.bars.map((b) => b.h - b.l) },
  body: {
    arity: 0,
    doc: "body as a percent of the bar's range",
    build: (c) => c.bars.map((b) => (100 * Math.abs(b.c - b.o)) / safe(b.h - b.l)),
  },
  pos: {
    arity: 0,
    doc: "close position within the bar's range, 0-100",
    build: (c) => c.bars.map((b) => (100 * (b.c - b.l)) / safe(b.h - b.l)),
  },
  green: { arity: 0, doc: "1 when the bar closed up", build: (c) => c.bars.map((b) => (b.c > b.o ? 1 : 0)) },
  mod: { arity: 0, doc: "minutes since exchange-local midnight", build: (c) => Array.from(c.minuteOfDay) },
  vwap: { arity: 0, doc: "session VWAP", build: (c) => sessionVwap(c.bars, c.sessionId) },
  vwapd: {
    arity: 0,
    doc: "distance from session VWAP in ATR(14) units",
    build: (c) => {
      const v = sessionVwap(c.bars, c.sessionId);
      const a = atr14(c);
      return map1(c.bars.length, (i) => (c.bars[i].c - v[i]) / safe(a[i]));
    },
  },

  // ---- one period argument ---------------------------------------------------------------
  ema: { arity: 1, doc: "exponential moving average of close", build: (c, [n]) => ema(closes(c), n) },
  sma: { arity: 1, doc: "simple moving average of close", build: (c, [n]) => sma(closes(c), n) },
  atr: { arity: 1, doc: "average true range (Wilder)", build: (c, [n]) => wilderAtr(c.bars, n) },
  natr: {
    arity: 1,
    doc: "ATR as a percent of close",
    build: (c, [n]) => {
      const a = wilderAtr(c.bars, n);
      return map1(c.bars.length, (i) => (100 * a[i]) / safe(c.bars[i].c));
    },
  },
  rsi: { arity: 1, doc: "relative strength index", build: (c, [n]) => rsi(closes(c), n) },
  std: { arity: 1, doc: "rolling standard deviation of close", build: (c, [n]) => rollingStd(closes(c), n) },
  rank: { arity: 1, doc: "percentile rank of close in the last n closes, 0-100", build: (c, [n]) => percentRank(closes(c), n) },
  hh: { arity: 1, doc: "highest high of the n bars BEFORE this one", build: (c, [n]) => priorExtreme(c.bars, n, "high") },
  ll: { arity: 1, doc: "lowest low of the n bars BEFORE this one", build: (c, [n]) => priorExtreme(c.bars, n, "low") },
  stoch: {
    arity: 1,
    doc: "stochastic %K",
    build: (c, [n]) => {
      const hh = rollExtreme(c.bars.map((b) => b.h), n, true);
      const ll = rollExtreme(c.bars.map((b) => b.l), n, false);
      return map1(c.bars.length, (i) => (100 * (c.bars[i].c - ll[i])) / safe(hh[i] - ll[i]));
    },
  },
  willr: {
    arity: 1,
    doc: "Williams %R",
    build: (c, [n]) => {
      const hh = rollExtreme(c.bars.map((b) => b.h), n, true);
      const ll = rollExtreme(c.bars.map((b) => b.l), n, false);
      return map1(c.bars.length, (i) => (-100 * (hh[i] - c.bars[i].c)) / safe(hh[i] - ll[i]));
    },
  },
  cci: {
    arity: 1,
    doc: "commodity channel index, on hlc3",
    build: (c, [n]) => {
      const tp = c.bars.map((b) => (b.h + b.l + b.c) / 3);
      const m = sma(tp, n);
      return map1(c.bars.length, (i) => {
        if (i < n - 1 || !Number.isFinite(m[i])) return NaN;
        let md = 0;
        for (let j = i - n + 1; j <= i; j++) md += Math.abs(tp[j] - m[i]);
        return (tp[i] - m[i]) / safe(0.015 * (md / n));
      });
    },
  },
  roc: {
    arity: 1,
    doc: "percent rate of change over n bars",
    build: (c, [n]) => map1(c.bars.length, (i) => (i < n ? NaN : (100 * (c.bars[i].c - c.bars[i - n].c)) / safe(c.bars[i - n].c))),
  },
  mom: {
    arity: 1,
    doc: "close minus close n bars ago, in points",
    build: (c, [n]) => map1(c.bars.length, (i) => (i < n ? NaN : c.bars[i].c - c.bars[i - n].c)),
  },
  slope: {
    arity: 1,
    doc: "linear-regression slope of close over n bars, in ATR(14) units",
    build: (c, [n]) => {
      const a = atr14(c);
      let den = 0;
      const xs: number[] = [];
      for (let j = 0; j < n; j++) xs.push(j - (n - 1) / 2);
      for (const x of xs) den += x * x;
      return map1(c.bars.length, (i) => {
        if (i < n - 1) return NaN;
        let mean = 0;
        for (let j = 0; j < n; j++) mean += c.bars[i - n + 1 + j].c;
        mean /= n;
        let num = 0;
        for (let j = 0; j < n; j++) num += xs[j] * (c.bars[i - n + 1 + j].c - mean);
        return num / den / safe(a[i]);
      });
    },
  },
  zscore: {
    arity: 1,
    doc: "close in rolling standard deviations from its own mean",
    build: (c, [n]) => {
      const m = sma(closes(c), n);
      const s = rollingStd(closes(c), n);
      return map1(c.bars.length, (i) => (c.bars[i].c - m[i]) / safe(s[i]));
    },
  },
  bbw: {
    arity: 1,
    doc: "Bollinger band width, percent of the middle band",
    build: (c, [n]) => {
      const m = sma(closes(c), n);
      const s = rollingStd(closes(c), n);
      return map1(c.bars.length, (i) => (400 * s[i]) / safe(m[i]));
    },
  },
  rvol: {
    arity: 1,
    doc: "volume over its own n-bar mean",
    build: (c, [n]) => {
      const m = sma(c.bars.map((b) => b.v), n);
      return map1(c.bars.length, (i) => c.bars[i].v / safe(m[i]));
    },
  },
  stretch: {
    arity: 1,
    doc: "EMASTRETCH: percent distance of close from EMA(n)",
    build: (c, [n]) => {
      const e = ema(closes(c), n);
      return map1(c.bars.length, (i) => 100 * (c.bars[i].c / safe(e[i]) - 1));
    },
  },
  emadist: {
    arity: 1,
    doc: "distance of close from EMA(n) in ATR(14) units",
    build: (c, [n]) => {
      const e = ema(closes(c), n);
      const a = atr14(c);
      return map1(c.bars.length, (i) => (c.bars[i].c - e[i]) / safe(a[i]));
    },
  },
  emaslope: {
    arity: 1,
    doc: "one-bar change in EMA(n), in ATR(14) units",
    build: (c, [n]) => {
      const e = ema(closes(c), n);
      const a = atr14(c);
      return map1(c.bars.length, (i) => (i === 0 ? NaN : (e[i] - e[i - 1]) / safe(a[i])));
    },
  },
  adx: { arity: 1, doc: "average directional index", build: (c, [n]) => directional(c, n).adx },
  pdi: { arity: 1, doc: "+DI", build: (c, [n]) => directional(c, n).pdi },
  ndi: { arity: 1, doc: "-DI", build: (c, [n]) => directional(c, n).ndi },
  di: {
    arity: 1,
    doc: "+DI minus -DI",
    build: (c, [n]) => {
      const d = directional(c, n);
      return map1(c.bars.length, (i) => d.pdi[i] - d.ndi[i]);
    },
  },
  hull: {
    arity: 1,
    doc: "Hull moving average",
    build: (c, [n]) => {
      const half = Math.max(1, Math.round(n / 2));
      const sq = Math.max(1, Math.round(Math.sqrt(n)));
      const a = ema(closes(c), half);
      const b = ema(closes(c), n);
      const raw: number[] = [];
      for (let i = 0; i < c.bars.length; i++) raw.push(2 * a[i] - b[i]);
      return ema(raw, sq);
    },
  },

  // ---- several arguments ------------------------------------------------------------------
  macd: {
    arity: 3,
    doc: "MACD histogram in ATR(14) units: macd(fast, slow, signal)",
    build: (c, [f, s, g]) => {
      const cl = closes(c);
      const fast = ema(cl, f);
      const slow = ema(cl, s);
      const line: number[] = [];
      for (let i = 0; i < cl.length; i++) line.push(fast[i] - slow[i]);
      const sig = ema(line, g);
      const a = atr14(c);
      return map1(cl.length, (i) => (line[i] - sig[i]) / safe(a[i]));
    },
  },
  cross: {
    arity: 2,
    doc: "+1 the bar EMA(a) crosses above EMA(b), -1 below, else 0: cross(a, b)",
    build: (c, [a, b]) => {
      const ea = ema(closes(c), a);
      const eb = ema(closes(c), b);
      return map1(c.bars.length, (i) => {
        if (i === 0 || !Number.isFinite(ea[i]) || !Number.isFinite(eb[i]) || !Number.isFinite(ea[i - 1]) || !Number.isFinite(eb[i - 1])) return 0;
        const now = Math.sign(ea[i] - eb[i]);
        const was = Math.sign(ea[i - 1] - eb[i - 1]);
        return now !== was ? now : 0;
      });
    },
  },
  since: {
    arity: 2,
    doc: "bars since EMA(a) last crossed above EMA(b): since(a, b)",
    build: (c, [a, b]) => {
      const x = get(c, "cross", [a, b]);
      let last = -1;
      return map1(c.bars.length, (i) => {
        if (x[i] > 0) last = i;
        return last < 0 ? Number.POSITIVE_INFINITY : i - last;
      });
    },
  },
};

/** 96 MB of indicator arrays — enough for a wide period sweep, small enough to live in a tab. */
export const DEFAULT_INDICATOR_BUDGET = 96 * 1024 * 1024;

/** Memoised lookup. Throws with the catalogue rather than returning a silent NaN array. */
export function get(ctx: IndicatorContext, name: string, args: number[]): Float64Array {
  const k = `${ctx.key}|${name}|${args.join(",")}`;
  const hit = ctx.cache.get(k);
  if (hit) return hit;
  const spec = REGISTRY[name];
  if (!spec) throw new Error(`unknown indicator "${name}"`);
  if (spec.arity !== args.length) {
    throw new Error(`${name} takes ${spec.arity} argument${spec.arity === 1 ? "" : "s"}, got ${args.length}`);
  }
  const raw = spec.build(ctx, args);
  const out = raw instanceof Float64Array ? raw : Float64Array.from(raw as ArrayLike<number>);
  return ctx.cache.set(k, out, out.byteLength);
}

export function makeContext(
  bars: Bar[],
  sessionId: ArrayLike<number>,
  minuteOfDay: ArrayLike<number>,
  key: string,
  budgetBytes = DEFAULT_INDICATOR_BUDGET,
): IndicatorContext {
  return { bars, sessionId, minuteOfDay, key, cache: new ByteLru<Float64Array>(budgetBytes) };
}

export interface CatalogueEntry {
  name: string;
  arity: number;
  doc: string;
}

export function catalogue(): CatalogueEntry[] {
  return Object.entries(REGISTRY)
    .map(([name, s]) => ({ name, arity: s.arity, doc: s.doc }))
    .sort((a, b) => a.arity - b.arity || a.name.localeCompare(b.name));
}
