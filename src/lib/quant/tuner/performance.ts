/**
 * The statistics a backtest is actually judged on, computed in ONE streaming pass over the trades.
 *
 * The tuner's whole premise is that a configuration costs microseconds, so anything it reports has
 * to be O(trades) with O(1) memory or it stops being a tuner. That rules out the obvious
 * implementation — materialise a daily P&L array, then call the functions in `../stats` — for the
 * sweep. The way round it is that every statistic here is a function of a handful of RUNNING SUMS:
 *
 *     mean, variance, Sharpe        sum, sum of squares
 *     Sortino                       sum of squared negative days
 *     beta, correlation, alpha      sum of pnl x market
 *     residual (market-neutral)     the three above together
 *     drawdown, underwater          a running peak
 *     sub-period concentration      one accumulator per sub-period
 *
 * and the sessions the strategy did NOT trade contribute zero to every one of them. That is not a
 * convenience, it is the correctness requirement: `../stats` documents that dropping flat days is
 * the most common way an intraday Sharpe gets inflated two or three times, and a streaming sum
 * over trades includes them for free as long as the DENOMINATOR is the block's session count
 * rather than the number of sessions that traded.
 *
 * `finishBlock` is shared by the streaming path and by `perfFromDaily`, which takes an explicit
 * daily array; `performance.test.ts` asserts the two agree, so the fast path cannot drift from the
 * obvious one.
 *
 * WHY THE MARKET-NEUTRAL BLOCK IS NOT OPTIONAL
 * --------------------------------------------
 * `CLAUDE.md` records the finding this project paid for the hard way: the shipped 15-minute Turtle
 * scalp reads a holdout Sharpe of 0.222, and regressing its session P&L on the market's own move
 * across the same window shows **87% of the profit is beta**. Strip it and the Sharpe is 0.032.
 * A Sharpe computed on raw dollars cannot tell an edge from leverage, so `beta`, `residSharpe` and
 * `betaPnlShare` are computed next to every Sharpe here rather than offered as a separate report,
 * and the console ranks on the residual.
 */
import type { ExitReason } from "../types";

/** Sub-periods the concentration gate splits a block into. Five is the protocol's figure. */
export const CONCENTRATION_PARTS = 5;

/** Gate 9: no single sub-period may carry more than this share of the block's P&L. */
export const CONCENTRATION_LIMIT = 0.6;

/**
 * The fixed facts of one block — everything that depends on the bars and the window but not on the
 * strategy. Built once per (window, block) and reused by every configuration in the sweep.
 */
export interface BlockGeometry {
  label: "research" | "locked";
  /** First session ordinal in the block (inclusive). */
  from: number;
  /** One past the last session ordinal. */
  to: number;
  /** Sessions in the block, flat ones INCLUDED — the denominator of every daily statistic. */
  sessions: number;
  /** Bars in the block, for the exposure figure. */
  bars: number;
  /** Trading days per year, for annualisation. */
  daysPerYear: number;
  /**
   * P&L in USD of holding ONE long unit across the entry window, per session, indexed by
   * `ordinal - from`. This is the market factor every strategy statistic is neutralised against.
   */
  market: Float64Array;
  marketSum: number;
  marketSumSq: number;
}

/** The running sums. Public because `perfFromDaily` fills the same struct from an array. */
export interface BlockSums {
  n: number;
  net: number;
  /** Per-TRADE sum of squares, for the per-trade t-statistic. */
  tradeSumSq: number;
  wins: number;
  grossWin: number;
  grossLoss: number;
  byReason: [number, number, number, number];
  barsHeld: number;
  /** Sessions that produced at least one trade. */
  tradedSessions: number;
  /** Per-SESSION sums: squares, squared losing days, and the cross-product with the market. */
  daySumSq: number;
  dayDownSq: number;
  dayXMarket: number;
  /** Drawdown of the session-marked equity curve. */
  maxDailyDrawdown: number;
  /** Drawdown of the closed-trade equity curve — finer, and what a trade blotter shows. */
  maxTradeDrawdown: number;
  /** Longest run of sessions spent below a previous equity peak. */
  underwaterSessions: number;
  /** P&L per sub-period, for the concentration gate. */
  parts: Float64Array;
}

