/**
 * The tuner's public surface: load bars once, then turn knobs.
 *
 * `TunerSession` owns the four things that are expensive to build and cheap to reuse — the bar
 * set, the memoised indicator arrays, the exit tensors and the per-block market factor — so a UI
 * can hold one and every subsequent question is a lookup. See `tensor.ts` for why that is possible
 * at all, and `performance.ts` for why a full performance report costs the same as a trade count.
 *
 * Three guardrails are structural rather than advisory, and none has an off switch:
 *
 *   * a `SweepRow` carries RESEARCH-block statistics and nothing else. The locked block is
 *     computed in the same pass — it is free — but it lives on a separate field that the worker's
 *     projection never copies, and `reveal` is the only way to read it. Ranking on anything that
 *     touches the holdout puts the holdout inside the selection; `CLAUDE.md` records that
 *     happening twice, and both times the result looked better than it was. It happened a third
 *     time in this very file: the sweep used to return whole-sample trade counts, $/trade, win
 *     rate, profit factor and drawdown, and the console displayed them as its headline columns
 *     under a caption promising research-only numbers.
 *   * every result carries the count of configurations evaluated to produce it, because a grid
 *     this cheap makes multiplicity the binding constraint before anything else.
 *   * ranking is restricted by TYPE to research-block objectives — see `RANK_KEYS`.
 *
 * And one performance guarantee, which is what keeps the page usable: `sweepIter` is a generator
 * that yields between chunks, so the worker driving it can drain its message queue and abandon a
 * superseded run. Nothing here blocks for more than a few milliseconds at a time.
 */
import { clockFor, sessionIndex } from "../clock";
import { pointsToUsd } from "../instruments";
import type { Bar, Instrument } from "../types";
import { get, makeContext, type IndicatorContext } from "./indicators";
import { ByteLru } from "./lru";
import {
  BlockAccumulator,
  finishBlock,
  type BlockGeometry,
  type BlockPerf,
} from "./performance";
import { fillTemplate, ruleMask, templateKeys } from "./rule";
import {
  buildTensor,
  buildTensorIter,
  DEFAULT_COSTS,
  geometriesPerBatch,
  matchedControl,
  REASON_NAME,
  walk,
  type ControlResult,
  type CostModel,
  type ExitTensor,
  type Geometry,
  type Progress,
  type WalkStats,
  type WalkTrade,
} from "./tensor";

export * from "./tensor";
export * from "./performance";
export { catalogue, type CatalogueEntry } from "./indicators";
export { RuleError, templateKeys } from "./rule";
export { ByteLru } from "./lru";

/** The research/locked split: the first 65% of SESSIONS, matching the Python research layer. */
export const RESEARCH_FRACTION = 0.65;

/** Default cache budgets, in bytes. Chosen to sit well inside a browser tab's working set. */
export const DEFAULT_BUDGETS = {
  /** Exit tensors. Also the ceiling on ONE tensor, which sets the geometry batch size. */
  tensor: 384 * 1024 * 1024,
  /** Memoised indicator arrays. A period sweep is the thing that fills this. */
  indicator: 96 * 1024 * 1024,
  /** Trigger index lists and window masks — small, but one per rule x window. */
  trigger: 32 * 1024 * 1024,
};

/** Refuse rather than hang: a grid past this is a research job, not an interactive question. */
export const MAX_CONFIGURATIONS = 2_000_000;

export interface WindowSpec {
  label: string;
  /** [start, end) in exchange-local minutes. */
  minutes: [number, number];
}

export function parseWindow(spec: string): WindowSpec {
  const m = /^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$/.exec(spec);
  if (!m) throw new Error(`window must look like "09:30-11:00", got "${spec}"`);
  const a = Number(m[1]) * 60 + Number(m[2]);
  const b = Number(m[3]) * 60 + Number(m[4]);
  if (a > 1439 || b > 1440) throw new Error(`window "${spec}" is outside a day`);
  return { label: spec.trim(), minutes: [a, b] };
}

