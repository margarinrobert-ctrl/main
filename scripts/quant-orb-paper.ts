/**
 * The Zarattini / Barbon / Aziz 5-minute ORB, tested on NQ futures.
 *
 * Their specification, which differs from the ORB tested earlier in this repo:
 *   - opening range = the first 5 minutes
 *   - DIRECTION COMES FROM THE OPENING CANDLE'S BODY, not from which edge broke. A bearish opening
 *     range refuses the upside break outright. They call this the crucial parameter.
 *   - stop = 10% of the trailing 14-day ATR from the entry — an absolute distance, not a fraction
 *     of the opening range
 *   - NO PROFIT TARGET. Exit at the end of the day.
 *
 * What cannot be reproduced: their alpha comes overwhelmingly from "Stocks in Play" — each day's 20
 * highest relative-volume names out of ~7,000, driven by company news. That is a CROSS-SECTIONAL
 * selector. NQ is one instrument, so the part of the paper that does the work is unavailable here,
 * and this tests only the mechanical geometry.
 *
 * Protocol: research 60% / validate 20% / LOCKED 20%, selection on dollars, and the winning
 * configuration priced against the size of the search that found it.
 *
 * Usage: npx tsx scripts/quant-orb-paper.ts
 */
import { readFileSync } from "node:fs";
import { runStrategy } from "../src/lib/quant/backtest";
import { bootstrapCI } from "../src/lib/quant/bootstrap";
import { clockFor, inWindow } from "../src/lib/quant/clock";
import { parseCsv } from "../src/lib/quant/data";
import { instrument } from "../src/lib/quant/instruments";
import { monteCarloTrades } from "../src/lib/quant/montecarlo";
import { postSelectionCriticalR, validateRRecord } from "../src/lib/quant/rmultiple";
import { mean, neweyWestT, summarize } from "../src/lib/quant/stats";
import { walkForward } from "../src/lib/quant/walkforward";
import { openingRange as S } from "../src/lib/quant/strategies";

const inst = { ...instrument("NQ"), session: [570, 960] as [number, number] };
const cfg = { inst, fillModel: "realistic" as const, startEquity: 50_000 };
const bars = parseCsv(readFileSync("data/NQ_1m.csv", "utf8"));
const ck = clockFor(bars, inst.tz);
const seg = bars.filter((_, i) => inWindow(ck.minuteOfDay[i], 570, 960));
const n = seg.length;
const rEnd = Math.floor(n * 0.6);
const vEnd = Math.floor(n * 0.8);

/** The paper's specification, as written. */
const PAPER = {
  ...S.defaults, orMinutes: 5, entryMode: 0, dirMode: 1, stopMode: 2, atrFrac: 10, atrDays: 14,
  targetPct: 0, sideMode: 0, breakBuffer: 0, minRangePct: 0, maxRangePct: 100,
};

function report(label: string, P: Record<string, number>, sub = seg) {
  const r = runStrategy(S, sub, P, cfg);
  const s = summarize(r, sub, inst);
  if (s.trades < 10) return `  ${label.padEnd(38)} n=${s.trades} (too few)`;
  const rs = r.trades.map((t) => t.r);
  const ci = bootstrapCI(rs, mean, { samples: 2000, seed: 31 });
  return `  ${label.padEnd(38)} n=${String(s.trades).padStart(4)} win=${(s.winRate * 100).toFixed(1)}% ` +
    `E=${s.expectancyR >= 0 ? "+" : ""}${s.expectancyR.toFixed(3)}R PF=${s.profitFactor.toFixed(2)} ` +
    `t=${neweyWestT(rs).t.toFixed(2)} CI[${ci.lower.toFixed(3)},${ci.upper.toFixed(3)}] $${s.totalPnl.toFixed(0)}`;
}

console.log("=".repeat(112));
console.log("1. THE PAPER'S SPECIFICATION, AS WRITTEN, ON NQ");
console.log("=".repeat(112) + "\n");
console.log(report("paper spec (5m, body, ATR10%, EoD)", PAPER));
console.log(report("  research 60%", PAPER, seg.slice(0, rEnd)));
console.log(report("  validate 20%", PAPER, seg.slice(rEnd, vEnd)));
console.log(report("  LOCKED 20%", PAPER, seg.slice(vEnd)));
console.log("\n  the two components of their spec, isolated:");
console.log(report("without the body rule (dirMode 0)", { ...PAPER, dirMode: 0 }));
console.log(report("without the ATR stop (opposite edge)", { ...PAPER, stopMode: 0 }));
console.log(report("with a 1:2 target instead of EoD", { ...PAPER, targetPct: 200 }));

