import { clockFor, type ExchangeTz } from "./clock";
import { atr } from "./series";
import { correctMultiple } from "./multipletest";
import { mean, neweyWestT, normalCdf, pValueTwoSided, std } from "./stats";
import type { Bar, Instrument } from "./types";

// Alpha discovery: what predictability is actually IN the series, before any trading rule exists.
//
// This stage exists because a strategy backtest confounds two very different questions — "is there
// exploitable structure in this market?" and "does this particular rule capture it?". Measuring the
// raw structure first tells you whether there is anything to capture at all, and in the only unit
// that decides a scalping question: TICKS OF FORECASTABLE MOVE versus TICKS OF COST. If the largest
// conditional edge in the data is 1.2 ticks and a round turn costs 3.8, no rule, no parameter set
// and no machine learning model can fix that. It is arithmetic, not skill.
//
// Everything here is computed WITHIN sessions: a return spanning the overnight break is not a
// 5-minute return, and pooling the two manufactures both autocorrelation and volatility.

/** Contiguous within-session runs of bar indices, split at session changes and at time gaps. */
export function segments(bars: Bar[], tz: ExchangeTz): number[][] {
  if (!bars.length) return [];
  const clock = clockFor(bars, tz);
  const diffs = new Map<number, number>();
  for (let i = 1; i < bars.length; i++) {
    const d = bars[i].t - bars[i - 1].t;
    diffs.set(d, (diffs.get(d) ?? 0) + 1);
  }
  let modal = 300_000;
  let best = 0;
  for (const [d, n] of diffs) if (n > best) { best = n; modal = d; }

  const out: number[][] = [];
  let cur: number[] = [0];
  for (let i = 1; i < bars.length; i++) {
    const contiguous = bars[i].t - bars[i - 1].t <= modal * 1.5 && clock.dayIndex[i] === clock.dayIndex[i - 1];
    if (contiguous) cur.push(i);
    else {
      if (cur.length > 1) out.push(cur);
      cur = [i];
    }
  }
  if (cur.length > 1) out.push(cur);
  return out;
}

export interface AutocorrRow {
  lag: number;
  rho: number;
  /** Bartlett standard error under the null of no autocorrelation. */
  se: number;
  t: number;
  p: number;
}

/**
 * Autocorrelation of within-session bar returns.
 *
 * Positive rho at short lags is momentum (a breakout rule has something to work with); negative rho
 * is short-horizon reversal (a fade rule does). Both are usually far too small to pay for a spread,
 * which is precisely the point of measuring rather than assuming.
 */
export function returnAutocorrelation(bars: Bar[], tz: ExchangeTz, maxLag = 12): AutocorrRow[] {
  const segs = segments(bars, tz);
  const rets: number[][] = segs.map((seg) => seg.slice(1).map((i, k) => Math.log(bars[i].c / bars[seg[k]].c)));
  const flat = rets.flat();
  const m = mean(flat);
  const denom = flat.reduce((s, r) => s + (r - m) ** 2, 0);
  const n = flat.length;

  const rows: AutocorrRow[] = [];
  let cumSq = 0;
  for (let lag = 1; lag <= maxLag; lag++) {
    let acc = 0;
    let pairs = 0;
    for (const r of rets) {
      for (let i = lag; i < r.length; i++) {
        acc += (r[i] - m) * (r[i - lag] - m);
        pairs++;
      }
    }
    const rho = denom > 0 ? acc / denom : 0;
    // Bartlett: Var(rho_k) ≈ (1 + 2*sum_{j<k} rho_j^2) / n.
    const se = Math.sqrt((1 + 2 * cumSq) / Math.max(n, 1));
    cumSq += rho * rho;
    const t = se > 0 ? rho / se : 0;
    rows.push({ lag, rho, se, t, p: pValueTwoSided(t), });
    void pairs;
  }
  return rows;
}

export interface VarianceRatio {
  q: number;
  vr: number;
  /** Lo-MacKinlay heteroskedasticity-robust z statistic against VR = 1. */
  z: number;
  p: number;
  reading: "momentum" | "random walk" | "mean reversion";
}

/**
 * Lo-MacKinlay variance ratio test, pooled over within-session segments.
 *
 * VR(q) > 1 means q-bar moves are larger than q times a 1-bar move — the series trends.
 * VR(q) < 1 means it reverts. VR = 1 is a random walk, i.e. nothing for a rule to exploit.
 * The z statistic is the heteroskedasticity-robust one, because intraday variance is anything but
 * constant and the homoskedastic version would reject the random walk on volatility clustering alone.
 */