export interface Config {
  rule: string;
  side: 1 | -1;
  window: string;
  geom: Geometry;
  atrPeriod: number;
  costs: CostModel;
}

export interface Outcome {
  config: Config;
  stats: WalkStats;
  triggers: number;
  research: BlockPerf;
  /** Present only when the caller asked for it — sweeps do not compute controls for every cell. */
  control?: ControlResult;
}

/**
 * What a sweep may be ranked by. Every one of these reads the RESEARCH block; there is
 * deliberately no way to spell "rank by the locked block" in this type.
 *
 * `residSharpe` is first because it is the one `CLAUDE.md` says to rank on: a Sharpe computed on
 * raw dollars cannot tell an edge from leverage, and on the strategy this repository shipped, 87%
 * of the holdout profit turned out to be market beta.
 */
export const RANK_KEYS = ["residSharpe", "sharpe", "perTrade", "netUsd", "profitFactor", "calmar", "tDaily"] as const;
export type RankKey = (typeof RANK_KEYS)[number];

export interface SweepAxes {
  rule: string;
  sides: (1 | -1)[];
  windows: string[];
  stops: number[];
  targets: number[];
  maxBars: number[];
  atrPeriod: number;
  costs: CostModel[];
  /** Values for each {name} placeholder in the rule. */
  params: Record<string, number[]>;
  minTrades: number;
  rankBy?: RankKey;
}

export const DEFAULT_AXES: SweepAxes = {
  rule: "always",
  sides: [1],
  windows: ["09:30-11:00"],
  stops: [1, 1.5, 2, 2.5],
  targets: [0.5, 1, 1.5, 2],
  maxBars: [12],
  atrPeriod: 14,
  costs: [DEFAULT_COSTS],
  params: {},
  minTrades: 30,
  rankBy: "residSharpe",
};

/** Identifies a configuration well enough to rebuild it, so nothing depends on a live cache. */
export interface ConfigRef {
  side: 1 | -1;
  window: string;
  atrPeriod: number;
  geom: Geometry;
  rule: string;
  costs: CostModel;
}

export interface SweepRow {
  key: string;
  rule: string;
  params: Record<string, number>;
  side: 1 | -1;
  window: string;
  stop: number;
  target: number;
  maxBars: number;
  costLabel: string;
  /** RESEARCH block. This is the only performance object a sweep result is allowed to display. */
  research: BlockPerf;
  /**
   * Locked block, computed in the same pass because it is free, and never sent to a UI. `reveal`
   * is the only reader. See this file's header for why the field is separate rather than merged.
   */
  locked: BlockPerf;
  ref: ConfigRef;
}

export interface SweepResult {
  rows: SweepRow[];
  /** Configurations evaluated, INCLUDING those dropped for too few trades. */
  evaluated: number;
  dropped: number;
  minTrades: number;
  rankBy: RankKey;
  ms: number;
  tensorMs: number;
  /** Tensors built for this sweep. More than one means the geometry axis was batched. */
  tensors: number;
  cache: { tensorBytes: number; indicatorBytes: number };
}

export type SweepProgress = Progress;

export class TunerSession {
  readonly ctx: IndicatorContext;
  /** Raw session ids (day-based, sparse across weekends) — what session VWAP groups on. */
  readonly sessionOfBar: Int32Array;
  /** Dense 0-based session ordinals. Every block boundary and every daily statistic uses these. */
  readonly ordinalOfBar: Int32Array;
  readonly sessionCount: number;
  /** First ordinal of the locked block. */
  readonly lockedFromOrdinal: number;
  /** Bars in each block, for the exposure figure. */
  readonly blockBars: { research: number; locked: number };

  private readonly tensors: ByteLru<ExitTensor>;
  private readonly triggerCache: ByteLru<Int32Array>;
  private readonly maskCache = new Map<string, Uint8Array>();
  private readonly geometryCache = new Map<string, { research: BlockGeometry; locked: BlockGeometry }>();

