/// <reference lib="webworker" />
/**
 * The tuner runs in a Web Worker, and — the part that matters — it YIELDS while it runs.
 *
 * Building an exit tensor over a few hundred thousand bars is hundreds of milliseconds and a sweep
 * can be seconds; on the main thread that is a frozen tab and a text box that will not accept
 * keystrokes. Moving it to a worker fixes the text box and nothing else, because a worker is also
 * single-threaded: a sweep that runs to completion inside one `onmessage` handler cannot see the
 * message asking it to stop, so every superseded sweep still runs in full and the next one queues
 * behind it. Turning a stop list into `1,1.5,2,2.5` one keystroke at a time used to enqueue ten
 * sweeps and wait for all ten.
 *
 * So the sweep is a generator here, driven a time-slice at a time with a real macrotask between
 * slices. That gives the event loop a chance to deliver pending messages, which is what makes
 * cancellation possible at all — and a new sweep implicitly cancels the one it supersedes.
 *
 * The worker also owns the `TunerSession`, which keeps the bar set, the memoised indicator arrays
 * and the tensors alive between messages — that caching is the entire reason a second question is
 * faster than the first, and it would be thrown away by any design that recomputed per request.
 */
import { instrument } from "../instruments";
import { parseCsv } from "../data";
import { syntheticSeries } from "../synth";
import type { Bar, Instrument } from "../types";
import { catalogue, resampleBars, TunerSession, type Config, type SweepAxes, type SweepResult, type SweepRow } from "./index";
import { publicRow, type LoadedInfo, type PublicDetail, type PublicSweep } from "./project";
import type { WalkTrade } from "./tensor";

export * from "./project";

type Source = { type: "csv"; text?: string; file?: File } | { type: "demo"; days: number };

type Req =
  | { id: number; kind: "load"; source: Source; symbol: string; timeframe: number }
  | { id: number; kind: "run"; config: Config; controlDraws: number }
  | { id: number; kind: "sweep"; axes: SweepAxes }
  | { id: number; kind: "reveal"; keys: string[]; draws: number }
  | { id: number; kind: "detail"; key: string }
  | { id: number; kind: "cancel" }
  | { id: number; kind: "cacheStats" }
  | { id: number; kind: "catalogue" };

let session: TunerSession | null = null;
let lastSweep: SweepResult | null = null;
let info: LoadedInfo | null = null;

/** The job currently occupying the worker, if any. A new sweep supersedes it. */
let running: { id: number; cancelled: boolean } | null = null;

const post = (m: unknown) => (self as unknown as Worker).postMessage(m);

function need(): TunerSession {
  if (!session) throw new Error("load a bar file first");
  return session;
}

/**
 * Hand the event loop a turn.
 *
 * `setTimeout(0)` would do it, except that after five nested timers browsers clamp it to 4ms — on
 * an 8ms slice that is a third of the run spent waiting. A MessageChannel task is not clamped.
 */
const channel = typeof MessageChannel !== "undefined" ? new MessageChannel() : null;
function yieldToEventLoop(): Promise<void> {
  if (!channel) return new Promise((resolve) => setTimeout(resolve, 0));
  return new Promise((resolve) => {
    channel.port1.onmessage = () => resolve();
    channel.port2.postMessage(0);
  });
}

async function load(msg: Extract<Req, { kind: "load" }>): Promise<LoadedInfo> {
  const inst: Instrument = instrument(msg.symbol);
  let raw: Bar[];
  let synthetic = false;
  if (msg.source.type === "demo") {
    // Clearly-labelled synthetic bars so the controls can be tried without a licensed file.
    // They have NO edge in them by construction, which also makes them the right null: any rule
    // that looks good here is measuring the search, not the market.
    raw = syntheticSeries(msg.symbol.toUpperCase() === "MNQ" ? "NQ" : msg.symbol, { days: msg.source.days, seed: 20260824 });
    synthetic = true;
  } else {
    // Reading the File HERE rather than on the main thread is deliberate: `file.text()` on a
    // hundred-megabyte CSV blocks whatever thread calls it, and the resulting string then has to
    // be structure-cloned across. A File is a Blob handle and crosses for free.
    const text = msg.source.file ? await msg.source.file.text() : msg.source.text;
    if (text === undefined) throw new Error("no CSV content was sent");
    raw = parseCsv(text);
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
    researchSessions: session.lockedFromOrdinal,
    lockedSessions: session.sessionCount - session.lockedFromOrdinal,
    synthetic,
    geometriesPerTensor: session.batchSize(),
  };
  return info;
}

