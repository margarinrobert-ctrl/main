/**
 * Dump the TypeScript engine's trades to csv, so the Python layer can be checked against it
 * trade-for-trade rather than on summary statistics — two engines can agree on expectancy while
 * disagreeing about which trades they took.
 *
 * Usage: npx tsx scripts/quant-export-trades.ts <out.csv> [retrPct] [stopPct] [rrMult]
 */
import { writeFileSync } from "node:fs";
import { readFileSync } from "node:fs";
import { runStrategy } from "../src/lib/quant/backtest";
import { clockFor, inWindow } from "../src/lib/quant/clock";
import { parseCsv } from "../src/lib/quant/data";
import { instrument } from "../src/lib/quant/instruments";
import { summarize } from "../src/lib/quant/stats";
import { initialBalance as S } from "../src/lib/quant/strategies";

const out = process.argv[2] ?? "/tmp/ts_trades.csv";
const retrPct = Number(process.argv[3] ?? 50);
const stopPct = Number(process.argv[4] ?? 80);
const rrMult = Number(process.argv[5] ?? 2);

const inst = { ...instrument("NQ"), session: [570, 719] as [number, number] };
const cfg = { inst, fillModel: "realistic" as const };
const bars = parseCsv(readFileSync("data/NQ_1m.csv", "utf8"));
const ck = clockFor(bars, inst.tz);
const seg = bars.filter((_, i) => inWindow(ck.minuteOfDay[i], 570, 719));

const P = { ...S.defaults, ibMinutes: 60, retrPct, stopPct, rrMode: 1, rrMult, sideMode: 0, minRangePct: 0, maxRangePct: 100, breakBuffer: 0 };
const res = runStrategy(S, seg, P, cfg);
const s = summarize(res, seg, inst);

const rows = ["entryIndex,exitIndex,side,entryPx,exitPx,pnl,r,reason"];
for (const t of res.trades) {
  rows.push([t.entryIndex, t.exitIndex, t.side, t.entryPx, t.exitPx, t.pnl.toFixed(6), t.r.toFixed(6), t.reason].join(","));
}
writeFileSync(out, rows.join("\n"));
console.log(`${res.trades.length} trades -> ${out}`);
console.log(`  n=${s.trades} win=${(s.winRate * 100).toFixed(2)}% E=${s.expectancyR.toFixed(4)}R PF=${s.profitFactor.toFixed(4)} $${s.totalPnl.toFixed(2)}`);
console.log(`  segment bars = ${seg.length}`);