  constructor(
    readonly bars: Bar[],
    readonly inst: Instrument,
    readonly label = "bars",
    budgets: Partial<typeof DEFAULT_BUDGETS> = {},
  ) {
    const b = { ...DEFAULT_BUDGETS, ...budgets };
    this.tensors = new ByteLru<ExitTensor>(b.tensor);
    this.triggerCache = new ByteLru<Int32Array>(b.trigger);

    const clock = clockFor(bars, inst.tz);
    this.sessionOfBar = sessionIndex(clock, inst.session[0]);
    // Session ids are day-based, so they skip weekends and holidays. Every block boundary, market
    // series index and sub-period split below assumes a DENSE 0..count-1 coordinate; deriving it
    // once here is what lets those be plain array indices instead of map lookups in a hot loop.
    const unique = new Set<number>();
    for (let i = 0; i < this.sessionOfBar.length; i++) unique.add(this.sessionOfBar[i]);
    const sorted = Array.from(unique).sort((a, z) => a - z);
    this.sessionCount = sorted.length;
    const ordinalOf = new Map<number, number>();
    sorted.forEach((id, k) => ordinalOf.set(id, k));
    this.ordinalOfBar = new Int32Array(this.sessionOfBar.length);
    for (let i = 0; i < this.sessionOfBar.length; i++) this.ordinalOfBar[i] = ordinalOf.get(this.sessionOfBar[i])!;

    this.lockedFromOrdinal = Math.floor(RESEARCH_FRACTION * this.sessionCount);
    let researchBars = 0;
    for (let i = 0; i < this.ordinalOfBar.length; i++) if (this.ordinalOfBar[i] < this.lockedFromOrdinal) researchBars++;
    this.blockBars = { research: researchBars, locked: bars.length - researchBars };

    this.ctx = makeContext(bars, this.sessionOfBar, clock.minuteOfDay, label, b.indicator);
  }

  cacheStats() {
    return { tensor: this.tensors.stats(), indicator: this.ctx.cache.stats(), trigger: this.triggerCache.stats() };
  }

  /** ATR the stop is sized in — memoised through the same registry the rules use. */
  atr(period: number): Float64Array {
    return get(this.ctx, "atr", [period]);
  }

  windowMask(w: WindowSpec): Uint8Array {
    const key = `win|${w.minutes[0]}|${w.minutes[1]}`;
    const hit = this.maskCache.get(key);
    if (hit) return hit;
    const clock = clockFor(this.bars, this.inst.tz);
    const out = new Uint8Array(this.bars.length);
    const [a, b] = w.minutes;
    for (let i = 0; i < out.length; i++) {
      const m = clock.minuteOfDay[i];
      out[i] = (a <= b ? m >= a && m < b : m >= a || m < b) ? 1 : 0;
    }
    this.maskCache.set(key, out);
    return out;
  }

  /**
   * The market factor: P&L in USD of holding ONE long unit across the entry window, per session.
   *
   * This is the regressor `performance.ts` neutralises against, and it has to be the move across
   * the STRATEGY'S OWN window rather than the whole session — a rule that only trades 09:30-11:00
   * is exposed to that hour and a half, not to the close. Sessions with no bars in the window
   * score zero, which is right: no exposure was available to take, and no trade could have been.
   */
  private marketSeries(w: WindowSpec): Float64Array {
    const out = new Float64Array(this.sessionCount);
    const mask = this.windowMask(w);
    let cur = -1;
    let open = 0;
    for (let i = 0; i < this.bars.length; i++) {
      if (!mask[i]) continue;
      const o = this.ordinalOfBar[i];
      if (o !== cur) {
        cur = o;
        open = this.bars[i].o;
      }
      out[o] = pointsToUsd(this.inst, this.bars[i].c - open);
    }
    return out;
  }

