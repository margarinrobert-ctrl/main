import { clockFor, inWindow } from "./clock";
import { commissionPoints, pointsToUsd, roundTurnCostPoints, snap, takerSideCostPoints } from "./instruments";
import type { Bar, EntryIntent, ExitReason, Instrument, Strategy, Params, Trade } from "./types";

// Bar-by-bar backtester built around three anti-self-deception rules:
//
//  1. DECIDE ON CLOSE, FILL ON NEXT OPEN. A signal computed from bar i can only be executed at the
//     open of bar i+1. No same-bar fills, ever — that single shortcut is responsible for most
//     "amazing" scalping backtests.
//  2. PESSIMISTIC INTRABAR PATH. When a bar's range contains both the stop and the target, the stop
//     is assumed to have been hit first. We cannot see the path inside a bar, so we take the loss.
//  3. COSTS ARE CHARGED IN FULL, EVERY TRADE. Spread + two-sided slippage + commission, converted to
//     price units, deducted from every round turn regardless of how it exited.

export interface BacktestConfig {
  inst: Instrument;
  /** Restrict entries to the instrument's UTC session. Default true. */
  sessionOnly?: boolean;
  /** Cap on entries per UTC day — a real scalper's discipline constraint. Default unlimited. */
  maxTradesPerDay?: number;
  allowedSides?: "both" | "long" | "short";
  /** Fixed unit size. When `riskPerTradeUsd` is set, size floats to equalise risk instead. */
  units?: number;
  riskPerTradeUsd?: number;
  startEquity?: number;
  /** Override the modelled round-turn cost (price units). Used by the cost-sensitivity sweep. */
  costPointsOverride?: number;
  /**
   * How orders reach the market. This is the single biggest lever on a scalping result, so it is an
   * explicit modelling choice rather than a hidden assumption:
   *
   *  - `taker`     every trade pays the full round turn, entry and exit. Conservative, and what a
   *                market-order system actually experiences. This is the default.
   *  - `realistic` entry takes liquidity, a target exit is a resting limit and pays no spread, a
   *                stop exit takes liquidity. This is how a competent discretionary desk trades.
   *  - `passive`   entry is a resting limit that only fills if price trades THROUGH it, targets are
   *                passive, stops take liquidity. Cheapest, but see the adverse-selection caveat:
   *                bars are not order books, so a limit that fills in this model always fills, while
   *                a real resting order fills preferentially when the market is about to move
   *                against it. Treat `passive` as an upper bound on what execution can buy you.
   */
  fillModel?: "taker" | "realistic" | "passive";
  /** For `passive` entries: how many ticks BETTER than the signal close to rest the order. */
  limitOffsetTicks?: number;
}

export interface BacktestResult {
  trades: Trade[];
  /** Equity after each trade, starting with the opening balance. */
  equity: number[];
  /** Net USD P&L keyed by UTC day index — the series used for Sharpe and cross-strategy correlation. */
  dailyPnl: Map<number, number>;
  /** Reference round-turn cost, for reporting. Per-trade cost lives on each `Trade`. */
  costPoints: number;
  bars: number;
  config: BacktestConfig;
  /** `passive` fill model only: signals that never filled because price did not trade through. */
  unfilledLimits: number;
  /**
   * Exits where the SAME bar contained both the stop and the target. Rule 2 books those as losses
   * because the intrabar path is unknown. That is the right call, but it is a known conservative
   * bias whose size scales with stop distance relative to bar range — so it is measured, not hidden.
   */
  ambiguousExits: number;
}

interface OpenPos {
  side: 1 | -1;
  entryIndex: number;
  entryPx: number;
  stopPx: number;
  targetPx: number;
  stopDist: number;
  maxBars: number;
  units: number;
  tag?: string;
}