console.log("\n" + "=".repeat(112));
console.log("2. EVERY COMBINATION, SELECTED ON RESEARCH ONLY, THEN OPENED ON THE LOCKED HOLDOUT");
console.log("=".repeat(112));
const grid: Record<string, number>[] = [];
for (const orMinutes of [5, 15, 30, 60])
  for (const dirMode of [0, 1])
    for (const entryMode of [0, 1])
      for (const stopMode of [0, 1, 2])
        for (const atrFrac of stopMode === 2 ? [5, 10, 20, 33, 50] : [10])
          for (const stopPct of stopMode === 1 ? [30, 50, 75, 100] : [50])
            for (const targetPct of [0, 50, 100, 200, 300])
              for (const sideMode of [0, 1, -1])
                grid.push({ ...S.defaults, orMinutes, dirMode, entryMode, stopMode, atrFrac, atrDays: 14, stopPct, targetPct, sideMode, retrPct: 25, breakBuffer: 0, minRangePct: 0, maxRangePct: 100 });

const rows = grid.map((P) => {
  const r = runStrategy(S, seg, P, cfg);
  const ei = r.trades.map((t) => t.exitIndex);
  const pnl = r.trades.map((t) => t.pnl);
  const pick = (lo: number, hi: number) => pnl.filter((_, k) => ei[k] >= lo && ei[k] < hi);
  const res = pick(0, rEnd), val = pick(rEnd, vEnd), hold = pick(vEnd, n);
  const sum = (a: number[]) => a.reduce((x, y) => x + y, 0);
  return { P, nRes: res.length, nHold: hold.length, dRes: sum(res), dVal: sum(val), dHold: sum(hold), rs: r.trades.map((t) => t.r) };
}).filter((x) => x.nRes >= 30 && x.nHold >= 20);

console.log(`\n  ${grid.length} configurations, ${rows.length} with enough trades in both ends`);
const sorted = [...rows].sort((a, b) => b.dRes - a.dRes);
const holdAll = rows.map((x) => x.dHold);
const pctOf = (v: number) => (holdAll.filter((x) => x < v).length / holdAll.length) * 100;
console.log(`  locked-holdout P&L across all of them: mean $${(holdAll.reduce((a, b) => a + b, 0) / holdAll.length).toFixed(0)}, ` +
  `median $${[...holdAll].sort((a, b) => a - b)[Math.floor(holdAll.length / 2)].toFixed(0)}, ${(holdAll.filter((x) => x > 0).length / holdAll.length * 100).toFixed(0)}% profitable`);
console.log(`\n  ${"rank on research".padEnd(20)}${"research $".padStart(12)}${"validate $".padStart(12)}${"LOCKED $".padStart(12)}${"locked pctile".padStart(15)}  configuration`);
for (const k of [0, 1, 2, 4, 9]) {
  const x = sorted[k];
  if (!x) continue;
  const d = x.P;
  console.log(`  ${`#${k + 1}`.padEnd(20)}${x.dRes.toFixed(0).padStart(12)}${x.dVal.toFixed(0).padStart(12)}${x.dHold.toFixed(0).padStart(12)}${pctOf(x.dHold).toFixed(1).padStart(15)}` +
    `  or${d.orMinutes} dir${d.dirMode} entry${d.entryMode} stop${d.stopMode}${d.stopMode === 2 ? `@${d.atrFrac}%atr` : d.stopMode === 1 ? `@${d.stopPct}%` : ""} tgt${d.targetPct} side${d.sideMode}`);
}
const paperRow = rows.find((x) => x.P.orMinutes === 5 && x.P.dirMode === 1 && x.P.stopMode === 2 && x.P.atrFrac === 10 && x.P.targetPct === 0 && x.P.sideMode === 0 && x.P.entryMode === 0);
if (paperRow) {
  console.log(`  ${"the paper's spec".padEnd(20)}${paperRow.dRes.toFixed(0).padStart(12)}${paperRow.dVal.toFixed(0).padStart(12)}${paperRow.dHold.toFixed(0).padStart(12)}${pctOf(paperRow.dHold).toFixed(1).padStart(15)}  (pre-specified, not searched)`);
}