  /** Fixed per-block facts for one window, built once and reused by every cell of the sweep. */
  blockGeometry(w: WindowSpec): { research: BlockGeometry; locked: BlockGeometry } {
    const hit = this.geometryCache.get(w.label);
    if (hit) return hit;
    const market = this.marketSeries(w);
    const cut = this.lockedFromOrdinal;
    const make = (label: "research" | "locked", from: number, to: number, bars: number): BlockGeometry => {
      const slice = market.slice(from, to);
      let sum = 0;
      let sumSq = 0;
      for (const v of slice) {
        sum += v;
        sumSq += v * v;
      }
      return {
        label, from, to,
        sessions: Math.max(to - from, 0),
        bars,
        daysPerYear: this.inst.daysPerYear,
        market: slice,
        marketSum: sum,
        marketSumSq: sumSq,
      };
    };
    const made = {
      research: make("research", 0, cut, this.blockBars.research),
      locked: make("locked", cut, this.sessionCount, this.blockBars.locked),
    };
    this.geometryCache.set(w.label, made);
    return made;
  }

  tensorKey(side: 1 | -1, window: WindowSpec, atrPeriod: number, geoms: Geometry[]): string {
    const g = geoms.map((x) => `${x.stop}/${x.target}/${x.maxBars}`).join(";");
    return `${this.label}|${side}|${window.label}|${atrPeriod}|${g}`;
  }

  private tensorSpec(side: 1 | -1, window: WindowSpec, atrPeriod: number, geoms: Geometry[]) {
    return {
      bars: this.bars,
      inst: this.inst,
      side,
      geoms,
      atrPeriod,
      atr: this.atr(atrPeriod),
      window: window.minutes,
      eligible: this.windowMask(window),
    };
  }

  tensor(side: 1 | -1, window: WindowSpec, atrPeriod: number, geoms: Geometry[]): ExitTensor {
    const key = this.tensorKey(side, window, atrPeriod, geoms);
    return this.tensors.take(key, () => {
      const value = buildTensor(this.tensorSpec(side, window, atrPeriod, geoms));
      return { value, bytes: value.bytes };
    });
  }

  /** Same, but yielding after every geometry — see `buildTensorIter` for why that matters. */
  *tensorIter(side: 1 | -1, window: WindowSpec, atrPeriod: number, geoms: Geometry[]): Generator<Progress, ExitTensor, void> {
    const key = this.tensorKey(side, window, atrPeriod, geoms);
    const hit = this.tensors.get(key);
    if (hit) return hit;
    const built = yield* buildTensorIter(this.tensorSpec(side, window, atrPeriod, geoms));
    return this.tensors.set(key, built, built.bytes);
  }

  /** How many geometries one tensor may hold under the current budget. */
  batchSize(): number {
    return geometriesPerBatch(this.bars.length, this.tensors.stats().budget);
  }

  triggers(rule: string, window: WindowSpec): Int32Array {
    const key = `${this.label}|${rule}||${window.label}`;
    return this.triggerCache.take(key, () => {
      const mask = ruleMask(rule, this.ctx);
      const wm = this.windowMask(window);
      let count = 0;
      for (let i = 0; i < mask.length; i++) if (mask[i] && wm[i]) count++;
      const arr = new Int32Array(count);
      let w = 0;
      for (let i = 0; i < mask.length; i++) if (mask[i] && wm[i]) arr[w++] = i;
      return { value: arr, bytes: arr.byteLength };
    });
  }

  /** One configuration, with the matched control on by default — it costs milliseconds. */
  run(cfg: Config, controlDraws = 2000, seed = 7): Outcome & { trades: WalkTrade[] } {
    const w = parseWindow(cfg.window);
    const t = this.tensor(cfg.side, w, cfg.atrPeriod, [cfg.geom]);
    const trig = this.triggers(cfg.rule, w);
    const trades: WalkTrade[] = [];
    const geo = this.blockGeometry(w);
    const perf = { research: new BlockAccumulator(geo.research), locked: new BlockAccumulator(geo.locked) };
    const stats = walk(t, 0, trig, cfg.costs, this.lockedFromOrdinal, this.ordinalOfBar, trades, perf);
    const out: Outcome & { trades: WalkTrade[] } = {
      config: cfg,
      stats,
      triggers: trig.length,
      research: finishBlock(perf.research.finish(), geo.research),
      trades,
    };
    if (controlDraws > 0 && stats.n > 3) {
      out.control = matchedControl(
        t, 0, trig, cfg.costs, this.lockedFromOrdinal, this.ordinalOfBar,
        {
          all: stats.n ? stats.netUsd / stats.n : 0,
          research: stats.nResearch ? stats.netResearch / stats.nResearch : 0,
          locked: stats.nLocked ? stats.netLocked / stats.nLocked : 0,
        },
        controlDraws, seed,
      );
    }
    return out;
  }

