/**
 * Walk-forward analysis of the screenshot configuration, in both senses of the term.
 *
 *   npx tsx scripts/quant-ib-walkforward.ts
 *
 * Two questions get called walk-forward and they have opposite answers here. The first is whether a
 * PRE-SPECIFIED geometry holds up period after period, which is the quarterly table. The second is
 * what happens when each fold re-searches the whole parameter space on its training window and
 * trades the next block with whatever won — which prices in the cost of choosing parameters. Every
 * re-optimised configuration is compared against the fixed one over the identical stitched
 * out-of-sample bars, because that comparison is the only thing that says whether the search paid.
 *
 * Slow: three walk-forward configurations at 3,000 combinations per fold. See
 * docs/ib/STUDY_IB_SCREENSHOT.md.
 */
import { readFileSync } from "node:fs";
import { runStrategy } from "../src/lib/quant/backtest";
import { clockFor, inWindow } from "../src/lib/quant/clock";
import { parseCsv } from "../src/lib/quant/data";
import { instrument } from "../src/lib/quant/instruments";
import { summarize, mean, neweyWestT } from "../src/lib/quant/stats";
import { bootstrapCI } from "../src/lib/quant/bootstrap";
import { walkForward } from "../src/lib/quant/walkforward";
import { initialBalance as S } from "../src/lib/quant/strategies";

const inst = { ...instrument("NQ"), session: [570, 719] as [number, number] };
const cfg = { inst, fillModel: "realistic" as const, startEquity: 50000 };
// The screenshot: IB 60m, 25% retracement entry, 80% stop, fixed 1:1 target, longs only.
const SHOT = { ...S.defaults, ibMinutes: 60, retrPct: 25, stopPct: 80, rrMode: 1, rrMult: 1, sideMode: 1, minRangePct: 0, maxRangePct: 100, breakBuffer: 0 };
// The structural trio without the direction filter — the part the decomposition says is honest.
const TRIO = { ...SHOT, sideMode: 0 };

const bars = parseCsv(readFileSync("data/NQ_1m.csv", "utf8"));
const ck = clockFor(bars, inst.tz);
const seg = bars.filter((_: unknown, i: number) => inWindow(ck.minuteOfDay[i], inst.session[0], inst.session[1]));
const segClock = clockFor(seg, inst.tz);
const barsPerDay = 150; // 09:30-11:59 inclusive

function line(tag: string, rs: number[], pnl: number) {
  if (rs.length < 5) return console.log(`  ${tag}  n=${rs.length} (too few)`);
  const ci = bootstrapCI(rs, mean, { samples: 3000, seed: 31 });
  const wins = rs.filter(r => r > 0).length;
  console.log(`  ${tag}  n=${String(rs.length).padStart(3)}  win=${(100*wins/rs.length).toFixed(1)}%  E=${mean(rs).toFixed(3)}R  t=${neweyWestT(rs).t.toFixed(2)}  CI[${ci.lower.toFixed(3)},${ci.upper.toFixed(3)}]  $${pnl.toFixed(0)}`);
}

// ---------------------------------------------------------------------------
// 1. FIXED-CONFIG walk-forward. No re-optimisation: the screenshot geometry is
//    pre-specified, so the only question is whether it survives period after
//    period. Sequential, non-overlapping 3-month test blocks.
// ---------------------------------------------------------------------------
for (const [name, P] of [["SCREENSHOT (longs only)", SHOT], ["STRUCTURAL TRIO (both sides)", TRIO]] as [string, typeof SHOT][]) {
  console.log(`\n===== FIXED-CONFIG ROLLING PERIODS — ${name} =====`);
  const full = runStrategy(S, seg, P, cfg);
  // bucket trades by calendar quarter of entry
  const byQ = new Map<string, { rs: number[]; pnl: number }>();
  for (const t of full.trades) {
    const d = new Date(t.entryTime);
    const q = `${d.getUTCFullYear()}Q${Math.floor(d.getUTCMonth() / 3) + 1}`;
    const b = byQ.get(q) ?? { rs: [], pnl: 0 };
    b.rs.push(t.r); b.pnl += t.pnl; byQ.set(q, b);
  }
  const qs = [...byQ].sort((a, b) => a[0] < b[0] ? -1 : 1);
  let pos = 0;
  for (const [q, b] of qs) {
    const w = b.rs.filter(r => r > 0).length;
    if (b.pnl > 0) pos++;
    console.log(`  ${q}  n=${String(b.rs.length).padStart(3)}  win=${(100*w/b.rs.length).toFixed(0).padStart(3)}%  E=${b.rs.length?mean(b.rs).toFixed(3):"  n/a"}R  $${b.pnl.toFixed(0).padStart(7)}`);
  }
  console.log(`  --> ${pos}/${qs.length} quarters positive`);
}

// ---------------------------------------------------------------------------
// 2. TRUE WALK-FORWARD with re-optimisation. Each fold re-searches the full
//    10-dimensional geometry on the training window and trades the next block
//    with whatever it picked. This measures the cost of CHOOSING parameters,
//    which the screenshot's user does not pay (the geometry is fixed) but which
//    anyone tuning it would.
// ---------------------------------------------------------------------------
for (const [mode, train, test] of [["rolling", 250, 60], ["rolling", 400, 90], ["anchored", 250, 60]] as ["rolling"|"anchored", number, number][]) {
  const wf = walkForward(S, seg, cfg, {
    trainBars: train * barsPerDay,
    testBars: test * barsPerDay,
    mode,
    objective: "sharpe",
    minTrades: 20,
    maxCombos: 3000,
    seed: 11,
  });
  console.log(`\n===== WALK-FORWARD (${mode}, train ${train}d / test ${test}d) — ${wf.folds.length} folds, ${wf.totalTrials.toLocaleString()} trials =====`);
  for (const f of wf.folds) {
    const p = f.params;
    console.log(`  fold ${f.index}  IS=${f.inSampleObjective.toFixed(3)}  OOS=${f.outOfSampleObjective.toFixed(3)}  n=${String(f.trades).padStart(3)}  $${f.oosPnl.toFixed(0).padStart(7)}   ib=${p.ibMinutes} retr=${p.retrPct} stop=${p.stopPct} ${p.rrMode===1?`rr=${p.rrMult}`:`tgt=${p.targetPct}%`} side=${p.sideMode} buf=${p.breakBuffer} rng=${p.minRangePct}-${p.maxRangePct}`);
  }
  line("STITCHED OOS", wf.oosTrades.map(t => t.r), wf.oos.totalPnl);
  console.log(`  efficiency=${wf.efficiency.toFixed(3)}  foldHitRate=${(wf.foldHitRate*100).toFixed(0)}%  maxDD=${(wf.oos.maxDrawdownPct*100).toFixed(1)}%  PF=${wf.oos.profitFactor.toFixed(3)}`);
  const stab = Object.entries(wf.paramStability).sort((a,b)=>b[1]-a[1]).map(([k,v])=>`${k} ${(v*100).toFixed(0)}%`).join("  ");
  console.log(`  param stability: ${stab}`);

  // The comparison that matters: over the SAME stitched OOS bar range, what did
  // the fixed screenshot config earn without any re-optimisation at all?
  const [a, b] = wf.oosRange;
  const sub = seg.slice(a, b);
  for (const [nm, P] of [["fixed SCREENSHOT", SHOT], ["fixed TRIO", TRIO]] as [string, typeof SHOT][]) {
    const r = runStrategy(S, sub, P, cfg);
    const s = summarize(r, sub, inst);
    line(`  same range, ${nm.padEnd(16)}`, r.trades.map(t => t.r), s.totalPnl);
  }
}