export function varianceRatios(bars: Bar[], tz: ExchangeTz, qs: number[] = [2, 3, 5, 10, 20]): VarianceRatio[] {
  const segs = segments(bars, tz);
  const retSegs = segs.map((seg) => seg.slice(1).map((i, k) => Math.log(bars[i].c / bars[seg[k]].c)));
  const flat = retSegs.flat();
  const n = flat.length;
  const mu = mean(flat);
  const dev = flat.map((r) => r - mu);
  const sumSq = dev.reduce((s, d) => s + d * d, 0);
  const var1 = sumSq / Math.max(n - 1, 1);

  return qs.map((q) => {
    // q-period overlapping sums, never spanning a session break.
    let acc = 0;
    let m = 0;
    for (const r of retSegs) {
      for (let i = q; i <= r.length; i++) {
        let s = 0;
        for (let j = i - q; j < i; j++) s += r[j];
        acc += (s - q * mu) ** 2;
        m++;
      }
    }
    if (!m || var1 <= 0) return { q, vr: 1, z: 0, p: 1, reading: "random walk" as const };
    const varQ = acc / (m * q);
    const vr = varQ / var1;

    // Heteroskedasticity-robust variance of VR (Lo & MacKinlay 1988, statistic M2).
    let theta = 0;
    for (let j = 1; j < q; j++) {
      let num = 0;
      let cnt = 0;
      let off = 0;
      for (const r of retSegs) {
        for (let i = j; i < r.length; i++) {
          num += (r[i] - mu) ** 2 * (r[i - j] - mu) ** 2;
          cnt++;
        }
        off += r.length;
      }
      void cnt;
      void off;
      const delta = sumSq > 0 ? num / (sumSq / n) ** 2 / n : 0;
      theta += ((2 * (q - j)) / q) ** 2 * delta;
    }
    const z = theta > 0 ? ((vr - 1) * Math.sqrt(n)) / Math.sqrt(theta) : 0;
    const p = 2 * (1 - normalCdf(Math.abs(z)));
    return { q, vr, z, p, reading: p > 0.05 ? ("random walk" as const) : vr > 1 ? ("momentum" as const) : ("mean reversion" as const) };
  });
}

export interface TimeBucket {
  label: string;
  minuteOfDay: number;
  bars: number;
  /** Mean bar return over the bucket, in ticks. */
  meanTicks: number;
  tStat: number;
  /** Mean absolute bar move in ticks — the volatility profile. */
  volTicks: number;
  meanVolume: number;
}

/**
 * Time-of-day profile: mean signed move and mean absolute move per intraday bucket, in ticks.
 *
 * The absolute-move column is where a scalper's opportunity actually lives (you cannot scalp a
 * quiet tape at any hit rate), and the signed column with its t-stat says whether there is a
 * directional drift worth a seasonality rule — usually there is not, once the sample is honest.
 */
export function timeOfDayProfile(bars: Bar[], inst: Instrument, bucketMinutes = 30): TimeBucket[] {
  const clock = clockFor(bars, inst.tz);
  const groups = new Map<number, { rets: number[]; abs: number[]; vol: number[] }>();
  for (let i = 1; i < bars.length; i++) {
    if (clock.dayIndex[i] !== clock.dayIndex[i - 1]) continue;
    const key = Math.floor(clock.minuteOfDay[i] / bucketMinutes) * bucketMinutes;
    let g = groups.get(key);
    if (!g) groups.set(key, (g = { rets: [], abs: [], vol: [] }));
    const move = (bars[i].c - bars[i - 1].c) / inst.tickSize;
    g.rets.push(move);
    g.abs.push(Math.abs(move));
    g.vol.push(bars[i].v);
  }
  return [...groups.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([key, g]) => {
      const nw = neweyWestT(g.rets);
      return {
        label: `${String(Math.floor(key / 60)).padStart(2, "0")}:${String(key % 60).padStart(2, "0")}`,
        minuteOfDay: key,
        bars: g.rets.length,
        meanTicks: mean(g.rets),
        tStat: nw.t,
        volTicks: mean(g.abs),
        meanVolume: mean(g.vol),
      };
    });
}

export interface EventResponse {
  horizon: number;
  events: number;
  /** Mean forward move in ticks, signed in the direction the condition predicts. */
  meanTicks: number;
  medianTicks: number;
  tStat: number;
  p: number;
  hitRate: number;
  /**
   * The edge with market DRIFT removed: mean(side x forward) - mean(side) x mean(forward).
   *
   * This column is the one that matters. A condition that fires long slightly more often than short
   * will show a large positive raw mean on any index that trended over the sample — NQ roughly
   * doubled across 2023-2025 — and that is exposure, not prediction. Subtracting the unconditional
   * forward move times the condition's directional bias leaves only the part attributable to the
   * signal itself.
   */
  driftAdjustedTicks: number;
  driftAdjustedT: number;
  driftAdjustedP: number;
  /** Share of events that were long — reveals whether a "signal" is really a drift proxy. */
  longShare: number;
  /** Drift-adjusted edge minus the round-turn cost: what is actually left to capture. */
  netOfCostTicks: number;
}

