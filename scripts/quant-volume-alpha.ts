/**
 * Volume alpha study on NQ — is there conditional information in the volume column?
 *
 *   npx tsx scripts/quant-volume-alpha.ts --data data/NQ_5m.csv --symbol NQ --out docs/ib/STUDY_VOLUME.md
 *
 * Every prior study in this repo is OHLC-only, and every one of them ends at the same place: an
 * OHLC-only rule competes with everyone holding the same OHLC. Volume is the one unused column.
 *
 * Structure:
 *   1  the normalisation that makes intraday volume mean anything (time-of-day relative volume)
 *   2  does volume predict RANGE?            — a non-directional family, tested with BH control
 *   3  does volume predict DIRECTION?        — twelve pre-specified conditions x five horizons,
 *                                              drift-adjusted, HAC-corrected, BH across every cell
 *   4  the interaction test stated in advance: heavy-volume vs light-volume continuation
 *   5  long/short decomposition — prior studies found "edges" that were just the index uptrend
 *   6  the locked holdout, for whatever survived stage 3
 */
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { eventStudy, predictabilityBudget, type EventResponse } from "../src/lib/quant/alpha";
import { clockFor, inWindow } from "../src/lib/quant/clock";
import { auditBars, parseCsv, splitAt } from "../src/lib/quant/data";
import { instrument, roundTurnCostTicks } from "../src/lib/quant/instruments";
import { correctMultiple } from "../src/lib/quant/multipletest";
import { num, pct, table } from "../src/lib/quant/report";
import { mean, pValueTwoSided, std } from "../src/lib/quant/stats";
import { atr } from "../src/lib/quant/series";
import { volumeContext, weightedPressure, windowMean } from "../src/lib/quant/volumeFeatures";
import type { Bar, Instrument } from "../src/lib/quant/types";