export function runBacktest(bars: Bar[], signal: (i: number) => EntryIntent | null, cfg: BacktestConfig): BacktestResult {
  const inst = cfg.inst;
  const sessionOnly = cfg.sessionOnly ?? true;
  const allowed = cfg.allowedSides ?? "both";
  const startEquity = cfg.startEquity ?? 100_000;
  const fillModel = cfg.fillModel ?? "taker";
  const referenceCost = cfg.costPointsOverride ?? roundTurnCostPoints(inst);
  // When a cost override is supplied (the sensitivity sweep), scale every component by the same
  // factor so the sweep stays meaningful under any fill model.
  const costScale = referenceCost / Math.max(roundTurnCostPoints(inst), 1e-12);
  const takerSide = takerSideCostPoints(inst) * costScale;
  const commission = commissionPoints(inst) * costScale;

  /** Cost actually charged to a trade, given how it entered and how it left. */
  const costFor = (reason: ExitReason): number => {
    if (fillModel === "taker") return referenceCost;
    const entry = fillModel === "passive" ? 0 : takerSide;
    const exit = reason === "target" ? 0 : takerSide; // a target rests; a stop must take liquidity
    return entry + exit + commission;
  };

  // Sessions and day boundaries are exchange-local: an ET trading day, not a UTC day.
  const clock = clockFor(bars, inst.tz);
  const dayOf = (i: number) => clock.dayIndex[i];

  const trades: Trade[] = [];
  const equity: number[] = [startEquity];
  const dailyPnl = new Map<number, number>();
  let cash = startEquity;
  let pos: OpenPos | null = null;
  let tradesToday = 0;
  let ambiguousExits = 0;
  let unfilledLimits = 0;
  let curDay = bars.length ? dayOf(0) : 0;

  const inSession = (i: number): boolean => (sessionOnly ? inWindow(clock.minuteOfDay[i], inst.session[0], inst.session[1]) : true);

  const close = (exitIndex: number, exitPx: number, reason: ExitReason) => {
    if (!pos) return;
    const gross = pos.side * (exitPx - pos.entryPx);
    const costPoints = costFor(reason);
    const net = gross - costPoints;
    const pnl = pointsToUsd(inst, net) * pos.units;
    const riskUsd = pointsToUsd(inst, pos.stopDist) * pos.units;
    cash += pnl;
    const b = bars[exitIndex];
    trades.push({
      side: pos.side,
      entryIndex: pos.entryIndex,
      exitIndex,
      entryTime: bars[pos.entryIndex].t,
      exitTime: b.t,
      entryPx: pos.entryPx,
      exitPx,
      grossPoints: gross,
      costPoints,
      pnl,
      r: riskUsd > 0 ? pnl / riskUsd : 0,
      barsHeld: exitIndex - pos.entryIndex,
      reason,
      tag: pos.tag,
    });
    equity.push(cash);
    const d = dayOf(exitIndex);
    dailyPnl.set(d, (dailyPnl.get(d) ?? 0) + pnl);
    pos = null;
  };

  for (let i = 0; i < bars.length; i++) {
    const bar = bars[i];
    const d = dayOf(i);
    if (d !== curDay) {
      curDay = d;
      tradesToday = 0;
    }

    // ---- manage an open position on the CURRENT bar (entry bar included) ----
    if (pos) {
      const long = pos.side === 1;
      const gapped = long ? bar.o <= pos.stopPx : bar.o >= pos.stopPx;
      const gappedTarget = long ? bar.o >= pos.targetPx : bar.o <= pos.targetPx;
      const hitStop = long ? bar.l <= pos.stopPx : bar.h >= pos.stopPx;
      const hitTarget = long ? bar.h >= pos.targetPx : bar.l <= pos.targetPx;

      if (gapped) {
        // Opened through the stop — the fill is the open, not the stop level.
        close(i, bar.o, "stop");
      } else if (hitStop) {
        // Rule 2: stop wins any ambiguous bar.
        if (hitTarget) ambiguousExits++;
        close(i, pos.stopPx, "stop");
      } else if (gappedTarget) {
        close(i, bar.o, "target");
      } else if (hitTarget) {
        close(i, pos.targetPx, "target");
      } else if (i - pos.entryIndex >= pos.maxBars) {
        close(i, bar.c, "time");
      } else if (sessionOnly && (!inSession(i) || i + 1 >= bars.length || dayOf(i + 1) !== d)) {
        // Never carry a scalp out of its liquidity window or over a session break.
        close(i, bar.c, "session");
      }
    }

    // ---- decide on this close, fill on the next open ----
    if (!pos && i + 1 < bars.length) {
      const next = bars[i + 1];
      const capOk = cfg.maxTradesPerDay === undefined || tradesToday < cfg.maxTradesPerDay;
      if (capOk && inSession(i + 1) && dayOf(i + 1) === d) {
        const intent = signal(i);
        if (intent && intent.stopDist > 0 && intent.targetDist > 0) {
          const sideOk =
            allowed === "both" || (allowed === "long" && intent.side === 1) || (allowed === "short" && intent.side === -1);
          if (sideOk) {
            let entryPx = next.o;
            if (fillModel === "passive") {
              // Rest the order a tick or two better than the close and require the next bar to
              // trade through it. A touch is not a fill: at the front of the queue you are behind
              // everyone already resting there.
              const offset = (cfg.limitOffsetTicks ?? 1) * inst.tickSize;
              const limitPx = bars[i].c - intent.side * offset;
              const through = intent.side === 1 ? next.l < limitPx : next.h > limitPx;
              if (!through) {
                unfilledLimits++;
                continue;
              }
              // Fill at the limit, or better if the bar opened past it.
              entryPx = intent.side === 1 ? Math.min(limitPx, next.o) : Math.max(limitPx, next.o);
            }
            const stopDist = Math.max(intent.stopDist, inst.tickSize);
            const units =
              cfg.riskPerTradeUsd !== undefined
                ? Math.max(cfg.riskPerTradeUsd / Math.max(pointsToUsd(inst, stopDist), 1e-9), 0)
                : cfg.units ?? 1;
            pos = {
              side: intent.side,
              entryIndex: i + 1,
              entryPx,
              stopPx: snap(inst, entryPx - intent.side * stopDist, intent.side === 1 ? -1 : 1),
              targetPx: snap(inst, entryPx + intent.side * intent.targetDist, intent.side === 1 ? 1 : -1),
              stopDist,
              maxBars: Math.max(1, Math.round(intent.maxBars)),
              units,
              tag: intent.tag,
            };
            tradesToday++;
            // No index fiddling: the next loop iteration lands on bar i+1, which is the entry bar,
            // and manages it from the top — so an entry can be stopped out on its own bar.
          }
        }
      }
    }
  }

  if (pos) close(bars.length - 1, bars[bars.length - 1].c, "eod");

  return { trades, equity, dailyPnl, costPoints: referenceCost, bars: bars.length, config: cfg, ambiguousExits, unfilledLimits };
}

/** Convenience: build a strategy on a series and run it. */
export function runStrategy(strategy: Strategy, bars: Bar[], params: Params, cfg: BacktestConfig): BacktestResult {
  return runBacktest(bars, strategy.build(bars, params, cfg.inst), cfg);
}
