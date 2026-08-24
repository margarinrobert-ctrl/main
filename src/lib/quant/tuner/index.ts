/**
 * The tuner's public surface: load bars once, then turn knobs.
 *
 * `TunerSession` owns the three things that are expensive to build and cheap to reuse — the bar
 * set, the memoised indicator arrays, and the exit tensors — so a UI can hold one and every
 * subsequent question is a lookup. See `tensor.ts` for why that is possible at all.
 *
 * Two guardrails are structural rather than advisory, and neither has an off switch:
 *
 *   * `sweep` returns RESEARCH-block statistics. The locked block is computed but returned only
 *     from `reveal`, which states the multiplicity first and flags any configuration that is
 *     BETTER on locked than on research as the wrong shape. Ranking on anything that touches the
 *     holdout puts the holdout inside the selection; `CLAUDE.md` records that happening twice,
 *     and both times the result looked better than it was.
 *   * every result carries the count of configurations evaluated to produce it, because a grid
 *     this cheap makes multiplicity the binding constraint before anything else.
 */
import { clockFor, sessionIndex } from "../clock";
import type { Bar, Instrument } from "../types";
import { get, makeContext, type IndicatorContext } from "./indicators";
import { fillTemplate, ruleMask, templateKeys } from "./rule";
import { costHurdle, exitSplit, medianBarTicks, verdict, type CostHurdle, type EdgeVerdict, type ExitSplit } from "./edge";
import {
  buildTensor,
  DEFAULT_COSTS,
  matchedControl,
  REASON_NAME,
  walk,
  type ControlResult,
  type CostModel,
  type ExitTensor,
  type Geometry,
  type WalkStats,
  type WalkTrade,
} from "./tensor";

export * from "./tensor";
export { costHurdle, exitSplit, medianBarTicks, verdict } from "./edge";
export type { CostHurdle, EdgeVerdict, ExitSplit } from "./edge";
export { catalogue, type CatalogueEntry } from "./indicators";
export { RuleError, templateKeys } from "./rule";

/** The research/locked split: the first 65% of SESSIONS, matching the Python research layer. */
export const RESEARCH_FRACTION = 0.65;

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
  /** Present only when the caller asked for it — sweeps do not compute controls for every cell. */
  control?: ControlResult;
}

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
};

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
  n: number;
  perTrade: number;
  netUsd: number;
  winPct: number;
  profitFactor: number;
  maxDrawdown: number;
  tStat: number;
  stopPct: number;
  /** Research block — the only block a sweep ranks or displays. */
  nResearch: number;
  perTradeResearch: number;
  winPctResearch: number;
  /** Locked block, carried for `reveal` and deliberately not surfaced by the sweep UI. */
  lockedInternal: { n: number; perTrade: number; netUsd: number; winPct: number };
  /** Indices back into the session's tensor cache, so `reveal` need not recompute the walk. */
  ref: { tensorKey: string; gi: number; triggerKey: string; costs: CostModel };
}

export interface SweepResult {
  rows: SweepRow[];
  /** Configurations evaluated, INCLUDING those dropped for too few trades. */
  evaluated: number;
  dropped: number;
  minTrades: number;
  ms: number;
  tensorMs: number;
}

const pf = (w: number, l: number) => (l > 0 ? w / l : w > 0 ? Infinity : 0);

function tStat(s: WalkStats): number {
  if (s.n < 2) return 0;
  const mean = s.netUsd / s.n;
  const v = s.sumSq / s.n - mean * mean;
  return v > 0 ? mean / Math.sqrt(v / s.n) : 0;
}

export class TunerSession {
  readonly ctx: IndicatorContext;
  readonly sessionOfBar: Int32Array;
  readonly sessionCount: number;
  readonly lockedFromSession: number;
  private readonly tensors = new Map<string, ExitTensor>();
  private readonly triggerCache = new Map<string, Int32Array>();
  private readonly maskCache = new Map<string, Uint8Array>();

