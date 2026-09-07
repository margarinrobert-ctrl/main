/**
 * Does the Initial Balance strategy work on the Asia session?
 *
 * Run in four stages, deliberately ordered so the cheapest falsification comes first:
 *
 *   1. TRANSPLANT the validated RTH geometry unchanged. Pre-specified, nothing searched.
 *   2. DIAGNOSE the cost hurdle: Asia ranges are a quarter of RTH's while the round turn costs
 *      the same dollars, so every trade starts several times further underwater in R terms.
 *   3. MEASURE GROSS edge at zero cost across a geometry grid. If no directional signal exists
 *      before costs, no geometry can rescue it and the search is over.
 *   4. SPLIT the best-looking cells on research/holdout, to see whether "best of 81" survives.
 *
 * Usage: npx tsx scripts/quant-asia-study.ts
 */
import { readFileSync } from "node:fs";
import { runStrategy } from "../src/lib/quant/backtest";
import { clockFor, inWindow, minutesSinceOpen, sessionIndex } from "../src/lib/quant/clock";
import { parseCsv } from "../src/lib/quant/data";
import { instrument } from "../src/lib/quant/instruments";
import { summarize, mean, neweyWestT } from "../src/lib/quant/stats";
import { bootstrapCI } from "../src/lib/quant/bootstrap";
import { initialBalance as S } from "../src/lib/quant/strategies";

const bars = parseCsv(readFileSync("data/NQ_1m.csv", "utf8"));
const D = { ...S.defaults, rrMode: 1, sideMode: 0, minRangePct: 0, maxRangePct: 100, breakBuffer: 0 };
/** The geometry validated on RTH. Transplanted with nothing changed. */
const RTH_WINNER = { ...D, ibMinutes: 60, retrPct: 50, stopPct: 80, rrMult: 2 };
const med = (xs: number[]) => { const v = [...xs].sort((a, b) => a - b); return v[Math.floor(v.length / 2)]; };

/** Overnight books are thinner than RTH. The sweep reports how much that assumption matters. */
const nq = (session: [number, number], spreadTicks = 1, slippageTicks = 1) =>
  ({ ...instrument("NQ"), spreadTicks, slippageTicks, session });
const free = (session: [number, number]) =>
  ({ ...instrument("NQ"), spreadTicks: 0, slippageTicks: 0, commissionRoundTurn: 0, session });

function segFor(session: [number, number]) {
  const ck = clockFor(bars, "America/New_York");
  return bars.filter((_, i) => inWindow(ck.minuteOfDay[i], session[0], session[1]));
}

function line(inst: ReturnType<typeof nq>, P: Record<string, number>, label: string) {
  const cfg = { inst, fillModel: "realistic" as const };
  const seg = segFor(inst.session as [number, number]);
  const cut = Math.floor(seg.length * 0.7);
  const r = runStrategy(S, seg, P, cfg);
  const s = summarize(r, seg, inst);
  if (s.trades < 10) return `${label}  n=${s.trades} (too few)`;
  const rs = r.trades.map((t) => t.r);
  const ci = bootstrapCI(rs, mean, { samples: 2000, seed: 31 });
  const a = summarize(runStrategy(S, seg.slice(0, cut), P, cfg), seg.slice(0, cut), inst);
  const b = summarize(runStrategy(S, seg.slice(cut), P, cfg), seg.slice(cut), inst);
  return `${label}  n=${String(s.trades).padStart(4)} win=${(s.winRate * 100).toFixed(1)}% E=${s.expectancyR.toFixed(3)}R PF=${s.profitFactor.toFixed(2)} t=${neweyWestT(rs).t.toFixed(2)} CI[${ci.lower.toFixed(3)},${ci.upper.toFixed(3)}] $${s.totalPnl.toFixed(0)}  res ${a.expectancyR.toFixed(3)} / hold ${b.expectancyR.toFixed(3)}`;
}

const SESSIONS: [string, [number, number]][] = [
  ["18:00-03:00 Globex reopen", [1080, 180]],
  ["19:00-03:00              ", [1140, 180]],
  ["20:00-03:00 Tokyo open   ", [1200, 180]],
  ["20:00-02:00              ", [1200, 120]],
  ["18:00-23:59              ", [1080, 1439]],
];