export function emptySums(parts = CONCENTRATION_PARTS): BlockSums {
  return {
    n: 0, net: 0, tradeSumSq: 0, wins: 0, grossWin: 0, grossLoss: 0,
    byReason: [0, 0, 0, 0], barsHeld: 0, tradedSessions: 0,
    daySumSq: 0, dayDownSq: 0, dayXMarket: 0,
    maxDailyDrawdown: 0, maxTradeDrawdown: 0, underwaterSessions: 0,
    parts: new Float64Array(parts),
  };
}

/**
 * Streaming accumulator for one block.
 *
 * Trades must arrive in bar order, which the no-overlap walk guarantees, so session ordinals are
 * non-decreasing and a session can be closed out the moment the next one starts. That is what keeps
 * the daily statistics O(1) in memory: there is never more than one open session.
 */
export class BlockAccumulator {
  readonly sums: BlockSums;
  private open = -1;
  private openPnl = 0;
  private eq = 0;
  private peak = 0;
  private peakOrdinal = 0;
  private tradeEq = 0;
  private tradePeak = 0;

  constructor(readonly geo: BlockGeometry, parts = CONCENTRATION_PARTS) {
    this.sums = emptySums(parts);
    this.peakOrdinal = geo.from;
  }

  /** Which sub-period a session ordinal falls in. */
  private part(ordinal: number): number {
    const p = this.sums.parts.length;
    const k = Math.floor(((ordinal - this.geo.from) * p) / Math.max(this.geo.sessions, 1));
    return k < 0 ? 0 : k >= p ? p - 1 : k;
  }

  add(pnl: number, ordinal: number, reason: number, barsHeld: number): void {
    const s = this.sums;
    if (ordinal !== this.open) {
      this.flush();
      this.open = ordinal;
      this.openPnl = 0;
    }
    this.openPnl += pnl;
    s.n++;
    s.net += pnl;
    s.tradeSumSq += pnl * pnl;
    s.barsHeld += barsHeld;
    if (reason >= 1 && reason <= 4) s.byReason[reason - 1]++;
    if (pnl > 0) {
      s.wins++;
      s.grossWin += pnl;
    } else s.grossLoss -= pnl;
    s.parts[this.part(ordinal)] += pnl;

    this.tradeEq += pnl;
    if (this.tradeEq > this.tradePeak) this.tradePeak = this.tradeEq;
    const dd = this.tradePeak - this.tradeEq;
    if (dd > s.maxTradeDrawdown) s.maxTradeDrawdown = dd;
  }

  /** Fold the open session into the daily sums. Idempotent; safe to call with nothing open. */
  private flush(): void {
    if (this.open < 0) return;
    const s = this.sums;
    const x = this.openPnl;
    s.tradedSessions++;
    s.daySumSq += x * x;
    if (x < 0) s.dayDownSq += x * x;
    const y = this.geo.market[this.open - this.geo.from];
    if (Number.isFinite(y)) s.dayXMarket += x * y;

    this.eq += x;
    if (this.eq > this.peak) {
      this.peak = this.eq;
      this.peakOrdinal = this.open;
    }
    const dd = this.peak - this.eq;
    if (dd > s.maxDailyDrawdown) s.maxDailyDrawdown = dd;
    const under = this.open - this.peakOrdinal;
    if (under > s.underwaterSessions) s.underwaterSessions = under;
    this.open = -1;
    this.openPnl = 0;
  }

  /** Close the last session and hand back the sums. Call exactly once, at the end of the walk. */
  finish(): BlockSums {
    this.flush();
    // A block that ends underwater has been underwater since its last peak, whether or not it
    // traded again — measuring only to the last TRADED session would understate the drought.
    const tail = this.geo.to - 1 - this.peakOrdinal;
    if (tail > this.sums.underwaterSessions) this.sums.underwaterSessions = tail;
    return this.sums;
  }
}