/**
 * Event study: given a per-bar condition returning +1 / -1 / 0, measure the average forward move in
 * the predicted direction over several horizons, in ticks, against the cost line.
 *
 * This is the cleanest possible test of a signal, because it involves no stop, no target and no
 * position management — nothing that can accidentally manufacture or hide an edge. If a condition
 * has no forward information here, no exit rule can rescue it.
 */
export function eventStudy(
  bars: Bar[],
  inst: Instrument,
  condition: (i: number) => -1 | 0 | 1,
  horizons: number[] = [1, 3, 6, 12, 24],
  costTicks = 0,
): EventResponse[] {
  const clock = clockFor(bars, inst.tz);
  return horizons.map((h) => {
    // Unconditional forward move over the same horizon and the same same-session constraint —
    // the benchmark a signed condition has to beat to be a signal rather than a drift proxy.
    let driftSum = 0;
    let driftN = 0;
    for (let i = 0; i + h < bars.length; i++) {
      if (clock.dayIndex[i + h] !== clock.dayIndex[i]) continue;
      driftSum += (bars[i + h].c - bars[i].c) / inst.tickSize;
      driftN++;
    }
    const muFwd = driftN ? driftSum / driftN : 0;

    const moves: number[] = [];
    const excess: number[] = [];
    const sides: number[] = [];
    for (let i = 0; i + h < bars.length; i++) {
      const side = condition(i);
      if (!side) continue;
      if (clock.dayIndex[i + h] !== clock.dayIndex[i]) continue; // never measure across a session break
      const fwd = (bars[i + h].c - bars[i].c) / inst.tickSize;
      moves.push(side * fwd);
      excess.push(side * fwd - side * muFwd);
      sides.push(side);
    }
    if (!moves.length)
      return {
        horizon: h, events: 0, meanTicks: 0, medianTicks: 0, tStat: 0, p: 1, hitRate: 0,
        driftAdjustedTicks: 0, driftAdjustedT: 0, driftAdjustedP: 1, longShare: 0, netOfCostTicks: -costTicks,
      };
    // Overlapping h-bar forward windows induce an MA(h-1) structure in the event series, so the
    // HAC lag must be at least h. Using the default rule here would overstate every t-statistic.
    const hacLag = Math.max(h, Math.floor(4 * (moves.length / 100) ** (2 / 9)));
    const nw = neweyWestT(moves, hacLag);
    const nwEx = neweyWestT(excess, hacLag);
    const sorted = [...moves].sort((a, b) => a - b);
    return {
      horizon: h,
      events: moves.length,
      meanTicks: mean(moves),
      medianTicks: sorted[Math.floor(sorted.length / 2)],
      tStat: nw.t,
      p: pValueTwoSided(nw.t),
      hitRate: moves.filter((m) => m > 0).length / moves.length,
      driftAdjustedTicks: mean(excess),
      driftAdjustedT: nwEx.t,
      driftAdjustedP: pValueTwoSided(nwEx.t),
      longShare: sides.filter((x) => x > 0).length / sides.length,
      netOfCostTicks: mean(excess) - costTicks,
    };
  });
}

