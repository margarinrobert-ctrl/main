/**
 * The exit tensor: the reason a knob-turn is instant instead of a re-run.
 *
 * `runBacktest` walks the price series once per configuration. That is correct and it is what
 * every number in `docs/` was measured with — but a stop x target x hold x session grid is
 * hundreds of configurations per rule, and a period sweep multiplies that again.
 *
 * The observation this file is built on: in `runBacktest` a trade's outcome depends ONLY on the
 * bar it was signalled from and the geometry. No trade's P&L depends on which OTHER trades were
 * taken — the single coupling between trades is that a new signal is ignored while a position is
 * open, and that needs the exit BAR, not the price path. So the walk can be done once per
 * geometry for EVERY bar as a hypothetical entry, and cached:
 *
 *     exits[g][i]  ->  exit bar, exit reason, gross points
 *
 * A rule is then a mask, and evaluating it is a gather plus a sequential no-overlap scan — no
 * price data touched. Stop, target, max hold and session window become array indices.
 *
 * Costs are deliberately NOT baked into the cached number. `gross` is the raw price move in the
 * trade's favour; commission and spread are affine in it, so any cost assumption is applied at
 * read time. Cost sensitivity — the test most likely to kill a scalping result — is therefore
 * free rather than the one you skip.
 *
 * `tuner.test.ts` asserts this reproduces `runBacktest` trade for trade.
 */
import { clockFor, inWindow, type Clock } from "../clock";
import { feePoints, fillFrictionPoints, type FillContext } from "../costs";
import { pointsToUsd, snap } from "../instruments";
import { trueRange } from "../series";
import type { Bar, ExitReason, Instrument } from "../types";

export const REASON = { stop: 1, target: 2, time: 3, session: 4, none: 0 } as const;
export type ReasonCode = (typeof REASON)[keyof typeof REASON];

export const REASON_NAME: Record<number, ExitReason> = { 1: "stop", 2: "target", 3: "time", 4: "session" };

export interface Geometry {
  /** Stop distance as a multiple of ATR(atrPeriod). */
  stop: number;
  /** Target as a multiple of the stop distance — the R multiple. */
  target: number;
  /** Hard time stop, in bars held. */
  maxBars: number;
}

export interface TensorSpec {
  bars: Bar[];
  inst: Instrument;
  side: 1 | -1;
  geoms: Geometry[];
  atrPeriod: number;
  /** ATR array for the stop unit, indexed by SIGNAL bar. Supplied so it is memoised upstream. */
  atr: ArrayLike<number>;
  /** The tuner's entry window, in exchange-local minutes. Carried for labelling; the restriction
   *  itself is applied through `eligible`, because a window limits where a signal is DECIDED. */
  window: [number, number];
  /** Bars a hypothetical entry may be signalled on. Outside this, no exit is computed at all. */
  eligible?: Uint8Array;
}

export interface ExitTensor {
  /** exitBar[g * n + i], or -1 where bar i could not open a trade under geometry g. */
  exitBar: Int32Array;
  reason: Uint8Array;
  /** Gross price move in the trade's favour, in POINTS, before any cost. */
  gross: Float64Array;
  n: number;
  geoms: Geometry[];
  clock: Clock;
  window: [number, number];
  side: 1 | -1;
  inst: Instrument;
  /** Bars per geometry that could actually open a trade — the control samples from these. */
  eligible: Uint8Array;
  /**
   * Spread + slippage for a TAKER fill landing on each bar, and for a STOP fill landing on each
   * bar, in price units.
   *
   * These are per BAR, not per trade, which is the observation that keeps costs a read-time
   * lookup even though slippage is now bar-dependent: friction is a function of the bar a fill
   * lands on and the role it played, and the tensor already stores the exit bar and the exit
   * reason. So the fill model, the broker and the cost multiplier all stay free to change without
   * rebuilding anything, and the per-bar arrays cost 2n doubles instead of 2 x geometries x n.
   */
  frictionTaker: Float64Array;
  frictionStop: Float64Array;
  bytes: number;
}

/**
 * Whether a signal at bar i can be filled at i+1.
 *
 * This is `runBacktest`'s condition and deliberately NOT the tuner's entry window: the fill bar
 * must be inside the INSTRUMENT's session and on the same exchange-local day. The entry window is
 * a restriction on where a signal may be DECIDED, and it is applied to the signal bar through
 * `spec.eligible`. Conflating the two silently drops every signal on the window's last bar --
 * which is how this function was written first, and it cost 32 of 781 trades against the engine.
 */
function fillable(clock: Clock, i: number, n: number, session: [number, number]): boolean {
  if (i + 1 >= n) return false;
  if (!inWindow(clock.minuteOfDay[i + 1], session[0], session[1])) return false;
  return clock.dayIndex[i + 1] === clock.dayIndex[i];
}

