import type { Bar, Instrument, Trade } from "./types";

// Prop-firm evaluation simulator.
//
// A backtest answers "does this rule make money". A prop-firm evaluation asks four other questions
// that expectancy cannot see:
//
//   1. Does the equity path ever touch a TRAILING threshold that ratchets up behind every new high?
//      A drawdown measured from the start is irrelevant; the one measured from the running peak is
//      the one that ends the account. These are not the same number and are usually not close.
//   2. Does it reach the target before it touches that threshold — a race, not a sum.
//   3. Does it get there inside the minimum number of trading days?
//   4. Is the profit spread evenly enough to satisfy a consistency rule at payout time?
//
// The order of the same set of trades decides all four. That is why this module simulates paths
// rather than aggregates, and why it takes the INTRADAY equity path rather than closed P&L: most
// firms trail the peak of unrealised equity, so a trade that goes 40 points your way and comes back
// has already moved the threshold up behind you even though it booked nothing.

export interface PropRules {
  label: string;
  startBalance: number;
  /** Distance below the running peak at which the account is dead. */
  trailingDrawdown: number;
  /** "intraday" trails the peak of unrealised equity; "eod" only the closed balance at each day's end. */
  trailMode: "intraday" | "eod";
  /**
   * The threshold stops trailing once it would exceed startBalance + this offset, and locks there.
   * Apex-style accounts lock at +100; TopStep-style lock at the starting balance (0).
   * Infinity means the threshold trails forever and never locks.
   */
  lockAt: number;
  profitTarget: number;
  /** Closed loss on a single day that fails the account outright. Undefined = no such rule. */
  dailyLossLimit?: number;
  minTradingDays: number;
  /** At payout, the largest winning day must be at most this fraction of total profit. */
  consistencyPct?: number;
}

/** One session's contribution to the equity curve, for one unit of size. */
export interface DayPath {
  day: number;
  /** Closed P&L for the day, USD per contract. */
  pnl: number;
  /**
   * Cumulative intraday equity relative to the day's opening balance, USD per contract, in time
   * order. Includes unrealised excursion while a position is open, so a trailing threshold is
   * tested against the path and not only against the close.
   */
  marks: number[];
}

export type PropOutcome = "passed" | "blown" | "daily-loss" | "ran-out-of-days";

export interface PropRun {
  outcome: PropOutcome;
  /** Trading days consumed before the run ended. */
  days: number;
  /** Closed profit at the end of the run, relative to the starting balance. */
  profit: number;
  /** True when the run passed the target but the consistency rule would block the payout. */
  consistencyBlocked: boolean;
  largestWinningDay: number;
}

/**
 * Walk one ordered sequence of days against one rule set.
 *
 * The threshold is recomputed after every mark, because a new equity high moves it up immediately —
 * the account can be killed by a retracement from a peak it only touched for one minute.
 */