/** Condition builders for the standard microstructure hypotheses a scalping study should test. */
export function conditions(bars: Bar[], inst: Instrument) {
  const a = atr(bars, 14);
  const clock = clockFor(bars, inst.tz);
  const rets = bars.map((b, i) => (i ? (b.c - bars[i - 1].c) / inst.tickSize : 0));
  const volMean = bars.map((_, i) => (i >= 20 ? mean(bars.slice(i - 20, i).map((b) => b.v)) : NaN));
  const sameDay = (i: number, k: number) => i - k >= 0 && clock.dayIndex[i - k] === clock.dayIndex[i];

  return {
    /** Continuation: does a large up-bar predict another up-bar? */
    momentum1Bar: (i: number): -1 | 0 | 1 => {
      if (!sameDay(i, 1) || !Number.isFinite(a[i]) || a[i] <= 0) return 0;
      const move = bars[i].c - bars[i].o;
      if (Math.abs(move) < 0.5 * a[i]) return 0;
      return move > 0 ? 1 : -1;
    },
    /** Reversal: does a large move revert on the next bars? */
    reversal1Bar: (i: number): -1 | 0 | 1 => {
      if (!sameDay(i, 1) || !Number.isFinite(a[i]) || a[i] <= 0) return 0;
      const move = bars[i].c - bars[i].o;
      if (Math.abs(move) < a[i]) return 0;
      return move > 0 ? -1 : 1;
    },
    /** Volume-confirmed continuation — the classic "real move vs noise move" filter. */
    volumeSurgeMomentum: (i: number): -1 | 0 | 1 => {
      if (!sameDay(i, 1) || !Number.isFinite(volMean[i]) || !Number.isFinite(a[i]) || a[i] <= 0) return 0;
      if (bars[i].v < 2 * volMean[i]) return 0;
      const move = bars[i].c - bars[i].o;
      if (Math.abs(move) < 0.5 * a[i]) return 0;
      return move > 0 ? 1 : -1;
    },
    /** Three consecutive same-direction bars — the runs test in tradeable form. */
    threeBarRun: (i: number): -1 | 0 | 1 => {
      if (!sameDay(i, 3)) return 0;
      const up = rets[i] > 0 && rets[i - 1] > 0 && rets[i - 2] > 0;
      const dn = rets[i] < 0 && rets[i - 1] < 0 && rets[i - 2] < 0;
      return up ? 1 : dn ? -1 : 0;
    },
    /** Range compression then expansion — the volatility-breakout premise, isolated. */
    compressionBreak: (i: number): -1 | 0 | 1 => {
      if (!sameDay(i, 6) || !Number.isFinite(a[i]) || a[i] <= 0) return 0;
      let hi = -Infinity;
      let lo = Infinity;
      for (let j = i - 6; j < i; j++) {
        hi = Math.max(hi, bars[j].h);
        lo = Math.min(lo, bars[j].l);
      }
      if (hi - lo > 1.5 * a[i]) return 0;
      if (bars[i].c > hi) return 1;
      if (bars[i].c < lo) return -1;
      return 0;
    },
  };
}

export interface PredictabilityBudget {
  /** The largest statistically credible conditional edge found, in ticks. */
  bestEdgeTicks: number;
  bestLabel: string;
  costTicks: number;
  /** bestEdgeTicks / costTicks. Below 1 there is no rule that can be profitable, at any parameters. */
  ratio: number;
  verdict: string;
}

/**
 * The decisive scalping arithmetic: the biggest DRIFT-ADJUSTED conditional forward move that
 * survives a t-test, against the round-turn cost. This is the number to look at before any strategy
 * is written — and it uses the drift-adjusted column deliberately, because on a market that
 * trended as hard as NQ did over this sample, the raw column mostly measures the trend.
 */
export function predictabilityBudget(
  results: { label: string; responses: EventResponse[] }[],
  costTicks: number,
  maxQ = 0.1,
): PredictabilityBudget {
  // Every cell in the event-study grid is a hypothesis test. Taking the best one at face value is
  // the same mistake as taking the best parameter set at face value, so the survivor has to clear
  // false-discovery-rate control across the whole grid it was picked from.
  const cells = results.flatMap((r) => r.responses.map((resp) => ({ label: `${r.label} @ ${resp.horizon} bars`, resp })));
  const corrected = correctMultiple(cells.map((c) => ({ label: c.label, p: c.resp.driftAdjustedP })), maxQ);
  const qByLabel = new Map(corrected.map((c) => [c.label, c.qBH]));

  let bestEdge = -Infinity;
  let bestLabel = "none";
  for (const c of cells) {
    if ((qByLabel.get(c.label) ?? 1) > maxQ || c.resp.events < 100) continue;
    if (c.resp.driftAdjustedTicks > bestEdge) {
      bestEdge = c.resp.driftAdjustedTicks;
      bestLabel = c.label;
    }
  }
  if (!Number.isFinite(bestEdge)) {
    return {
      bestEdgeTicks: 0, bestLabel: "none", costTicks, ratio: 0,
      verdict:
        `no tested condition shows a drift-adjusted edge that survives false-discovery control (q <= ${maxQ}) — ` +
        `on this sample and session none of these hypotheses is distinguishable from noise, which does not prove the ` +
        `market is unpredictable, only that these signals do not predict it`,
    };
  }
  const ratio = costTicks > 0 ? bestEdge / costTicks : Infinity;
  return {
    bestEdgeTicks: bestEdge,
    bestLabel,
    costTicks,
    ratio,
    verdict:
      ratio >= 2
        ? "raw edge comfortably exceeds costs — a rule has room to work"
        : ratio >= 1
          ? "raw edge barely exceeds costs — only near-perfect execution could monetise it"
          : "raw edge is smaller than the cost of trading it — no rule at any parameters can be profitable here",
  };
}

export { std };