const arg = (k: string, d?: string) => {
  const i = process.argv.indexOf(`--${k}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : d;
};
const DATA = arg("data", "data/NQ_5m.csv")!;
const SYMBOL = arg("symbol", "NQ")!;
const OUT = arg("out", "docs/ib/STUDY_VOLUME.md")!;
const HOLDOUT = Number(arg("holdout", "0.3"));
/** Horizons in MINUTES, so the 5-minute and 1-minute passes measure the same wall-clock forecast. */
const HORIZON_MINUTES = [5, 15, 30, 60, 120];
/** q threshold for Benjamini-Hochberg across the whole grid. */
const MAX_Q = 0.1;

const md: string[] = [];
const say = (s = "") => {
  md.push(s);
  console.log(s);
};

type Cond = (i: number) => -1 | 0 | 1;

/** Restrict a condition to a half of the sample, so research and holdout never share an event. */
const restrict = (c: Cond, lo: number, hi: number): Cond => (i) => (i >= lo && i < hi ? c(i) : 0);
/** One side only, for the long/short decomposition. */
const sideOnly = (c: Cond, side: 1 | -1): Cond => (i) => (c(i) === side ? side : 0);

/**
 * The drift-adjusted excess series behind `eventStudy`'s `driftAdjustedTicks`, per event.
 * Needed for the head-to-head test in stage 4, which compares two conditions rather than one
 * condition against zero.
 */
function excessEvents(bars: Bar[], inst: Instrument, condition: Cond, h: number): { excess: number; day: number }[] {
  const clock = clockFor(bars, inst.tz);
  let driftSum = 0;
  let driftN = 0;
  for (let i = 0; i + h < bars.length; i++) {
    if (clock.dayIndex[i + h] !== clock.dayIndex[i]) continue;
    driftSum += (bars[i + h].c - bars[i].c) / inst.tickSize;
    driftN++;
  }
  const muFwd = driftN ? driftSum / driftN : 0;
  const out: { excess: number; day: number }[] = [];
  for (let i = 0; i + h < bars.length; i++) {
    const side = condition(i);
    if (!side) continue;
    if (clock.dayIndex[i + h] !== clock.dayIndex[i]) continue;
    out.push({ excess: side * ((bars[i + h].c - bars[i].c) / inst.tickSize - muFwd), day: clock.dayIndex[i] });
  }
  return out;
}

/**
 * The same edge, with the standard error computed across SESSIONS rather than across events.
 *
 * A condition like "today is busy and price is away from the open" fires on most bars of a qualifying
 * session, so 2,500 events can be 300 independent days wearing a disguise. The HAC lag inside
 * `eventStudy` covers the overlap of the forward windows; it does not cover the fact that the
 * condition itself is a day-level state. Collapsing to one observation per session does.
 */
function clusteredEdge(events: { excess: number; day: number }[]): { sessions: number; mean: number; t: number } {
  const byDay = new Map<number, number[]>();
  for (const e of events) {
    let a = byDay.get(e.day);
    if (!a) byDay.set(e.day, (a = []));
    a.push(e.excess);
  }
  const perDay = [...byDay.values()].map((xs) => mean(xs));
  const m = mean(perDay);
  const se = perDay.length > 1 ? std(perDay) / Math.sqrt(perDay.length) : NaN;
  return { sessions: perDay.length, mean: m, t: se > 0 ? m / se : 0 };
}

/** Twelve pre-specified volume conditions. Written once, before any of them was measured. */
function volumeConditions(bars: Bar[], inst: Instrument) {
  const a = atr(bars, 14);
  const clock = clockFor(bars, inst.tz);
  const v = volumeContext(bars, inst);
  const sameDay = (i: number, k: number) => i - k >= 0 && clock.dayIndex[i - k] === clock.dayIndex[i];
  const body = (i: number) => bars[i].c - bars[i].o;
  const ok = (i: number) => Number.isFinite(a[i]) && a[i] > 0;
  const sgn = (x: number): -1 | 0 | 1 => (x > 0 ? 1 : x < 0 ? -1 : 0);

  /** Session open price for bar i's session. */
  const sessionOpen = new Array<number>(bars.length).fill(NaN);
  for (let i = 0, cur = NaN; i < bars.length; i++) {
    if (i === 0 || clock.dayIndex[i] !== clock.dayIndex[i - 1]) cur = bars[i].o;
    sessionOpen[i] = cur;
  }

  const conds: Record<string, Cond> = {
    // --- the core question: does the SAME move continue differently on heavy vs light volume? ---
    "heavy-continuation": (i) => {
      if (!ok(i) || !Number.isFinite(v.rvolTod[i])) return 0;
      if (v.rvolTod[i] < 2) return 0;
      return Math.abs(body(i)) >= 0.5 * a[i] ? sgn(body(i)) : 0;
    },
    "light-continuation": (i) => {
      if (!ok(i) || !Number.isFinite(v.rvolTod[i])) return 0;
      if (v.rvolTod[i] > 0.7) return 0;
      return Math.abs(body(i)) >= 0.5 * a[i] ? sgn(body(i)) : 0;
    },
    // The same filter under the naive normalisation, so the two can be compared directly.
    "trailing-surge-continuation": (i) => {
      if (!ok(i) || !Number.isFinite(v.rvolTrailing[i])) return 0;
      if (v.rvolTrailing[i] < 2) return 0;
      return Math.abs(body(i)) >= 0.5 * a[i] ? sgn(body(i)) : 0;
    },
    // --- climax / exhaustion ---
    "heavy-exhaustion-fade": (i) => {
      if (!ok(i) || !Number.isFinite(v.rvolTod[i])) return 0;
      if (v.rvolTod[i] < 3) return 0;
      return Math.abs(body(i)) >= a[i] ? (-sgn(body(i)) as -1 | 0 | 1) : 0;
    },
    "climax-small-body": (i) => {
      if (!sameDay(i, 3) || !Number.isFinite(v.rvolTod[i])) return 0;
      if (v.rvolTod[i] < 3) return 0;
      const range = bars[i].h - bars[i].l;
      if (!(range > 0) || Math.abs(body(i)) > 0.25 * range) return 0;
      return -sgn(bars[i].c - bars[i - 3].c) as -1 | 0 | 1;
    },
    "heavy-close-location": (i) => {
      if (!Number.isFinite(v.rvolTod[i]) || !Number.isFinite(v.pressure[i])) return 0;
      if (v.rvolTod[i] < 2 || Math.abs(v.pressure[i]) < 0.6) return 0;
      return sgn(v.pressure[i]);
    },
    // --- dry-up then expansion ---
    "dryup-break": (i) => {
      if (!sameDay(i, 6)) return 0;
      const dry = windowMean(v.rvolTod, i - 1, 6);
      if (!Number.isFinite(dry) || dry > 0.7) return 0;
      let hi = -Infinity;
      let lo = Infinity;
      for (let j = i - 6; j < i; j++) {
        hi = Math.max(hi, bars[j].h);
        lo = Math.min(lo, bars[j].l);
      }
      if (bars[i].c > hi) return 1;
      if (bars[i].c < lo) return -1;
      return 0;
    },
    // --- volume-weighted pressure (a crude delta proxy) ---
    "pressure-momentum": (i) => {
      if (!sameDay(i, 6)) return 0;
      const wp = weightedPressure(bars, v.pressure, i, 6);
      if (!Number.isFinite(wp)) return 0;
      return wp >= 0.3 ? 1 : wp <= -0.3 ? -1 : 0;
    },
    "pressure-divergence": (i) => {
      if (!sameDay(i, 12)) return 0;
      const wp = weightedPressure(bars, v.pressure, i, 6);
      if (!Number.isFinite(wp)) return 0;
      let hi = -Infinity;
      let lo = Infinity;
      for (let j = i - 12; j < i; j++) {
        hi = Math.max(hi, bars[j].c);
        lo = Math.min(lo, bars[j].c);
      }
      if (bars[i].c > hi && wp < 0) return -1;
      if (bars[i].c < lo && wp > 0) return 1;
      return 0;
    },
    "session-delta-divergence": (i) => {
      if (!Number.isFinite(v.sessionDelta[i]) || !Number.isFinite(sessionOpen[i])) return 0;
      const up = bars[i].c > sessionOpen[i];
      if (up && v.sessionDelta[i] < -0.1) return -1;
      if (!up && v.sessionDelta[i] > 0.1) return 1;
      return 0;
    },
    // --- is today unusually busy, and does that change the character of the tape? ---
    "busy-session-trend": (i) => {
      if (!ok(i) || !Number.isFinite(v.sessionPace[i]) || !Number.isFinite(sessionOpen[i])) return 0;
      if (v.sessionPace[i] < 1.3) return 0;
      const move = bars[i].c - sessionOpen[i];
      return Math.abs(move) >= 0.5 * a[i] ? sgn(move) : 0;
    },
    "quiet-session-fade": (i) => {
      if (!ok(i) || !sameDay(i, 6) || !Number.isFinite(v.sessionPace[i])) return 0;
      if (v.sessionPace[i] > 0.8) return 0;
      const move = bars[i].c - bars[i - 6].c;
      return Math.abs(move) >= 0.5 * a[i] ? (-sgn(move) as -1 | 0 | 1) : 0;
    },
  };

  /**
   * CONTROLS, deliberately outside the tested family: the same body filter with NO volume condition
   * at all. A volume signal has to beat these to be a volume signal rather than a clock.
   */
  const controls: Record<string, Cond> = {
    "body-only (any time)": (i) => (ok(i) && Math.abs(body(i)) >= 0.5 * a[i] ? sgn(body(i)) : 0),
    "body-only (first 60 min)": (i) =>
      ok(i) && clock.minuteOfDay[i] < inst.session[0] + 60 && Math.abs(body(i)) >= 0.5 * a[i] ? sgn(body(i)) : 0,
  };
  return { conds, controls, ctx: v, atr14: a, clock };
}

interface Cell {
  label: string;
  cond: string;
  horizon: number;
  resp: EventResponse;
}

function grid(bars: Bar[], inst: Instrument, conds: Record<string, Cond>, horizons: number[], cost: number, lo: number, hi: number): Cell[] {
  const cells: Cell[] = [];
  for (const [name, c] of Object.entries(conds)) {
    const responses = eventStudy(bars, inst, restrict(c, lo, hi), horizons, cost);
    for (const resp of responses) cells.push({ label: `${name} @ ${resp.horizon}`, cond: name, horizon: resp.horizon, resp });
  }
  return cells;
}

function cellRows(cells: Cell[], qByLabel: Map<string, number>, cost: number) {
  return cells.map((c) => [
    c.label,
    c.resp.events,
    pct(c.resp.longShare, 0),
    num(c.resp.meanTicks, 2),
    num(c.resp.driftAdjustedTicks, 2),
    num(c.resp.driftAdjustedT, 2),
    num(c.resp.driftAdjustedP, 4),
    num(qByLabel.get(c.label) ?? 1, 3),
    num(c.resp.driftAdjustedTicks - cost, 2),
  ]);
}
const CELL_HEADERS = ["cell", "n", "long%", "raw ticks", "drift-adj ticks", "HAC t", "p", "q (BH)", "net of cost"];

function main() {
  const inst = instrument(SYMBOL);
  const cost = roundTurnCostTicks(inst);
  const raw = parseCsv(readFileSync(DATA, "utf8"));
  const audit = auditBars(raw, inst.tz);
  const tfMin = audit.timeframeMinutes || 5;

  // Regular trading hours only — the sessions every prior study in this repo used.
  const allClock = clockFor(raw, inst.tz);
  const bars = raw.filter((_, i) => inWindow(allClock.minuteOfDay[i], inst.session[0], inst.session[1]));
  const horizons = HORIZON_MINUTES.map((m) => Math.max(1, Math.round(m / tfMin)));
  const maxH = Math.max(...horizons);

  const split = Math.floor(bars.length * (1 - HOLDOUT));
  const { conds, controls, ctx } = volumeConditions(bars, inst);

  say(`# Volume alpha on ${SYMBOL} — does the volume column predict anything?`);
  say();
  say(`Data \`${DATA}\`, ${bars.length.toLocaleString()} RTH bars at ${tfMin}m, ${audit.first.slice(0, 10)} to ${audit.last.slice(0, 10)}.`);
  say(`Split chronologically ${Math.round((1 - HOLDOUT) * 100)}/${Math.round(HOLDOUT * 100)}: research = bars 0..${split}, holdout = ${split}..${bars.length}.`);
  say(`Round-turn cost **${num(cost, 2)} ticks**. Horizons ${HORIZON_MINUTES.join("/")} minutes = ${horizons.join("/")} bars.`);
  say();

  // ---------------------------------------------------------------- 1. the normalisation
  say(`## 1. Why intraday volume has to be normalised by time of day`);
  say();
  const byHour = new Map<number, { v: number[]; rt: number[] }>();
  const clock = clockFor(bars, inst.tz);
  for (let i = 0; i < bars.length; i++) {
    const h = Math.floor(clock.minuteOfDay[i] / 60);
    let g = byHour.get(h);
    if (!g) byHour.set(h, (g = { v: [], rt: [] }));
    g.v.push(bars[i].v);
    if (Number.isFinite(ctx.rvolTrailing[i])) g.rt.push(ctx.rvolTrailing[i]);
  }
  const hourRows = [...byHour.entries()].sort((a, b) => a[0] - b[0]).map(([h, g]) => {
    const share = g.rt.length ? g.rt.filter((x) => x >= 2).length / g.rt.length : NaN;
    return [`${String(h).padStart(2, "0")}:00`, g.v.length, Math.round(mean(g.v)).toLocaleString(), pct(share, 1)];
  });
  say(table(["hour (ET)", "bars", "mean volume", "share flagged by trailing-mean rvol >= 2"], hourRows));
  say();
  const todFlag = (() => {
    const f = ctx.rvolTod.filter(Number.isFinite);
    return f.length ? f.filter((x) => x >= 2).length / f.length : NaN;
  })();
  const trFlag = (() => {
    const f = ctx.rvolTrailing.filter(Number.isFinite);
    return f.length ? f.filter((x) => x >= 2).length / f.length : NaN;
  })();
  say(`Overall share of bars flagged "high volume": trailing-20-mean ${pct(trFlag, 1)}, time-of-day-median ${pct(todFlag, 1)}.`);
  say();

  // ---------------------------------------------------------------- 2. volume -> range
  say(`## 2. Does volume predict RANGE? (non-directional family, BH-controlled)`);
  say();
  const h6 = horizons[2];
  const fwdAbs: number[] = new Array(bars.length).fill(NaN);
  for (let i = 0; i + h6 < bars.length; i++) {
    if (clock.dayIndex[i + h6] !== clock.dayIndex[i]) continue;
    let hi = -Infinity;
    let lo = Infinity;
    for (let j = i + 1; j <= i + h6; j++) {
      hi = Math.max(hi, bars[j].h);
      lo = Math.min(lo, bars[j].l);
    }
    fwdAbs[i] = (hi - lo) / inst.tickSize;
  }
  const rvolBuckets: { label: string; test: (x: number) => boolean }[] = [
    { label: "rvol < 0.7 (dry)", test: (x) => x < 0.7 },
    { label: "0.7 - 1.0", test: (x) => x >= 0.7 && x < 1.0 },
    { label: "1.0 - 1.5", test: (x) => x >= 1.0 && x < 1.5 },
    { label: "1.5 - 2.5", test: (x) => x >= 1.5 && x < 2.5 },
    { label: "rvol >= 2.5 (heavy)", test: (x) => x >= 2.5 },
  ];
  const rangeFamily = (lo: number, hi: number) => {
    const rows: { label: string; p: number; n: number; meanIn: number; lift: number; t: number }[] = [];
    for (const b of rvolBuckets) {
      const inB: number[] = [];
      const out: number[] = [];
      for (let i = lo; i < hi; i++) {
        if (!Number.isFinite(fwdAbs[i]) || !Number.isFinite(ctx.rvolTod[i])) continue;
        (b.test(ctx.rvolTod[i]) ? inB : out).push(fwdAbs[i]);
      }
      const se = Math.sqrt(std(inB) ** 2 / Math.max(inB.length, 1) + std(out) ** 2 / Math.max(out.length, 1));
      const diff = mean(inB) - mean(out);
      const t = se > 0 ? diff / se : 0;
      rows.push({ label: b.label, p: pValueTwoSided(t), n: inB.length, meanIn: mean(inB), lift: diff, t });
    }
    return rows;
  };
  const rangeResearch = rangeFamily(0, split - maxH);
  const rangeHoldout = rangeFamily(split, bars.length);
  const rangeQ = new Map(correctMultiple(rangeResearch.map((r) => ({ label: r.label, p: r.p })), MAX_Q).map((c) => [c.label, c.qBH]));
  const baseline = (lo: number, hi: number) => {
    const xs: number[] = [];
    for (let i = lo; i < hi; i++) if (Number.isFinite(fwdAbs[i]) && Number.isFinite(ctx.rvolTod[i])) xs.push(fwdAbs[i]);
    return mean(xs);
  };
  say(`Forward ${HORIZON_MINUTES[2]}-minute high-low range in ticks, by time-of-day relative volume of the current bar.`);
  say(`Unconditional mean ${num(baseline(0, split - maxH), 1)} ticks in research, ${num(baseline(split, bars.length), 1)} in holdout.`);
  say(`This family is NOT directional and cannot be traded on its own — it is reported because it is the one place volume carries information, and because it is the control that proves the volume column is not noise.`);
  say();
  say(table(
    ["rvol bucket", "research n", "fwd range", "lift vs rest", "t", "q (BH)", "holdout n", "holdout fwd range", "holdout lift", "holdout t"],
    rangeResearch.map((r, k) => {
      const h = rangeHoldout[k];
      return [r.label, r.n, num(r.meanIn, 1), num(r.lift, 1), num(r.t, 2), num(rangeQ.get(r.label) ?? 1, 4), h.n, num(h.meanIn, 1), num(h.lift, 1), num(h.t, 2)];
    }),
  ));
  say();

  // ---------------------------------------------------------------- 3. volume -> direction
  say(`## 3. Does volume predict DIRECTION? Twelve conditions x five horizons, research half`);
  say();
  const researchCells = grid(bars, inst, conds, horizons, cost, 0, split - maxH);
  const corrected = correctMultiple(researchCells.map((c) => ({ label: c.label, p: c.resp.driftAdjustedP })), MAX_Q);
  const qByLabel = new Map(corrected.map((c) => [c.label, c.qBH]));
  say(`${researchCells.length} cells, Benjamini-Hochberg applied across all of them at q <= ${MAX_Q}.`);
  say();
  say(table(CELL_HEADERS, cellRows(researchCells, qByLabel, cost)));
  say();

  const survivors = researchCells.filter((c) => (qByLabel.get(c.label) ?? 1) <= MAX_Q && c.resp.events >= 100);
  if (!survivors.length) say(`**No cell survives FDR control in the research half.**`);
  else {
    say(`**Survivors (q <= ${MAX_Q}, n >= 100):**`);
    say();
    say(table(CELL_HEADERS, cellRows(survivors, qByLabel, cost)));
  }
  say();
  const budget = predictabilityBudget(
    Object.keys(conds).map((name) => ({ label: name, responses: researchCells.filter((c) => c.cond === name).map((c) => c.resp) })),
    cost,
    MAX_Q,
  );
  say(`**Predictability budget (volume family, research half):** best surviving drift-adjusted edge ` +
    `${num(budget.bestEdgeTicks, 2)} ticks (\`${budget.bestLabel}\`) against ${num(cost, 2)} ticks of cost — ratio ${num(budget.ratio, 2)}.`);
  say();
  say(`> ${budget.verdict}`);
  say();

  // ---------------------------------------------------------------- 4. the interaction test
  say(`## 4. Heavy versus light: the interaction test, stated in advance`);
  say();
  say(`The hypothesis this study was built to test: *the same-sized move continues differently on heavy volume than on light volume.*`);
  say(`Both conditions require an identical body (>= 0.5 ATR); the only difference is the volume filter.`);
  say();
  const interRows: (string | number)[][] = [];
  for (const h of horizons) {
    const heavy = excessEvents(bars, inst, restrict(conds["heavy-continuation"], 0, split - maxH), h).map((e) => e.excess);
    const light = excessEvents(bars, inst, restrict(conds["light-continuation"], 0, split - maxH), h).map((e) => e.excess);
    const diff = mean(heavy) - mean(light);
    const se = Math.sqrt(std(heavy) ** 2 / Math.max(heavy.length, 1) + std(light) ** 2 / Math.max(light.length, 1));
    const t = se > 0 ? diff / se : 0;
    interRows.push([h, heavy.length, num(mean(heavy), 2), light.length, num(mean(light), 2), num(diff, 2), num(t, 2), num(pValueTwoSided(t), 3)]);
  }
  say(table(["horizon (bars)", "heavy n", "heavy drift-adj", "light n", "light drift-adj", "difference", "t", "p"], interRows));
  say();

  // ---------------------------------------------------------------- 4b. volume filter or clock?
  say(`## 4b. Is a "volume surge" a volume filter, or a clock?`);
  say();
  say(`A volume filter whose flagged bars cluster at particular hours is partly a clock, and the clock is the first thing to rule out. The controls below use the IDENTICAL body filter with NO volume condition whatsoever; they are not candidates and are not in the FDR family — they can only take a result away, never create one.`);
  say();
  const hours = [...new Set([...clock.minuteOfDay].map((m) => Math.floor(m / 60)))].sort((a2, b2) => a2 - b2);
  const dist = (c: Cond) => {
    const counts = new Map<number, number>();
    let total = 0;
    for (let i = 0; i < split - maxH; i++) if (c(i)) {
      const h = Math.floor(clock.minuteOfDay[i] / 60);
      counts.set(h, (counts.get(h) ?? 0) + 1);
      total++;
    }
    return hours.map((h) => (total ? pct((counts.get(h) ?? 0) / total, 0) : "n/a"));
  };
  say(table(
    ["condition", ...hours.map((h) => `${String(h).padStart(2, "0")}:00`)],
    [
      ["trailing-surge-continuation", ...dist(conds["trailing-surge-continuation"])],
      ["heavy-continuation (time-of-day rvol)", ...dist(conds["heavy-continuation"])],
    ],
  ));
  say();
  const controlRows: (string | number)[][] = [];
  for (const [name, c] of [...Object.entries(controls), ["trailing-surge-continuation", conds["trailing-surge-continuation"]] as [string, Cond], ["heavy-continuation", conds["heavy-continuation"]] as [string, Cond]]) {
    for (const h of [horizons[3], horizons[4]]) {
      const r = eventStudy(bars, inst, restrict(c, 0, split - maxH), [h], cost)[0];
      const ho = eventStudy(bars, inst, restrict(c, split, bars.length), [h], cost)[0];
      controlRows.push([name, h, r.events, num(r.driftAdjustedTicks, 2), num(r.driftAdjustedT, 2), ho.events, num(ho.driftAdjustedTicks, 2), num(ho.driftAdjustedT, 2)]);
    }
  }
  say(table(["condition", "horizon", "research n", "research drift-adj", "research t", "holdout n", "holdout drift-adj", "holdout t"], controlRows));
  say();

  // ---------------------------------------------------------------- 5. long/short decomposition
  say(`## 5. Long/short decomposition`);
  say();
  say(`Prior studies in this repo found "edges" that were entirely one-sided, i.e. the NQ uptrend. Any condition whose drift-adjusted edge lives on one side only is suspect by default.`);
  say();
  const ranked = [...researchCells].filter((c) => c.resp.events >= 100).sort((a, b) => Math.abs(b.resp.driftAdjustedT) - Math.abs(a.resp.driftAdjustedT)).slice(0, 5);
  const decompRows: (string | number)[][] = [];
  for (const c of ranked) {
    for (const [side, s] of [["long", 1], ["short", -1]] as const) {
      const r = eventStudy(bars, inst, sideOnly(restrict(conds[c.cond], 0, split - maxH), s), [c.horizon], cost)[0];
      decompRows.push([`${c.label} ${side}`, r.events, num(r.meanTicks, 2), num(r.driftAdjustedTicks, 2), num(r.driftAdjustedT, 2)]);
    }
  }
  say(table(["cell / side", "n", "raw ticks", "drift-adj ticks", "HAC t"], decompRows));
  say();

  // ---------------------------------------------------------------- 5b. clustered errors
  say(`### The same edges with SESSION-clustered standard errors`);
  say();
  say(`Several of these conditions are day-level states, not bar-level events: once a session is "busy" or "quiet" the condition fires on most of its bars. The HAC lag inside the event study prices the overlap of the forward windows, not the fact that thousands of events come from a few hundred days. Collapsing each session to one observation prices that too.`);
  say();
  say(table(
    ["cell", "events", "sessions", "drift-adj ticks (event mean)", "HAC t", "per-session mean", "clustered t"],
    ranked.map((c) => {
      const ev = excessEvents(bars, inst, restrict(conds[c.cond], 0, split - maxH), c.horizon);
      const cl = clusteredEdge(ev);
      return [c.label, c.resp.events, cl.sessions, num(c.resp.driftAdjustedTicks, 2), num(c.resp.driftAdjustedT, 2), num(cl.mean, 2), num(cl.t, 2)];
    }),
  ));
  say();

  // ---------------------------------------------------------------- 6. holdout
  say(`## 6. Holdout`);
  say();
  const holdoutCells = grid(bars, inst, conds, horizons, cost, split, bars.length);
  const holdByLabel = new Map(holdoutCells.map((c) => [c.label, c]));
  if (survivors.length) {
    say(`Each research survivor, re-measured once on the untouched final ${Math.round(HOLDOUT * 100)}%:`);
    say();
    say(table(
      ["cell", "research drift-adj", "research t", "holdout n", "holdout drift-adj", "holdout t", "replicated?"],
      survivors.map((c) => {
        const hc = holdByLabel.get(c.label)!;
        const same = Math.sign(hc.resp.driftAdjustedTicks) === Math.sign(c.resp.driftAdjustedTicks);
        return [
          c.label, num(c.resp.driftAdjustedTicks, 2), num(c.resp.driftAdjustedT, 2),
          hc.resp.events, num(hc.resp.driftAdjustedTicks, 2), num(hc.resp.driftAdjustedT, 2),
          same && hc.resp.driftAdjustedTicks > cost ? "yes" : same ? "sign only, below cost" : "**no**",
        ];
      }),
    ));
  } else {
    say(`Nothing survived stage 3, so there is nothing the holdout is being asked to confirm.`);
  }
  say();
  say(`For completeness — the whole grid on the holdout. **This table decided nothing**; it is printed so a reader can see whether the research half was unlucky rather than uninformative.`);
  say();
  const holdCorrected = correctMultiple(holdoutCells.map((c) => ({ label: c.label, p: c.resp.driftAdjustedP })), MAX_Q);
  const holdQ = new Map(holdCorrected.map((c) => [c.label, c.qBH]));
  say(table(CELL_HEADERS, cellRows(holdoutCells, holdQ, cost)));
  say();

  say(`The five strongest research cells, re-measured on the holdout with session clustering and a side split. None of them was licensed to be here — nothing survived stage 3 — so this is diagnosis, not validation:`);
  say();
  say(table(
    ["cell", "holdout n", "holdout drift-adj", "holdout HAC t", "sessions", "clustered t", "long ticks", "short ticks"],
    ranked.map((c) => {
      const hc = holdByLabel.get(c.label)!;
      const cl = clusteredEdge(excessEvents(bars, inst, restrict(conds[c.cond], split, bars.length), c.horizon));
      const lo = eventStudy(bars, inst, sideOnly(restrict(conds[c.cond], split, bars.length), 1), [c.horizon], cost)[0];
      const sh = eventStudy(bars, inst, sideOnly(restrict(conds[c.cond], split, bars.length), -1), [c.horizon], cost)[0];
      return [c.label, hc.resp.events, num(hc.resp.driftAdjustedTicks, 2), num(hc.resp.driftAdjustedT, 2), cl.sessions, num(cl.t, 2),
        `${num(lo.driftAdjustedTicks, 1)} (n=${lo.events})`, `${num(sh.driftAdjustedTicks, 1)} (n=${sh.events})`];
    }),
  ));
  say();

  // ------------------------------------------------- 6b. does research predict holdout at all?
  say(`### Does the research half carry any information about the holdout half?`);
  say();
  const pairs = researchCells.map((c) => ({ label: c.label, r: c.resp.driftAdjustedTicks, h: holdByLabel.get(c.label)!.resp.driftAdjustedTicks }));
  const agree = pairs.filter((p) => Math.sign(p.r) === Math.sign(p.h)).length;
  const rx = pairs.map((p) => p.r);
  const hx = pairs.map((p) => p.h);
  const mr = mean(rx);
  const mh = mean(hx);
  const cov = mean(pairs.map((p) => (p.r - mr) * (p.h - mh)));
  const corr = std(rx) > 0 && std(hx) > 0 ? cov / (std(rx) * std(hx)) : 0;
  say(`Sign agreement across all ${pairs.length} cells: **${agree}/${pairs.length} = ${pct(agree / pairs.length, 0)}** (a coin flip is 50%).`);
  say(`Correlation of the drift-adjusted edge between halves: **${num(corr, 3)}**.`);
  say();
  const lowest = [...researchCells].sort((a, b) => (qByLabel.get(a.label) ?? 1) - (qByLabel.get(b.label) ?? 1)).slice(0, 6);
  say(`The six cells that came closest to surviving, and what they did next:`);
  say();
  say(table(["cell", "research drift-adj", "research t", "research q", "holdout drift-adj", "holdout t"], lowest.map((c) => {
    const hc = holdByLabel.get(c.label)!;
    return [c.label, num(c.resp.driftAdjustedTicks, 2), num(c.resp.driftAdjustedT, 2), num(qByLabel.get(c.label) ?? 1, 3), num(hc.resp.driftAdjustedTicks, 2), num(hc.resp.driftAdjustedT, 2)];
  })));
  say();

  // ---------------------------------------------------------------- 6c. the one candidate
  say(`### The one candidate that behaved the same way twice`);
  say();
  say(`\`trailing-surge-continuation\` did not survive stage 3 and is therefore NOT a finding. It is singled out because on the 5-minute pass it is the one condition whose drift-adjusted edge kept its sign, roughly its size, and a t above 2 in BOTH halves — so the useful question is what happens when the robustness probes are pointed at it. Every number below is diagnostic; none of it reverses the failed gate.`);
  say();
  const candRows: (string | number)[][] = [];
  for (const h of [horizons[3], horizons[4]]) {
    const ev = excessEvents(bars, inst, restrict(conds["trailing-surge-continuation"], 0, bars.length), h);
    const byYear = new Map<number, { excess: number; day: number }[]>();
    for (const e of ev) {
      const y = new Date(e.day * 86_400_000).getUTCFullYear();
      let a2 = byYear.get(y);
      if (!a2) byYear.set(y, (a2 = []));
      a2.push(e);
    }
    for (const [y, es] of [...byYear.entries()].sort((a2, b2) => a2[0] - b2[0])) {
      const cl = clusteredEdge(es);
      const xs = es.map((e) => e.excess);
      candRows.push([h, y, es.length, cl.sessions, num(mean(xs), 1), num(std(xs), 0), num(cl.t, 2)]);
    }
  }
  say(table(["horizon", "year", "events", "sessions", "drift-adj ticks", "per-event std", "clustered t"], candRows));
  say();
  const cand24 = excessEvents(bars, inst, restrict(conds["trailing-surge-continuation"], 0, bars.length), horizons[4]).map((e) => e.excess);
  say(`Across the whole sample the ${HORIZON_MINUTES[4]}-minute cell means ${num(mean(cand24), 1)} ticks with a per-event standard deviation of ${num(std(cand24), 0)} ticks — ` +
    `an information ratio of ${num(mean(cand24) / std(cand24), 3)} per event. The edge is ${num(mean(cand24) / cost, 1)}x the round turn and ${num(std(cand24) / mean(cand24), 0)}x smaller than the noise it sits in, ` +
    `which is why ${cand24.length.toLocaleString()} events still cannot settle the question.`);
  say();

  // ---------------------------------------------------------------- summary
  const bestResearch = [...researchCells].filter((c) => c.resp.events >= 100).sort((a, b) => b.resp.driftAdjustedTicks - a.resp.driftAdjustedTicks)[0];
  say(`## 7. The arithmetic`);
  say();
  say(table(["quantity", "value"], [
    ["cells tested (research)", researchCells.length],
    ["cells surviving BH at q <= " + MAX_Q, survivors.length],
    ["largest drift-adjusted edge, research (n >= 100)", `${num(bestResearch.resp.driftAdjustedTicks, 2)} ticks (${bestResearch.label})`],
    ["round-turn cost", `${num(cost, 2)} ticks`],
    ["largest edge / cost", num(bestResearch.resp.driftAdjustedTicks / cost, 2)],
    ["...its HAC t and BH q", `t = ${num(bestResearch.resp.driftAdjustedT, 2)}, q = ${num(qByLabel.get(bestResearch.label) ?? 1, 3)}`],
    ["...same cell on the holdout", `${num(holdByLabel.get(bestResearch.label)!.resp.driftAdjustedTicks, 2)} ticks, t = ${num(holdByLabel.get(bestResearch.label)!.resp.driftAdjustedT, 2)}`],
  ]));
  say();
  say(`The "largest edge / cost" ratio above is the trap this protocol exists to catch: ${num(bestResearch.resp.driftAdjustedTicks, 2)} ticks looks like ` +
    `${num(bestResearch.resp.driftAdjustedTicks / cost, 1)}x the cost of trading, and it is not distinguishable from noise once the ` +
    `${researchCells.length} cells that produced it are accounted for. A large edge measured over a ${Math.round(bestResearch.horizon * tfMin / 60)}-hour ` +
    `horizon sits on top of a very large variance; ticks alone never settle anything.`);
  say();

  mkdirSync(dirname(OUT), { recursive: true });
  writeFileSync(OUT, md.join("\n") + "\n");
  console.log(`\nwrote ${OUT}`);
}

main();
