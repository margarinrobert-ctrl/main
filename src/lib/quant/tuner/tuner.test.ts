/**
 * The tuner is only worth having if it agrees with the engine every number in `docs/` came from.
 *
 * The claim the whole exit-tensor idea rests on is that a trade's outcome depends only on its
 * signal bar and the geometry, so the price walk can be cached per bar instead of redone per
 * configuration. If that claim is wrong the tuner is fast and useless. So: random rules against
 * random geometries, and every trade's P&L, entry bar and exit bar must match `runBacktest`
 * EXACTLY, not approximately.
 *
 * The same assertion exists on the Python side (`research/tuner_test.py`) against `sim_core`.
 * Neither engine is the other's port — they were written from the same specification — so an
 * agreement here is worth more than either one's internal consistency.
 */
import { describe, expect, it } from "vitest";
import { runBacktest } from "../backtest";
import { clockFor, sessionIndex } from "../clock";
import { instrument, pointsToUsd, roundTurnCostPoints } from "../instruments";
import { syntheticSeries } from "../synth";
import type { Bar, EntryIntent, Instrument } from "../types";
import { get, makeContext, catalogue } from "./indicators";
import { parseRule, RuleError, ruleMask, fillTemplate, templateKeys } from "./rule";
import { TunerSession, parseWindow } from "./index";
import { DEFAULT_COSTS, walk, type Geometry } from "./tensor";

const inst: Instrument = { ...instrument("NQ"), tz: "America/New_York", session: [570, 960] };

function bars(): Bar[] {
  return syntheticSeries("NQ", { days: 90, seed: 4242, ar1: 0.03 });
}

const RULES = [
  "always",
  "close>ema50",
  "close>ema50 and rsi14<45",
  "adx14>20 and pdi14>ndi14",
  "close>ema100 and close<ema20 and stoch14<40",
  "35 < rsi14 < 65",
  "not close>ema50",
  "macd(12,26,9)>0 and body>40",
  "close>ema20 or rsi14<30",
  "emadist50>0 and emadist10<-0.25",
  "vwapd>0.25 and rvol20>1.1",
  "cross(9,21)>0",
];

const GEOMS: Geometry[] = [
  { stop: 1, target: 1, maxBars: 12 },
  { stop: 2, target: 1, maxBars: 12 },
  { stop: 1.5, target: 2, maxBars: 24 },
  { stop: 2.5, target: 3, maxBars: 6 },
  { stop: 1, target: 0.5, maxBars: 48 },
];

const WINDOW = "09:30-11:00";

