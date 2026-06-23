import type { HistoryBar, OptionContract } from "../barchart/types";
import type { GexSample } from "../gex-history";
import { netDex, putCallRatio } from "../flow/analytics";
import type { AnomalyIntel } from "../flow/anomalyPro";
import type { SignalBoard } from "../flow/signals";
import type { MMHedge } from "../flow/mmhedge";
import { resolveForSymbol } from "./resolve";

// Centralised prediction journal — the historical database behind the performance-intelligence layer.
// Every directional call the platform makes (anomaly engine, signal board, MM-hedge plan) is recorded
// with its inputs, confidence, target/stop, regime, market conditions and a numeric feature snapshot.
// Later, the recorded session price series (GexSample spots) RESOLVES each matured prediction against
// what price actually did — yielding REAL hit-rate, calibration, edge-decay and feature analytics.
//
// HONEST SCOPE: this is browser-local (localStorage) and resolves off the intraday session series, so
// long-horizon calls only resolve while you keep tabs open and metrics stabilise after enough samples.
// No fabricated results — every outcome is measured from actual recorded price.

export type IntelDir = "bullish" | "bearish" | "neutral";
export type IntelSource = "anomaly" | "signals" | "mmhedge";

export interface Outcome {
  resolvedAt: number;
  exit: number;
  realizedReturn: number; // (exit-entry)/entry
  dirReturn: number; // directional return = sign(direction) * realizedReturn
  correct: boolean; // directional call was right
  hitTarget: boolean | null;
  hitStop: boolean | null;
  mfe: number; // max favourable excursion over the path (fraction, ≥0)
  mae: number; // max adverse excursion over the path (fraction, ≥0)
  brier: number; // (confidence/100 − correct)²
  bars: number; // samples spanned
}

export interface PredictionRecord {
  id: string;
  t: number; // epoch ms recorded
  symbol: string;
  source: IntelSource;
  model: string; // sub-strategy label for ranking/grouping
  label: string; // human description
  direction: IntelDir;
  confidence: number; // 0..100 — model's stated probability the call is correct
  strength: number | null;
  entry: number;
  target: number | null;
  stop: number | null;
  horizonMs: number;
  regime: "long" | "short" | "unknown";
  volRegime: string;
  features: Record<string, number>;
  conditions: { netGex: number | null; flip: number | null; iv: number | null; pcr: number | null; relVol: number | null };
  outcome: Outcome | null;
}

const KEY = "intel:journal";
const CAP = 2500;
const MIN_GAP_MS = 4 * 60_000; // collapse repeat same-direction calls from one source within 4 min

export const HORIZON_MS: Record<string, number> = {
  "5m": 5 * 60_000,
  "15m": 15 * 60_000,
  "30m": 30 * 60_000,
  "1h": 60 * 60_000,
  "4h": 4 * 60 * 60_000,
  "1d": 24 * 60 * 60_000,
};

export function readJournal(): PredictionRecord[] {
  if (typeof window === "undefined") return [];
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(v) ? (v as PredictionRecord[]) : [];
  } catch {
    return [];
  }
}

export function writeJournal(records: PredictionRecord[]): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(KEY, JSON.stringify(records.slice(-CAP)));
  } catch {
    /* storage full / disabled — ignore */
  }
}

export function readJournalFor(symbol: string): PredictionRecord[] {
  const s = symbol.toUpperCase();
  return readJournal().filter((r) => r.symbol === s);
}

/** Should a freshly-built candidate be journaled, or is it a near-duplicate of the last same-source call? */
export function shouldRecord(journal: PredictionRecord[], cand: PredictionRecord, minGapMs = MIN_GAP_MS): boolean {
  let last: PredictionRecord | undefined;
  for (const r of journal) if (r.symbol === cand.symbol && r.source === cand.source && (!last || r.t > last.t)) last = r;
  if (!last) return true;
  return cand.direction !== last.direction || cand.t - last.t >= minGapMs;
}

function relativeVolume(daily: HistoryBar[]): number {
  const vols = daily.map((b) => b.volume).filter((x) => x > 0);
  if (vols.length < 6) return 1;
  const base = vols.slice(-21, -1);
  const m = base.reduce((s, x) => s + x, 0) / base.length;
  return m > 0 ? vols[vols.length - 1] / m : 1;
}

function horizonFromText(h: string): number {
  const s = h.toLowerCase();
  if (s.includes("scalp") || s.includes("0–1") || s.includes("0-1") || s.includes("0dte")) return HORIZON_MS["1h"];
  if (s.includes("intraday")) return HORIZON_MS["4h"];
  return HORIZON_MS["1d"];
}

const uid = (src: string, sym: string, t: number) => `${src}-${sym}-${t}-${Math.random().toString(36).slice(2, 7)}`;