/** Drive the sweep generator, yielding whenever the current time slice is used up. */
async function runSweep(id: number, axes: SweepAxes): Promise<PublicSweep> {
  const job = { id, cancelled: false };
  if (running) running.cancelled = true;
  running = job;
  const s = need();
  const it = s.sweepIter(axes);
  const SLICE_MS = 8;
  let sliceStart = Date.now();
  let lastReport = 0;
  try {
    for (;;) {
      const step = it.next();
      if (step.done) {
        // Only a run that finished replaces the result `reveal` and `detail` read, so a cancelled
        // sweep can never leave the UI showing rows whose keys no longer resolve.
        lastSweep = step.value;
        return { ...step.value, rows: step.value.rows.map(publicRow) };
      }
      if (Date.now() - sliceStart < SLICE_MS) continue;
      const p = step.value;
      // Progress messages are throttled separately: a repaint is worth ~10 a second, not 120.
      if (Date.now() - lastReport > 80) {
        lastReport = Date.now();
        post({ id, progress: { done: p.done, total: p.total, phase: p.phase } });
      }
      await yieldToEventLoop();
      if (job.cancelled) throw new CancelledError();
      sliceStart = Date.now();
    }
  } finally {
    if (running === job) running = null;
  }
}

class CancelledError extends Error {
  readonly cancelled = true;
  constructor() {
    super("cancelled");
  }
}

function rowFor(key: string): SweepRow {
  if (!lastSweep) throw new Error("run a sweep before asking about one of its rows");
  const row = lastSweep.rows.find((r) => r.key === key);
  if (!row) throw new Error("that configuration is not in the current sweep");
  return row;
}

function detail(key: string): PublicDetail {
  const row = rowFor(key);
  const d = need().detail(row.ref);
  return {
    key,
    ref: row.ref,
    research: d.research,
    daily: Array.from(d.dailyResearch),
    market: Array.from(d.marketResearch),
    trades: d.trades.map((t: WalkTrade, k: number) => ({
      signalBar: t.signalBar,
      entryBar: t.entryBar,
      exitBar: t.exitBar,
      reason: t.reason,
      pnl: t.pnl,
      ms: d.tradeMs[k],
    })),
  };
}

self.onmessage = async (ev: MessageEvent<Req>) => {
  const msg = ev.data;
  const reply = (payload: unknown) => post({ id: msg.id, ok: true, payload });
  const fail = (e: unknown) =>
    post({
      id: msg.id,
      ok: false,
      error: e instanceof Error ? e.message : String(e),
      cancelled: e instanceof CancelledError,
    });
  try {
    switch (msg.kind) {
      case "catalogue":
        return reply(catalogue());
      case "cancel":
        if (running) running.cancelled = true;
        return reply({ cancelled: true });
      case "cacheStats":
        return reply(session ? session.cacheStats() : null);
      case "load":
        if (running) running.cancelled = true;
        return reply(await load(msg));
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
        return reply({ research: out.research, control: out.control, triggers: out.triggers, equity: eq, info });
      }
      case "sweep": {
        const res = await runSweep(msg.id, msg.axes);
        return reply(res);
      }
      case "reveal": {
        if (!lastSweep) throw new Error("run a sweep before revealing the locked block");
        const chosen = msg.keys.map(rowFor);
        const revealed = need().reveal(lastSweep, chosen, msg.draws);
        return reply(
          revealed.map((r) => ({
            row: publicRow(r.row),
            window: r.window,
            locked: r.locked,
            control: r.control,
            shape: r.shape,
            searched: r.searched,
            bonferroni: r.bonferroni,
          })),
        );
      }
      case "detail":
        return reply(detail(msg.key));
    }
  } catch (e) {
    fail(e);
  }
};