export function buildTensor(spec: TensorSpec): ExitTensor {
  const { bars, inst, side, geoms, atr, window } = spec;
  const n = bars.length;
  const g = geoms.length;
  const clock = clockFor(bars, inst.tz);
  const exitBar = new Int32Array(g * n).fill(-1);
  const reason = new Uint8Array(g * n);
  const gross = new Float64Array(g * n);
  const eligible = new Uint8Array(n);

  // Slippage scales with how fast the bar was, measured against the instrument's own MEDIAN true
  // range. Median rather than mean: bar ranges are heavy-tailed, and a mean is dragged up by the
  // same fast bars the model is trying to charge extra for, flattening the effect being measured.
  const tr = trueRange(bars);
  const sorted = tr.filter((x) => Number.isFinite(x) && x > 0).sort((a, b) => a - b);
  const medianTr = sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0;
  const frictionTaker = new Float64Array(n);
  const frictionStop = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const ctx: FillContext = {
      volRatio: medianTr > 0 && Number.isFinite(tr[i]) ? tr[i] / medianTr : 1,
      inSession: inWindow(clock.minuteOfDay[i], inst.session[0], inst.session[1]),
    };
    frictionTaker[i] = fillFrictionPoints(inst, "taker", ctx);
    frictionStop[i] = fillFrictionPoints(inst, "stop", ctx);
  }

  const allowed = spec.eligible;
  for (let i = 0; i < n; i++) {
    const a = atr[i];
    if (!Number.isFinite(a) || a <= 0) continue;
    if (allowed && !allowed[i]) continue;
    if (!fillable(clock, i, n, inst.session)) continue;
    eligible[i] = 1;
  }

  const long = side === 1;
  for (let gi = 0; gi < g; gi++) {
    const geo = geoms[gi];
    const maxBars = Math.max(1, Math.round(geo.maxBars));
    const base = gi * n;
    for (let i = 0; i < n; i++) {
      if (!eligible[i]) continue;
      const e = i + 1;
      const entryPx = bars[e].o;
      const rawStop = Math.max(geo.stop * atr[i], inst.tickSize);
      const stopPx = snap(inst, entryPx - side * rawStop, long ? -1 : 1);
      const targetPx = snap(inst, entryPx + side * geo.target * rawStop, long ? 1 : -1);
      const day = clock.dayIndex[e];

      for (let j = e; j < n; j++) {
        const b = bars[j];
        // Precedence is `runBacktest`'s, in its order: a gap through the stop fills at the open;
        // a bar holding BOTH levels books the stop, because the path inside a bar is unknown.
        const gapStop = long ? b.o <= stopPx : b.o >= stopPx;
        const hitStop = long ? b.l <= stopPx : b.h >= stopPx;
        const gapTarget = long ? b.o >= targetPx : b.o <= targetPx;
        const hitTarget = long ? b.h >= targetPx : b.l <= targetPx;
        let px = NaN;
        let why: ReasonCode = REASON.none;
        if (gapStop) {
          px = b.o;
          why = REASON.stop;
        } else if (hitStop) {
          px = stopPx;
          why = REASON.stop;
        } else if (gapTarget) {
          px = b.o;
          why = REASON.target;
        } else if (hitTarget) {
          px = targetPx;
          why = REASON.target;
        } else if (j - e >= maxBars) {
          px = b.c;
          why = REASON.time;
        } else if (!inWindow(clock.minuteOfDay[j], inst.session[0], inst.session[1]) || j + 1 >= n || clock.dayIndex[j + 1] !== day) {
          // Never carry a scalp out of its liquidity window or over a session break.
          px = b.c;
          why = REASON.session;
        }
        if (why !== REASON.none) {
          exitBar[base + i] = j;
          reason[base + i] = why;
          gross[base + i] = side * (px - entryPx);
          break;
        }
      }
    }
  }

  return {
    exitBar,
    reason,
    gross,
    n,
    geoms,
    clock,
    window,
    side,
    inst,
    eligible,
    frictionTaker,
    frictionStop,
    bytes: exitBar.byteLength + reason.byteLength + gross.byteLength + frictionTaker.byteLength + frictionStop.byteLength,
  };
}

// ------------------------------------------------------------------ costs, applied at read time
export interface CostModel {
  /**
   * How orders reached the market. `taker` assumes every fill crossed the spread, including the
   * target — conservative, and what a pure market-order system experiences. `realistic` lets a
   * target rest, so it pays fees only. `passive` additionally treats the ENTRY as a resting limit;
   * the tensor does not model whether such an entry would have filled, so use it only alongside a
   * fill test, and read it as an upper bound on what execution can buy you.
   */
  fillModel: "taker" | "realistic" | "passive";
  /** Multiplier on every component. 2 is the standard stress case. */
  mult: number;
}