/** Everything a professional blotter puts at the top of a report, for one block. */
export interface BlockPerf {
  block: "research" | "locked";
  sessions: number;
  trades: number;
  tradesPerSession: number;
  netUsd: number;
  perTrade: number;
  winPct: number;
  profitFactor: number;
  payoffRatio: number;
  /** Annualised Sharpe of the per-session P&L stream, flat sessions included. */
  sharpe: number;
  sortino: number;
  calmar: number;
  /** Net P&L per year at this block's session rate. */
  annualUsd: number;
  maxDrawdown: number;
  maxTradeDrawdown: number;
  underwaterSessions: number;
  /** Fraction of bars in the block spent in a position. */
  exposure: number;
  avgBarsHeld: number;
  /** t of mean SESSION P&L against zero. The HAC version needs the series; see `perfFromDaily`. */
  tDaily: number;
  /** t of mean per-TRADE P&L against zero — the number the old sweep reported. */
  tTrade: number;
  /** Share of trades ending at the stop, the target, the time stop and the session close. */
  exitMix: [number, number, number, number];
  // ---- market-neutral block: never report a Sharpe without these three ----
  /** Regression slope of session P&L on the market's own move across the window. */
  beta: number;
  correlation: number;
  /** Sharpe of `pnl - beta x market` — the part of the result that is not exposure. */
  residSharpe: number;
  /** Intercept: mean session P&L left after the market is regressed out. */
  alphaUsd: number;
  /** `beta x total market move / net` — how much of the profit the market explains. */
  betaPnlShare: number;
  // ---- concentration ----
  /** Largest share of the block's P&L earned in any one of its sub-periods. */
  concentration: number;
  parts: number[];
}

const REASONS: ExitReason[] = ["stop", "target", "time", "session"];
export const EXIT_ORDER = REASONS;

export function finishBlock(sums: BlockSums, geo: BlockGeometry): BlockPerf {
  const N = Math.max(geo.sessions, 1);
  const ppy = geo.daysPerYear;
  const mean = sums.net / N;
  const varD = Math.max(sums.daySumSq / N - mean * mean, 0);
  const sd = Math.sqrt(varD);
  const downside = Math.sqrt(sums.dayDownSq / N);

  const mktMean = geo.marketSum / N;
  const mktVar = Math.max(geo.marketSumSq / N - mktMean * mktMean, 0);
  const cov = sums.dayXMarket / N - mean * mktMean;
  const beta = mktVar > 0 ? cov / mktVar : 0;
  const residVar = Math.max(varD - (mktVar > 0 ? (cov * cov) / mktVar : 0), 0);
  const alpha = mean - beta * mktMean;

  const years = N / ppy;
  const annual = years > 0 ? sums.net / years : 0;
  const totalAbs = Math.abs(sums.net);
  let concentration = NaN;
  if (totalAbs > 1e-9) {
    let best = -Infinity;
    for (const p of sums.parts) best = Math.max(best, p / sums.net);
    concentration = best;
  }

  const wins = sums.wins;
  const losses = sums.n - wins;
  return {
    block: geo.label,
    sessions: geo.sessions,
    trades: sums.n,
    tradesPerSession: sums.n / N,
    netUsd: sums.net,
    perTrade: sums.n ? sums.net / sums.n : 0,
    winPct: sums.n ? (100 * wins) / sums.n : 0,
    profitFactor: sums.grossLoss > 0 ? sums.grossWin / sums.grossLoss : sums.grossWin > 0 ? Infinity : 0,
    payoffRatio: wins && losses ? sums.grossWin / wins / (sums.grossLoss / losses) : 0,
    sharpe: sd > 0 ? (mean / sd) * Math.sqrt(ppy) : 0,
    sortino: downside > 0 ? (mean / downside) * Math.sqrt(ppy) : 0,
    calmar: sums.maxDailyDrawdown > 0 ? annual / sums.maxDailyDrawdown : 0,
    annualUsd: annual,
    maxDrawdown: sums.maxDailyDrawdown,
    maxTradeDrawdown: sums.maxTradeDrawdown,
    underwaterSessions: sums.underwaterSessions,
    exposure: geo.bars > 0 ? sums.barsHeld / geo.bars : 0,
    avgBarsHeld: sums.n ? sums.barsHeld / sums.n : 0,
    tDaily: sd > 0 ? (mean / sd) * Math.sqrt(N) : 0,
    tTrade: tradeT(sums),
    exitMix: sums.n
      ? [sums.byReason[0] / sums.n, sums.byReason[1] / sums.n, sums.byReason[2] / sums.n, sums.byReason[3] / sums.n]
      : [0, 0, 0, 0],
    beta,
    correlation: sd > 0 && mktVar > 0 ? cov / (sd * Math.sqrt(mktVar)) : 0,
    residSharpe: residVar > 0 ? (alpha / Math.sqrt(residVar)) * Math.sqrt(ppy) : 0,
    alphaUsd: alpha,
    betaPnlShare: totalAbs > 1e-9 ? (beta * geo.marketSum) / sums.net : NaN,
    concentration,
    parts: Array.from(sums.parts),
  };
}

