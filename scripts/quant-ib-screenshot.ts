/**
 * The IB strategy as configured in the TradingView settings screenshot, and a decomposition of it.
 *
 *   npx tsx scripts/quant-ib-screenshot.ts
 *
 * The screenshot differs from the published Pine defaults in four places: flatten 11:59 rather than
 * 15:55, an 80% stop rather than 60%, a fixed 1:1 reward-to-risk target rather than a target scaled
 * to the IB range, and longs only. This runs the exact configuration on both timeframes with a
 * research/holdout split, then re-enables shorts to see what the direction filter is actually
 * removing. See docs/ib/STUDY_IB_SCREENSHOT.md.
 */
import { readFileSync } from "node:fs";
import { runStrategy } from "../src/lib/quant/backtest";
import { clockFor, inWindow } from "../src/lib/quant/clock";
import { parseCsv } from "../src/lib/quant/data";
import { instrument } from "../src/lib/quant/instruments";
import { summarize, mean, neweyWestT } from "../src/lib/quant/stats";
import { bootstrapCI } from "../src/lib/quant/bootstrap";
import { monteCarloTrades } from "../src/lib/quant/montecarlo";
import { subsetStats } from "../src/lib/quant/ibFeatures";
import { initialBalance as S } from "../src/lib/quant/strategies";

// EXACTLY the screenshot configuration:
//   IB 09:30-10:30, flatten 11:59, entry 25% retracement, stop 80% of range from the broken edge,
//   fixed R:R target at 1:1, breakeven off, LONGS ONLY, no range filters, one trade per day.
const inst = { ...instrument("NQ"), session: [570, 719] as [number, number] };
const cfg = { inst, fillModel: "realistic" as const };
const P = { ...S.defaults, ibMinutes: 60, retrPct: 25, stopPct: 80, rrMode: 1, rrMult: 1, sideMode: 1, minRangePct: 0, maxRangePct: 100, breakBuffer: 0 };

for (const file of ["data/NQ_5m.csv", "data/NQ_1m.csv"]) {
  const bars = parseCsv(readFileSync(file, "utf8"));
  const ck = clockFor(bars, inst.tz);
  const seg0 = bars.filter((_: unknown, i: number) => inWindow(ck.minuteOfDay[i], inst.session[0], inst.session[1]));
  const split = Math.floor(seg0.length * 0.7);
  console.log(`\n########## ${file} — ${seg0.length.toLocaleString()} bars in the 09:30-11:59 window ##########`);
  for (const [sn, seg] of [["RESEARCH", seg0.slice(0, split)], ["HOLDOUT ", seg0.slice(split)], ["FULL    ", seg0]] as [string, typeof seg0][]) {
    const r = runStrategy(S, seg, P, cfg);
    const s = summarize(r, seg, inst);
    if (s.trades < 5) { console.log(`  ${sn} n=${s.trades}`); continue; }
    const rs = r.trades.map(t => t.r);
    const ci = bootstrapCI(rs, mean, { samples: 3000, seed: 31 });
    const sessions = new Set(clockFor(seg, inst.tz).dayIndex).size;
    console.log(`  ${sn} n=${String(s.trades).padStart(3)}/${sessions}d  win=${(s.winRate*100).toFixed(1)}%  E=${s.expectancyR.toFixed(3)}R  PF=${s.profitFactor.toFixed(3)}  t=${neweyWestT(rs).t.toFixed(2)}  CI[${ci.lower.toFixed(3)},${ci.upper.toFixed(3)}]  $${s.totalPnl.toFixed(0)}  maxDD=${(s.maxDrawdownPct*100).toFixed(1)}%  unfilled=${r.cancelledOrders}`);
  }
  // The screenshot turns shorts OFF. Every search in this repo that was handed direction chose
  // longs-only and was fitting the index trend, so this is the first thing to check.
  const both = runStrategy(S, seg0, { ...P, sideMode: 0 }, cfg);
  const bs = summarize(both, seg0, inst);
  const L = subsetStats(both.trades.filter(t => t.side === 1)), Sh = subsetStats(both.trades.filter(t => t.side === -1));
  console.log(`  --- with SHORTS RE-ENABLED: n=${bs.trades} E=${bs.expectancyR.toFixed(3)}R PF=${bs.profitFactor.toFixed(3)} $${bs.totalPnl.toFixed(0)}`);
  console.log(`      long side  E=${L.meanR.toFixed(3)}R n=${L.n} t=${L.t.toFixed(2)}   short side E=${Sh.meanR.toFixed(3)}R n=${Sh.n} t=${Sh.t.toFixed(2)}`);
  if (file.includes("1m")) {
    const full = runStrategy(S, seg0, P, cfg);
    const mc = monteCarloTrades(full.trades, { paths: 20000, seed: 7, startEquity: 50000, method: "bootstrap" });
    const mcs = monteCarloTrades(full.trades, { paths: 20000, seed: 7, startEquity: 50000, method: "shuffle" });
    console.log(`  --- MONTE CARLO (20k paths, $50k, 1 contract)`);
    console.log(`      reshuffle  medianDD ${(mcs.drawdownP50*100).toFixed(1)}%  p95DD ${(mcs.drawdownP95*100).toFixed(1)}%  P(loss) ${(mcs.probLoss*100).toFixed(1)}%  P(25%DD) ${(mcs.probRuin*100).toFixed(1)}%`);
    console.log(`      resample   medianDD ${(mc.drawdownP50*100).toFixed(1)}%  p95DD ${(mc.drawdownP95*100).toFixed(1)}%  P(loss) ${(mc.probLoss*100).toFixed(1)}%  P(25%DD) ${(mc.probRuin*100).toFixed(1)}%  median $${mc.medianFinalPnl.toFixed(0)}  5th pct $${mc.p05FinalPnl.toFixed(0)}`);
    const byYear = new Map<number, number>();
    for (const t of full.trades) { const y = new Date(t.entryTime).getUTCFullYear(); byYear.set(y, (byYear.get(y) ?? 0) + t.pnl); }
    console.log(`  --- by year: ${[...byYear].sort((a,b)=>a[0]-b[0]).map(([y,v])=>`${y} $${v.toFixed(0)}`).join("  ")}`);
  }
}