// ---------------------------------------------------------------------------------------------
console.log("=".repeat(118));
console.log("STAGE 1 — transplant the RTH winner (IB60 / retr50 / stop80 / 1:2 / both sides) unchanged");
console.log("=".repeat(118));
console.log("\n  RTH baseline:");
console.log("   " + line(nq([570, 719]), RTH_WINNER, "  09:30-11:59 RTH          "));
console.log("\n  Asia, at RTH cost assumptions (1 tick spread — OPTIMISTIC for overnight):");
for (const [nm, sess] of SESSIONS) console.log("   " + line(nq(sess), RTH_WINNER, `  ${nm}`));
console.log("\n  Asia, at realistic overnight cost (2 tick spread, 2 tick slippage):");
for (const [nm, sess] of SESSIONS.slice(0, 3)) console.log("   " + line(nq(sess, 2, 2), RTH_WINNER, `  ${nm}`));

// ---------------------------------------------------------------------------------------------
console.log("\n" + "=".repeat(118));
console.log("STAGE 2 — the cost hurdle. Risk = 30% of the IB range at the validated geometry.");
console.log("=".repeat(118));
console.log("\n  session            IBmin  medianIB  medianRisk   costR@1t  costR@2t");
for (const [nm, start, ibMin] of [
  ["09:30 RTH   ", 570, 60], ["18:00 Globex", 1080, 60], ["20:00 Tokyo ", 1200, 60],
  ["18:00 Globex", 1080, 120], ["20:00 Tokyo ", 1200, 120], ["20:00 Tokyo ", 1200, 180],
] as [string, number, number][]) {
  const ck = clockFor(bars, "America/New_York");
  const sess = sessionIndex(ck, start);
  const hi = new Map<number, number>(), lo = new Map<number, number>();
  for (let i = 0; i < bars.length; i++) {
    if (minutesSinceOpen(ck.minuteOfDay[i], start) >= ibMin) continue;
    hi.set(sess[i], Math.max(hi.get(sess[i]) ?? -Infinity, bars[i].h));
    lo.set(sess[i], Math.min(lo.get(sess[i]) ?? Infinity, bars[i].l));
  }
  const ranges = [...hi.keys()].map((d) => hi.get(d)! - lo.get(d)!).filter((x) => Number.isFinite(x) && x > 0);
  const mIB = med(ranges), risk = 0.3 * mIB;
  const c1 = 0.25 + 0.5 + 0.2, c2 = 0.5 + 1.0 + 0.2;
  console.log(`  ${nm}   ${String(ibMin).padStart(4)}  ${mIB.toFixed(1).padStart(8)}  ${risk.toFixed(1).padStart(10)}   ${(c1 / risk).toFixed(3).padStart(8)}  ${(c2 / risk).toFixed(3).padStart(8)}`);
}

// ---------------------------------------------------------------------------------------------
console.log("\n" + "=".repeat(118));
console.log("STAGE 3 — gross edge at ZERO cost. Not tradeable; a test of whether any signal exists.");
console.log("=".repeat(118));
const grid: Record<string, number>[] = [];
for (const ibMinutes of [60, 120, 180])
  for (const retrPct of [10, 25, 50])
    for (const stopPct of [60, 80, 100])
      for (const rrMult of [1, 1.5, 2])
        grid.push({ ...D, ibMinutes, retrPct, stopPct, rrMult });

