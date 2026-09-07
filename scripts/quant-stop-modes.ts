/**
 * Which stop rule is best on the validated IB geometry?
 *
 * Four stops that are genuinely different trades, not one trade with a different number:
 *   0 percent of the IB range from the broken edge — scales with the day's own auction
 *   1 a multiple of ATR from the entry           — scales with recent volatility
 *   2 a fixed number of points from the entry    — scales with nothing
 *   3 the opposite edge of the initial balance   — scales with the auction, maximally wide
 *
 * Everything else is held at the validated v3 geometry (IB 60, 50% retracement, fixed 1:2, both
 * sides, flatten 11:59) so the stop is the only thing moving. Reported with the research/holdout
 * split, because that is the column that has caught every failure in this repo.
 *
 * Usage: npx tsx scripts/quant-stop-modes.ts
 */
import { readFileSync } from "node:fs";
import { runStrategy } from "../src/lib/quant/backtest";
import { clockFor, inWindow } from "../src/lib/quant/clock";
import { parseCsv } from "../src/lib/quant/data";
import { instrument } from "../src/lib/quant/instruments";
import { summarize, mean, neweyWestT } from "../src/lib/quant/stats";
import { bootstrapCI } from "../src/lib/quant/bootstrap";
import { monteCarloTrades } from "../src/lib/quant/montecarlo";
import { initialBalance as S } from "../src/lib/quant/strategies";

const inst = { ...instrument("NQ"), session: [570, 719] as [number, number] };
const cfg = { inst, fillModel: "realistic" as const };
const bars = parseCsv(readFileSync("data/NQ_1m.csv", "utf8"));
const ck = clockFor(bars, inst.tz);
const seg = bars.filter((_, i) => inWindow(ck.minuteOfDay[i], 570, 719));
const cut = Math.floor(seg.length * 0.7);

/** The v3 geometry, with the stop left open. */
const BASE = { ...S.defaults, ibMinutes: 60, retrPct: 50, rrMode: 1, rrMult: 2, sideMode: 0, minRangePct: 0, maxRangePct: 100, breakBuffer: 0 };

function row(label: string, P: Record<string, number>) {
  const r = runStrategy(S, seg, P, cfg);
  const s = summarize(r, seg, inst);
  if (s.trades < 20) return `  ${label.padEnd(30)} n=${s.trades} (too few)`;
  const rs = r.trades.map((t) => t.r);
  const ci = bootstrapCI(rs, mean, { samples: 3000, seed: 31 });
  const a = summarize(runStrategy(S, seg.slice(0, cut), P, cfg), seg.slice(0, cut), inst);
  const b = summarize(runStrategy(S, seg.slice(cut), P, cfg), seg.slice(cut), inst);
  const mc = monteCarloTrades(r.trades, { paths: 5000, seed: 7, startEquity: 50000, method: "bootstrap" });
  return `  ${label.padEnd(30)} n=${String(s.trades).padStart(4)} win=${(s.winRate * 100).toFixed(1)}% E=${s.expectancyR >= 0 ? "+" : ""}${s.expectancyR.toFixed(3)}R PF=${s.profitFactor.toFixed(2)} t=${neweyWestT(rs).t.toFixed(2)} CI[${ci.lower.toFixed(3)},${ci.upper.toFixed(3)}] $${String(s.totalPnl.toFixed(0)).padStart(6)} DD=${(s.maxDrawdownPct * 100).toFixed(1)}% mcDD95=${(mc.drawdownP95 * 100).toFixed(1)}%  res ${a.expectancyR >= 0 ? "+" : ""}${a.expectancyR.toFixed(3)} / hold ${b.expectancyR >= 0 ? "+" : ""}${b.expectancyR.toFixed(3)}`;
}

console.log("\n=== MODE 0 — percent of IB range from the broken edge (the v3 default) ===");
for (const stopPct of [60, 70, 80, 90, 100]) console.log(row(`stop ${stopPct}% of range`, { ...BASE, stopMode: 0, stopPct }));

console.log("\n=== MODE 1 — ATR multiple from the entry ===");
for (const atrLen of [14, 30])
  for (const atrMult of [1, 1.5, 2, 3]) console.log(row(`ATR(${atrLen}) x ${atrMult}`, { ...BASE, stopMode: 1, atrLen, atrMult }));

console.log("\n=== MODE 2 — fixed points from the entry ===");
for (const stopPts of [20, 30, 40, 60, 80]) console.log(row(`${stopPts} points`, { ...BASE, stopMode: 2, stopPts }));

console.log("\n=== MODE 3 — the opposite edge of the IB ===");
console.log(row("opposite edge", { ...BASE, stopMode: 3 }));

console.log("\n=== the same four, at the 25% retracement (the screenshot's entry) ===");
const B25 = { ...BASE, retrPct: 25 };
console.log(row("mode 0, stop 80%", { ...B25, stopMode: 0, stopPct: 80 }));
console.log(row("mode 1, ATR(14) x 1.5", { ...B25, stopMode: 1, atrLen: 14, atrMult: 1.5 }));
console.log(row("mode 2, 40 points", { ...B25, stopMode: 2, stopPts: 40 }));
console.log(row("mode 3, opposite edge", { ...B25, stopMode: 3 }));