  constructor(
    readonly bars: Bar[],
    readonly inst: Instrument,
    readonly label = "bars",
  ) {
    const clock = clockFor(bars, inst.tz);
    this.sessionOfBar = sessionIndex(clock, inst.session[0]);
    const unique = new Set<number>();
    for (let i = 0; i < this.sessionOfBar.length; i++) unique.add(this.sessionOfBar[i]);
    const sorted = Array.from(unique).sort((a, b) => a - b);
    this.sessionCount = sorted.length;
    // Sessions are dense integers from sessionIndex, but do not assume it: map through the sorted
    // list so the cut is the 65th percentile of SESSIONS however they are numbered.
    const cutSession = sorted[Math.floor(RESEARCH_FRACTION * sorted.length)] ?? Infinity;
    this.lockedFromSession = cutSession;
    this.ctx = makeContext(bars, this.sessionOfBar, clock.minuteOfDay, label);
  }

  /** Median bar range in ticks — the scale that makes the cost hurdle interpretable. */
  medianBarTicks(): number {
    if (this._medBar === undefined) {
      this._medBar = medianBarTicks(
        this.bars.map((b) => b.h),
        this.bars.map((b) => b.l),
        this.inst.tickSize,
      );
    }
    return this._medBar;
  }

  private _medBar: number | undefined;

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

  tensorKey(side: 1 | -1, window: WindowSpec, atrPeriod: number, geoms: Geometry[]): string {
    const g = geoms.map((x) => `${x.stop}/${x.target}/${x.maxBars}`).join(";");
    return `${side}|${window.label}|${atrPeriod}|${g}`;
  }

  tensor(side: 1 | -1, window: WindowSpec, atrPeriod: number, geoms: Geometry[]): ExitTensor {
    const key = this.tensorKey(side, window, atrPeriod, geoms);
    const hit = this.tensors.get(key);
    if (hit) return hit;
    const t = buildTensor({
      bars: this.bars,
      inst: this.inst,
      side,
      geoms,
      atrPeriod,
      atr: this.atr(atrPeriod),
      window: window.minutes,
      eligible: this.windowMask(window),
    });
    this.tensors.set(key, t);
    return t;
  }

  triggers(rule: string, window: WindowSpec): Int32Array {
    const key = `${rule}||${window.label}`;
    const hit = this.triggerCache.get(key);
    if (hit) return hit;
    const mask = ruleMask(rule, this.ctx);
    const wm = this.windowMask(window);
    const out: number[] = [];
    for (let i = 0; i < mask.length; i++) if (mask[i] && wm[i]) out.push(i);
    const arr = Int32Array.from(out);
    this.triggerCache.set(key, arr);
    return arr;
  }

