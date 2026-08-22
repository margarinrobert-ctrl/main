/**
 * Direct sweeps of the four IB geometry parameters the walk-forward folds disagreed about.
 *
 *   npx tsx scripts/quant-ib-geometry.ts
 *
 * The folds in quant-ib-walkforward.ts agreed on almost nothing except a 50% entry retracement
 * rather than the screenshot's 25%, which they picked in every stable fold across all three
 * configurations. This tests that directly, then sweeps IB length, reward-to-risk multiple and stop
 * depth around it. Research/holdout expectancy is printed for every row because the point of the
 * exercise is which settings hold their sign across the split, not which score highest.
 *
 * See docs/ib/STUDY_IB_SCREENSHOT.md section 6.
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
const cfg = { inst, fillModel: "realistic" as const, startEquity: 50000 };
const BASE = { ...S.defaults, ibMinutes: 60, retrPct: 25, stopPct: 80, rrMode: 1, rrMult: 1, sideMode: 0, minRangePct: 0, maxRangePct: 100, breakBuffer: 0 };

const bars = parseCsv(readFileSync("data/NQ_1m.csv", "utf8"));
const ck = clockFor(bars, inst.tz);
const seg0 = bars.filter((_: unknown, i: number) => inWindow(ck.minuteOfDay[i], inst.session[0], inst.session[1]));
const split = Math.floor(seg0.length * 0.7);
const halves: [string, typeof seg0][] = [["FULL", seg0], ["research", seg0.slice(0, split)], ["holdout", seg0.slice(split)]];

function row(tag: string, P: typeof BASE) {
  const out: string[] = [];
  for (const [nm, sg] of halves) {
    const r = runStrategy(S, sg, P, cfg);
    const s = summarize(r, sg, inst);
    const rs = r.trades.map(t => t.r);
    if (rs.length < 5) { out.push(`${nm} n=${rs.length}`); continue; }
    if (nm === "FULL") {
      const ci = bootstrapCI(rs, mean, { samples: 3000, seed: 31 });
      out.push(`n=${String(s.trades).padStart(3)} win=${(s.winRate*100).toFixed(1)}% E=${s.expectancyR.toFixed(3)} PF=${s.profitFactor.toFixed(2)} t=${neweyWestT(rs).t.toFixed(2)} CI[${ci.lower.toFixed(3)},${ci.upper.toFixed(3)}] $${s.totalPnl.toFixed(0)} DD=${(s.maxDrawdownPct*100).toFixed(1)}%`);
    } else out.push(`${nm} ${s.expectancyR.toFixed(3)}`);
  }
  console.log(`  ${tag.padEnd(34)} ${out.join("  |  ")}`);
}

console.log("\n===== RETRACEMENT DEPTH, both sides, everything else = structural trio =====");
for (const retrPct of [10, 25, 40, 50]) row(`retr ${retrPct}%`, { ...BASE, retrPct });

console.log("\n===== same, LONGS ONLY (screenshot's direction filter) =====");
for (const retrPct of [10, 25, 40, 50]) row(`retr ${retrPct}% longs`, { ...BASE, retrPct, sideMode: 1 });

console.log("\n===== IB LENGTH at retr 50, both sides =====");
for (const ibMinutes of [30, 45, 60, 90]) row(`ib ${ibMinutes}m`, { ...BASE, retrPct: 50, ibMinutes });

console.log("\n===== R:R MULTIPLE at retr 50 / ib 60, both sides =====");
for (const rrMult of [1, 1.5, 2, 3]) row(`rr 1:${rrMult}`, { ...BASE, retrPct: 50, rrMult });

console.log("\n===== STOP DEPTH at retr 50 / ib 60 / rr 1, both sides =====");
for (const stopPct of [40, 60, 80, 100]) row(`stop ${stopPct}%`, { ...BASE, retrPct: 50, stopPct });

const best = { ...BASE, retrPct: 50 };
const full = runStrategy(S, seg0, best, cfg);
const mc = monteCarloTrades(full.trades, { paths: 20000, seed: 7, startEquity: 50000, method: "bootstrap" });
const mcs = monteCarloTrades(full.trades, { paths: 20000, seed: 7, startEquity: 50000, method: "shuffle" });
console.log(`\n===== MONTE CARLO on retr 50 / both sides =====`);
console.log(`  reshuffle  medianDD ${(mcs.drawdownP50*100).toFixed(1)}%  p95DD ${(mcs.drawdownP95*100).toFixed(1)}%  P(loss) ${(mcs.probLoss*100).toFixed(1)}%`);
console.log(`  resample   medianDD ${(mc.drawdownP50*100).toFixed(1)}%  p95DD ${(mc.drawdownP95*100).toFixed(1)}%  P(loss) ${(mc.probLoss*100).toFixed(1)}%  P(25%DD) ${(mc.probRuin*100).toFixed(1)}%  median $${mc.medianFinalPnl.toFixed(0)}  5th pct $${mc.p05FinalPnl.toFixed(0)}`);
const byQ = new Map<string, number>();
for (const t of full.trades) { const d = new Date(t.entryTime); const q = `${d.getUTCFullYear()}Q${Math.floor(d.getUTCMonth()/3)+1}`; byQ.set(q, (byQ.get(q) ?? 0) + t.pnl); }
const qs = [...byQ].sort((a,b)=> a[0] < b[0] ? -1 : 1);
console.log(`  quarters: ${qs.map(([q,v])=>`${q} $${v.toFixed(0)}`).join("  ")}`);
console.log(`  --> ${qs.filter(([,v])=>v>0).length}/${qs.length} positive`);
