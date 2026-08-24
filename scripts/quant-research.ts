/**
 * Full systematic-research protocol, start to finish.
 *
 *   npx tsx scripts/quant-research.ts --data data/NQ_5m.csv --symbol NQ --out docs/STUDY_NQ.md
 *
 * The order of the stages is the point. Every stage is capable of killing a candidate, and the ones
 * most likely to kill it run FIRST, so no effort is spent optimising something that was never real:
 *
 *   0  engine null-calibration on simulated martingale data  (does the machinery lie?)
 *   1  data audit                                            (is the input trustworthy?)
 *   2  in-sample parameter search + surface diagnosis        (plateau or mined spike?)
 *   3  White Reality Check / Hansen SPA across candidates    (is the winner better than luck?)
 *   4  PBO via combinatorially symmetric CV                  (does the SELECTION process work?)
 *   5  walk-forward out-of-sample                            (does it survive re-fitting over time?)
 *   6  Deflated Sharpe on the OOS stream                     (priced for the size of the search)
 *   7  cost, regime, sub-period, Monte Carlo robustness      (is it tradeable, not just positive?)
 *   8  multiple-testing correction across strategies         (family-wide error control)
 *   9  portfolio combination                                 (what does combining actually buy?)
 *  10  locked holdout, evaluated exactly once                (the only truly clean number)
 */
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { runStrategy } from "../src/lib/quant/backtest";
import { bootstrapCI, realityCheck } from "../src/lib/quant/bootstrap";
import { clockFor, hhmm, inWindow } from "../src/lib/quant/clock";
import { probabilityOfBacktestOverfitting } from "../src/lib/quant/cpcv";
import { conditions, eventStudy, predictabilityBudget, returnAutocorrelation, timeOfDayProfile, varianceRatios } from "../src/lib/quant/alpha";
import { auditBars, parseCsv } from "../src/lib/quant/data";
import { deflatedSharpe, trialSharpeDispersion } from "../src/lib/quant/deflated";
import { instrument, roundTurnCostTicks } from "../src/lib/quant/instruments";
import { monteCarloTrades } from "../src/lib/quant/montecarlo";
import { correctMultiple } from "../src/lib/quant/multipletest";
import { gridSearch, plateauReport, type SearchResult } from "../src/lib/quant/optimize";
import { alignDaily, buildPortfolio, correlationMatrix, pruneCorrelated } from "../src/lib/quant/portfolio";
import { cumulative, num, pct, SUMMARY_HEADERS, sparkline, summaryRow, table, usd } from "../src/lib/quant/report";
import { costSensitivity, regimeBreakdown, subPeriodConsistency, verdict } from "../src/lib/quant/robustness";
import { pValueTwoSided, sharpeRatio, summarize } from "../src/lib/quant/stats";
import { ALPHA_CANDIDATES, STRATEGIES } from "../src/lib/quant/strategies";
import { syntheticSeries } from "../src/lib/quant/synth";
import { walkForward, type WalkForwardResult } from "../src/lib/quant/walkforward";
import type { Instrument, Params } from "../src/lib/quant/types";

