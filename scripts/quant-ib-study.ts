/**
 * Deep study of the Initial Balance breakout-retracement strategy.
 *
 *   npx tsx scripts/quant-ib-study.ts --data data/NQ_5m.csv --symbol NQ --out docs/ib/STUDY_IB.md
 *
 * Structure:
 *   1  baseline at the published geometry, no tuning at all
 *   2  anomaly search — which day features predict whether the trade works
 *   3  parameter search over the full geometry, with plateau diagnosis
 *   4  walk-forward, so parameter choice is paid for
 *   5  PBO, Deflated Sharpe, bootstrap intervals
 *   6  Monte Carlo on the trade sequence
 *   7  the combined "best" configuration, tested honestly
 *   8  locked holdout, evaluated once
 */
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { runStrategy, type BacktestConfig } from "../src/lib/quant/backtest";
import { bootstrapCI, realityCheck } from "../src/lib/quant/bootstrap";
import { clockFor, hhmm, inWindow } from "../src/lib/quant/clock";
import { probabilityOfBacktestOverfitting } from "../src/lib/quant/cpcv";
import { auditBars, parseCsv } from "../src/lib/quant/data";
import { deflatedSharpe, trialSharpeDispersion } from "../src/lib/quant/deflated";
import { conditionalEdges, ibBucketers, ibDays, subsetStats, type IbDay } from "../src/lib/quant/ibFeatures";
import { instrument, roundTurnCostTicks } from "../src/lib/quant/instruments";
import { monteCarloTrades } from "../src/lib/quant/montecarlo";
import { gridSearch, plateauReport } from "../src/lib/quant/optimize";
import { cumulative, num, pct, sparkline, table, usd } from "../src/lib/quant/report";
import { costSensitivity, regimeBreakdown, subPeriodConsistency, verdict } from "../src/lib/quant/robustness";
import { dailySeries, sharpeRatio, summarize } from "../src/lib/quant/stats";
import { initialBalance } from "../src/lib/quant/strategies";
import { walkForward } from "../src/lib/quant/walkforward";
import type { Params, Trade } from "../src/lib/quant/types";

