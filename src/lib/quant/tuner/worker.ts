/// <reference lib="webworker" />
/**
 * The tuner runs in a Web Worker.
 *
 * Building an exit tensor over a few hundred thousand bars is hundreds of milliseconds and a sweep
 * can be seconds; on the main thread that is a frozen tab and a text box that will not accept
 * keystrokes. The worker also owns the `TunerSession`, which is what keeps the bar set, the
 * memoised indicator arrays and the tensors alive between messages — that caching is the entire
 * reason a second question is faster than the first, and it would be thrown away by any design
 * that recomputed per request.
 */
import { describe as describeCosts, feesRoundTurn, scheduleFor } from "../costs";
import { instrument, roundTurnCostTicks } from "../instruments";
import { parseCsv } from "../data";
import { syntheticSeries } from "../synth";
import type { Bar, Instrument } from "../types";
import { catalogue, resampleBars, TunerSession, type Config, type RevealRow, type SweepAxes, type SweepResult } from "./index";
import type { WalkTrade } from "./tensor";

type Req =
  | {
      id: number;
      kind: "load";
      source: { type: "csv"; text: string } | { type: "demo"; days: number };
      symbol: string;
      timeframe: number;
      /** Broker preset from `costs.ts`. Changes the fee lines, not the slippage model. */
      broker?: string;
    }
  | { id: number; kind: "run"; config: Config; controlDraws: number }
  | { id: number; kind: "sweep"; axes: SweepAxes }
  | { id: number; kind: "reveal"; keys: string[]; draws: number }
  | { id: number; kind: "catalogue" };

export interface LoadedInfo {
  bars: number;
  sessions: number;
  timeframe: number;
  symbol: string;
  firstMs: number;
  lastMs: number;
  researchSessions: number;
  lockedSessions: number;
  synthetic: boolean;
  /** The cost breakdown actually in force, so the page can show what it charged. */
  costs: string;
  roundTurnTicks: number;
}

let session: TunerSession | null = null;
let lastSweep: SweepResult | null = null;
let info: LoadedInfo | null = null;

function need(): TunerSession {
  if (!session) throw new Error("load a bar file first");
  return session;
}

function load(msg: Extract<Req, { kind: "load" }>): LoadedInfo {
  const base: Instrument = instrument(msg.symbol);
  // The broker preset changes the FEE lines only. Spread and the slippage model belong to the
  // instrument and the market, not to who clears the trade.
  const fees = scheduleFor(msg.symbol, msg.broker ?? "discount");
  const inst: Instrument = { ...base, fees, commissionRoundTurn: feesRoundTurn(fees) };
  let raw: Bar[];
  let synthetic = false;
  if (msg.source.type === "demo") {
    // Clearly-labelled synthetic bars so the controls can be tried without a licensed file.
    // They have NO edge in them by construction, which also makes them the right null: any rule
    // that looks good here is measuring the search, not the market.
    raw = syntheticSeries(msg.symbol.toUpperCase() === "MNQ" ? "NQ" : msg.symbol, { days: msg.source.days, seed: 20260824 });
    synthetic = true;
  } else {
    raw = parseCsv(msg.source.text);
  }
  if (raw.length < 500) throw new Error(`only ${raw.length} bars parsed — expected timestamp,open,high,low,close,volume`);
  const bars = resampleBars(raw, msg.timeframe, inst);
  session = new TunerSession(bars, inst, `${msg.symbol}|${msg.timeframe}`);
  lastSweep = null;
  info = {
    bars: bars.length,
    sessions: session.sessionCount,
    timeframe: msg.timeframe,
    symbol: msg.symbol,
    firstMs: bars[0].t,
    lastMs: bars[bars.length - 1].t,
    researchSessions: Math.floor(session.sessionCount * 0.65),
    lockedSessions: session.sessionCount - Math.floor(session.sessionCount * 0.65),
    synthetic,
    costs: describeCosts(inst),
    roundTurnTicks: roundTurnCostTicks(inst),
  };
  return info;
}

self.onmessage = (ev: MessageEvent<Req>) => {
  const msg = ev.data;
  const reply = (payload: unknown) => (self as unknown as Worker).postMessage({ id: msg.id, ok: true, payload });
  const fail = (e: unknown) => (self as unknown as Worker).postMessage({ id: msg.id, ok: false, error: e instanceof Error ? e.message : String(e) });
  try {
    switch (msg.kind) {
      case "catalogue":
        return reply(catalogue());
      case "load":
        return reply(load(msg));
      case "run": {
        const out = need().run(msg.config, msg.controlDraws);
        // The trade list can be tens of thousands of rows and the UI only draws an equity curve,
        // so send a compact cumulative series instead of the trades themselves.
        const eq: number[] = [];
        let acc = 0;
        for (const t of out.trades as WalkTrade[]) {
          acc += t.pnl;
          eq.push(acc);
        }
        return reply({ stats: out.stats, control: out.control, triggers: out.triggers, equity: eq, info });
      }
      case "sweep": {
        const res = need().sweep(msg.axes, (done, total) => {
          (self as unknown as Worker).postMessage({ id: msg.id, progress: { done, total } });
        });
        lastSweep = res;
        // `ref` holds live typed arrays; strip it for the structured clone and key rows instead.
        return reply({
          rows: res.rows.map((r) => ({ ...r, ref: undefined, lockedInternal: undefined })),
          evaluated: res.evaluated,
          dropped: res.dropped,
          minTrades: res.minTrades,
          ms: res.ms,
          tensorMs: res.tensorMs,
        });
      }
      case "reveal": {
        if (!lastSweep) throw new Error("run a sweep before revealing the locked block");
        const chosen = msg.keys.map((k) => {
          const row = lastSweep!.rows.find((r) => r.key === k);
          if (!row) throw new Error("that configuration is not in the current sweep");
          return row;
        });
        const revealed: RevealRow[] = need().reveal(lastSweep, chosen, msg.draws);
        return reply(revealed.map((r) => ({ ...r, row: { ...r.row, ref: undefined, lockedInternal: undefined } })));
      }
    }
  } catch (e) {
    fail(e);
  }
};