function tradeT(s: BlockSums): number {
  if (s.n < 2) return 0;
  const m = s.net / s.n;
  const v = s.tradeSumSq / s.n - m * m;
  return v > 0 ? m / Math.sqrt(v / s.n) : 0;
}

/**
 * The same statistics from an explicit per-session array — the obvious implementation.
 *
 * Used by the detail view, where the series is wanted anyway for the equity curve, and by the test
 * that holds the streaming path to it. `daily` must cover EVERY session in the block in order,
 * zeros included.
 */
export function perfFromDaily(
  daily: ArrayLike<number>,
  geo: BlockGeometry,
  extra: Pick<BlockSums, "n" | "tradeSumSq" | "wins" | "grossWin" | "grossLoss" | "byReason" | "barsHeld" | "maxTradeDrawdown">,
  parts = CONCENTRATION_PARTS,
): BlockPerf {
  const sums = emptySums(parts);
  Object.assign(sums, extra);
  sums.parts = new Float64Array(parts);
  let eq = 0;
  let peak = 0;
  let peakAt = 0;
  sums.net = 0;
  for (let i = 0; i < daily.length; i++) {
    const x = daily[i];
    if (x !== 0) sums.tradedSessions++;
    sums.net += x;
    sums.daySumSq += x * x;
    if (x < 0) sums.dayDownSq += x * x;
    const y = geo.market[i];
    if (Number.isFinite(y)) sums.dayXMarket += x * y;
    const k = Math.min(parts - 1, Math.floor((i * parts) / Math.max(daily.length, 1)));
    sums.parts[k] += x;
    eq += x;
    if (eq > peak) {
      peak = eq;
      peakAt = i;
    }
    sums.maxDailyDrawdown = Math.max(sums.maxDailyDrawdown, peak - eq);
    sums.underwaterSessions = Math.max(sums.underwaterSessions, i - peakAt);
  }
  return finishBlock(sums, geo);
}

/**
 * Does this block clear the protocol's research gates?
 *
 * Deliberately a plain, readable predicate rather than a score: a gate that can be traded off
 * against another gate is not a gate. `CLAUDE.md` records that Gate 9 — the concentration limit —
 * caught nothing on the shipped scalp because it was specified out-of-sample, while on research
 * 20% of the sessions carried 76% of the profit. It is checked HERE, on whichever block is passed,
 * and the console passes the research block.
 */
export interface GateResult {
  name: string;
  pass: boolean;
  detail: string;
}

export function gates(p: BlockPerf, minTrades: number): GateResult[] {
  const conc = p.concentration;
  return [
    { name: "trades", pass: p.trades >= minTrades, detail: `${p.trades} vs ${minTrades} minimum` },
    { name: "profit factor", pass: p.profitFactor >= 1.05, detail: p.profitFactor.toFixed(2) },
    { name: "sharpe > 0", pass: p.sharpe > 0, detail: p.sharpe.toFixed(2) },
    {
      name: "not one sub-period",
      pass: Number.isFinite(conc) ? conc <= CONCENTRATION_LIMIT : false,
      detail: Number.isFinite(conc) ? `${(100 * conc).toFixed(0)}% of P&L in its biggest fifth` : "no P&L to attribute",
    },
    {
      name: "not market beta",
      pass: Number.isFinite(p.betaPnlShare) ? p.betaPnlShare <= 0.5 : false,
      detail: Number.isFinite(p.betaPnlShare) ? `${(100 * p.betaPnlShare).toFixed(0)}% of P&L is beta` : "no P&L to attribute",
    },
    { name: "residual sharpe > 0", pass: p.residSharpe > 0, detail: p.residSharpe.toFixed(2) },
    { name: "drawdown < gain", pass: p.maxDrawdown > 0 && p.netUsd > p.maxDrawdown, detail: `${p.maxDrawdown.toFixed(0)} vs ${p.netUsd.toFixed(0)}` },
  ];
}