const arg = (k: string, d?: string) => {
  const i = process.argv.indexOf(`--${k}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : d;
};

const DATA = arg("data", "data/NQ_5m.csv")!;
const SYMBOL = arg("symbol", "NQ")!;
const OUT = arg("out", `docs/STUDY_${SYMBOL}.md`)!;
const HOLDOUT = Number(arg("holdout", "0.3"));
const MAX_COMBOS = Number(arg("combos", "400"));
const SEED = Number(arg("seed", "20250822"));
const FILL = (arg("fill", "taker") ?? "taker") as "taker" | "realistic" | "passive";
/** Override the instrument's session, as local `HH:MM-HH:MM`, e.g. --session 09:30-10:30. */
const SESSION = arg("session");
const TAG = arg("tag", "");

const md: string[] = [];
const say = (s = "") => {
  md.push(s);
  console.log(s);
};

// ---------------------------------------------------------------- stage 0: null calibration
/**
 * Run the whole library over simulated MARTINGALE bars. There is no edge in that series by
 * construction, so any strategy that comes out significantly profitable is evidence of a bug in the
 * engine — look-ahead, an exit that resolves in the trader's favour, a cost that never gets charged.
 * This must pass before a single number from the real data is worth reading.
 */
function nullCalibration(inst: Instrument): { failures: string[]; rows: (string | number)[][] } {
  const synthInst: Instrument = { ...inst, tz: "UTC", session: [0, 1440] };
  const bars = syntheticSeries(SYMBOL, { days: 500, seed: SEED, barsPerDay: 78, minutesPerBar: 5, sessionStartUtc: 9 });
  // Costs are zeroed here so the table isolates the engine's own bias: on a martingale the GROSS
  // edge should be ~0, and whatever it is instead is the price of the pessimistic intrabar rule.
  const freeInst: Instrument = { ...synthInst, spreadTicks: 0, slippageTicks: 0, commissionRoundTurn: 0 };
  const rows: (string | number)[][] = [];
  const failures: string[] = [];
  for (const s of STRATEGIES) {
    const res = runStrategy(s, bars, s.defaults, { inst: freeInst, sessionOnly: false, fillModel: FILL });
    const sum = summarize(res, bars, freeInst);
    const ambiguous = res.trades.length ? res.ambiguousExits / res.trades.length : 0;
    rows.push([s.id, sum.trades, num(sum.grossEdgeTicks), pct(ambiguous, 0), num(sum.sharpe), num(sum.tStat), num(sum.pValue, 3)]);
    if (sum.trades >= 50 && sum.tStat > 2.5) failures.push(`${s.id} is significantly profitable on a martingale (t=${sum.tStat.toFixed(2)}) — engine bug`);
  }
  return { failures, rows };
}

/** Same idea in reverse: inject a known effect and confirm the pipeline can see it. */
function powerCheck(inst: Instrument): (string | number)[][] {
  const synthInst: Instrument = { ...inst, tz: "UTC", session: [0, 1440], spreadTicks: 0, slippageTicks: 0, commissionRoundTurn: 0 };
  const rows: (string | number)[][] = [];
  for (const ar1 of [0, 0.15, 0.3]) {
    const bars = syntheticSeries(SYMBOL, { days: 400, seed: SEED + 1, barsPerDay: 78, minutesPerBar: 5, sessionStartUtc: 9, ar1 });
    const s = STRATEGIES.find((x) => x.id === "vol-breakout")!;
    const res = runStrategy(s, bars, { ...s.defaults, minVolPct: 0 }, { inst: synthInst, sessionOnly: false, fillModel: FILL });
    const sum = summarize(res, bars, synthInst);
    rows.push([`momentum AR(1)=${ar1}`, sum.trades, num(sum.netEdgeTicks), num(sum.sharpe), num(sum.tStat)]);
  }
  return rows;
}

// ---------------------------------------------------------------- main
function parseSession(spec: string): [number, number] {
  const m = /^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$/.exec(spec.trim());
  if (!m) throw new Error(`--session must look like 09:30-16:00, got "${spec}"`);
  return [+m[1] * 60 + +m[2], +m[3] * 60 + +m[4]];
}

function main() {
  const inst = instrument(SYMBOL);
  if (SESSION) inst.session = parseSession(SESSION);
  const cfgBase = { inst, fillModel: FILL } as const;
  const t0 = Date.now();

  say(`# Systematic scalping study — ${SYMBOL}${TAG ? ` (${TAG})` : ""}`);
  say();
  say(`> Generated ${new Date().toISOString()} · seed \`${SEED}\` · every number below is reproducible from this repo.`);
  say(`> Research output, not trading advice. A passed protocol is a licence to paper-trade, not to size up.`);
  say();

  // ---- stage 1: data ----
  const allBars = parseCsv(readFileSync(DATA, "utf8"));
  const audit = auditBars(allBars, inst.tz);
  const clock = clockFor(allBars, inst.tz);
  const bars = allBars.filter((_, i) => inWindow(clock.minuteOfDay[i], inst.session[0], inst.session[1]));

  say(`## 1. Data`);
  say();
  say(
    table(
      ["field", "value"],
      [
        ["file", `\`${DATA}\``],
        ["raw bars", audit.bars.toLocaleString()],
        ["timeframe", `${audit.timeframeMinutes} min`],
        ["range", `${audit.first} → ${audit.last}`],
        ["session studied", `${hhmm(inst.session[0])}–${hhmm(inst.session[1])} ${inst.tz}`],
        ["fill model", `\`${FILL}\``],
        ["bars in session", bars.length.toLocaleString()],
        ["sessions", audit.tradingDays.toLocaleString()],
        ["duplicate stamps", audit.duplicateStamps],
        ["out of order", audit.outOfOrder],
        ["invalid OHLC", audit.invalidOhlc],
        ["missing-data gaps", audit.missingDataGaps],
        ["structural (session-break) gaps", audit.structuralGaps],
        ["fat-tail bars (>10 robust σ)", audit.fatTailBars],
        ["suspect prints (>10σ and >3%)", audit.suspectPrints],
      ],
    ),
  );
  say();
  if (audit.notes.length) {
    say(`Audit notes:`);
    for (const n of audit.notes) say(`- ${n}`);
    say();
  }

  const costTicks = roundTurnCostTicks(inst);
  say(
    `**Cost model.** ${inst.spreadTicks} tick spread + ${inst.slippageTicks} tick slippage per side + ` +
      `$${inst.commissionRoundTurn.toFixed(2)} commission = **${costTicks.toFixed(2)} ticks ($${(costTicks * inst.tickValue).toFixed(2)}) per round turn**. ` +
      `Every strategy below must clear that before it has an edge at all.`,
  );
  say();

  // ---- split ----
  const splitIdx = Math.floor(bars.length * (1 - HOLDOUT));
  const research = bars.slice(0, splitIdx);
  const holdout = bars.slice(splitIdx);
  const rClock = clockFor(research, inst.tz);
  const hClock = clockFor(holdout, inst.tz);
  say(
    `**Sample split.** Research set: ${research.length.toLocaleString()} bars ` +
      `(${new Date(research[0].t).toISOString().slice(0, 10)} → ${new Date(research[research.length - 1].t).toISOString().slice(0, 10)}, ` +
      `${new Set(rClock.dayIndex).size} sessions). ` +
      `Locked holdout: ${holdout.length.toLocaleString()} bars ` +
      `(${new Date(holdout[0].t).toISOString().slice(0, 10)} → ${new Date(holdout[holdout.length - 1].t).toISOString().slice(0, 10)}, ` +
      `${new Set(hClock.dayIndex).size} sessions), evaluated once in stage 11 and never used for any choice.`,
  );
  say();

  // ---- stage 0: engine validity ----
  say(`## 2. Engine validity — null calibration`);
  say();
  say(
    `Before trusting any result, the machinery is run over simulated martingale bars with costs switched OFF. ` +
      `There is no edge in that series by construction, so a profitable, significant result here would be a bug, not an alpha. ` +
      `The gross-edge column also prices the engine's one deliberate pessimism: when a bar contains both the stop and the target ` +
      `the trade is booked as a loss, because the intrabar path is unknown. The "ambiguous bars" column is how often that rule fired, ` +
      `and the negative gross edge next to it is what that costs. Real results are conservative by roughly that much.`,
  );
  say();
  const nul = nullCalibration(inst);
  say(table(["strategy", "trades", "gross edge (ticks)", "ambiguous bars", "Sharpe", "t (HAC)", "p"], nul.rows));
  say();
  if (nul.failures.length) {
    say(`**FAILED — do not read further until fixed:**`);
    for (const f of nul.failures) say(`- ${f}`);
  } else {
    say(`**Passed.** No strategy is significantly profitable on data with no edge in it.`);
  }
  say();
  say(`Power check — inject known momentum into the simulator and confirm the pipeline detects it (costs zeroed to isolate detection):`);
  say();
  say(table(["injected effect", "trades", "net edge (ticks)", "Sharpe", "t (HAC)"], powerCheck(inst)));
  say();

  // ---- stage 2.5: is there anything to trade at all? ----
  say(`## 3. Alpha discovery — is there anything to trade?`);
  say();
  say(
    `A strategy backtest confounds two questions: does this market contain exploitable structure, and does this ` +
      `particular rule capture it? This stage answers the first one on its own, on the research set only, with no ` +
      `stops, targets or position management that could manufacture or mask an effect. Everything is measured in ` +
      `TICKS, against the ${costTicks.toFixed(2)}-tick round turn, because that comparison decides the whole question.`,
  );
  say();

  say(`**Return autocorrelation** (within-session ${audit.timeframeMinutes}-minute bar returns). Positive = momentum, negative = reversal.`);
  say();
  const ac = returnAutocorrelation(research, inst.tz, 8);
  say(
    table(
      ["lag", ...ac.map((r) => String(r.lag))],
      [
        ["rho", ...ac.map((r) => num(r.rho, 4))],
        ["t", ...ac.map((r) => num(r.t, 2))],
        ["p", ...ac.map((r) => num(r.p, 3))],
      ],
    ),
  );
  say();
  const sigLags = ac.filter((r) => Math.abs(r.t) > 2);
  say(
    sigLags.length
      ? `Significant at |t| > 2: ${sigLags.map((r) => `lag ${r.lag} (rho ${r.rho.toFixed(4)}, ${r.rho > 0 ? "momentum" : "reversal"})`).join(", ")}. ` +
          `Note the magnitude: a rho of ${Math.abs(sigLags[0].rho).toFixed(4)} on a bar whose typical move is a few ticks is a fraction of a tick of forecast.`
      : `No lag reaches |t| > 2. At this timeframe the series is serially unpredictable from its own returns alone.`,
  );
  say();

  say(`**Variance ratio** (Lo-MacKinlay, heteroskedasticity-robust). VR > 1 trends, VR < 1 reverts, VR = 1 is a random walk.`);
  say();
  const vrs = varianceRatios(research, inst.tz, [2, 3, 5, 10, 20]);
  say(
    table(
      ["q (bars)", "VR", "z", "p", "reading"],
      vrs.map((v) => [v.q, num(v.vr, 3), num(v.z, 2), num(v.p, 3), v.reading]),
    ),
  );
  say();

  say(`**Time-of-day profile.** Mean signed move is where a seasonality edge would live; mean absolute move is where scalping opportunity lives.`);
  say();
  const tod = timeOfDayProfile(research, inst, 30);
  say(
    table(
      ["local time", "bars", "mean move (ticks)", "t", "mean |move| (ticks)", "mean volume"],
      tod.map((b) => [b.label, b.bars, num(b.meanTicks, 3), num(b.tStat, 2), num(b.volTicks, 2), Math.round(b.meanVolume).toLocaleString()]),
    ),
  );
  say();
  const todCorrected = correctMultiple(tod.map((b) => ({ label: b.label, p: pValueTwoSided(b.tStat) })), 0.05);
  const todSurvivors = todCorrected.filter((c) => c.rejectBH);
  say(
    todSurvivors.length
      ? `After Benjamini-Hochberg correction across the ${tod.length} buckets, ${todSurvivors.length} survive: ${todSurvivors.map((c) => c.label).join(", ")}.`
      : `**No time-of-day bucket survives Benjamini-Hochberg correction across the ${tod.length} buckets tested.** Any single bucket with |t| > 2 in the table above is what testing ${tod.length} buckets on noise produces.`,
  );
  say();
  const bestVol = [...tod].sort((a, b) => b.volTicks - a.volTicks)[0];
  const worstVol = [...tod].sort((a, b) => a.volTicks - b.volTicks)[0];
  say(
    `Widest tape: **${bestVol.label}** at ${bestVol.volTicks.toFixed(1)} ticks per bar; quietest: **${worstVol.label}** at ${worstVol.volTicks.toFixed(1)}. ` +
      `A ${costTicks.toFixed(2)}-tick round turn is ${((costTicks / worstVol.volTicks) * 100).toFixed(0)}% of a typical bar in the quiet window and ` +
      `${((costTicks / bestVol.volTicks) * 100).toFixed(0)}% in the busy one — which is why session selection matters more than entry logic.`,
  );
  say();

  say(`**Event studies.** For each classic microstructure hypothesis, the average forward move in the predicted direction, in ticks.`);
  say();
  const cond = conditions(research, inst);
  const studies: { label: string; responses: ReturnType<typeof eventStudy> }[] = [
    { label: "momentum after a >0.5 ATR bar", responses: eventStudy(research, inst, cond.momentum1Bar, [1, 3, 6, 12], costTicks) },
    { label: "reversal after a >1 ATR bar", responses: eventStudy(research, inst, cond.reversal1Bar, [1, 3, 6, 12], costTicks) },
    { label: "volume-surge continuation", responses: eventStudy(research, inst, cond.volumeSurgeMomentum, [1, 3, 6, 12], costTicks) },
    { label: "three-bar run continuation", responses: eventStudy(research, inst, cond.threeBarRun, [1, 3, 6, 12], costTicks) },
    { label: "compression break", responses: eventStudy(research, inst, cond.compressionBreak, [1, 3, 6, 12], costTicks) },
  ];
  const evCells = studies.flatMap((st) => st.responses.map((r) => ({ st, r, label: `${st.label} @${r.horizon}` })));
  const evCorrected = correctMultiple(evCells.map((c) => ({ label: c.label, p: c.r.driftAdjustedP })), 0.05);
  const qByLabel = new Map(evCorrected.map((c) => [c.label, c.qBH]));
  const evRows: (string | number)[][] = evCells.map(({ st, r, label }) => [
    st.label,
    r.horizon,
    r.events.toLocaleString(),
    pct(r.longShare, 0),
    num(r.meanTicks, 2),
    num(r.driftAdjustedTicks, 2),
    num(r.driftAdjustedT, 2),
    num(qByLabel.get(label) ?? 1, 3),
    pct(r.hitRate, 1),
    num(r.netOfCostTicks, 2),
  ]);
  say(table(["condition", "horizon", "events", "long %", "raw (ticks)", "drift-adj (ticks)", "t (HAC)", "BH q", "hit rate", "net of cost"], evRows));
  say();
  say(
    `The **drift-adjusted** column is the one to read. NQ roughly doubled over this sample, so any condition that fires long ` +
      `more often than short earns a large raw mean from exposure alone — the "long %" column shows how much of that is in play. ` +
      `Drift adjustment subtracts \`mean(side) x mean(unconditional forward move)\`, leaving only what the signal itself predicts. ` +
      `BH q-values control the false discovery rate across all ${evCells.length} cells tested here.`,
  );
  say();

  const budget = predictabilityBudget(studies, costTicks, 0.1);
  say(
    table(
      ["quantity", "value"],
      [
        ["largest credible conditional edge (drift-adjusted, q <= 0.10)", `${num(budget.bestEdgeTicks, 2)} ticks`],
        ["from", budget.bestLabel],
        ["round-turn cost", `${num(budget.costTicks, 2)} ticks`],
        ["edge / cost", num(budget.ratio, 2)],
      ],
    ),
  );
  say();
  say(`**${budget.verdict}.**`);
  say();

  // ---- stage 2: in-sample search ----
  say(`## 4. In-sample parameter search`);
  say();
  say(
    `Grid search on the research set only, objective = annualised Sharpe of daily P&L, minimum 50 trades. ` +
      `The winner's score is NOT evidence of anything — it is the maximum of ${MAX_COMBOS} draws. What matters is the shape ` +
      `of the surface around it, reported as the plateau verdict.`,
  );
  say();

  const searches = new Map<string, SearchResult>();
  const searchRows: (string | number)[][] = [];
  let totalTrials = 0;
  for (const s of STRATEGIES) {
    const res = gridSearch(s, research, cfgBase, { objective: "sharpe", minTrades: 50, maxCombos: MAX_COMBOS, seed: SEED });
    searches.set(s.id, res);
    totalTrials += res.trialCount;
    const pl = plateauReport(res, s.space);
    searchRows.push([
      s.id,
      res.trialCount,
      num(res.best.objective),
      res.best.summary.trades,
      num(res.best.summary.netEdgeTicks),
      num(pl.stability),
      pct(pl.neighbourHitRate, 0),
      pl.verdict,
    ]);
  }
  say(table(["strategy", "trials", "best Sharpe (IS)", "trades", "net (ticks)", "neighbour stability", "neighbour hit", "surface"], searchRows));
  say();
  say(`Best parameters found in sample:`);
  say();
  say(
    table(
      ["strategy", "parameters"],
      STRATEGIES.map((s) => [
        s.id,
        `\`${Object.entries(searches.get(s.id)!.best.params)
          .map(([k, v]) => `${k}=${v}`)
          .join(" ")}\``,
      ]),
    ),
  );
  say();
  say(`Total configurations evaluated in stage 4: **${totalTrials}**. This number is carried into the Deflated Sharpe in stage 8.`);
  say();

  // ---- stage 3: reality check ----
  say(`## 5. Reality check across the candidate set`);
  say();
  say(
    `White's Reality Check and Hansen's SPA, applied to the daily P&L of each strategy's in-sample winner, ` +
      `stationary block bootstrap (2,000 resamples) over the cross-section so correlation between candidates is preserved. ` +
      `The null is "no candidate has an edge"; a high p-value means the best result is what picking the max of ${STRATEGIES.length} noisy candidates looks like.`,
  );
  say();
  const rcDays = [...new Set(rClock.dayIndex)].sort((a, b) => a - b);
  const rcSeries = STRATEGIES.map((s) => {
    const best = searches.get(s.id)!.best;
    const res = runStrategy(s, research, best.params, cfgBase);
    return rcDays.map((d) => res.dailyPnl.get(d) ?? 0);
  });
  const rc = realityCheck(rcSeries, STRATEGIES.map((s) => s.id), { samples: 2000, seed: SEED });
  say(
    table(
      ["statistic", "value"],
      [
        ["best candidate", `\`${rc.bestLabel}\``],
        ["mean daily P&L of best", usd(rc.bestMean)],
        ["candidates", rc.candidates],
        ["observations (sessions)", rc.observations],
        ["White Reality Check p", num(rc.pWhite, 3)],
        ["Hansen SPA p", num(rc.pSpa, 3)],
      ],
    ),
  );
  say();

  // ---- stage 4: PBO ----
  say(`## 6. Probability of backtest overfitting (CSCV)`);
  say();
  say(
    `For each strategy, the daily P&L of up to 120 sampled configurations is split into 10 contiguous blocks; ` +
      `every balanced train/test partition (252 of them) picks the in-sample winner and asks where that winner lands out of sample. ` +
      `PBO is the share of partitions where it falls below the median. **PBO > 0.5 means the selection procedure itself is selecting noise.**`,
  );
  say();
  const pboRows: (string | number)[][] = [];
  const pboById = new Map<string, number>();
  for (const s of STRATEGIES) {
    const trials = searches.get(s.id)!.trials.filter((t) => Number.isFinite(t.objective));
    const sample = trials.slice(0, 120);
    if (sample.length < 8) {
      pboRows.push([s.id, sample.length, "n/a", "n/a", "n/a", "too few valid configurations"]);
      pboById.set(s.id, NaN);
      continue;
    }
    const series = sample.map((t) => {
      const res = runStrategy(s, research, t.params, cfgBase);
      return rcDays.map((d) => res.dailyPnl.get(d) ?? 0);
    });
    try {
      const pbo = probabilityOfBacktestOverfitting(series, 10);
      pboById.set(s.id, pbo.pbo);
      pboRows.push([s.id, sample.length, num(pbo.pbo, 3), num(pbo.degradationSlope, 3), pct(pbo.oosLossRate, 0), pbo.pbo < 0.3 ? "selection informative" : pbo.pbo < 0.5 ? "weak" : "selecting noise"]);
    } catch (e) {
      pboById.set(s.id, NaN);
      pboRows.push([s.id, sample.length, "n/a", "n/a", "n/a", String((e as Error).message)]);
    }
  }
  say(table(["strategy", "configs", "PBO", "IS→OOS slope", "OOS loss rate", "reading"], pboRows));
  say();

  // ---- stage 5: walk-forward ----
  say(`## 7. Walk-forward out-of-sample`);
  say();
  // Window lengths are expressed in SESSIONS and converted using this file's own bars-per-session,
  // so the same study is comparable across timeframes instead of silently training on 8x less
  // history when the data is 1-minute rather than 5-minute.
  const barsPerSession = Math.max(1, Math.round(research.length / new Set(rClock.dayIndex).size));
  const trainBars = barsPerSession * 120;
  const testBars = barsPerSession * 40;
  say(
    `Rolling walk-forward on the research set: re-optimise on ${trainBars.toLocaleString()} bars (120 sessions at ` +
      `${barsPerSession} bars/session), trade the next ${testBars.toLocaleString()} bars (40 sessions) with those parameters, ` +
      `step forward, never look back. ` +
      `The stitched test windows are the first genuinely out-of-sample record in this study.`,
  );
  say();
  const wf = new Map<string, WalkForwardResult>();
  const wfRows: (string | number)[][] = [];
  for (const s of STRATEGIES) {
    const r = walkForward(s, research, cfgBase, { trainBars, testBars, mode: "rolling", objective: "sharpe", minTrades: 20, maxCombos: Math.min(MAX_COMBOS, 200), seed: SEED });
    wf.set(s.id, r);
    totalTrials += r.totalTrials;
    wfRows.push([s.id, r.folds.length, r.oos.trades, num(r.oos.netEdgeTicks), num(r.oos.profitFactor), num(r.oos.sharpe), num(r.oos.tStat), num(r.efficiency), pct(r.foldHitRate, 0), usd(r.oos.totalPnl)]);
  }
  say(table(["strategy", "folds", "OOS trades", "net (ticks)", "PF", "Sharpe", "t (HAC)", "WF efficiency", "folds up", "OOS P&L"], wfRows));
  say();
  for (const s of STRATEGIES) {
    const r = wf.get(s.id)!;
    if (r.oos.trades > 0) say(`\`${s.id.padEnd(15)}\` OOS equity: \`${sparkline(cumulative(r.oosDaily))}\``);
  }
  say();
  say(`Parameter stability across folds (share of folds choosing the modal value):`);
  say();
  say(
    table(
      ["strategy", "stability by parameter"],
      STRATEGIES.map((s) => [
        s.id,
        Object.entries(wf.get(s.id)!.paramStability)
          .map(([k, v]) => `${k} ${pct(v, 0)}`)
          .join(", "),
      ]),
    ),
  );
  say();

  // ---- stage 6: deflated sharpe + multiple testing ----
  say(`## 8. Deflated Sharpe and family-wide error control`);
  say();
  say(
    `A backtest Sharpe is the maximum of however many were looked at. The Deflated Sharpe Ratio prices that in ` +
      `using the actual number of configurations evaluated (**${totalTrials}**) and the cross-sectional dispersion of trial Sharpes, ` +
      `together with the skew and fat tails of the realised daily stream. DSR is the probability the true Sharpe exceeds what the best of ${totalTrials} trials would produce by luck.`,
  );
  say();
  const dsrRows: (string | number)[][] = [];
  const dsrById = new Map<string, number>();
  const pRows: { label: string; p: number }[] = [];
  for (const s of STRATEGIES) {
    const r = wf.get(s.id)!;
    const dispersion = trialSharpeDispersion(searches.get(s.id)!.trials.map((t) => t.dailySharpe));
    if (r.oosDaily.length < 30) {
      dsrRows.push([s.id, "n/a", "n/a", "n/a", "n/a", "insufficient OOS days"]);
      dsrById.set(s.id, NaN);
      continue;
    }
    const d = deflatedSharpe(r.oosDaily, totalTrials, dispersion, inst.daysPerYear);
    dsrById.set(s.id, d.dsr);
    const ci = bootstrapCI(r.oosDaily, (x) => sharpeRatio(x, inst.daysPerYear), { samples: 2000, seed: SEED });
    dsrRows.push([
      s.id,
      num(d.annualisedSr),
      `[${num(ci.lower)}, ${num(ci.upper)}]`,
      num(d.expectedMaxSr * Math.sqrt(inst.daysPerYear)),
      num(d.dsr, 3),
      Number.isFinite(d.minTrackRecord) ? `${Math.ceil(d.minTrackRecord)} days` : "never",
    ]);
    pRows.push({ label: s.id, p: r.oos.pValue });
  }
  say(table(["strategy", "OOS Sharpe", "bootstrap 95% CI", "expected max under null", "DSR", "min track record"], dsrRows));
  say();
  if (pRows.length) {
    say(`Multiple-testing correction over the ${pRows.length} strategies carried to walk-forward:`);
    say();
    const corrected = correctMultiple(pRows, 0.05);
    say(
      table(
        ["rank", "strategy", "raw p", "BH q", "Holm p", "survives BH", "survives Holm"],
        corrected.map((c) => [c.rank, c.label, num(c.p, 4), num(c.qBH, 4), num(c.pHolm, 4), c.rejectBH ? "yes" : "no", c.rejectHolm ? "yes" : "no"]),
      ),
    );
    say();
  }

  // ---- stage 7: robustness on the OOS record ----
  say(`## 9. Robustness of the out-of-sample record`);
  say();
  const verdicts = new Map<string, ReturnType<typeof verdict>>();
  for (const s of STRATEGIES) {
    const r = wf.get(s.id)!;
    if (r.oos.trades < 20) continue;
    say(`### ${s.id} — ${s.label}`);
    say();
    say(`*${s.rationale}*`);
    say();
    const modal = modalParams(r.folds.map((f) => f.params));
    const cs = costSensitivity(s, research, modal, cfgBase);
    say(
      table(
        ["cost multiple", ...cs.points.map((p) => `${p.multiple}x`)],
        [
          ["cost (ticks)", ...cs.points.map((p) => num(p.costTicks, 2))],
          ["expectancy ($/trade)", ...cs.points.map((p) => num(p.expectancyUsd, 2))],
          ["Sharpe", ...cs.points.map((p) => num(p.sharpe, 2))],
        ],
      ),
    );
    say();
    say(`Cost tolerance: **${cs.verdict}** (modelled cost ${cs.baseCostTicks.toFixed(2)} ticks).`);
    say();

    const regimes = regimeBreakdown(r.oosTrades, research);
    const cons = subPeriodConsistency(r.oosTrades, 6);
    const mc = monteCarloTrades(r.oosTrades, { paths: 5000, seed: SEED, startEquity: 100_000 });
    say(
      table(
        ["probe", "result"],
        [
          ["profitable OOS sub-periods (6ths)", pct(cons.profitableShare, 0)],
          ["worst sub-period", usd(cons.worstChunkPnl)],
          ["best year's share of P&L", pct(regimes.bestYearShare, 0)],
          ["profitable years", pct(regimes.profitableYearShare, 0)],
          ["profitable hours of day", pct(regimes.profitableHourShare, 0)],
          ["Monte Carlo median maxDD", pct(mc.drawdownP50)],
          ["Monte Carlo 95th pct maxDD", pct(mc.drawdownP95)],
          ["P(losing overall) across orderings", pct(mc.probLoss, 0)],
          ["P(25% drawdown)", pct(mc.probRuin, 0)],
          ["median worst losing streak", mc.medianMaxLosingStreak],
        ],
      ),
    );
    say();
    say(`By exit reason: ${regimes.byExitReason.map((b) => `${b.key} ${b.trades} (${usd(b.pnl)})`).join(" · ")}`);
    say();
    say(`By volatility tercile: ${regimes.byVolTercile.map((b) => `${b.key} ${usd(b.pnl)}`).join(" · ")}`);
    say();
    const v = verdict({
      oos: r.oos,
      pbo: pboById.get(s.id) ?? 1,
      dsr: dsrById.get(s.id) ?? 0,
      cost: cs,
      plateau: plateauReport(searches.get(s.id)!, s.space).verdict,
      consistency: cons.profitableShare,
      bestYearShare: regimes.bestYearShare,
      wfEfficiency: r.efficiency,
    });
    verdicts.set(s.id, v);
    say(`**Gates passed ${v.passes.length}/${v.passes.length + v.failures.length}.**`);
    say();
    for (const p of v.passes) say(`- PASS — ${p}`);
    for (const f of v.failures) say(`- FAIL — ${f}`);
    say();
  }

  // ---- stage 9: portfolio ----
  say(`## 10. Portfolio combination`);
  say();
  // The time-of-day control is a null benchmark, not a candidate — it never enters a portfolio.
  const live = ALPHA_CANDIDATES.filter((s) => (wf.get(s.id)?.oos.trades ?? 0) >= 20);
  if (live.length >= 2) {
    const aligned = alignDaily(live.map((s) => ({ label: s.id, dailyPnl: wf.get(s.id)!.oosDailyPnl })));
    const corr = correlationMatrix(aligned.matrix);
    say(`Correlation of walk-forward out-of-sample daily P&L:`);
    say();
    say(
      table(
        ["", ...aligned.labels],
        aligned.labels.map((l, i) => [l, ...corr[i].map((v) => num(v, 2))]),
      ),
    );
    say();
    const pruned = pruneCorrelated(aligned, 0.7);
    if (pruned.dropped.length) {
      say(`Pruned as near-duplicates (|r| > 0.7): ${pruned.dropped.map((d) => `${aligned.labels[d.index]} vs ${aligned.labels[d.against]} (r=${d.corr.toFixed(2)})`).join(", ")}`);
      say();
    }
    const rows: (string | number)[][] = [];
    for (const scheme of ["equal", "inverse-vol", "risk-parity", "min-variance"] as const) {
      const p = buildPortfolio(aligned, scheme, inst.daysPerYear);
      rows.push([scheme, num(p.sharpe), num(p.tStat), num(p.diversificationRatio), num(p.averagePairwiseCorrelation, 2), num(p.sharpeUplift), p.weights.map((w) => (w * 100).toFixed(0) + "%").join(" / ")]);
    }
    say(table(["scheme", "Sharpe", "t (HAC)", "diversification", "avg pairwise r", "uplift vs best single", "weights"], rows));
    say();
    say(`Weights are in risk units — each stream is scaled to unit daily volatility first, so a weight is a share of risk, not of dollars.`);
  } else {
    say(`Fewer than two strategies produced a usable out-of-sample record; there is nothing to combine.`);
  }
  say();

  // ---- stage 10: holdout ----
  say(`## 11. Locked holdout — evaluated once`);
  say();
  say(
    `Parameters are frozen to the modal walk-forward choice (the value each parameter took in the most folds) and run over ` +
      `the held-back final ${pct(HOLDOUT, 0)} of the sample, which no stage above has touched. This is the only number in the study ` +
      `that has never influenced a decision.`,
  );
  say();
  const holdRows: (string | number)[][] = [];
  for (const s of STRATEGIES) {
    const r = wf.get(s.id);
    if (!r || !r.folds.length) continue;
    const modal = modalParams(r.folds.map((f) => f.params));
    const res = runStrategy(s, holdout, modal, cfgBase);
    const sum = summarize(res, holdout, inst);
    holdRows.push(summaryRow(s.id, sum));
  }
  say(table(SUMMARY_HEADERS, holdRows));
  say();

  // ---- conclusion ----
  say(`## 12. Verdict`);
  say();
  const tradeable = [...verdicts.entries()].filter(([, v]) => v.tradeable).map(([k]) => k);
  const partial = [...verdicts.entries()].filter(([, v]) => !v.tradeable && v.score >= 0.7).map(([k, v]) => `${k} (${v.passes.length}/${v.passes.length + v.failures.length})`);
  say(
    table(
      ["strategy", "gates passed", "status"],
      [...verdicts.entries()].map(([k, v]) => [k, `${v.passes.length}/${v.passes.length + v.failures.length}`, v.tradeable ? "cleared all gates" : v.score >= 0.7 ? "partial — not tradeable" : "rejected"]),
    ),
  );
  say();
  if (tradeable.length) say(`Cleared every gate: **${tradeable.join(", ")}**. Next step is forward paper trading, not sizing up.`);
  else say(`**No strategy cleared every gate.** On this instrument, session and cost model, the honest conclusion is that none of the tested rules demonstrates an edge that survives costs, search deflation and out-of-sample testing.`);
  if (partial.length) say(`Partial passes worth another research cycle: ${partial.join(", ")}.`);
  say();
  say(`---`);
  say();
  say(`Runtime ${((Date.now() - t0) / 1000).toFixed(1)}s · configurations evaluated ${totalTrials} · seed ${SEED}.`);

  mkdirSync(dirname(OUT), { recursive: true });
  writeFileSync(OUT, md.join("\n") + "\n");
  console.error(`\nwrote ${OUT}`);
}

/** The value each parameter took in the most walk-forward folds — a stability-weighted freeze. */
function modalParams(list: Params[]): Params {
  const out: Params = {};
  if (!list.length) return out;
  for (const k of Object.keys(list[0])) {
    const counts = new Map<number, number>();
    for (const p of list) counts.set(p[k], (counts.get(p[k]) ?? 0) + 1);
    let bestV = list[0][k];
    let bestN = -1;
    for (const [v, n] of counts) if (n > bestN) { bestN = n; bestV = v; }
    out[k] = bestV;
  }
  return out;
}

main();
