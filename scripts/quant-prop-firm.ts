/**
 * Can any configuration on this branch pass a prop-firm evaluation and produce payouts?
 *
 * The backtest question and the prop-firm question are different. A backtest sums P&L; an evaluation
 * is a race between a profit target and a threshold that ratchets up behind every equity high, run
 * under a minimum-day rule and a consistency rule. The same trades in a different order give a
 * different answer, so this is simulated over resampled paths rather than computed.
 *
 * Usage: npx tsx scripts/quant-prop-firm.ts [--paths 20000]
 */
import { readFileSync } from "node:fs";
import { runStrategy } from "../src/lib/quant/backtest";
import { clockFor, inWindow } from "../src/lib/quant/clock";
import { parseCsv } from "../src/lib/quant/data";
import { instrument } from "../src/lib/quant/instruments";
import { mulberry32 } from "../src/lib/quant/rng";
import { summarize } from "../src/lib/quant/stats";
import { PROP_RULES, dayPathsFromTrades, simulatePropRun, type DayPath, type PropRules } from "../src/lib/quant/propFirm";
import { initialBalance as S } from "../src/lib/quant/strategies";

const arg = (k: string, d: number) => {
  const i = process.argv.indexOf(`--${k}`);
  return i >= 0 ? Number(process.argv[i + 1]) : d;
};
const PATHS = arg("paths", 20000);

const GEOM = { ...S.defaults, ibMinutes: 60, retrPct: 25, stopPct: 80, rrMode: 1, rrMult: 1, minRangePct: 0, maxRangePct: 100, breakBuffer: 0 };
const CONFIGS: [string, Record<string, number>][] = [
  ["screenshot (longs only)", { ...GEOM, sideMode: 1 }],
  ["structural trio (both sides)", { ...GEOM, sideMode: 0 }],
];

const pct = (x: number) => `${(100 * x).toFixed(1)}%`;
const quantile = (xs: number[], q: number) => {
  if (!xs.length) return NaN;
  const v = [...xs].sort((a, b) => a - b);
  return v[Math.min(v.length - 1, Math.max(0, Math.floor(q * v.length)))];
};

/**
 * Resample whole SESSIONS with replacement. The session is the unit because the strategy takes at
 * most one trade per day, so a session is the atom of the equity path; resampling trades instead
 * would destroy the intraday path the trailing threshold is tested against.
 */
function resample(days: DayPath[], n: number, rnd: () => number): DayPath[] {
  const out: DayPath[] = [];
  for (let i = 0; i < n; i++) out.push(days[Math.floor(rnd() * days.length)]);
  return out;
}

interface Verdict {
  passRate: number;
  blowRate: number;
  medianDays: number;
  consistencyBlockRate: number;
}

function evaluate(days: DayPath[], rules: PropRules, contracts: number, budget: number, paths: number): Verdict {
  const rnd = mulberry32(99);
  let passed = 0, blown = 0, blocked = 0;
  const daysToPass: number[] = [];
  for (let p = 0; p < paths; p++) {
    const r = simulatePropRun(resample(days, budget, rnd), rules, contracts, budget);
    if (r.outcome === "passed") { passed++; daysToPass.push(r.days); if (r.consistencyBlocked) blocked++; }
    else if (r.outcome === "blown" || r.outcome === "daily-loss") blown++;
  }
  return {
    passRate: passed / paths,
    blowRate: blown / paths,
    medianDays: passed ? quantile(daysToPass, 0.5) : NaN,
    consistencyBlockRate: passed ? blocked / passed : NaN,
  };
}


// ---------------------------------------------------------------------------------------------
// Part A — headline comparison at the sizes people actually trade.
// ---------------------------------------------------------------------------------------------
const bars = parseCsv(readFileSync("data/NQ_1m.csv", "utf8"));

function prep(instId: string, P: Record<string, number>) {
  const inst = { ...instrument(instId), session: [570, 719] as [number, number] };
  const cfg = { inst, fillModel: "realistic" as const };
  const ck = clockFor(bars, inst.tz);
  const seg = bars.filter((_, i) => inWindow(ck.minuteOfDay[i], inst.session[0], inst.session[1]));
  const segClock = clockFor(seg, inst.tz);
  const res = runStrategy(S, seg, P, cfg);
  return {
    inst,
    sessions: new Set(segClock.dayIndex).size,
    summary: summarize(res, seg, inst),
    days: dayPathsFromTrades(res.trades, seg, inst, segClock.dayIndex),
  };
}

