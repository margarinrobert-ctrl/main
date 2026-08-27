/**
 * The performance layer has one property worth testing above all others: the streaming sums it
 * computes inside the sweep have to equal the numbers you would get by materialising the daily
 * series and doing it the obvious way. If they ever drift, the sweep is ranking on something
 * subtly different from what the detail view shows for the same configuration — which is the
 * hardest class of bug to notice and the easiest to act on.
 *
 * So `finishBlock` (streaming) and `perfFromDaily` (array) are held against each other on real
 * bars, and the individual statistics are pinned against hand-computed cases besides.
 */
import { describe, expect, it } from "vitest";
import { instrument } from "../instruments";
import { syntheticSeries } from "../synth";
import type { Instrument } from "../types";
import { TunerSession, parseWindow } from "./index";
import { CONCENTRATION_PARTS, EXIT_ORDER, finishBlock, gates, perfFromDaily, emptySums, type BlockGeometry, type BlockSums } from "./performance";
import { DEFAULT_COSTS } from "./tensor";

const inst: Instrument = { ...instrument("NQ"), tz: "America/New_York", session: [570, 960] };
const WINDOW = "09:30-11:00";

/** A block with a market factor supplied directly, for pinning the formulas. */
function geoFrom(market: number[], daysPerYear = 252): BlockGeometry {
  const m = Float64Array.from(market);
  let sum = 0;
  let sumSq = 0;
  for (const v of m) {
    sum += v;
    sumSq += v * v;
  }
  return {
    label: "research",
    from: 0,
    to: m.length,
    sessions: m.length,
    bars: m.length * 10,
    daysPerYear,
    market: m,
    marketSum: sum,
    marketSumSq: sumSq,
  };
}

const NO_TRADES: Pick<BlockSums, "n" | "tradeSumSq" | "wins" | "grossWin" | "grossLoss" | "byReason" | "barsHeld" | "maxTradeDrawdown"> = {
  n: 0, tradeSumSq: 0, wins: 0, grossWin: 0, grossLoss: 0, byReason: [0, 0, 0, 0], barsHeld: 0, maxTradeDrawdown: 0,
};

describe("daily statistics", () => {
  it("divides by every session in the block, not by the ones that traded", () => {
    // Ten sessions, one of them worth $10. Mean is 1, not 10 — dropping flat days is the most
    // common way an intraday Sharpe gets inflated, and `../stats` says so in its own header.
    const geo = geoFrom(new Array(10).fill(0));
    const p = perfFromDaily([10, 0, 0, 0, 0, 0, 0, 0, 0, 0], geo, NO_TRADES);
    expect(p.sessions).toBe(10);
    // mean 1, E[x^2] 10, var 9, sd 3.
    expect(p.sharpe).toBeCloseTo((1 / 3) * Math.sqrt(252), 9);
    // Only the one losing-free day, so downside deviation is zero and Sortino cannot be finite.
    expect(p.sortino).toBe(0);
  });

  it("takes drawdown and the underwater run from the session-marked equity curve", () => {
    const geo = geoFrom(new Array(6).fill(0));
    const p = perfFromDaily([10, -4, -3, 2, 1, 5], geo, NO_TRADES);
    // Equity 10, 6, 3, 5, 6, 11 — peak 10 at session 0, trough 3 at session 2.
    expect(p.maxDrawdown).toBeCloseTo(7, 9);
    // Sessions 1 to 4 sit below that peak; session 5 sets a new one. Four sessions underwater.
    expect(p.underwaterSessions).toBe(4);
  });
});

describe("the market-neutral block", () => {
  it("reads beta 2 and no residual when the strategy IS the market, doubled", () => {
    const market = [3, -1, 2, -4, 5, 0, -2, 1];
    const geo = geoFrom(market);
    const p = perfFromDaily(market.map((m) => 2 * m), geo, NO_TRADES);
    expect(p.beta).toBeCloseTo(2, 9);
    expect(p.correlation).toBeCloseTo(1, 9);
    expect(p.residSharpe).toBeCloseTo(0, 9);
    expect(p.betaPnlShare).toBeCloseTo(1, 9);
  });

  it("reads beta 0 and leaves the Sharpe alone when the two are uncorrelated", () => {
    const geo = geoFrom([1, -1, 1, -1]);
    const p = perfFromDaily([1, 1, -1, -1], geo, NO_TRADES);
    expect(p.beta).toBeCloseTo(0, 12);
    expect(p.correlation).toBeCloseTo(0, 12);
    expect(p.residSharpe).toBeCloseTo(p.sharpe, 9);
    expect(p.betaPnlShare).toBeNaN(); // net is zero: there is no share of nothing
  });

  it("attributes most of the P&L to beta when most of it IS beta", () => {
    // The shape `CLAUDE.md` records for the shipped scalp: a small alpha riding a large exposure.
    const market = [4, -3, 6, -5, 2, -1, 3, -4];
    const geo = geoFrom(market);
    const p = perfFromDaily(market.map((m) => 0.5 * m + 0.05), geo, NO_TRADES);
    expect(p.beta).toBeCloseTo(0.5, 9);
    expect(p.alphaUsd).toBeCloseTo(0.05, 9);
    expect(p.betaPnlShare).toBeGreaterThan(0.5);
  });
});

