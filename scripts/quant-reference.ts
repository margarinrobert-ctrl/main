/**
 * Print a single strategy's reference statistics, so a port to another platform (Pine, Python, a
 * broker's own tester) can be checked against this engine instead of merely looking plausible.
 *
 *   npx tsx scripts/quant-reference.ts --strategy ou-reversion --data data/NQ_5m.csv --symbol NQ
 */
import { readFileSync } from "node:fs";
import { runStrategy } from "../src/lib/quant/backtest";
import { clockFor, hhmm, inWindow } from "../src/lib/quant/clock";
import { parseCsv } from "../src/lib/quant/data";
import { instrument, roundTurnCostTicks } from "../src/lib/quant/instruments";
import { summarize } from "../src/lib/quant/stats";
import { strategy } from "../src/lib/quant/strategies";

const arg = (k: string, d?: string) => {
  const i = process.argv.indexOf(`--${k}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : d;
};

const s = strategy(arg("strategy", "ou-reversion")!);
const inst = instrument(arg("symbol", "NQ")!);
const fill = (arg("fill", "realistic") ?? "realistic") as "taker" | "realistic" | "passive";
const bars = parseCsv(readFileSync(arg("data", "data/NQ_5m.csv")!, "utf8"));
const clock = clockFor(bars, inst.tz);
const session = bars.filter((_, i) => inWindow(clock.minuteOfDay[i], inst.session[0], inst.session[1]));

const params = { ...s.defaults };
for (const k of Object.keys(params)) {
  const v = arg(k);
  if (v !== undefined) params[k] = Number(v);
}

const res = runStrategy(s, session, params, { inst, fillModel: fill });
const sum = summarize(res, session, inst);
const first = session[0], last = session[session.length - 1];

console.log(`strategy   ${s.id} — ${s.label}`);
console.log(`params     ${Object.entries(params).map(([k, v]) => `${k}=${v}`).join(" ")}`);
console.log(`symbol     ${inst.id}  session ${hhmm(inst.session[0])}-${hhmm(inst.session[1])} ${inst.tz}  fill ${fill}`);
console.log(`data       ${session.length.toLocaleString()} bars, ${new Date(first.t).toISOString().slice(0, 10)} -> ${new Date(last.t).toISOString().slice(0, 10)}`);
console.log(`cost       ${roundTurnCostTicks(inst).toFixed(2)} ticks reference; realised mean ${sum.costTicks.toFixed(2)} ticks/trade`);
console.log("");
console.log(`trades          ${sum.trades}`);
console.log(`win rate        ${(sum.winRate * 100).toFixed(1)}%`);
console.log(`gross edge      ${sum.grossEdgeTicks.toFixed(2)} ticks/trade`);
console.log(`net edge        ${sum.netEdgeTicks.toFixed(2)} ticks/trade`);
console.log(`profit factor   ${sum.profitFactor.toFixed(3)}`);
console.log(`total P&L       $${sum.totalPnl.toFixed(0)} (1 contract)`);
console.log(`avg bars held   ${sum.avgBarsHeld.toFixed(1)}`);
console.log(`max drawdown    ${(sum.maxDrawdownPct * 100).toFixed(1)}%`);
console.log(`Sharpe (daily)  ${sum.sharpe.toFixed(2)}`);
console.log(`HAC t-stat      ${sum.tStat.toFixed(2)}  (p=${sum.pValue.toFixed(3)})`);
console.log(`ambiguous bars  ${res.ambiguousExits} of ${sum.trades} exits resolved as stops`);
const byReason = new Map<string, number>();
for (const t of res.trades) byReason.set(t.reason, (byReason.get(t.reason) ?? 0) + 1);
console.log(`exit reasons    ${[...byReason].map(([k, v]) => `${k} ${v}`).join(", ")}`);