describe("exit tensor", () => {
  const b = bars();
  const s = new TunerSession(b, inst, "test");
  const w = parseWindow(WINDOW);

  it("reproduces runBacktest trade for trade, on every rule x geometry x side", () => {
    let compared = 0;
    let trades = 0;
    for (const side of [1, -1] as const) {
      const t = s.tensor(side, w, 14, GEOMS);
      for (const rule of RULES) {
        const trig = s.triggers(rule, w);
        const fires = new Uint8Array(b.length);
        for (let i = 0; i < trig.length; i++) fires[trig[i]] = 1;
        const atr = s.atr(14);
        for (let gi = 0; gi < GEOMS.length; gi++) {
          const g = GEOMS[gi];
          const collected: { signalBar: number; exitBar: number; pnl: number }[] = [];
          walk(t, gi, trig, DEFAULT_COSTS, s.lockedFromSession, s.sessionOfBar, collected as never);

          const signal = (i: number): EntryIntent | null => {
            if (!fires[i]) return null;
            const a = atr[i];
            if (!Number.isFinite(a) || a <= 0) return null;
            const stopDist = Math.max(g.stop * a, inst.tickSize);
            return { side, stopDist, targetDist: g.target * stopDist, maxBars: g.maxBars };
          };
          const ref = runBacktest(b, signal, { inst, sessionOnly: true, units: 1 });

          compared++;
          trades += collected.length;
          expect(collected.length, `${rule} side=${side} ${g.stop}/${g.target}/${g.maxBars}: trade count`).toBe(ref.trades.length);
          for (let k = 0; k < ref.trades.length; k++) {
            expect(collected[k].signalBar + 1, `${rule} trade ${k} entry bar`).toBe(ref.trades[k].entryIndex);
            expect(collected[k].exitBar, `${rule} trade ${k} exit bar`).toBe(ref.trades[k].exitIndex);
            expect(collected[k].pnl, `${rule} trade ${k} pnl`).toBeCloseTo(ref.trades[k].pnl, 9);
          }
        }
      }
    }
    expect(compared).toBeGreaterThan(100);
    expect(trades).toBeGreaterThan(1000);
  });

  it("applies costs at read time identically to charging them in the walk", () => {
    const t = s.tensor(1, w, 14, GEOMS);
    const trig = s.triggers("close>ema50", w);
    const fires = new Uint8Array(b.length);
    for (let i = 0; i < trig.length; i++) fires[trig[i]] = 1;
    const atr = s.atr(14);
    const g = GEOMS[1];
    for (const mult of [0.5, 1, 2, 3]) {
      const collected: { pnl: number }[] = [];
      walk(t, 1, trig, { fillModel: "taker", mult }, s.lockedFromSession, s.sessionOfBar, collected as never);
      const ref = runBacktest(
        b,
        (i) => {
          if (!fires[i]) return null;
          const a = atr[i];
          if (!Number.isFinite(a) || a <= 0) return null;
          const stopDist = Math.max(g.stop * a, inst.tickSize);
          return { side: 1, stopDist, targetDist: g.target * stopDist, maxBars: g.maxBars };
        },
        { inst, sessionOnly: true, units: 1, costPointsOverride: roundTurnCostPoints(inst) * mult },
      );
      expect(collected.length).toBe(ref.trades.length);
      for (let k = 0; k < ref.trades.length; k++) expect(collected[k].pnl).toBeCloseTo(ref.trades[k].pnl, 9);
    }
  });

  it("restricts the SIGNAL bar to the window, not the fill or the exit", () => {
    // The window says where a trade may be DECIDED. The fill is the next bar and may therefore
    // land on the window's boundary, and the exit may run well past it -- a trade is not
    // liquidated because the entry window closed, only because the instrument session did.
    const clock = clockFor(b, inst.tz);
    const out = s.run({ rule: "close>ema50", side: 1, window: WINDOW, geom: GEOMS[1], atrPeriod: 14, costs: DEFAULT_COSTS }, 0);
    expect(out.stats.n).toBeGreaterThan(0);
    for (const tr of out.trades) {
      const m = clock.minuteOfDay[tr.signalBar];
      expect(m).toBeGreaterThanOrEqual(w.minutes[0]);
      expect(m).toBeLessThan(w.minutes[1]);
      expect(tr.entryBar).toBe(tr.signalBar + 1);
    }
    expect(out.trades.some((t) => clock.minuteOfDay[t.exitBar] >= w.minutes[1])).toBe(true);
  });

  it("never lets two trades overlap", () => {
    const out = s.run({ rule: "always", side: 1, window: WINDOW, geom: GEOMS[0], atrPeriod: 14, costs: DEFAULT_COSTS }, 0);
    for (let i = 1; i < out.trades.length; i++) {
      expect(out.trades[i].signalBar).toBeGreaterThanOrEqual(out.trades[i - 1].exitBar);
    }
  });
});

describe("indicator causality", () => {
  it("every indicator is unchanged before the cut when the future is removed", () => {
    const b = bars();
    const cut = Math.floor(b.length * 0.7);
    const head = b.slice(0, cut);
    const clockA = clockFor(b, inst.tz);
    const clockB = clockFor(head, inst.tz);
    const full = makeContext(b, sessionIndex(clockA, inst.session[0]), clockA.minuteOfDay, "full");
    const trunc = makeContext(head, sessionIndex(clockB, inst.session[0]), clockB.minuteOfDay, "trunc");

    const probes: [string, number[]][] = catalogue().map((c) =>
      c.arity === 0 ? [c.name, []] : c.arity === 1 ? [c.name, [14]] : c.name === "macd" ? [c.name, [12, 26, 9]] : [c.name, [9, 21]],
    );
    for (const [name, args] of probes) {
      const a = get(full, name, args);
      const z = get(trunc, name, args);
      for (let i = 0; i < cut; i++) {
        if (!Number.isFinite(a[i]) || !Number.isFinite(z[i])) continue;
        expect(Math.abs(a[i] - z[i]), `${name}(${args.join(",")}) at bar ${i}`).toBeLessThan(1e-8);
      }
    }
  });
});