  /** Total configurations a set of axes describes, without evaluating any of them. */
  static size(axes: SweepAxes): { combos: number; geoms: number; total: number } {
    const keys = templateKeys(axes.rule);
    let combos = 1;
    for (const k of keys) combos *= Math.max(axes.params[k]?.length ?? 0, 0);
    const geoms = axes.stops.length * axes.targets.length * axes.maxBars.length;
    return { combos, geoms, total: axes.sides.length * axes.windows.length * combos * axes.costs.length * geoms };
  }

  /**
   * The whole grid, as a generator that yields progress between chunks.
   *
   * Geometry axes are free — they index one tensor — so widen those first and the rule last, which
   * is the opposite of how a search is usually written. The generator shape is not decoration: the
   * worker drives it and awaits a macrotask between chunks, which is the only way a message asking
   * it to stop can be delivered to a single-threaded worker mid-sweep.
   */
  *sweepIter(axes: SweepAxes): Generator<SweepProgress, SweepResult, void> {
    const t0 = Date.now();
    let tensorMs = 0;
    let tensorCount = 0;
    const rankBy: RankKey = axes.rankBy ?? "residSharpe";
    const keys = templateKeys(axes.rule);
    const combos: Record<string, number>[] = [{}];
    for (const k of keys) {
      const vals = axes.params[k];
      if (!vals?.length) throw new Error(`the rule uses {${k}} but no values were given for it`);
      const next: Record<string, number>[] = [];
      for (const base of combos) for (const v of vals) next.push({ ...base, [k]: v });
      combos.length = 0;
      combos.push(...next);
    }
    const allGeoms: Geometry[] = [];
    for (const stop of axes.stops) for (const target of axes.targets) for (const maxBars of axes.maxBars) allGeoms.push({ stop, target, maxBars });
    if (!allGeoms.length) throw new Error("give at least one stop, target and max hold");

    const total = axes.sides.length * axes.windows.length * combos.length * axes.costs.length * allGeoms.length;
    if (total > MAX_CONFIGURATIONS) {
      throw new Error(
        `${total.toLocaleString()} configurations is past this tool's ${MAX_CONFIGURATIONS.toLocaleString()} ceiling. ` +
          `That is a batch job, not an interactive question — narrow an axis, or run it from research/.`,
      );
    }

    // One tensor never exceeds the cache budget: the geometry axis is cut into batches that do fit.
    const batch = this.batchSize();
    const batches: Geometry[][] = [];
    for (let i = 0; i < allGeoms.length; i += batch) batches.push(allGeoms.slice(i, i + batch));

    const rows: SweepRow[] = [];
    let evaluated = 0;
    let dropped = 0;
    let done = 0;
    // Yield often enough that a cancel lands promptly, rarely enough that the yields are free.
    const CHUNK = 256;
    let sinceYield = 0;

    for (const side of axes.sides) {
      for (const winSpec of axes.windows) {
        const w = parseWindow(winSpec);
        const geo = this.blockGeometry(w);
        for (const geoms of batches) {
          const tb = Date.now();
          const tKey = this.tensorKey(side, w, axes.atrPeriod, geoms);
          const cached = this.tensors.get(tKey) !== undefined;
          if (!cached) tensorCount++;
          const t = yield* this.tensorIter(side, w, axes.atrPeriod, geoms);
          tensorMs += Date.now() - tb;

          for (const params of combos) {
            const rule = keys.length ? fillTemplate(axes.rule, params) : axes.rule;
            const trig = this.triggers(rule, w);
            for (const costs of axes.costs) {
              for (let gi = 0; gi < geoms.length; gi++) {
                evaluated++;
                done++;
                const perf = { research: new BlockAccumulator(geo.research), locked: new BlockAccumulator(geo.locked) };
                walk(t, gi, trig, costs, this.lockedFromOrdinal, this.ordinalOfBar, undefined, perf);
                const research = finishBlock(perf.research.finish(), geo.research);
                if (research.trades < axes.minTrades) {
                  dropped++;
                } else {
                  rows.push({
                    key: `${tKey}|${rule}|${gi}|${costs.fillModel}x${costs.mult}`,
                    rule,
                    params,
                    side,
                    window: w.label,
                    stop: geoms[gi].stop,
                    target: geoms[gi].target,
                    maxBars: geoms[gi].maxBars,
                    costLabel: `${costs.fillModel}${costs.mult === 1 ? "" : ` x${costs.mult}`}`,
                    research,
                    locked: finishBlock(perf.locked.finish(), geo.locked),
                    ref: { side, window: w.label, atrPeriod: axes.atrPeriod, geom: geoms[gi], rule, costs },
                  });
                }
                if (++sinceYield >= CHUNK) {
                  sinceYield = 0;
                  yield { phase: "grid", done, total };
                }
              }
            }
          }
        }
      }
    }
    rows.sort((a, b) => rankValue(b, rankBy) - rankValue(a, rankBy));
    yield { phase: "grid", done, total };
    return {
      rows,
      evaluated,
      dropped,
      minTrades: axes.minTrades,
      rankBy,
      ms: Date.now() - t0,
      tensorMs,
      tensors: tensorCount,
      cache: { tensorBytes: this.tensors.bytes, indicatorBytes: this.ctx.cache.bytes },
    };
  }