/** Shared numeric feature snapshot + market conditions used by every source's record. */
function snapshot(chain: OptionContract[], spot: number, bars: HistoryBar[], intel: AnomalyIntel, board: SignalBoard, mm: MMHedge) {
  const flip = mm.flip;
  const pcr = putCallRatio(chain).vol;
  const relVol = relativeVolume(bars);
  const features: Record<string, number> = {
    strength: intel.strength,
    pUp: intel.bullish,
    confidence: intel.confidence,
    biasScore: board.biasScore,
    pressureScore: mm.pressureScore,
    conviction: mm.conviction,
    netGex: mm.netGex ?? 0,
    netDex: netDex(chain, spot) ?? 0,
    ivPct: (mm.frontIv ?? 0) * 100,
    pcr: pcr ?? 0,
    flipDistPct: flip != null && spot ? ((spot - flip) / spot) * 100 : 0,
    relVol,
    charmFlow: mm.charmFlow ?? 0,
    vannaFlow: mm.vannaFlow ?? 0,
  };
  const conditions = { netGex: mm.netGex, flip, iv: mm.frontIv, pcr, relVol };
  return { features, conditions, volRegime: intel.quant["Vol regime"] ?? "n/a" };
}

/** Build candidate records (one per source) from the current engine outputs. Neutral/'wait' → skipped. */
export function buildCandidates(symbol: string, t: number, chain: OptionContract[], spot: number | null, bars: HistoryBar[], intel: AnomalyIntel, board: SignalBoard, mm: MMHedge): PredictionRecord[] {
  if (spot == null || spot <= 0 || !chain.length) return [];
  const sym = symbol.toUpperCase();
  const { features, conditions, volRegime } = snapshot(chain, spot, bars, intel, board, mm);
  const common = { symbol: sym, t, entry: spot, regime: mm.regime, volRegime, features, conditions, outcome: null as Outcome | null };
  const out: PredictionRecord[] = [];

  // 1) Anomaly engine — primary, fast-resolving source
  if (!intel.neutral && intel.strength > 0) {
    const dir: IntelDir = intel.bullish >= 50 ? "bullish" : "bearish";
    const em = intel.expectedMove;
    out.push({
      ...common,
      id: uid("anomaly", sym, t),
      source: "anomaly",
      model: "Anomaly",
      label: intel.anomalyType,
      direction: dir,
      confidence: Math.max(intel.bullish, intel.bearish),
      strength: intel.strength,
      target: intel.targets[0]?.price ?? null,
      stop: em != null ? (dir === "bullish" ? spot - em : spot + em) : null,
      horizonMs: HORIZON_MS[intel.timeForecast.window] ?? HORIZON_MS["30m"],
    });
  }

  // 2) Signal board — top directional idea
  const sig = board.signals.find((s) => s.side !== "neutral");
  if (sig && board.bias !== "neutral") {
    out.push({
      ...common,
      id: uid("signals", sym, t),
      source: "signals",
      model: `Signal:${sig.category}`,
      label: sig.title,
      direction: sig.side === "bullish" ? "bullish" : "bearish",
      confidence: Math.round(sig.score),
      strength: Math.abs(board.biasScore),
      target: sig.targets[0] ?? null,
      stop: sig.stop,
      horizonMs: horizonFromText(sig.horizon),
    });
  }

  // 3) MM-hedge plan — dealer-pressure directional trade
  if (mm.trade && mm.trade.side !== "wait") {
    const dir: IntelDir = mm.trade.side === "long" ? "bullish" : "bearish";
    out.push({
      ...common,
      id: uid("mmhedge", sym, t),
      source: "mmhedge",
      model: `MM:${mm.regime}-γ`,
      label: `Dealer ${mm.pressure} pressure (${mm.pressureScore})`,
      direction: dir,
      confidence: mm.trade.pWin != null ? Math.round(mm.trade.pWin * 100) : mm.conviction,
      strength: mm.conviction,
      target: mm.trade.targets[0]?.price ?? null,
      stop: mm.trade.stop,
      horizonMs: HORIZON_MS["1h"],
    });
  }

  return out;
}

/**
 * Collect new predictions and resolve matured ones — the always-on intelligence loop. Builds
 * candidates from the engines, gates near-duplicates, resolves this symbol's open records against the
 * recorded session spot series, persists, and returns a small counter for the caller.
 */
export function collectAndResolve(
  symbol: string,
  ctx: { chain: OptionContract[]; spot: number | null; bars: HistoryBar[]; samples: GexSample[]; intel: AnomalyIntel; board: SignalBoard; mm: MMHedge },
): { added: number; resolved: number; open: number; total: number } {
  const sym = symbol.toUpperCase();
  let journal = readJournal();

  const cands = buildCandidates(sym, Date.now(), ctx.chain, ctx.spot, ctx.bars, ctx.intel, ctx.board, ctx.mm);
  let added = 0;
  for (const cand of cands)
    if (shouldRecord(journal, cand)) {
      journal = [...journal, cand];
      added++;
    }

  const before = journal.filter((r) => r.symbol === sym && r.outcome != null).length;
  journal = resolveForSymbol(journal, sym, ctx.samples, Date.now());
  const after = journal.filter((r) => r.symbol === sym && r.outcome != null).length;

  if (added || after !== before) writeJournal(journal);
  return { added, resolved: after - before, open: journal.filter((r) => r.symbol === sym && r.outcome == null).length, total: journal.filter((r) => r.symbol === sym).length };
}