console.log("\n" + "=".repeat(112));
console.log("3. THE RESEARCH WINNER, PRICED AGAINST THE SEARCH THAT FOUND IT");
console.log("=".repeat(112) + "\n");
const win = sorted[0];
const v1 = validateRRecord(win.rs, 1);
const vK = validateRRecord(win.rs, rows.length);
console.log(`  best-on-research: n=${v1.n}, cumulative ${v1.cumulativeR.toFixed(1)}R, implied b=${v1.impliedB.toFixed(2)}, z=${v1.z.toFixed(2)}`);
console.log(`    as a single pre-specified test : needs ${v1.criticalR.toFixed(1)}R -> ${v1.significant ? "PASSES" : "fails"}`);
console.log(`    priced as best-of-${rows.length}        : needs ${vK.postSelectionCriticalR.toFixed(1)}R -> ${vK.survivesSelection ? "PASSES" : "fails"}`);
if (paperRow) {
  const vp = validateRRecord(paperRow.rs, 1);
  console.log(`  paper spec:       n=${vp.n}, cumulative ${vp.cumulativeR.toFixed(1)}R, implied b=${vp.impliedB.toFixed(2)}, z=${vp.z.toFixed(2)}, needs ${vp.criticalR.toFixed(1)}R -> ${vp.significant ? "PASSES" : "fails"}`);
  console.log(`    observed variance ${vp.observedVar.toFixed(2)} against the model's ${vp.nullVar.toFixed(2)} (ratio ${(vp.observedVar / vp.nullVar).toFixed(2)})`);
}

console.log("\n" + "=".repeat(112));
console.log("4. WALK-FORWARD AND MONTE CARLO ON THE PAPER'S SPEC");
console.log("=".repeat(112) + "\n");
const perDay = 390;
for (const [mode, tr, te] of [["rolling", 250, 60], ["anchored", 250, 60]] as ["rolling" | "anchored", number, number][]) {
  const wf = walkForward(S, seg, cfg, { trainBars: tr * perDay, testBars: te * perDay, mode, objective: "sharpe", minTrades: 20, maxCombos: 600, seed: 11 });
  const rs = wf.oosTrades.map((t) => t.r);
  console.log(`  walk-forward ${mode} ${tr}d/${te}d: ${wf.folds.length} folds, stitched n=${rs.length}, ` +
    `E=${rs.length ? mean(rs).toFixed(3) : "n/a"}R, $${wf.oos.totalPnl.toFixed(0)}, efficiency ${wf.efficiency.toFixed(3)}, hit ${(wf.foldHitRate * 100).toFixed(0)}%`);
}
const full = runStrategy(S, seg, PAPER, cfg);
if (full.trades.length >= 20) {
  const mc = monteCarloTrades(full.trades, { paths: 20_000, seed: 7, startEquity: 50_000, method: "bootstrap" });
  const mcs = monteCarloTrades(full.trades, { paths: 20_000, seed: 7, startEquity: 50_000, method: "shuffle" });
  console.log(`\n  Monte Carlo, paper spec, 20,000 paths on $50k:`);
  console.log(`    reshuffle  medianDD ${(mcs.drawdownP50 * 100).toFixed(1)}%  p95 ${(mcs.drawdownP95 * 100).toFixed(1)}%  P(loss) ${(mcs.probLoss * 100).toFixed(1)}%`);
  console.log(`    resample   medianDD ${(mc.drawdownP50 * 100).toFixed(1)}%  p95 ${(mc.drawdownP95 * 100).toFixed(1)}%  P(loss) ${(mc.probLoss * 100).toFixed(1)}%  median $${mc.medianFinalPnl.toFixed(0)}  5th pct $${mc.p05FinalPnl.toFixed(0)}`);
  const byYear = new Map<number, number>();
  for (const t of full.trades) { const y = new Date(t.entryTime).getUTCFullYear(); byYear.set(y, (byYear.get(y) ?? 0) + t.pnl); }
  console.log(`    by year: ${[...byYear].sort((a, b) => a[0] - b[0]).map(([y, v]) => `${y} $${v.toFixed(0)}`).join("  ")}`);
}