export function simulatePropRun(days: DayPath[], rules: PropRules, contracts: number, maxDays = Infinity): PropRun {
  const start = rules.startBalance;
  let equity = start;
  let peak = start;
  let used = 0;
  let largestWinningDay = 0;
  const cap = start + rules.lockAt;

  // The THRESHOLD locks when it reaches the lock point — not when the peak does. Getting this
  // backwards caps the threshold the moment the account is $100 up and makes every run look safe.
  const thresholdFor = (pk: number) => Math.min(pk - rules.trailingDrawdown, cap);

  for (const d of days) {
    if (used >= maxDays) return { outcome: "ran-out-of-days", days: used, profit: equity - start, consistencyBlocked: false, largestWinningDay };
    const dayOpen = equity;
    used++;

    if (rules.trailMode === "intraday") {
      for (const m of d.marks) {
        const e = dayOpen + m * contracts;
        if (e > peak) peak = e;
        if (e <= thresholdFor(peak)) {
          return { outcome: "blown", days: used, profit: e - start, consistencyBlocked: false, largestWinningDay };
        }
      }
    }

    const dayPnl = d.pnl * contracts;
    equity = dayOpen + dayPnl;
    if (dayPnl > largestWinningDay) largestWinningDay = dayPnl;

    if (rules.dailyLossLimit !== undefined && dayPnl <= -rules.dailyLossLimit) {
      return { outcome: "daily-loss", days: used, profit: equity - start, consistencyBlocked: false, largestWinningDay };
    }

    if (equity > peak) peak = equity;
    if (equity <= thresholdFor(peak)) {
      return { outcome: "blown", days: used, profit: equity - start, consistencyBlocked: false, largestWinningDay };
    }

    const profit = equity - start;
    if (profit >= rules.profitTarget && used >= rules.minTradingDays) {
      const blocked = rules.consistencyPct !== undefined && largestWinningDay > rules.consistencyPct * profit;
      // A consistency rule does not stop the evaluation passing; it stops the money leaving. The run
      // continues so the trader can dilute the outlier day, but the flag records that it was needed.
      if (!blocked) return { outcome: "passed", days: used, profit, consistencyBlocked: false, largestWinningDay };
    }
  }

  const profit = equity - start;
  const passedTarget = profit >= rules.profitTarget && used >= rules.minTradingDays;
  return {
    outcome: passedTarget ? "passed" : "ran-out-of-days",
    days: used,
    profit,
    consistencyBlocked: passedTarget && rules.consistencyPct !== undefined && largestWinningDay > rules.consistencyPct * profit,
    largestWinningDay,
  };
}

/**
 * Reconstruct per-session equity paths from a completed backtest.
 *
 * Marks use the ADVERSE extreme of each bar the position is open (the low for a long, the high for a
 * short) and then the favourable one, so a single bar both raises the peak and tests the threshold.
 * Within one bar that is doubly pessimistic; on 1-minute bars it is a small effect, and erring
 * towards killing the account is the right direction for a question about surviving one.
 *
 * The round-turn cost is charged at entry rather than exit, so the path never shows profit the
 * account has not actually earned.
 */
export function dayPathsFromTrades(trades: Trade[], bars: Bar[], inst: Instrument, dayIndex: Int32Array | number[]): DayPath[] {
  const perPoint = inst.tickValue / inst.tickSize;
  const byDay = new Map<number, DayPath>();

  const dayOf = (i: number) => dayIndex[i];
  for (const t of trades) {
    const day = dayOf(t.entryIndex);
    let d = byDay.get(day);
    if (!d) { d = { day, pnl: 0, marks: [] }; byDay.set(day, d); }

    const base = d.pnl; // equity already banked earlier in this same session
    const costUsd = t.costPoints * perPoint;
    d.marks.push(base - costUsd); // cost hits the moment the position opens

    for (let i = t.entryIndex; i <= t.exitIndex && i < bars.length; i++) {
      const adverse = t.side === 1 ? bars[i].l : bars[i].h;
      const favour = t.side === 1 ? bars[i].h : bars[i].l;
      const mtm = (px: number) => base - costUsd + t.side * (px - t.entryPx) * perPoint;
      d.marks.push(mtm(favour));
      d.marks.push(mtm(adverse));
    }
    d.marks.push(base + t.pnl);
    d.pnl = base + t.pnl;
  }

  return [...byDay.values()].sort((a, b) => a.day - b.day);
}

/** Rule sets modelled on the two most common $50k futures evaluations. Verify against current terms. */
export const PROP_RULES: Record<string, PropRules> = {
  apex50k: {
    label: "Apex-style $50k",
    startBalance: 50_000,
    trailingDrawdown: 2_500,
    trailMode: "intraday",
    lockAt: 100,
    profitTarget: 3_000,
    minTradingDays: 7,
    consistencyPct: 0.3,
  },
  topstep50k: {
    label: "TopStep-style $50k",
    startBalance: 50_000,
    trailingDrawdown: 2_000,
    trailMode: "eod",
    lockAt: 0,
    profitTarget: 3_000,
    dailyLossLimit: 1_000,
    minTradingDays: 5,
    consistencyPct: 0.5,
  },
};
