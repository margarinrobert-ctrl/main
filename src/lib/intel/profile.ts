import { calibration, healthState, summarize, type CalBin, type HealthState } from "./performance";
import { whatIfRules, type WhatIf } from "./experiment";
import type { IntelSource, PredictionRecord } from "./journal";
import { resolved } from "./resolve";

// Closed-loop optimisation profile: what the Intel journal has LEARNED, packaged for the rest of the
// app to consume. Every other section reads this to (a) weight the engines that have actually worked
// and (b) recalibrate their stated confidence toward realised hit-rates — so the whole platform is
// tuned by its own measured track record, not static assumptions. All derived from resolved outcomes.

export interface SourceStat {
  source: IntelSource;
  weight: number; // 0..1, normalised across sources (realised skill × sample reliability)
  edge: number | null; // realised expectancy, %/call
  hitRate: number | null;
  sharpe: number | null;
  n: number; // resolved sample
}

export interface LearnedProfile {
  ready: boolean; // enough resolved calls to trust weights/calibration
  n: number; // resolved count
  sources: SourceStat[]; // sorted by weight desc
  calBins: CalBin[];
  calError: number | null;
  bestFilters: WhatIf[]; // decision filters that beat take-all (out-of-sample-ish)
  health: HealthState;
}

const SOURCES: IntelSource[] = ["anomaly", "signals", "mmhedge"];
const MIN_READY = 12;
const skill = (edge: number | null) => (edge == null ? 0.5 : 0.5 + 0.5 * Math.tanh(edge / 0.3));

/** Derive the learned profile (per-source weights, calibration, best filters, health) from the journal. */
export function learnedProfile(records: PredictionRecord[]): LearnedProfile {
  const n = resolved(records).length;
  const raw = SOURCES.map((source) => {
    const s = summarize(records.filter((r) => r.source === source));
    const reliability = s.n / (s.n + 8); // shrink small samples toward neutral
    return { source, edge: s.expectancy, hitRate: s.hitRate, sharpe: s.sharpe, n: s.n, _w: 0.04 + skill(s.expectancy) * reliability };
  });
  const wsum = raw.reduce((a, b) => a + b._w, 0) || 1;
  const sources = raw.map(({ _w, ...r }) => ({ ...r, weight: _w / wsum })).sort((a, b) => b.weight - a.weight);
  const cal = calibration(records);
  return {
    ready: n >= MIN_READY,
    n,
    sources,
    calBins: cal.bins,
    calError: cal.error,
    bestFilters: whatIfRules(records).filter((w) => (w.deltaVsAll ?? 0) > 0).slice(0, 3),
    health: healthState(records),
  };
}

/**
 * Recalibrate a stated confidence through the journal's calibration curve (piecewise-linear over the
 * confidence bands), shrunk toward the stated value by sample size. Returns the input unchanged until
 * the journal is mature — no distortion on thin data.
 */
export function calibrateConfidence(stated: number, profile: LearnedProfile): number {
  const bins = profile.calBins;
  if (!profile.ready || bins.length < 2) return Math.round(stated);
  const pts = bins.slice().sort((a, b) => a.predicted - b.predicted);
  let mapped: number;
  if (stated <= pts[0].predicted) mapped = pts[0].realized;
  else if (stated >= pts[pts.length - 1].predicted) mapped = pts[pts.length - 1].realized;
  else {
    mapped = pts[pts.length - 1].realized;
    for (let i = 1; i < pts.length; i++) {
      if (stated <= pts[i].predicted) {
        const a = pts[i - 1];
        const b = pts[i];
        const t = b.predicted === a.predicted ? 0 : (stated - a.predicted) / (b.predicted - a.predicted);
        mapped = a.realized + t * (b.realized - a.realized);
        break;
      }
    }
  }
  const totalN = bins.reduce((s, b) => s + b.n, 0);
  const shrink = totalN / (totalN + 20);
  return Math.round(Math.max(0, Math.min(100, stated + (mapped - stated) * shrink)));
}

export function sourceStat(profile: LearnedProfile, source: IntelSource): SourceStat | null {
  return profile.sources.find((s) => s.source === source) ?? null;
}