for (const [nm, session] of [SESSIONS[0], SESSIONS[2]]) {
  const seg = segFor(session);
  const rows: { p: Record<string, number>; g: number; gt: number; n: number; net: number }[] = [];
  for (const p of grid) {
    const gr = runStrategy(S, seg, p, { inst: free(session), fillModel: "realistic" as const });
    const gs = summarize(gr, seg, free(session));
    if (gs.trades < 30) continue;
    const ni = nq(session, 2, 2);
    const ns = summarize(runStrategy(S, seg, p, { inst: ni, fillModel: "realistic" as const }), seg, ni);
    rows.push({ p, g: gs.expectancyR, gt: neweyWestT(gr.trades.map((t) => t.r)).t, n: gs.trades, net: ns.expectancyR });
  }
  rows.sort((a, b) => b.g - a.g);
  console.log(`\n  ${nm} — ${rows.length} geometries`);
  for (const r of rows.slice(0, 5))
    console.log(`    ib${String(r.p.ibMinutes).padStart(3)} retr${String(r.p.retrPct).padStart(2)} stop${String(r.p.stopPct).padStart(3)} rr1:${r.p.rrMult}  n=${String(r.n).padStart(4)}  GROSS ${r.g >= 0 ? "+" : ""}${r.g.toFixed(3)}R (t=${r.gt.toFixed(2)})  ->  NET ${r.net >= 0 ? "+" : ""}${r.net.toFixed(3)}R`);
  console.log(`    worst (a strongly NEGATIVE gross would mean fading the break works):`);
  for (const r of rows.slice(-2))
    console.log(`    ib${String(r.p.ibMinutes).padStart(3)} retr${String(r.p.retrPct).padStart(2)} stop${String(r.p.stopPct).padStart(3)} rr1:${r.p.rrMult}  n=${String(r.n).padStart(4)}  GROSS ${r.g >= 0 ? "+" : ""}${r.g.toFixed(3)}R (t=${r.gt.toFixed(2)})`);
  console.log(`    --> mean GROSS ${(rows.reduce((a, r) => a + r.g, 0) / rows.length).toFixed(3)}R over ${rows.length} geometries; ` +
              `max |t| gross = ${Math.max(...rows.map((r) => Math.abs(r.gt))).toFixed(2)}; ${rows.filter((r) => r.net > 0).length} positive after costs`);
}

// ---------------------------------------------------------------------------------------------
console.log("\n" + "=".repeat(118));
console.log("STAGE 4 — the best-of-81 cells on a split they were NOT selected on (2t spread, 2t slip)");
console.log("=".repeat(118) + "\n");
const CAND: [string, [number, number], Record<string, number>][] = [
  ["Tokyo  ib180 retr25 stop60 1:2", [1200, 180], { ...D, ibMinutes: 180, retrPct: 25, stopPct: 60, rrMult: 2 }],
  ["Tokyo  ib180 retr25 stop60 1:1", [1200, 180], { ...D, ibMinutes: 180, retrPct: 25, stopPct: 60, rrMult: 1 }],
  ["Tokyo  ib120 retr25 stop60 1:2", [1200, 180], { ...D, ibMinutes: 120, retrPct: 25, stopPct: 60, rrMult: 2 }],
  ["Globex ib180 retr25 stop60 1:2", [1080, 180], { ...D, ibMinutes: 180, retrPct: 25, stopPct: 60, rrMult: 2 }],
  ["Globex ib120 retr25 stop60 1:1.5", [1080, 180], { ...D, ibMinutes: 120, retrPct: 25, stopPct: 60, rrMult: 1.5 }],
];
for (const [nm, session, P] of CAND) {
  const inst = nq(session, 2, 2);
  const cfg = { inst, fillModel: "realistic" as const };
  const seg = segFor(session);
  const cut = Math.floor(seg.length * 0.7);
  const out = ([["FULL", seg], ["research", seg.slice(0, cut)], ["holdout", seg.slice(cut)]] as [string, typeof seg][]).map(([pn, sg]) => {
    const r = runStrategy(S, sg, P, cfg);
    const s = summarize(r, sg, inst);
    if (s.trades < 10) return `${pn} n=${s.trades}`;
    return `${pn} n=${String(s.trades).padStart(3)} E=${s.expectancyR >= 0 ? "+" : ""}${s.expectancyR.toFixed(3)} t=${neweyWestT(r.trades.map((t) => t.r)).t.toFixed(2)} $${s.totalPnl.toFixed(0)}`;
  });
  console.log(`  ${nm.padEnd(34)} ${out.join("  |  ")}`);
}
