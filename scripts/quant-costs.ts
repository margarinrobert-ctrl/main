/**
 * What real costs do to every strategy.
 *
 * The cost line used to be one lumped commission plus a flat tick of slippage charged identically
 * on every fill. This reports what changes when it becomes an itemised fee stack (broker,
 * exchange, clearing, regulatory, per side) and a slippage model that depends on how fast the bar
 * was and on how the trade exited.
 *
 * The comparison is deliberately arranged so the new model CANNOT flatter anything: it is
 * calibrated to charge exactly what the old flat model charged on a calm, in-session, market-in /
 * market-out round turn, and to be worse everywhere else. So any strategy that gets cheaper here
 * is a bug, and the script says so.
 *
 *   npx tsx scripts/quant-costs.ts --data data/NQ_5m.csv --symbol NQ
 *   npx tsx scripts/quant-costs.ts --broker premium          (no data file: synthetic bars)
 */
import { readFileSync } from "node:fs";
import { existsSync } from "node:fs";
import { runBacktest } from "../src/lib/quant/backtest";
import {
  BROKER_PRESETS,
  describe as describeCosts,
  feesRoundTurn,
  FLAT_SLIPPAGE,
  scheduleFor,
} from "../src/lib/quant/costs";
import { parseCsv } from "../src/lib/quant/data";
import { instrument, pointsToUsd, roundTurnCostPoints, roundTurnCostTicks, worstRoundTurnCostPoints } from "../src/lib/quant/instruments";
import { STRATEGIES } from "../src/lib/quant/strategies";
import { syntheticSeries } from "../src/lib/quant/synth";
import type { Bar, Instrument } from "../src/lib/quant/types";

function arg(name: string, fallback?: string): string | undefined {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 ? process.argv[i + 1] : fallback;
}

const SYMBOL = (arg("symbol", "NQ") ?? "NQ").toUpperCase();
const DATA = arg("data");
const BROKER = arg("broker", "discount") ?? "discount";

/** The instrument as it was costed BEFORE this change: lumped commission, flat slippage. */
function legacyInstrument(inst: Instrument): Instrument {
  return {
    ...inst,
    fees: undefined,
    slippage: { ...FLAT_SLIPPAGE, base: inst.slippageTicks },
    // The old lumped figure for these products, before the exchange and regulatory lines existed.
    commissionRoundTurn: { NQ: 4.0, ES: 4.0, MNQ: 1.34, GC: 4.5, MGC: 1.5, CL: 4.5, MCL: 1.5 }[inst.id] ?? inst.commissionRoundTurn,
  };
}

function load(): { bars: Bar[]; label: string } {
  if (DATA && existsSync(DATA)) return { bars: parseCsv(readFileSync(DATA, "utf8")), label: DATA };
  return { bars: syntheticSeries(SYMBOL === "MNQ" ? "NQ" : SYMBOL, { days: 500, seed: 7 }), label: "synthetic (no data file given)" };
}

function main(): void {
  const real = instrument(SYMBOL);
  const old = legacyInstrument(real);
  const { bars, label } = load();

  console.log("=".repeat(96));
  console.log(`REAL COSTS — ${SYMBOL}, broker preset "${BROKER}"`);
  console.log("=".repeat(96));
  console.log(describeCosts(real));
  console.log(`\n  worst case (stopped out, fast bar, out of session): ` +
    `${(worstRoundTurnCostPoints(real) / real.tickSize).toFixed(2)} ticks = ` +
    `$${pointsToUsd(real, worstRoundTurnCostPoints(real)).toFixed(2)}`);

  console.log(`\n  BEFORE this change: $${old.commissionRoundTurn.toFixed(2)} lumped commission, ` +
    `flat ${old.slippageTicks} tick(s) every fill  ->  ` +
    `${(roundTurnCostPoints(old) / old.tickSize).toFixed(2)} ticks round turn`);
  console.log(`  AFTER:              $${feesRoundTurn(real.fees!).toFixed(2)} itemised fees, ` +
    `slippage scaled by bar speed and exit type  ->  ` +
    `${roundTurnCostTicks(real).toFixed(2)} ticks on a calm bar`);

  console.log("\n  broker presets, round-turn fees for this product:");
  for (const id of Object.keys(BROKER_PRESETS)) {
    console.log(`    ${id.padEnd(10)} $${feesRoundTurn(scheduleFor(SYMBOL, id)).toFixed(2)}   ${BROKER_PRESETS[id].note}`);
  }

  console.log(`\n${"=".repeat(96)}`);
  console.log(`EVERY STRATEGY, OLD COSTS vs REAL COSTS   [${label}, ${bars.length.toLocaleString()} bars]`);
  console.log("=".repeat(96));
  console.log(
    `  ${"strategy".padEnd(18)}${"trades".padStart(8)}${"old $/tr".padStart(10)}${"real $/tr".padStart(11)}` +
    `${"delta".padStart(9)}${"old net".padStart(11)}${"real net".padStart(11)}  verdict`,
  );

  let flipped = 0;
  let cheaper = 0;
  const costedReal = { ...real, fees: real.fees ? { ...real.fees, brokerPerSide: scheduleFor(SYMBOL, BROKER).brokerPerSide } : undefined };
  const withBroker: Instrument = { ...costedReal, commissionRoundTurn: feesRoundTurn(scheduleFor(SYMBOL, BROKER)), fees: scheduleFor(SYMBOL, BROKER) };

  for (const s of STRATEGIES) {
    const a = runBacktest(bars, s.build(bars, s.defaults, old), { inst: old, units: 1 });
    const b = runBacktest(bars, s.build(bars, s.defaults, withBroker), { inst: withBroker, units: 1 });
    if (a.trades.length < 30) continue;
    const oldPer = a.trades.reduce((x, t) => x + t.pnl, 0) / a.trades.length;
    const realPer = b.trades.reduce((x, t) => x + t.pnl, 0) / Math.max(b.trades.length, 1);
    const oldNet = a.trades.reduce((x, t) => x + t.pnl, 0);
    const realNet = b.trades.reduce((x, t) => x + t.pnl, 0);
    const delta = realPer - oldPer;
    let verdict = "";
    if (delta > 0.01) {
      verdict = "CHEAPER — investigate, the new model should never discount";
      cheaper++;
    } else if (oldNet > 0 && realNet <= 0) {
      verdict = "was profitable, now is not";
      flipped++;
    } else if (realNet > 0) {
      verdict = "still positive";
    } else {
      verdict = "negative either way";
    }
    console.log(
      `  ${s.id.padEnd(18)}${String(b.trades.length).padStart(8)}${oldPer.toFixed(2).padStart(10)}` +
      `${realPer.toFixed(2).padStart(11)}${delta.toFixed(2).padStart(9)}` +
      `${Math.round(oldNet).toLocaleString().padStart(11)}${Math.round(realNet).toLocaleString().padStart(11)}  ${verdict}`,
    );
  }

  console.log(`\n  ${flipped} strategy(ies) crossed from profitable to unprofitable on real costs.`);
  if (cheaper > 0) {
    console.log(`  ${cheaper} got CHEAPER, which should be impossible — the new model is calibrated to match`);
    console.log(`  the old one on a calm round turn and to be worse elsewhere. Investigate before trusting this.`);
  }
  console.log("\n  Fee values are dated assumptions, not quotes. Replace them with your own statement");
  console.log("  and the current CME schedule before sizing any real risk.");
}

main();
