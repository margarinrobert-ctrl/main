/**
 * The R-multiple validation framework (Viaggi), applied to this repository's own results.
 *
 * The paper is a validation methodology, not a strategy: it cannot produce an edge, it can only
 * say whether one is real in the unit the strategy is designed in. Applying it here is the useful
 * direction — and it turns out to explain, analytically, a pattern that was measured empirically
 * in STUDY_MEGA_SEARCH.md before the paper was read.
 *
 * Usage: npx tsx scripts/quant-rmultiple.ts
 */
import { readFileSync } from "node:fs";
import { runStrategy } from "../src/lib/quant/backtest";
import { clockFor, inWindow } from "../src/lib/quant/clock";
import { parseCsv } from "../src/lib/quant/data";
import { instrument } from "../src/lib/quant/instruments";
import {
  breakEvenWinRate, minTrackRecordLength, pathBenchmarks, validateRRecord,
} from "../src/lib/quant/rmultiple";
import { summarize } from "../src/lib/quant/stats";
import { initialBalance as S } from "../src/lib/quant/strategies";

const inst = { ...instrument("NQ"), session: [570, 719] as [number, number] };
const cfg = { inst, fillModel: "realistic" as const };
const bars = parseCsv(readFileSync("data/NQ_1m.csv", "utf8"));
const ck = clockFor(bars, inst.tz);
const seg = bars.filter((_, i) => inWindow(ck.minuteOfDay[i], 570, 719));
const B = { ...S.defaults, ibMinutes: 60, stopPct: 80, rrMode: 1, sideMode: 0, minRangePct: 0, maxRangePct: 100, breakBuffer: 0 };

console.log("=".repeat(104));
console.log("1. WHY A HIGHER REWARD-TO-RISK RATIO MAKES AN EDGE HARDER TO PROVE");
console.log("=".repeat(104));
console.log("\n   Under the zero-edge null the trade variance IS the reward multiple, so raising b");
console.log("   lowers the win rate you need and raises the noise by the same factor.\n");
console.log("   " + "b (R:R)".padStart(10) + "break-even win".padStart(16) + "null variance".padStart(15) + "trades to prove e=0.10".padStart(24) + "e=0.20".padStart(10) + "e=0.30".padStart(10));
for (const b of [1, 1.5, 2, 3, 4]) {
  const row = [0.1, 0.2, 0.3].map((e, i) => Math.ceil(minTrackRecordLength(b, e)).toLocaleString().padStart(i === 0 ? 24 : 10));
  console.log(`   ${`1:${b}`.padStart(10)}${(breakEvenWinRate(b) * 100).toFixed(1).padStart(15)}%${b.toFixed(2).padStart(15)}${row[0]}${row[1]}${row[2]}`);
}

console.log("\n" + "=".repeat(104));
console.log("2. THE REPOSITORY'S OWN CONFIGURATIONS, PUT THROUGH THE FRAMEWORK");
console.log("=".repeat(104));
const CONFIGS: [string, Record<string, number>, number][] = [
  ["published (retr25 stop60 1:1)", { ...B, retrPct: 25, stopPct: 60, rrMult: 1 }, 1],
  ["screenshot (retr25 stop80 1:1)", { ...B, retrPct: 25, rrMult: 1 }, 1],
  ["v3 validated (retr50 stop80 1:2)", { ...B, retrPct: 50, rrMult: 2 }, 1],
  ["v3, priced as best-of-1,536", { ...B, retrPct: 50, rrMult: 2 }, 1_536],
  ["v3, priced as best-of-225,792", { ...B, retrPct: 50, rrMult: 2 }, 225_792],
];
console.log("\n   " + "configuration".padEnd(34) + "n".padStart(5) + "win%".padStart(7) + "impl b".padStart(8) + "cumR".padStart(8) + "critR".padStart(8) + "z".padStart(7) + "p".padStart(7) + "  verdict");
for (const [name, P, trials] of CONFIGS) {
  const r = runStrategy(S, seg, P, cfg);
  const rs = r.trades.map((t) => t.r);
  const v = validateRRecord(rs, trials);
  const ok = trials === 1 ? v.significant : v.survivesSelection;
  const crit = trials === 1 ? v.criticalR : v.postSelectionCriticalR;
  console.log(`   ${name.padEnd(34)}${String(v.n).padStart(5)}${(v.winRate * 100).toFixed(1).padStart(7)}${v.impliedB.toFixed(2).padStart(8)}` +
              `${v.cumulativeR.toFixed(1).padStart(8)}${crit.toFixed(1).padStart(8)}${v.z.toFixed(2).padStart(7)}${v.p.toFixed(3).padStart(7)}  ${ok ? "PASSES" : "fails"}`);
}

