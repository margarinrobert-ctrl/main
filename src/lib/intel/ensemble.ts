import type { IntelDir, PredictionRecord } from "./journal";
import { kellyFraction, summarize } from "./performance";
import { resolved } from "./resolve";

// Forward-looking ENSEMBLE forecast — the "AI" layer on top of the self-scoring journal.
//
// Each engine (anomaly / signals / mm-hedge) emits its own directional call. Instead of treating them
// equally, the ensemble blends the latest live call from each source, weighting each by how that source
// has ACTUALLY performed on the resolved journal (its realised expectancy, shrunk for sample size) and
// by how fresh the call is. The result is a single probability-of-up, a calibrated confidence, the
// degree of agreement, a fractional-Kelly size suggestion, and a transparent per-source breakdown.
//
// Honest: weights are learned from REAL resolved outcomes, not a black box; with little history the
// blend falls back toward an equal, confidence-weighted vote. Educational — not financial advice.

const DAY = 24 * 60 * 60_000;

export interface EnsembleVote {
  source: string; // engine label (the latest record's model)
  direction: IntelDir;
  confidence: number; // the source's own stated confidence, 0..100
  ageMs: number; // how old the latest call is
  edge: number | null; // realised expectancy, %/call
  n: number; // resolved sample for this source
  weight: number; // normalised blend weight, 0..1
  contribution: number; // signed share of the blended score (−1..1)
}

export interface EnsembleForecast {
  available: boolean;
  direction: IntelDir;
  pUp: number; // blended probability of an up move, 0..1
  confidence: number; // 0..100, shrunk by agreement + sample size
  score: number; // net directional score, −100..+100
  agreement: number; // 0..1, weighted share aligned with the call
  kelly: number | null; // suggested fraction of unit risk (quarter-Kelly, capped)
  votes: EnsembleVote[];
  asOf: number | null; // timestamp of the freshest contributing call
  note: string;
}

const dirSign = (d: IntelDir) => (d === "bullish" ? 1 : d === "bearish" ? -1 : 0);
const clamp = (x: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, x));
// Smooth skill map: realised expectancy (%/call) → 0..1, centred at 0.5 for a flat edge.
const skillOf = (edge: number | null) => (edge == null ? 0.5 : 0.5 + 0.5 * Math.tanh(edge / 0.3));

const EMPTY: EnsembleForecast = {
  available: false,
  direction: "neutral",
  pUp: 0.5,
  confidence: 0,
  score: 0,
  agreement: 0,
  kelly: null,
  votes: [],
  asOf: null,
  note: "No live engine calls journaled yet — open a ticker tab so the engines emit calls.",
};

/**
 * Blend the latest call from each source into a single performance-weighted forecast.
 * `records` is the journal (already scoped to a symbol or all). `now` is injectable for tests.
 */
export function ensembleForecast(records: PredictionRecord[], now = Date.now()): EnsembleForecast {
  if (!records.length) return EMPTY;

  // realised expectancy per source (from resolved outcomes) → learned skill
  const perfBySource = new Map<string, { edge: number | null; n: number }>();
  for (const src of new Set(records.map((r) => r.source))) {
    const s = summarize(records.filter((r) => r.source === src));
    perfBySource.set(src, { edge: s.expectancy, n: s.n });
  }

  // latest directional call per source
  const latest = new Map<string, PredictionRecord>();
  for (const r of records) {
    if (r.direction === "neutral") continue;
    const cur = latest.get(r.source);
    if (!cur || r.t > cur.t) latest.set(r.source, r);
  }
  if (!latest.size) return { ...EMPTY, note: "No directional calls on record — the engines are neutral right now." };

  const raw: (EnsembleVote & { _w: number })[] = [];
  for (const [src, rec] of latest) {
    const perf = perfBySource.get(src) ?? { edge: null, n: 0 };
    const reliability = perf.n / (perf.n + 8); // shrink small samples toward neutral
    const skill = skillOf(perf.edge);
    const ageMs = Math.max(0, now - rec.t);
    const horizon = rec.horizonMs || 60 * 60_000;
    const freshness = 0.3 + 0.7 * Math.exp(-ageMs / Math.max(horizon, 30 * 60_000)); // stale calls fade, never to 0
    const w = (0.04 + skill * reliability) * freshness; // floor so a fresh call always counts a little
    raw.push({
      source: rec.model,
      direction: rec.direction,
      confidence: rec.confidence,
      ageMs,
      edge: perf.edge,
      n: perf.n,
      weight: 0,
      contribution: 0,
      _w: w,
    });
  }

  const wsum = raw.reduce((s, v) => s + v._w, 0) || 1;
  let score = 0; // −1..1
  for (const v of raw) {
    v.weight = v._w / wsum;
    v.contribution = v.weight * dirSign(v.direction) * (v.confidence / 100);
    score += v.contribution;
  }
  score = clamp(score, -1, 1);

  const dir: IntelDir = score > 0.04 ? "bullish" : score < -0.04 ? "bearish" : "neutral";
  const pUp = clamp(0.5 + 0.5 * score, 0, 1);
  const agreement = dir === "neutral" ? 0 : raw.filter((v) => dirSign(v.direction) === Math.sign(score)).reduce((s, v) => s + v.weight, 0);

  // confidence = blended probability of being right, shrunk by total sample size, floored honestly
  const totalN = raw.reduce((s, v) => s + v.n, 0);
  const shrink = totalN / (totalN + 12);
  const pCorrect = Math.max(pUp, 1 - pUp);
  const confidence = Math.round(clamp(50 + (pCorrect * 100 - 50) * shrink * (0.5 + 0.5 * agreement), 0, 95));

  // quarter-Kelly from the blended probability + the journal-wide win/loss payoff
  const all = summarize(records);
  let kelly: number | null = null;
  if (dir !== "neutral" && all.n >= 10 && all.mfe != null && all.mae != null) {
    const k = kellyFraction(pCorrect, Math.max(0.01, all.mfe), Math.max(0.01, all.mae));
    kelly = k != null ? Math.round(Math.min(0.25, k * 0.25) * 1000) / 1000 : null;
  }

  const asOf = Math.max(...raw.map((v) => now - v.ageMs));
  const votes = raw.map(({ _w, ...v }) => v).sort((a, b) => b.weight - a.weight);
  const reliableN = resolved(records).length;
  const note =
    reliableN < 12
      ? `Blend is still confidence-weighted — only ${reliableN} resolved calls, so source weights are near-equal until the journal matures.`
      : `Source weights are learned from ${reliableN} resolved outcomes; the freshest call drives the blend.`;

  return { available: true, direction: dir, pUp, confidence, score: Math.round(score * 100), agreement, kelly, votes, asOf, note };
}
