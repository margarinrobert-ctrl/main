import { clockFor } from "./clock";
import { mean, neweyWestT, pValueTwoSided, std } from "./stats";
import type { Bar, Instrument, Trade } from "./types";

// Day-level features of the Initial Balance, and the machinery for asking which of them predict
// whether the IB trade works. This is the "anomaly" layer: the base geometry is fixed, and the
// question is whether some sessions are systematically better to trade than others.
//
// Every feature here is computable at the moment the IB window closes — BEFORE the break, the
// entry, or the outcome. A feature that needs the rest of the day is not a filter, it is hindsight.

export interface IbDay {
  day: number;
  /** Bar index of the first bar after the IB window closed. */
  readyIndex: number;
  high: number;
  low: number;
  range: number;
  /** Where the IB window's final close sat inside the range, 0 = at the low, 1 = at the high. */
  closePosition: number;
  /** IB range as a percentile of the trailing 60 sessions (prior days only). */
  rangePercentile: number;
  /** Open of the IB window minus the previous session's last close, in IB-range units. */
  gapInRanges: number;
  /** IB range divided by the previous session's IB range. */
  rangeRatio: number;
  /** 0 = Sunday. */
  weekday: number;
  /** Did the IB window take out the previous session's high / low? */
  tookPriorHigh: boolean;
  tookPriorLow: boolean;
}

/** Build the per-session IB feature table. Uses only data available when the window closes. */
export function ibDays(bars: Bar[], inst: Instrument, ibMinutes = 60): IbDay[] {
  const clock = clockFor(bars, inst.tz);
  const start = inst.session[0];
  const end = start + ibMinutes;

  interface Acc {
    day: number;
    hi: number;
    lo: number;
    open: number;
    lastClose: number;
    readyIndex: number;
    weekday: number;
    sessionHi: number;
    sessionLo: number;
    prevSessionClose: number;
  }
  const accs: Acc[] = [];
  let cur: Acc | null = null;
  let lastSessionClose = NaN;
  let sessionHi = -Infinity;
  let sessionLo = Infinity;

  for (let i = 0; i < bars.length; i++) {
    const day = clock.dayIndex[i];
    if (!cur || cur.day !== day) {
      if (cur) {
        cur.sessionHi = sessionHi;
        cur.sessionLo = sessionLo;
        lastSessionClose = bars[i - 1].c;
      }
      cur = {
        day, hi: -Infinity, lo: Infinity, open: bars[i].o, lastClose: NaN, readyIndex: -1,
        weekday: clock.weekday[i], sessionHi: NaN, sessionLo: NaN, prevSessionClose: lastSessionClose,
      };
      accs.push(cur);
      sessionHi = -Infinity;
      sessionLo = Infinity;
    }
    sessionHi = Math.max(sessionHi, bars[i].h);
    sessionLo = Math.min(sessionLo, bars[i].l);
    const m = clock.minuteOfDay[i];
    if (m >= start && m < end) {
      cur.hi = Math.max(cur.hi, bars[i].h);
      cur.lo = Math.min(cur.lo, bars[i].l);
      cur.lastClose = bars[i].c;
    } else if (m >= end && cur.readyIndex < 0 && cur.hi > -Infinity) {
      cur.readyIndex = i;
    }
  }
  if (cur) {
    cur.sessionHi = sessionHi;
    cur.sessionLo = sessionLo;
  }

  const out: IbDay[] = [];
  const history: number[] = [];
  for (let k = 0; k < accs.length; k++) {
    const a = accs[k];
    if (a.readyIndex < 0 || a.hi <= -Infinity || a.hi <= a.lo) continue;
    const range = a.hi - a.lo;
    const prev = k > 0 ? accs[k - 1] : null;
    const prevRange = prev && prev.hi > -Infinity && prev.hi > prev.lo ? prev.hi - prev.lo : NaN;

    let pctl = 50;
    if (history.length >= 20) pctl = (history.filter((x) => x < range).length / history.length) * 100;

    out.push({
      day: a.day,
      readyIndex: a.readyIndex,
      high: a.hi,
      low: a.lo,
      range,
      closePosition: Number.isFinite(a.lastClose) ? (a.lastClose - a.lo) / range : 0.5,
      rangePercentile: pctl,
      gapInRanges: Number.isFinite(a.prevSessionClose) ? (a.open - a.prevSessionClose) / range : 0,
      rangeRatio: Number.isFinite(prevRange) ? range / prevRange : 1,
      weekday: a.weekday,
      tookPriorHigh: prev ? a.hi > prev.sessionHi : false,
      tookPriorLow: prev ? a.lo < prev.sessionLo : false,
    });
    history.push(range);
    if (history.length > 60) history.shift();
  }
  return out;
}

