import { readFileSync } from "node:fs";
import { auditBars, parseCsv } from "../src/lib/quant/data";
import { clockFor, inWindow } from "../src/lib/quant/clock";
import { instrument, roundTurnCostTicks } from "../src/lib/quant/instruments";
import { runStrategy } from "../src/lib/quant/backtest";
import { summarize } from "../src/lib/quant/stats";
import { STRATEGIES } from "../src/lib/quant/strategies";

const t0 = Date.now();
const bars = parseCsv(readFileSync("data/NQ_5m.csv", "utf8"));
const audit = auditBars(bars);
console.log("audit:", JSON.stringify({ ...audit, notes: audit.notes }, null, 1));

const inst = instrument("NQ");
const clock = clockFor(bars, inst.tz);
const rth = bars.filter((_, i) => inWindow(clock.minuteOfDay[i], inst.session[0], inst.session[1]));
console.log(`RTH bars: ${rth.length} (${(Date.now() - t0) / 1000}s to load)`);
console.log(`round-turn cost: ${roundTurnCostTicks(inst).toFixed(2)} ticks = $${(roundTurnCostTicks(inst) * inst.tickValue).toFixed(2)}`);

for (const s of STRATEGIES) {
  const t = Date.now();
  const res = runStrategy(s, rth, s.defaults, { inst });
  const sum = summarize(res, rth, inst);
  console.log(
    `${s.id.padEnd(16)} trades=${String(sum.trades).padStart(5)} win=${(sum.winRate * 100).toFixed(1)}% ` +
      `gross=${sum.grossEdgeTicks.toFixed(2)}t cost=${sum.costTicks.toFixed(2)}t net=${sum.netEdgeTicks.toFixed(2)}t ` +
      `PF=${sum.profitFactor.toFixed(2)} SR=${sum.sharpe.toFixed(2)} t=${sum.tStat.toFixed(2)} pnl=$${sum.totalPnl.toFixed(0)} (${Date.now() - t}ms)`,
  );
}