const arg = (k: string, d?: string) => {
  const i = process.argv.indexOf(`--${k}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : d;
};
const DATA = arg("data", "data/NQ_5m.csv")!;
const SYMBOL = arg("symbol", "NQ")!;
const OUT = arg("out", "docs/ib/STUDY_IB.md")!;
const FILL = (arg("fill", "realistic") ?? "realistic") as "taker" | "realistic" | "passive";
const HOLDOUT = Number(arg("holdout", "0.3"));
const COMBOS = Number(arg("combos", "1200"));
const SEED = Number(arg("seed", "20250822"));

const md: string[] = [];
const say = (s = "") => {
  md.push(s);
  console.log(s);
};

function main() {
  const t0 = Date.now();
  const inst = instrument(SYMBOL);
  const cfg: BacktestConfig = { inst, fillModel: FILL };
  const S = initialBalance;

  const all = parseCsv(readFileSync(DATA, "utf8"));
  const audit = auditBars(all, inst.tz);
  const clockAll = clockFor(all, inst.tz);
  const bars = all.filter((_, i) => inWindow(clockAll.minuteOfDay[i], inst.session[0], inst.session[1]));
  const splitIdx = Math.floor(bars.length * (1 - HOLDOUT));
  const research = bars.slice(0, splitIdx);
  const holdout = bars.slice(splitIdx);
  const costTicks = roundTurnCostTicks(inst);

  say(`# Initial Balance — deep study (${SYMBOL})`);
  say();
  say(`> Generated ${new Date().toISOString()} · seed \`${SEED}\` · fill model \`${FILL}\` · reproducible from this repo.`);
  say(`> Research output, not financial advice.`);
  say();
  say(
    table(
      ["field", "value"],
      [
        ["data", `\`${DATA}\` · ${audit.bars.toLocaleString()} bars @ ${audit.timeframeMinutes}m`],
        ["range", `${audit.first.slice(0, 10)} → ${audit.last.slice(0, 10)}`],
        ["session", `${hhmm(inst.session[0])}–${hhmm(inst.session[1])} ${inst.tz}`],
        ["research bars / sessions", `${research.length.toLocaleString()} / ${new Set(clockFor(research, inst.tz).dayIndex).size}`],
        ["holdout bars / sessions", `${holdout.length.toLocaleString()} / ${new Set(clockFor(holdout, inst.tz).dayIndex).size}`],
        ["round-turn cost", `${costTicks.toFixed(2)} ticks ($${(costTicks * inst.tickValue).toFixed(2)})`],
      ],
    ),
  );
  say();

  // ---------------------------------------------------------------- 1. baseline
  say(`## 1. Baseline — the published geometry, untouched`);
  say();
  say(
    `25% retracement entry, 60% stop, 50% target, all as fractions of the first hour's range, both sides, every session. ` +
      `No filtering, no tuning. This is the number every improvement below has to beat.`,
  );
  say();
  const baseRes = runStrategy(S, research, S.defaults, cfg);
  const base = summarize(baseRes, research, inst);
  say(
    table(
      ["metric", "value"],
      [
        ["trades", base.trades],
        ["fill rate", `${pct(base.trades / new Set(clockFor(research, inst.tz).dayIndex).size, 0)} of sessions`],
        ["unfilled limit orders", baseRes.cancelledOrders],
        ["win rate", pct(base.winRate)],
        ["gross edge", `${num(base.grossEdgeTicks)} ticks`],
        ["net edge", `${num(base.netEdgeTicks)} ticks`],
        ["expectancy", `${num(base.expectancyR, 3)} R`],
        ["profit factor", num(base.profitFactor, 3)],
        ["total P&L (1 contract)", usd(base.totalPnl)],
        ["Sharpe", num(base.sharpe)],
        ["HAC t-stat", `${num(base.tStat)} (p=${num(base.pValue, 3)})`],
        ["max drawdown", pct(base.maxDrawdownPct)],
      ],
    ),
  );
  say();
  const exits = new Map<string, { n: number; pnl: number }>();
  for (const t of baseRes.trades) {
    const e = exits.get(t.reason) ?? { n: 0, pnl: 0 };
    e.n++;
    e.pnl += t.pnl;
    exits.set(t.reason, e);
  }
  say(`Exit mix: ${[...exits].map(([k, v]) => `${k} ${v.n} (${usd(v.pnl)})`).join(" · ")}`);
  say();

  // ---------------------------------------------------------------- 2. anomalies
  say(`## 2. Anomaly search — which sessions are worth trading?`);
  say();
  say(
    `The geometry is held fixed and the question becomes: does some observable feature of the first hour predict whether ` +
      `the trade works? Every feature is computable the moment the IB window closes, before the break, the entry or the outcome. ` +
      `The statistic is the **lift** — this bucket's mean R minus every other trade's mean R — because a bucket can look good ` +
      `purely because the strategy is profitable overall. "Tuesdays make money" is not a finding when every day makes money.`,
  );
  say();
  const days = ibDays(research, inst, S.defaults.ibMinutes);
  const edges = conditionalEdges(baseRes.trades, days, ibBucketers());
  say(
    table(
      ["feature", "bucket", "trades", "mean R", "win", "lift (R)", "t", "p", "BH q"],
      edges.map((e) => [e.feature, e.bucket, e.trades, num(e.meanR, 3), pct(e.winRate, 0), num(e.lift, 3), num(e.t), num(e.p, 3), num(e.q, 3)]),
    ),
  );
  say();
  const survivors = edges.filter((e) => e.q <= 0.1);
  say(
    survivors.length
      ? `**Survives FDR control (q ≤ 0.10): ${survivors.map((s) => `${s.feature} = ${s.bucket} (lift ${s.lift.toFixed(3)}R)`).join("; ")}.**`
      : `**No feature survives FDR control across the ${edges.length} buckets tested.** ` +
          `The largest raw lift is ${edges[0] ? `${edges[0].lift.toFixed(3)}R (${edges[0].feature} = ${edges[0].bucket}, q=${edges[0].q.toFixed(3)})` : "n/a"}, ` +
          `which is what testing ${edges.length} slices of a profitable strategy produces by chance.`,
  );
  say();

  // ---------------------------------------------------------------- 3. parameter search
  say(`## 3. Parameter search over the full geometry`);
  say();
  const search = gridSearch(S, research, cfg, { objective: "sharpe", minTrades: 60, maxCombos: COMBOS, seed: SEED });
  const plateau = plateauReport(search, S.space);
  const bp = search.best.params;
  say(
    table(
      ["field", "value"],
      [
        ["configurations evaluated", search.trialCount],
        ["best parameters", `\`${Object.entries(bp).map(([k, v]) => `${k}=${v}`).join(" ")}\``],
        ["in-sample Sharpe", num(search.best.objective)],
        ["in-sample trades", search.best.summary.trades],
        ["in-sample net edge", `${num(search.best.summary.netEdgeTicks)} ticks`],
        ["neighbour stability", num(plateau.stability)],
        ["neighbours still profitable", pct(plateau.neighbourHitRate, 0)],
        ["surface", plateau.verdict],
      ],
    ),
  );
  say();
  const top = [...search.trials].filter((t) => Number.isFinite(t.objective)).sort((a, b) => b.objective - a.objective).slice(0, 12);
  say(`Top 12 configurations in sample — note how little separates them, which is what a flat surface looks like:`);
  say();
  say(
    table(
      ["#", "parameters", "trades", "net (ticks)", "PF", "Sharpe"],
      top.map((t, i) => [
        i + 1,
        `\`${Object.entries(t.params).map(([k, v]) => `${k}=${v}`).join(" ")}\``,
        t.summary.trades,
        num(t.summary.netEdgeTicks),
        num(t.summary.profitFactor, 3),
        num(t.summary.sharpe),
      ]),
    ),
  );
  say();
  say(`Published geometry ranks **#${1 + search.trials.filter((t) => t.objective > baselineObjective(search, S.defaults)).length}** of ${search.trialCount}.`);
  say();

  // ---------------------------------------------------------------- 4. walk-forward
  say(`## 4. Walk-forward — paying for the parameter choice`);
  say();
  const rClock = clockFor(research, inst.tz);
  const perSession = Math.max(1, Math.round(research.length / new Set(rClock.dayIndex).size));
  const wf = walkForward(S, research, cfg, {
    trainBars: perSession * 150,
    testBars: perSession * 50,
    mode: "rolling",
    objective: "sharpe",
    minTrades: 25,
    maxCombos: Math.min(COMBOS, 400),
    seed: SEED,
  });
  say(
    table(
      ["metric", "walk-forward OOS"],
      [
        ["folds", wf.folds.length],
        ["trades", wf.oos.trades],
        ["net edge", `${num(wf.oos.netEdgeTicks)} ticks`],
        ["profit factor", num(wf.oos.profitFactor, 3)],
        ["Sharpe", num(wf.oos.sharpe)],
        ["HAC t-stat", `${num(wf.oos.tStat)} (p=${num(wf.oos.pValue, 3)})`],
        ["efficiency", num(wf.efficiency)],
        ["folds profitable", pct(wf.foldHitRate, 0)],
        ["total P&L", usd(wf.oos.totalPnl)],
      ],
    ),
  );
  say();
  if (wf.oosDaily.length) say(`OOS equity: \`${sparkline(cumulative(wf.oosDaily))}\``);
  say();
  say(`Parameter stability across folds: ${Object.entries(wf.paramStability).map(([k, v]) => `${k} ${pct(v, 0)}`).join(", ")}`);
  say();

  // ---------------------------------------------------------------- 5. deflation and PBO
  say(`## 5. Selection bias — PBO, Deflated Sharpe, bootstrap`);
  say();
  const totalTrials = search.trialCount + wf.totalTrials;
  const rcDays = [...new Set(rClock.dayIndex)].sort((a, b) => a - b);
  const sample = search.trials.filter((t) => Number.isFinite(t.objective)).slice(0, 120);
  let pboTxt = "insufficient valid configurations";
  let pboVal = NaN;
  if (sample.length >= 8) {
    const series = sample.map((t) => {
      const r = runStrategy(S, research, t.params, cfg);
      return rcDays.map((d) => r.dailyPnl.get(d) ?? 0);
    });
    try {
      const pbo = probabilityOfBacktestOverfitting(series, 10);
      pboVal = pbo.pbo;
      pboTxt = `${pbo.pbo.toFixed(3)} over ${pbo.splits} balanced splits of ${pbo.candidates} configurations`;
    } catch (e) {
      pboTxt = String((e as Error).message);
    }
  }
  const dispersion = trialSharpeDispersion(search.trials.map((t) => t.dailySharpe));
  const dsr = wf.oosDaily.length >= 30 ? deflatedSharpe(wf.oosDaily, totalTrials, dispersion, inst.daysPerYear) : null;
  const ci = wf.oosDaily.length >= 30 ? bootstrapCI(wf.oosDaily, (x) => sharpeRatio(x, inst.daysPerYear), { samples: 2000, seed: SEED }) : null;
  say(
    table(
      ["statistic", "value"],
      [
        ["configurations evaluated in total", totalTrials],
        ["PBO", pboTxt],
        ["walk-forward OOS Sharpe", dsr ? num(dsr.annualisedSr) : "n/a"],
        ["bootstrap 95% CI on that Sharpe", ci ? `[${num(ci.lower)}, ${num(ci.upper)}]` : "n/a"],
        ["expected max Sharpe under the null", dsr ? num(dsr.expectedMaxSr * Math.sqrt(inst.daysPerYear)) : "n/a"],
        ["Deflated Sharpe", dsr ? num(dsr.dsr, 3) : "n/a"],
        ["minimum track record", dsr && Number.isFinite(dsr.minTrackRecord) ? `${Math.ceil(dsr.minTrackRecord)} sessions` : "never at this Sharpe"],
      ],
    ),
  );
  say();

  // ---------------------------------------------------------------- 6. Monte Carlo
  say(`## 6. Monte Carlo on the out-of-sample trade sequence`);
  say();
  say(
    `The backtest shows one ordering of the trades that happened to occur. Reshuffling that order 20,000 times answers the ` +
      `question that decides whether it is tradeable with real money: how deep does the drawdown get in the unlucky-but-normal case?`,
  );
  say();
  const mcShuffle = monteCarloTrades(wf.oosTrades, { paths: 20_000, seed: SEED, startEquity: 50_000, method: "shuffle" });
  const mcBoot = monteCarloTrades(wf.oosTrades, { paths: 20_000, seed: SEED + 1, startEquity: 50_000, method: "bootstrap" });
  say(
    table(
      ["measure", "reshuffled order", "resampled with replacement"],
      [
        ["median max drawdown", pct(mcShuffle.drawdownP50), pct(mcBoot.drawdownP50)],
        ["95th percentile drawdown", pct(mcShuffle.drawdownP95), pct(mcBoot.drawdownP95)],
        ["99th percentile drawdown", pct(mcShuffle.drawdownP99), pct(mcBoot.drawdownP99)],
        ["P(ending below start)", pct(mcShuffle.probLoss, 1), pct(mcBoot.probLoss, 1)],
        ["P(25% drawdown on $50k)", pct(mcShuffle.probRuin, 1), pct(mcBoot.probRuin, 1)],
        ["median final P&L", usd(mcShuffle.medianFinalPnl), usd(mcBoot.medianFinalPnl)],
        ["5th percentile final P&L", usd(mcShuffle.p05FinalPnl), usd(mcBoot.p05FinalPnl)],
        ["median worst losing streak", mcShuffle.medianMaxLosingStreak, mcBoot.medianMaxLosingStreak],
      ],
    ),
  );
  say();
  say(
    `Reshuffling keeps the observed trades and asks about luck of ordering; resampling with replacement also asks what a ` +
      `different draw of trades from the same distribution would have looked like. The second is the harsher and more honest test.`,
  );
  say();

  // ---------------------------------------------------------------- 7. robustness of the tuned config
  say(`## 7. Robustness of the tuned configuration`);
  say();
  const modal = modalParams(wf.folds.map((f) => f.params));
  say(`Walk-forward modal parameters: \`${Object.entries(modal).map(([k, v]) => `${k}=${v}`).join(" ")}\``);
  say();
  const cs = costSensitivity(S, research, modal, cfg);
  say(
    table(
      ["cost multiple", ...cs.points.map((p) => `${p.multiple}x`)],
      [
        ["cost (ticks)", ...cs.points.map((p) => num(p.costTicks))],
        ["expectancy ($/trade)", ...cs.points.map((p) => num(p.expectancyUsd))],
        ["Sharpe", ...cs.points.map((p) => num(p.sharpe))],
      ],
    ),
  );
  say();
  say(`Cost tolerance: **${cs.verdict}**.`);
  say();
  const regimes = regimeBreakdown(wf.oosTrades, research);
  const cons = subPeriodConsistency(wf.oosTrades, 6);
  say(
    table(
      ["probe", "result"],
      [
        ["profitable OOS sub-periods", pct(cons.profitableShare, 0)],
        ["worst sub-period", usd(cons.worstChunkPnl)],
        ["best year's share of P&L", pct(regimes.bestYearShare, 0)],
        ["profitable years", pct(regimes.profitableYearShare, 0)],
        ["long vs short", regimes.byExitReason.length ? summariseSides(wf.oosTrades) : "n/a"],
      ],
    ),
  );
  say();
  const v = verdict({
    oos: wf.oos,
    pbo: Number.isFinite(pboVal) ? pboVal : 1,
    dsr: dsr?.dsr ?? 0,
    cost: cs,
    plateau: plateau.verdict,
    consistency: cons.profitableShare,
    bestYearShare: regimes.bestYearShare,
    wfEfficiency: wf.efficiency,
  });
  say(`**Gates passed ${v.passes.length}/${v.passes.length + v.failures.length}.**`);
  say();
  for (const p of v.passes) say(`- PASS — ${p}`);
  for (const f of v.failures) say(`- FAIL — ${f}`);
  say();

  // ---------------------------------------------------------------- 8. holdout
  say(`## 8. Locked holdout — evaluated once`);
  say();
  const hDays = ibDays(holdout, inst, modal.ibMinutes);
  const rows: (string | number)[][] = [];
  for (const [label, params] of [["published geometry", S.defaults], ["in-sample optimum", bp], ["walk-forward modal", modal]] as [string, Params][]) {
    const r = runStrategy(S, holdout, params, cfg);
    const s = summarize(r, holdout, inst);
    rows.push([label, s.trades, pct(s.winRate, 0), num(s.netEdgeTicks), num(s.expectancyR, 3), num(s.profitFactor, 3), num(s.sharpe), num(s.tStat), usd(s.totalPnl)]);
  }
  say(table(["configuration", "trades", "win", "net (ticks)", "R", "PF", "Sharpe", "t", "P&L"], rows));
  say();
  if (survivors.length) {
    say(`Applying the anomaly filters that survived FDR control to the holdout:`);
    say();
    const hRes = runStrategy(S, holdout, S.defaults, cfg);
    const filtered = filterByBuckets(hRes.trades, hDays, survivors.map((s) => [s.feature, s.bucket] as [string, string]));
    const st = subsetStats(filtered);
    const stAll = subsetStats(hRes.trades);
    say(
      table(
        ["set", "trades", "mean R", "win", "t", "P&L"],
        [
          ["all holdout trades", stAll.n, num(stAll.meanR, 3), pct(stAll.winRate, 0), num(stAll.t), usd(stAll.pnl)],
          ["filtered", st.n, num(st.meanR, 3), pct(st.winRate, 0), num(st.t), usd(st.pnl)],
        ],
      ),
    );
    say();
  }

  say(`---`);
  say();
  say(`Runtime ${((Date.now() - t0) / 1000).toFixed(1)}s · ${totalTrials} configurations evaluated · seed ${SEED}.`);

  mkdirSync(dirname(OUT), { recursive: true });
  writeFileSync(OUT, md.join("\n") + "\n");
  console.error(`\nwrote ${OUT}`);
}

function baselineObjective(search: ReturnType<typeof gridSearch>, defaults: Params): number {
  const key = (p: Params) => Object.keys(defaults).map((k) => `${k}=${p[k]}`).join("|");
  const hit = search.trials.find((t) => key(t.params) === key(defaults));
  return hit ? hit.objective : -Infinity;
}

function summariseSides(trades: Trade[]): string {
  const longs = trades.filter((t) => t.side === 1);
  const shorts = trades.filter((t) => t.side === -1);
  const p = (xs: Trade[]) => xs.reduce((s, t) => s + t.pnl, 0);
  return `${longs.length} long (${usd(p(longs))}) · ${shorts.length} short (${usd(p(shorts))})`;
}

function filterByBuckets(trades: Trade[], days: IbDay[], want: [string, string][]): Trade[] {
  const byDay = new Map(days.map((d) => [d.day, d]));
  const bucketers = ibBucketers();
  return trades.filter((t) => {
    const d = byDay.get(Math.floor(t.entryTime / 86_400_000));
    if (!d) return false;
    return want.every(([feature, bucket]) => bucketers[feature]?.(d) === bucket);
  });
}

function modalParams(list: Params[]): Params {
  const out: Params = {};
  if (!list.length) return out;
  for (const k of Object.keys(list[0])) {
    const counts = new Map<number, number>();
    for (const p of list) counts.set(p[k], (counts.get(p[k]) ?? 0) + 1);
    let bestV = list[0][k];
    let bestN = -1;
    for (const [val, cnt] of counts) if (cnt > bestN) { bestN = cnt; bestV = val; }
    out[k] = bestV;
  }
  return out;
}

main();