  /** Drive `sweepIter` to completion in one go. Convenient for tests and scripts, not for a UI. */
  sweep(axes: SweepAxes, onProgress?: (done: number, total: number) => void): SweepResult {
    const it = this.sweepIter(axes);
    for (;;) {
      const step = it.next();
      if (step.done) return step.value;
      onProgress?.(step.value.done, step.value.total);
    }
  }

  /**
   * Read the locked block, once, for configurations already chosen on research.
   *
   * The shape to look for is a research number that DECAYS. A configuration better on locked than
   * on research is the wrong shape — the holdout is where an edge decays, not where it appears —
   * and has twice been a defect here rather than a result.
   *
   * Everything needed is rebuilt from the row's `ref`, so this does not depend on a tensor still
   * being in the cache: an LRU that evicted the right entry must not change what the holdout says.
   */
  reveal(result: SweepResult, rows: SweepRow[], draws = 4000, seed = 7): RevealRow[] {
    return rows.map((r) => {
      const w = parseWindow(r.ref.window);
      const t = this.tensor(r.ref.side, w, r.ref.atrPeriod, [r.ref.geom]);
      const trig = this.triggers(r.ref.rule, w);
      const ctrl = matchedControl(
        t, 0, trig, r.ref.costs, this.lockedFromOrdinal, this.ordinalOfBar,
        {
          all: (r.research.netUsd + r.locked.netUsd) / Math.max(r.research.trades + r.locked.trades, 1),
          research: r.research.perTrade,
          locked: r.locked.perTrade,
        },
        draws, seed,
      );
      return {
        row: r,
        window: w.label,
        locked: r.locked,
        control: ctrl,
        shape: r.locked.perTrade < r.research.perTrade ? "decays" : "grew-on-locked",
        searched: result.evaluated,
        bonferroni: 0.05 / Math.max(result.evaluated, 1),
      };
    });
  }