export const DEFAULT_COSTS: CostModel = { fillModel: "taker", mult: 1 };

/**
 * Cost in POINTS for one trade: per-side fees, plus the spread and slippage each fill actually
 * paid on the bar it landed on.
 *
 * The two halves are kept apart on purpose. Fees are constant per trade, so a different broker is
 * free to try. Friction is bar-dependent, so it is looked up from the per-bar arrays the tensor
 * built — which is what lets slippage depend on how fast the market was without giving up the
 * property that every knob is a read-time lookup.
 */
export function costPointsFor(t: ExitTensor, costs: CostModel, why: number, entryBar: number, exitBar: number): number {
  const fees = 2 * feePoints(t.inst);
  const entry = costs.fillModel === "passive" ? 0 : t.frictionTaker[entryBar];
  let exit: number;
  if (why === REASON.stop) exit = t.frictionStop[exitBar];
  else if (why === REASON.target && costs.fillModel !== "taker") exit = 0;
  else exit = t.frictionTaker[exitBar];
  return (fees + entry + exit) * costs.mult;
}

// ------------------------------------------------------------------ the walk
export interface WalkStats {
  n: number;
  netUsd: number;
  wins: number;
  grossWin: number;
  grossLoss: number;
  sumSq: number;
  maxDrawdown: number;
  byReason: [number, number, number, number];
  /** Split by the ENTRY bar's session, using the research/locked cut supplied by the caller. */
  nResearch: number;
  netResearch: number;
  winsResearch: number;
  nLocked: number;
  netLocked: number;
  winsLocked: number;
}

const EMPTY: WalkStats = {
  n: 0, netUsd: 0, wins: 0, grossWin: 0, grossLoss: 0, sumSq: 0, maxDrawdown: 0,
  byReason: [0, 0, 0, 0], nResearch: 0, netResearch: 0, winsResearch: 0,
  nLocked: 0, netLocked: 0, winsLocked: 0,
};

export interface WalkTrade {
  signalBar: number;
  entryBar: number;
  exitBar: number;
  reason: ExitReason;
  pnl: number;
}

/**
 * The no-overlap scan for one geometry: take a signal only when the book is flat.
 *
 * A signal ON the exit bar is legal — the position closed during that bar, so its close finds the
 * book flat. That is `runBacktest`'s behaviour (position management runs before signal generation
 * within a bar) and it is reproduced here rather than approximated.
 */
export function walk(
  t: ExitTensor,
  gi: number,
  triggers: Int32Array,
  costs: CostModel,
  lockedFromSession: number,
  sessionOfBar: ArrayLike<number>,
  collect?: WalkTrade[],
): WalkStats {
  const base = gi * t.n;
  const s: WalkStats = { ...EMPTY, byReason: [0, 0, 0, 0] };
  let free = -1;
  let eq = 0;
  let peak = 0;
  for (let k = 0; k < triggers.length; k++) {
    const i = triggers[k];
    if (i < free) continue;
    const x = t.exitBar[base + i];
    if (x < 0) continue;
    const why = t.reason[base + i];
    const net = t.gross[base + i] - costPointsFor(t, costs, why, i + 1, x);
    const pnl = pointsToUsd(t.inst, net);
    free = x;
    s.n++;
    s.netUsd += pnl;
    s.sumSq += pnl * pnl;
    s.byReason[why - 1]++;
    if (pnl > 0) {
      s.wins++;
      s.grossWin += pnl;
    } else s.grossLoss -= pnl;
    eq += pnl;
    if (eq > peak) peak = eq;
    if (peak - eq > s.maxDrawdown) s.maxDrawdown = peak - eq;
    if (sessionOfBar[i] < lockedFromSession) {
      s.nResearch++;
      s.netResearch += pnl;
      if (pnl > 0) s.winsResearch++;
    } else {
      s.nLocked++;
      s.netLocked += pnl;
      if (pnl > 0) s.winsLocked++;
    }
    if (collect) collect.push({ signalBar: i, entryBar: i + 1, exitBar: x, reason: REASON_NAME[why], pnl });
  }
  return s;
}

// ------------------------------------------------------------------ the matched control
/** Bars grouped by minute-of-day, so a control draw can match the rule's session timing. */
export interface MinuteIndex {
  /** Concatenated bar indices, grouped by minute-of-day slot. */
  idx: Int32Array;
  /** Offsets into `idx`, length slots+1. */
  ptr: Int32Array;
  /** Slot for each bar, or -1 if the bar is not eligible. */
  slot: Int32Array;
}