  /** One configuration, with the matched control on by default — it costs milliseconds. */
  run(cfg: Config, controlDraws = 2000, seed = 7): Outcome & { trades: WalkTrade[] } {
    const w = parseWindow(cfg.window);
    const t = this.tensor(cfg.side, w, cfg.atrPeriod, [cfg.geom]);
    const trig = this.triggers(cfg.rule, w);
    const trades: WalkTrade[] = [];
    const stats = walk(t, 0, trig, cfg.costs, this.lockedFromSession, this.sessionOfBar, trades);
    const out: Outcome & { trades: WalkTrade[] } = { config: cfg, stats, triggers: trig.length, trades };
    if (controlDraws > 0 && stats.n > 3) {
      out.control = matchedControl(
        t, 0, trig, cfg.costs, this.lockedFromSession, this.sessionOfBar,
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

  /**
   * The whole grid. Geometry axes are free — they index one tensor — so widen those first and the
   * rule last, which is the opposite of how a search is usually written.
   */
  sweep(axes: SweepAxes, onProgress?: (done: number, total: number) => void): SweepResult {
    const t0 = Date.now();
    let tensorMs = 0;
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
    const geoms: Geometry[] = [];
    for (const stop of axes.stops) for (const target of axes.targets) for (const maxBars of axes.maxBars) geoms.push({ stop, target, maxBars });

    const rows: SweepRow[] = [];
    let evaluated = 0;
    let dropped = 0;
    const total = axes.sides.length * axes.windows.length * combos.length * axes.costs.length * geoms.length;
    let done = 0;

    for (const side of axes.sides) {
      for (const winSpec of axes.windows) {
        const w = parseWindow(winSpec);
        const tb = Date.now();
        const t = this.tensor(side, w, axes.atrPeriod, geoms);
        tensorMs += Date.now() - tb;
        const tKey = this.tensorKey(side, w, axes.atrPeriod, geoms);
        for (const params of combos) {
          const rule = keys.length ? fillTemplate(axes.rule, params) : axes.rule;
          const trig = this.triggers(rule, w);
          for (const costs of axes.costs) {
            for (let gi = 0; gi < geoms.length; gi++) {
              evaluated++;
              const s = walk(t, gi, trig, costs, this.lockedFromSession, this.sessionOfBar);
              done++;
              if (s.n < axes.minTrades) {
                dropped++;
                continue;
              }
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
                n: s.n,
                perTrade: s.netUsd / s.n,
                netUsd: s.netUsd,
                winPct: (100 * s.wins) / s.n,
                profitFactor: pf(s.grossWin, s.grossLoss),
                maxDrawdown: s.maxDrawdown,
                tStat: tStat(s),
                stopPct: (100 * s.byReason[0]) / s.n,
                nResearch: s.nResearch,
                perTradeResearch: s.nResearch ? s.netResearch / s.nResearch : 0,
                winPctResearch: s.nResearch ? (100 * s.winsResearch) / s.nResearch : 0,
                lockedInternal: {
                  n: s.nLocked,
                  perTrade: s.nLocked ? s.netLocked / s.nLocked : 0,
                  netUsd: s.netLocked,
                  winPct: s.nLocked ? (100 * s.winsLocked) / s.nLocked : 0,
                },
                ref: { tensorKey: tKey, gi, triggerKey: `${rule}||${w.label}`, costs },
              });
            }
          }
          onProgress?.(done, total);
        }
      }
    }
    rows.sort((a, b) => b.perTradeResearch - a.perTradeResearch);
    return { rows, evaluated, dropped, minTrades: axes.minTrades, ms: Date.now() - t0, tensorMs };
  }

  /**
   * Read the locked block, once, for configurations already chosen on research.
   *
   * The shape to look for is a research number that DECAYS. A configuration better on locked than
   * on research is the wrong shape — the holdout is where an edge decays, not where it appears —
   * and has twice been a defect here rather than a result.
   */
  reveal(result: SweepResult, rows: SweepRow[], draws = 4000, seed = 7): RevealRow[] {
    return rows.map((r) => {
      const [sideStr, winLabel, atrStr] = r.ref.tensorKey.split("|");
      void sideStr;
      void atrStr;
      const w = parseWindow(winLabel);
      const t = this.tensors.get(r.ref.tensorKey);
      const trig = this.triggerCache.get(r.ref.triggerKey);
      if (!t || !trig) throw new Error("reveal must be called on the session that produced the sweep");
      // Re-walk to recover the full statistics the sweep row does not carry -- the exit split in
      // particular, which is what separates a barrier edge from a direction bet.
      const full = walk(t, r.ref.gi, trig, r.ref.costs, this.lockedFromSession, this.sessionOfBar);
      const ctrl = matchedControl(
        t, r.ref.gi, trig, r.ref.costs, this.lockedFromSession, this.sessionOfBar,
        {
          all: r.perTrade,
          research: r.perTradeResearch,
          locked: r.lockedInternal.perTrade,
          winPct: full.n ? (100 * full.wins) / full.n : 0,
        },
        draws, seed,
      );
      const hurdle = costHurdle(this.inst, this.medianBarTicks());
      return {
        hurdle,
        exits: exitSplit(full),
        edge: verdict(full, ctrl, result.evaluated, hurdle),
        row: r,
        window: w.label,
        locked: r.lockedInternal,
        control: ctrl,
        shape: r.lockedInternal.perTrade < r.perTradeResearch ? "decays" : "grew-on-locked",
        searched: result.evaluated,
        bonferroni: 0.05 / Math.max(result.evaluated, 1),
      };
    });
  }
}

export interface RevealRow {
  /** The cost floor this configuration has to clear before it earns anything. */
  hurdle: CostHurdle;
  /** Where the trades ended — a barrier edge and a direction bet look identical without this. */
  exits: ExitSplit[];
  /** Win rate against its own geometry's base rate, plus the flags that survived. */
  edge: EdgeVerdict;
  row: SweepRow;
  window: string;
  locked: { n: number; perTrade: number; netUsd: number; winPct: number };
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