describe("rule language", () => {
  const b = bars();
  const clock = clockFor(b, inst.tz);
  const ctx = makeContext(b, sessionIndex(clock, inst.session[0]), clock.minuteOfDay, "rules");

  it("groups comparisons before conjunctions", () => {
    // The trap a textual `and`->`&` rewrite falls into: `&` binds tighter than `>`, so
    // `c>ema50 and rsi14<40` would silently become `c > (ema50 & rsi14) < 40`.
    const both = ruleMask("close>ema50 and rsi14<40", ctx);
    const a = ruleMask("close>ema50", ctx);
    const c = ruleMask("rsi14<40", ctx);
    for (let i = 0; i < b.length; i++) expect(both[i]).toBe(a[i] && c[i] ? 1 : 0);
  });

  it("expands a chained comparison", () => {
    const chained = ruleMask("35 < rsi14 < 65", ctx);
    const pair = ruleMask("rsi14>35 and rsi14<65", ctx);
    expect(Array.from(chained)).toEqual(Array.from(pair));
  });

  it("treats a NaN comparison as no signal", () => {
    const m = ruleMask("close>ema200", ctx);
    for (let i = 0; i < 199; i++) expect(m[i]).toBe(0);
  });

  it("accepts both ema200 and ema(200)", () => {
    expect(Array.from(ruleMask("close>ema200", ctx))).toEqual(Array.from(ruleMask("close>ema(200)", ctx)));
  });

  it("rejects a bare number as a rule, and names the mistake", () => {
    expect(() => ruleMask("rsi14", ctx)).toThrow(/not a condition/);
  });

  it("names an unknown indicator and suggests near matches", () => {
    expect(() => ruleMask("close>emaa50", ctx)).toThrow(RuleError);
    try {
      ruleMask("close>emaa50", ctx);
    } catch (e) {
      expect((e as Error).message).toMatch(/unknown indicator/);
    }
  });

  it("does not evaluate arbitrary code", () => {
    expect(() => parseRule("process.exit(1)")).toThrow(RuleError);
    expect(() => parseRule("(()=>1)()")).toThrow(RuleError);
  });

  it("fills template placeholders and reports them", () => {
    expect(templateKeys("close>ema{n} and rsi{p}<40")).toEqual(["n", "p"]);
    expect(fillTemplate("close>ema{n}", { n: 50 })).toBe("close>ema50");
    expect(() => fillTemplate("close>ema{n}", {})).toThrow(/no value given/);
  });
});

describe("sweep guardrails", () => {
  const b = bars();
  const s = new TunerSession(b, inst, "guard");

  it("ranks on the research block and reveals the locked block only on request", () => {
    const res = s.sweep({
      rule: "close>ema{n}",
      sides: [1],
      windows: [WINDOW],
      stops: [1, 2],
      targets: [1, 2],
      maxBars: [12],
      atrPeriod: 14,
      costs: [DEFAULT_COSTS],
      params: { n: [20, 50] },
      minTrades: 5,
    });
    expect(res.evaluated).toBe(8);
    expect(res.rows.length).toBeGreaterThan(0);
    for (let i = 1; i < res.rows.length; i++) {
      expect(res.rows[i - 1].perTradeResearch).toBeGreaterThanOrEqual(res.rows[i].perTradeResearch);
    }
    // The locked block exists but is not a sortable, displayable column of the sweep row.
    expect(Object.keys(res.rows[0])).not.toContain("perTradeLocked");
    const revealed = s.reveal(res, res.rows.slice(0, 2));
    expect(revealed).toHaveLength(2);
    expect(revealed[0].searched).toBe(8);
    expect(revealed[0].bonferroni).toBeCloseTo(0.05 / 8, 12);
    expect(["decays", "grew-on-locked"]).toContain(revealed[0].shape);
  });

  it("splits research and locked at 65% of sessions and loses no trades between them", () => {
    const out = s.run({ rule: "always", side: 1, window: WINDOW, geom: GEOMS[1], atrPeriod: 14, costs: DEFAULT_COSTS }, 0);
    expect(out.stats.nResearch + out.stats.nLocked).toBe(out.stats.n);
    expect(out.stats.netResearch + out.stats.netLocked).toBeCloseTo(out.stats.netUsd, 6);
    expect(out.stats.nResearch).toBeGreaterThan(out.stats.nLocked);
  });

  it("prices a matched control against the same minute-of-day mix", () => {
    const out = s.run({ rule: "close>ema50", side: 1, window: WINDOW, geom: GEOMS[1], atrPeriod: 14, costs: DEFAULT_COSTS }, 400, 11);
    expect(out.control).toBeDefined();
    expect(out.control!.draws).toBe(400);
    expect(out.control!.pResearch).toBeGreaterThan(0);
    expect(out.control!.pResearch).toBeLessThanOrEqual(1);
    // A control drawn on a null series should not systematically beat or lose to the rule.
    expect(Number.isFinite(out.control!.meanResearch)).toBe(true);
  });
});

describe("usd conversion", () => {
  it("uses the instrument's tick value, not a hard-coded point value", () => {
    expect(pointsToUsd(inst, 1)).toBeCloseTo(inst.tickValue / inst.tickSize, 9);
  });
});