export function minuteIndex(t: ExitTensor): MinuteIndex {
  const { clock, n, eligible } = t;
  const bySlot = new Map<number, number[]>();
  for (let i = 0; i < n; i++) {
    if (!eligible[i]) continue;
    const m = clock.minuteOfDay[i];
    const list = bySlot.get(m);
    if (list) list.push(i);
    else bySlot.set(m, [i]);
  }
  const mods = Array.from(bySlot.keys()).sort((a, b) => a - b);
  const slot = new Int32Array(n).fill(-1);
  const ptr = new Int32Array(mods.length + 1);
  let total = 0;
  mods.forEach((m, s) => {
    total += bySlot.get(m)!.length;
    ptr[s + 1] = total;
  });
  const idx = new Int32Array(total);
  let w = 0;
  mods.forEach((m, s) => {
    for (const i of bySlot.get(m)!) {
      idx[w++] = i;
      slot[i] = s;
    }
  });
  return { idx, ptr, slot };
}

/** xorshift64* — deterministic, so a control p-value is reproducible from its seed. */
function rng(seed: number): () => number {
  let s = BigInt(seed >>> 0) | 1n;
  const M = (1n << 64n) - 1n;
  return () => {
    s = (s ^ (s << 13n)) & M;
    s = s ^ (s >> 7n);
    s = (s ^ (s << 17n)) & M;
    return Number(s & 0xffffffffn) / 0x100000000;
  };
}

export interface ControlResult {
  draws: number;
  meanAll: number;
  meanResearch: number;
  meanLocked: number;
  /** One-sided p: how often a matched random entry set did at least as well per trade. */
  pAll: number;
  pResearch: number;
  pLocked: number;
  /**
   * The BASE RATE: what fraction of trades a random entry wins under this exact geometry.
   *
   * A win rate means nothing without it. The driftless bound for an R-multiple target is
   * 1/(1+R), but the real base rate is not that -- costs push it down, a wider barrier pushes it
   * back up, and drift lifts longs and sinks shorts. Measuring it from the same matched draws
   * that price the dollars means a rule is always scored against its own geometry rather than
   * against 50%.
   */
  meanWinPct: number;
  /** One-sided p on the win rate specifically. */
  pWin: number;
}

/**
 * Random entries with the SAME side, geometry and minute-of-day distribution as the rule.
 *
 * Matching minute-of-day is what makes this a control rather than a strawman: it prices in session
 * timing, drift over the holding period, the round-turn cost and the width of the barrier all at
 * once, so a rule that beats it has an edge that is none of those things. Only WHICH BARS differ.
 */
export function matchedControl(
  t: ExitTensor,
  gi: number,
  triggers: Int32Array,
  costs: CostModel,
  lockedFromSession: number,
  sessionOfBar: ArrayLike<number>,
  actual: { all: number; research: number; locked: number; winPct?: number },
  draws = 2000,
  seed = 7,
): ControlResult {
  const mi = minuteIndex(t);
  const rand = rng(seed);
  const perAll = new Float64Array(draws);
  const perRes = new Float64Array(draws);
  const perLok = new Float64Array(draws);
  const winPct = new Float64Array(draws);
  const pick = new Int32Array(triggers.length);
  for (let d = 0; d < draws; d++) {
    let m = 0;
    for (let k = 0; k < triggers.length; k++) {
      const s = mi.slot[triggers[k]];
      if (s < 0) continue;
      const a = mi.ptr[s];
      const b = mi.ptr[s + 1];
      if (b <= a) continue;
      pick[m++] = mi.idx[a + Math.floor(rand() * (b - a))];
    }
    const sample = pick.slice(0, m).sort();
    const st = walk(t, gi, sample, costs, lockedFromSession, sessionOfBar);
    perAll[d] = st.n ? st.netUsd / st.n : 0;
    perRes[d] = st.nResearch ? st.netResearch / st.nResearch : 0;
    perLok[d] = st.nLocked ? st.netLocked / st.nLocked : 0;
    winPct[d] = st.n ? (100 * st.wins) / st.n : 0;
  }
  const mean = (a: Float64Array) => a.reduce((x, y) => x + y, 0) / Math.max(a.length, 1);
  const p = (a: Float64Array, act: number) => {
    let c = 0;
    for (const v of a) if (v >= act) c++;
    return (c + 1) / (a.length + 1);
  };
  return {
    draws,
    meanAll: mean(perAll),
    meanResearch: mean(perRes),
    meanLocked: mean(perLok),
    pAll: p(perAll, actual.all),
    pResearch: p(perRes, actual.research),
    pLocked: p(perLok, actual.locked),
    meanWinPct: mean(winPct),
    pWin: actual.winPct === undefined ? NaN : p(winPct, actual.winPct),
  };
}
