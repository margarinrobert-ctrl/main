/**
 * The wire format between the worker and the page, and the projection that produces it.
 *
 * This is a policy file, not plumbing. `publicRow` is an explicit ALLOW-LIST: a field added to
 * `SweepRow` later is invisible to the UI until someone deliberately exposes it here, whereas the
 * deny-list it replaces (`{...row, locked: undefined}`) would have leaked it by default. The field
 * that must never make the trip is `SweepRow.locked`, and `tuner.test.ts` asserts it does not.
 *
 * It lives apart from `worker.ts` so the projection can be imported and tested without a
 * `WorkerGlobalScope` — importing the worker module runs its `self.onmessage` assignment, which is
 * a ReferenceError anywhere but a worker.
 */
import type { BlockPerf } from "./performance";
import type { ConfigRef, RankKey, SweepRow } from "./index";

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
  /** Geometries one tensor can hold under the memory budget — the batch size the sweep will use. */
  geometriesPerTensor: number;
}

export interface PublicRow {
  key: string;
  rule: string;
  params: Record<string, number>;
  side: 1 | -1;
  window: string;
  stop: number;
  target: number;
  maxBars: number;
  costLabel: string;
  /** RESEARCH block. There is no locked-block number anywhere on this type. */
  research: BlockPerf;
}

export function publicRow(r: SweepRow): PublicRow {
  return {
    key: r.key,
    rule: r.rule,
    params: r.params,
    side: r.side,
    window: r.window,
    stop: r.stop,
    target: r.target,
    maxBars: r.maxBars,
    costLabel: r.costLabel,
    research: r.research,
  };
}

export interface PublicSweep {
  rows: PublicRow[];
  evaluated: number;
  dropped: number;
  minTrades: number;
  rankBy: RankKey;
  ms: number;
  tensorMs: number;
  tensors: number;
  cache: { tensorBytes: number; indicatorBytes: number };
}

export interface PublicReveal {
  row: PublicRow;
  window: string;
  locked: BlockPerf;
  control: { draws: number; meanResearch: number; meanLocked: number; pResearch: number; pLocked: number };
  shape: "decays" | "grew-on-locked";
  searched: number;
  bonferroni: number;
}

export interface PublicTrade {
  signalBar: number;
  entryBar: number;
  exitBar: number;
  reason: string;
  pnl: number;
  /** Signal bar timestamp, epoch ms — enough to bucket by month without shipping the bar array. */
  ms: number;
}

export interface PublicDetail {
  key: string;
  ref: ConfigRef;
  research: BlockPerf;
  /** Per-session P&L across the research block, flat sessions included. */
  daily: number[];
  /** The market factor the residual statistics regress out, same index as `daily`. */
  market: number[];
  trades: PublicTrade[];
}