describe("the sub-period concentration gate", () => {
  it("reads 1.0 when one fifth of the sessions carried all of the profit", () => {
    const n = CONCENTRATION_PARTS * 4;
    const daily = new Array(n).fill(0);
    daily[1] = 100;
    const p = perfFromDaily(daily, geoFrom(new Array(n).fill(0)), NO_TRADES);
    expect(p.concentration).toBeCloseTo(1, 9);
    expect(gates(p, 0).find((g) => g.name === "not one sub-period")!.pass).toBe(false);
  });

  it("reads about a fifth when the profit is spread evenly", () => {
    const n = CONCENTRATION_PARTS * 8;
    const p = perfFromDaily(new Array(n).fill(1), geoFrom(new Array(n).fill(0)), NO_TRADES);
    expect(p.concentration).toBeCloseTo(1 / CONCENTRATION_PARTS, 9);
    expect(gates(p, 0).find((g) => g.name === "not one sub-period")!.pass).toBe(true);
  });

  it("declines to attribute a share of nothing", () => {
    const p = perfFromDaily([1, -1, 1, -1], geoFrom([0, 0, 0, 0]), NO_TRADES);
    expect(p.concentration).toBeNaN();
    expect(gates(p, 0).find((g) => g.name === "not one sub-period")!.pass).toBe(false);
  });
});

describe("streaming and array paths agree", () => {
  const bars = syntheticSeries("NQ", { days: 200, seed: 909, ar1: 0.02 });
  const s = new TunerSession(bars, inst, "perf");
  const w = parseWindow(WINDOW);

  for (const rule of ["always", "close>ema50", "rsi14<45 and close>ema200"]) {
    it(`matches every statistic for "${rule}"`, () => {
      const ref = { side: 1 as const, window: WINDOW, atrPeriod: 14, geom: { stop: 1.5, target: 1, maxBars: 12 }, rule, costs: DEFAULT_COSTS };
      const d = s.detail(ref);
      expect(d.research.trades).toBeGreaterThan(20);

      // Rebuild the trade-level sums the streaming accumulator kept, from the trade list, so the
      // only thing being compared is the DAILY aggregation.
      const geo = s.blockGeometry(w).research;
      const sums = emptySums();
      let eq = 0;
      let peak = 0;
      for (let k = 0; k < d.trades.length; k++) {
        if (d.tradeOrdinals[k] >= s.lockedFromOrdinal) continue;
        const t = d.trades[k];
        sums.n++;
        sums.tradeSumSq += t.pnl * t.pnl;
        sums.barsHeld += t.exitBar - t.entryBar;
        if (t.pnl > 0) {
          sums.wins++;
          sums.grossWin += t.pnl;
        } else sums.grossLoss -= t.pnl;
        // The tensor only ever books these four; `ExitReason` is wider because `runBacktest` also
        // has `signal` and `eod`, which no cached-exit geometry can produce.
        const idx = EXIT_ORDER.indexOf(t.reason);
        if (idx >= 0) sums.byReason[idx]++;
        eq += t.pnl;
        peak = Math.max(peak, eq);
        sums.maxTradeDrawdown = Math.max(sums.maxTradeDrawdown, peak - eq);
      }
      const fromArray = perfFromDaily(d.dailyResearch, geo, sums);

      for (const key of [
        "trades", "netUsd", "perTrade", "winPct", "profitFactor", "payoffRatio",
        "sharpe", "sortino", "calmar", "annualUsd", "maxDrawdown", "maxTradeDrawdown",
        "underwaterSessions", "exposure", "avgBarsHeld", "tDaily", "tTrade",
        "beta", "correlation", "residSharpe", "alphaUsd", "betaPnlShare", "concentration",
      ] as const) {
        const a = d.research[key] as number;
        const b = fromArray[key] as number;
        if (Number.isNaN(a) || Number.isNaN(b)) {
          expect(Number.isNaN(a), key).toBe(Number.isNaN(b));
        } else {
          expect(b, key).toBeCloseTo(a, 6);
        }
      }
      expect(fromArray.parts.map((x) => Math.round(x * 1e6))).toEqual(d.research.parts.map((x) => Math.round(x * 1e6)));
    });
  }

  it("splits the block's P&L across exactly the sub-periods it reports", () => {
    const d = s.detail({ side: 1, window: WINDOW, atrPeriod: 14, geom: { stop: 2, target: 1, maxBars: 12 }, rule: "always", costs: DEFAULT_COSTS });
    const summed = d.research.parts.reduce((a, b) => a + b, 0);
    expect(summed).toBeCloseTo(d.research.netUsd, 6);
    expect(d.dailyResearch.reduce((a, b) => a + b, 0)).toBeCloseTo(d.research.netUsd, 6);
  });
});

describe("finishBlock on an empty block", () => {
  it("returns zeros rather than NaNs a UI would have to guard", () => {
    const p = finishBlock(emptySums(), geoFrom(new Array(20).fill(0)));
    expect(p.trades).toBe(0);
    expect(p.sharpe).toBe(0);
    expect(p.perTrade).toBe(0);
    expect(p.profitFactor).toBe(0);
    expect(p.concentration).toBeNaN();
  });
});