console.log("\n" + "=".repeat(104));
console.log("3. DOES THE BINARY MODEL DESCRIBE OUR TRADES AT ALL?");
console.log("=".repeat(104));
console.log("\n   The framework assumes every trade pays exactly +b or -1. Ours do not: a session flat");
console.log("   or a gap through a level lands between the two. If the observed variance departs from");
console.log("   b, the analytic thresholds are being applied to the wrong process.\n");
console.log("   " + "configuration".padEnd(34) + "impl b".padStart(8) + "null var".padStart(10) + "obs var".padStart(10) + "ratio".padStart(8) + "% clean +b/-1".padStart(15));
for (const [name, P] of CONFIGS.slice(0, 3)) {
  const r = runStrategy(S, seg, P, cfg);
  const rs = r.trades.map((t) => t.r);
  const v = validateRRecord(rs, 1);
  const clean = rs.filter((x) => Math.abs(x + 1) < 0.05 || Math.abs(x - v.impliedB) < 0.25).length / rs.length;
  console.log(`   ${name.padEnd(34)}${v.impliedB.toFixed(2).padStart(8)}${v.nullVar.toFixed(2).padStart(10)}${v.observedVar.toFixed(2).padStart(10)}` +
              `${(v.observedVar / v.nullVar).toFixed(2).padStart(8)}${(clean * 100).toFixed(0).padStart(14)}%`);
}

console.log("\n" + "=".repeat(104));
console.log("4. WHAT A ZERO-EDGE SYSTEM'S EQUITY PATH LOOKS LIKE ANYWAY");
console.log("=".repeat(104));
const vv = validateRRecord(runStrategy(S, seg, { ...B, retrPct: 50, rrMult: 2 }, cfg).trades.map((t) => t.r), 1);
const bm = pathBenchmarks(vv.n, vv.impliedB, 20_000, 7);
console.log(`\n   ${vv.n} trades at b = ${vv.impliedB.toFixed(2)}, simulated 20,000 times with NO edge:\n`);
console.log(`     max drawdown           median ${bm.maxDrawdown.p50.toFixed(1)}R    95th pct ${bm.maxDrawdown.p95.toFixed(1)}R`);
console.log(`     equity MAE (worst low) median ${bm.equityMAE.p50.toFixed(1)}R    5th pct  ${bm.equityMAE.p95.toFixed(1)}R`);
console.log(`     equity MFE (best high) median ${bm.equityMFE.p50.toFixed(1)}R    95th pct ${bm.equityMFE.p95.toFixed(1)}R`);
console.log(`     longest losing streak  median ${bm.longestLosingStreak.p50.toFixed(0)}      95th pct ${bm.longestLosingStreak.p95.toFixed(0)}`);
console.log(`\n   Our realised cumulative R is ${vv.cumulativeR.toFixed(1)}R. A no-edge run of the same length reaches`);
console.log(`   ${bm.equityMFE.p50.toFixed(1)}R at some point half the time, and ${bm.equityMFE.p95.toFixed(1)}R one time in twenty.`);