console.log(`\n${"=".repeat(104)}`);
console.log("PART A — pass rate by instrument and size, 60 trading-day budget");
console.log("=".repeat(104));
for (const [name, P] of CONFIGS) {
  for (const instId of ["NQ", "MNQ"]) {
    const { inst, sessions, summary, days } = prep(instId, P);
    const rt = inst.commissionRoundTurn + (inst.spreadTicks + 2 * inst.slippageTicks) * inst.tickValue;
    console.log(`\n--- ${name} on ${instId}  (round turn $${rt.toFixed(2)}, E=${summary.expectancyR.toFixed(3)}R, $${summary.totalPnl.toFixed(0)} total, signals on ${days.length}/${sessions} sessions)`);
    for (const key of ["apex50k", "topstep50k"]) {
      const rules = PROP_RULES[key];
      const sizes = instId === "NQ" ? [1, 2, 3] : [1, 2, 3, 4, 5, 6, 8, 10];
      const row = sizes.map((c) => {
        const v = evaluate(days, rules, c, 60, PATHS);
        return `${c}x ${pct(v.passRate)}/${pct(v.blowRate)}`;
      });
      console.log(`    ${rules.label.padEnd(20)} pass/blow:  ${row.join("   ")}`);
    }
  }
}

// ---------------------------------------------------------------------------------------------
// Part B — size against patience. The two failure modes pull in opposite directions: too big and
// the threshold kills you, too small and you never reach the target inside the budget. The optimum
// is wherever those two curves cross, and it is not at the size most people trade.
// ---------------------------------------------------------------------------------------------
console.log(`\n${"=".repeat(104)}`);
console.log("PART B — MNQ size x day budget, Apex-style rules (pass% / blow% / median days to pass)");
console.log("=".repeat(104));
for (const [name, P] of CONFIGS) {
  const { days } = prep("MNQ", P);
  console.log(`\n--- ${name}`);
  console.log(`    ${"budget".padEnd(8)}${[2, 3, 4, 5, 6, 8].map((c) => `${c}x`.padStart(20)).join("")}`);
  for (const budget of [40, 60, 90, 120, 180]) {
    const cells = [2, 3, 4, 5, 6, 8].map((c) => {
      const v = evaluate(days, PROP_RULES.apex50k, c, budget, PATHS);
      return `${pct(v.passRate)}/${pct(v.blowRate)}/${Number.isFinite(v.medianDays) ? v.medianDays : "--"}`.padStart(20);
    });
    console.log(`    ${String(budget + "d").padEnd(8)}${cells.join("")}`);
  }
}

// ---------------------------------------------------------------------------------------------
// Part C — the funded account. Passing an evaluation is not the goal; a payout is. The funded
// account runs the SAME trailing threshold, so the survival problem does not go away once the fee
// is paid — it repeats, with the difference that now the money is real.
//
// Modelled as: reach the first-payout profit threshold before touching the threshold. Apex-style
// first payouts need roughly $2,000 clear on a $50k account plus a run of winning days.
// ---------------------------------------------------------------------------------------------
const FUNDED: PropRules = {
  label: "funded $50k, first payout",
  startBalance: 50_000,
  trailingDrawdown: 2_500,
  trailMode: "intraday",
  lockAt: 100,
  profitTarget: 2_000,
  minTradingDays: 8,
  consistencyPct: 0.3,
};

console.log(`\n${"=".repeat(104)}`);
console.log("PART C — fee to first payout: P(pass eval) x P(reach payout | funded), Apex-style");
console.log("=".repeat(104));
for (const [name, P] of CONFIGS) {
  const { days } = prep("MNQ", P);
  console.log(`\n--- ${name} on MNQ`);
  for (const c of [2, 3, 4, 5, 6]) {
    const evalV = evaluate(days, PROP_RULES.apex50k, c, 90, PATHS);
    const fundedV = evaluate(days, FUNDED, c, 90, PATHS);
    const joint = evalV.passRate * fundedV.passRate;
    console.log(
      `    ${c}x MNQ:  eval pass ${pct(evalV.passRate).padStart(6)}   funded->payout ${pct(fundedV.passRate).padStart(6)}` +
      `   joint ${pct(joint).padStart(6)}   evals per payout ${(joint > 0 ? 1 / joint : Infinity).toFixed(1)}`,
    );
  }
}