export interface Bucket {
  feature: string;
  bucket: string;
  trades: number;
  /** Mean R multiple of trades in this bucket. */
  meanR: number;
  winRate: number;
  /** Mean R here minus mean R everywhere else — the conditional lift. */
  lift: number;
  /** t-statistic of the LIFT, i.e. of the difference between this bucket and the rest. */
  t: number;
  p: number;
  /** Benjamini-Hochberg q across every bucket of every feature tested. */
  q: number;
  totalPnl: number;
}

/**
 * Test which day features predict the IB trade's outcome.
 *
 * The statistic is deliberately the DIFFERENCE between a bucket and every other trade, not the
 * bucket's own mean. A bucket can look excellent purely because the strategy is profitable overall,
 * and "Tuesdays make money" is not a finding when every day makes money. Welch's t on the
 * difference of means is what separates a real conditional edge from a slice of a good strategy.
 */
export function conditionalEdges(trades: Trade[], days: IbDay[], bucketers: Record<string, (d: IbDay) => string | null>): Bucket[] {
  const byDay = new Map<number, IbDay>();
  for (const d of days) byDay.set(d.day, d);

  const tagged = trades
    .map((t) => ({ t, d: byDay.get(Math.floor(t.entryTime / 86_400_000)) }))
    .filter((x): x is { t: Trade; d: IbDay } => !!x.d);

  const rows: Bucket[] = [];
  for (const [feature, bucketOf] of Object.entries(bucketers)) {
    const groups = new Map<string, Trade[]>();
    for (const { t, d } of tagged) {
      const b = bucketOf(d);
      if (b === null) continue;
      const arr = groups.get(b);
      if (arr) arr.push(t);
      else groups.set(b, [t]);
    }
    for (const [bucket, inBucket] of groups) {
      if (inBucket.length < 20) continue;
      const inSet = new Set(inBucket);
      const rest = tagged.map((x) => x.t).filter((t) => !inSet.has(t));
      if (rest.length < 20) continue;
      const a = inBucket.map((t) => t.r);
      const b = rest.map((t) => t.r);
      const ma = mean(a);
      const mb = mean(b);
      // Welch's t: the two groups have different sizes and, usually, different variances.
      const se = Math.sqrt(std(a) ** 2 / a.length + std(b) ** 2 / b.length);
      const t = se > 0 ? (ma - mb) / se : 0;
      rows.push({
        feature,
        bucket,
        trades: a.length,
        meanR: ma,
        winRate: inBucket.filter((x) => x.pnl > 0).length / a.length,
        lift: ma - mb,
        t,
        p: pValueTwoSided(t),
        q: 1,
        totalPnl: inBucket.reduce((s, x) => s + x.pnl, 0),
      });
    }
  }

  // Benjamini-Hochberg across every bucket of every feature — this whole table is one search.
  const order = rows.map((r, i) => ({ p: r.p, i })).sort((x, y) => x.p - y.p);
  const m = order.length;
  let running = 1;
  for (let k = m - 1; k >= 0; k--) {
    running = Math.min(running, (order[k].p * m) / (k + 1));
    rows[order[k].i].q = Math.min(1, running);
  }
  return rows.sort((x, y) => y.lift - x.lift);
}

/** The standard bucketings for an IB study. */
export function ibBucketers(): Record<string, (d: IbDay) => string | null> {
  const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  return {
    "IB range percentile": (d) => (d.rangePercentile < 33 ? "narrow" : d.rangePercentile < 67 ? "medium" : "wide"),
    "first-hour close position": (d) =>
      d.closePosition < 0.33 ? "closed low third" : d.closePosition < 0.67 ? "closed middle" : "closed high third",
    "overnight gap": (d) => (Math.abs(d.gapInRanges) < 0.25 ? "flat open" : d.gapInRanges > 0 ? "gap up" : "gap down"),
    "range vs prior IB": (d) => (d.rangeRatio < 0.8 ? "contracting" : d.rangeRatio > 1.25 ? "expanding" : "similar"),
    weekday: (d) => WD[d.weekday] ?? null,
    "took prior session extreme": (d) =>
      d.tookPriorHigh && d.tookPriorLow ? "both" : d.tookPriorHigh ? "took prior high" : d.tookPriorLow ? "took prior low" : "inside prior range",
  };
}

/** Per-trade R stats with a HAC t-stat, for reporting a filtered subset. */
export function subsetStats(trades: Trade[]): { n: number; meanR: number; winRate: number; t: number; p: number; pnl: number } {
  if (!trades.length) return { n: 0, meanR: 0, winRate: 0, t: 0, p: 1, pnl: 0 };
  const r = trades.map((x) => x.r);
  const nw = neweyWestT(r);
  return {
    n: trades.length,
    meanR: mean(r),
    winRate: trades.filter((x) => x.pnl > 0).length / trades.length,
    t: nw.t,
    p: pValueTwoSided(nw.t),
    pnl: trades.reduce((s, x) => s + x.pnl, 0),
  };
}