  /**
   * Everything the detail view needs for one configuration: the trade list and the daily series.
   *
   * Deliberately separate from the sweep. Materialising a per-session array per cell would make
   * the grid O(cells x sessions) in memory for a number nobody reads until they click a row.
   *
   * The trade list is CUT TO THE RESEARCH BLOCK. The walk necessarily produces the locked block's
   * trades too — the no-overlap scan cannot skip them without changing which research trades are
   * taken — but a blotter, a monthly table or an exported CSV containing them is a holdout read,
   * and `reveal` is the only sanctioned one.
   */
  detail(ref: ConfigRef): {
    trades: WalkTrade[];
    research: BlockPerf;
    dailyResearch: Float64Array;
    marketResearch: Float64Array;
    /** Session ordinal of every trade, so a UI can bucket by month without the bar array. */
    tradeOrdinals: Int32Array;
    firstMs: number;
    tradeMs: number[];
  } {
    const w = parseWindow(ref.window);
    const t = this.tensor(ref.side, w, ref.atrPeriod, [ref.geom]);
    const trig = this.triggers(ref.rule, w);
    const geo = this.blockGeometry(w);
    const all: WalkTrade[] = [];
    const perf = { research: new BlockAccumulator(geo.research), locked: new BlockAccumulator(geo.locked) };
    walk(t, 0, trig, ref.costs, this.lockedFromOrdinal, this.ordinalOfBar, all, perf);
    const research = finishBlock(perf.research.finish(), geo.research);

    const daily = new Float64Array(geo.research.sessions);
    const trades: WalkTrade[] = [];
    const ordinals: number[] = [];
    const ms: number[] = [];
    for (const tr of all) {
      const o = this.ordinalOfBar[tr.signalBar];
      if (o >= this.lockedFromOrdinal) continue;
      daily[o] += tr.pnl;
      trades.push(tr);
      ordinals.push(o);
      ms.push(this.bars[tr.signalBar].t);
    }
    return {
      trades,
      research,
      dailyResearch: daily,
      marketResearch: geo.research.market,
      tradeOrdinals: Int32Array.from(ordinals),
      firstMs: this.bars[0]?.t ?? 0,
      tradeMs: ms,
    };
  }
}

/** Rank value for a row. Reads the research block only, by construction of `RankKey`. */
export function rankValue(r: SweepRow, key: RankKey): number {
  const v = r.research[key];
  return Number.isFinite(v) ? v : -Infinity;
}

export interface RevealRow {
  row: SweepRow;
  window: string;
  locked: BlockPerf;
  control: ControlResult;
  /** `grew-on-locked` is a defect flag, not a result. */
  shape: "decays" | "grew-on-locked";
  searched: number;
  bonferroni: number;
}

export { REASON_NAME };

/**
 * Resample 1-minute bars to a research timeframe, anchored to EXCHANGE-LOCAL midnight.
 *
 * Anchoring matters: bucketing on UTC would put a 30-minute bar across the 09:30 open instead of
 * starting at it, so every session-relative statistic would be measured on straddled bars. This
 * mirrors what `scripts/quant-ingest.ts` does at ingest time, for the case where the file on disk
 * is 1-minute and the timeframe is chosen in the UI.
 */
export function resampleBars(src: Bar[], minutes: number, inst: Instrument): Bar[] {
  if (minutes <= 1 || src.length === 0) return src;
  const clock = clockFor(src, inst.tz);
  const out: Bar[] = [];
  let key = NaN;
  let cur: Bar | null = null;
  for (let i = 0; i < src.length; i++) {
    const k = clock.dayIndex[i] * 1440 + Math.floor(clock.minuteOfDay[i] / minutes) * minutes;
    const b = src[i];
    if (k !== key) {
      if (cur) out.push(cur);
      key = k;
      cur = { t: b.t, o: b.o, h: b.h, l: b.l, c: b.c, v: b.v };
    } else if (cur) {
      cur.h = Math.max(cur.h, b.h);
      cur.l = Math.min(cur.l, b.l);
      cur.c = b.c;
      cur.v += b.v;
    }
  }
  if (cur) out.push(cur);
  return out;
}