// ---------------------------------------------------------------------------------------------
// Part D — the same result in the unit that actually constrains the decision: calendar time.
//
// Every table above counts TRADING days, meaning days the strategy produced a signal. This rule
// signals on a minority of sessions, so a 90-trading-day budget is not four and a half months. The
// evaluation fee is charged monthly against calendar time, not against signals, which is why a
// configuration that looks strong per-trade can still be a losing proposition per-month.
// ---------------------------------------------------------------------------------------------
const FEE_PER_MONTH = 50; // discounted evaluation fee; substitute your own
const SESSIONS_PER_MONTH = 21;

console.log(`\n${"=".repeat(104)}`);
console.log(`PART D — calendar cost of a payout (assumes $${FEE_PER_MONTH}/month in evaluation fees)`);
console.log("=".repeat(104));
for (const [name, P] of CONFIGS) {
  const { sessions, days } = prep("MNQ", P);
  const signalRate = days.length / sessions;
  console.log(`\n--- ${name} on MNQ — signals on ${pct(signalRate)} of sessions (${(signalRate * 252).toFixed(0)} trading days/yr)`);
  for (const c of [2, 3, 4, 5]) {
    const budget = 90;
    const evalV = evaluate(days, PROP_RULES.apex50k, c, budget, PATHS);
    const fundedV = evaluate(days, FUNDED, c, budget, PATHS);
    const joint = evalV.passRate * fundedV.passRate;
    // A failed attempt burns the whole budget; a successful one burns the median days-to-pass.
    const monthsIf = (d: number) => d / signalRate / SESSIONS_PER_MONTH;
    const passMonths = monthsIf(evalV.medianDays);
    const failMonths = monthsIf(budget);
    const attemptsToPass = evalV.passRate > 0 ? 1 / evalV.passRate : Infinity;
    const monthsPerPass = (attemptsToPass - 1) * failMonths + passMonths;
    const monthsPerPayout = joint > 0 ? monthsPerPass / fundedV.passRate + monthsIf(fundedV.medianDays) : Infinity;
    console.log(
      `    ${c}x  pass ${pct(evalV.passRate).padStart(6)}  median ${passMonths.toFixed(1).padStart(4)} mo to pass` +
      `   attempts/payout ${(joint > 0 ? 1 / joint : Infinity).toFixed(1).padStart(4)}` +
      `   expected ${monthsPerPayout.toFixed(0).padStart(3)} mo and $${(monthsPerPayout * FEE_PER_MONTH).toFixed(0).padStart(5)} in fees per payout`,
    );
  }
}

// ---------------------------------------------------------------------------------------------
// Part E — how much edge degradation does the answer survive?
//
// Everything above assumes the measured expectancy is real and persists. The edge behind it is
// t = 2.46 on 349 trades, which is a long way from certain, and a prop evaluation is a race whose
// outcome is highly convex in the drift term. So: charge extra cost per round turn and watch the
// pass rate. This is the honest way to model degradation — scaling P&L would just be a smaller
// position, which is a different question already answered in Part B.
// ---------------------------------------------------------------------------------------------
console.log(`\n${"=".repeat(104)}`);
console.log("PART E — extra cost per round turn (models worse fills, a weaker edge, or both)");
console.log("=".repeat(104));
for (const [name, P] of CONFIGS) {
  console.log(`\n--- ${name} on MNQ, Apex-style, 90-day budget`);
  for (const extra of [0, 1, 2, 4, 7]) {
    const base = instrument("MNQ");
    const inst = { ...base, commissionRoundTurn: base.commissionRoundTurn + extra, session: [570, 719] as [number, number] };
    const cfg = { inst, fillModel: "realistic" as const };
    const ck = clockFor(bars, inst.tz);
    const seg = bars.filter((_, i) => inWindow(ck.minuteOfDay[i], inst.session[0], inst.session[1]));
    const segClock = clockFor(seg, inst.tz);
    const res = runStrategy(S, seg, P, cfg);
    const s = summarize(res, seg, inst);
    const days = dayPathsFromTrades(res.trades, seg, inst, segClock.dayIndex);
    const cells = [3, 4, 5].map((c) => {
      const v = evaluate(days, PROP_RULES.apex50k, c, 90, PATHS);
      return `${c}x ${pct(v.passRate)}/${pct(v.blowRate)}`.padStart(18);
    });
    console.log(`    +$${extra}/RT  E=${s.expectancyR.toFixed(3)}R  $${s.totalPnl.toFixed(0).padStart(5)}  ${cells.join("")}`);
  }
}
