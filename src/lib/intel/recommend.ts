import type { PredictionRecord } from "./journal";
import { resolved } from "./resolve";
import { breakdown, calibration, edgeDecay, featureDrift, featureImportance, summarize, type Group } from "./performance";

// Self-learning recommendations. Every recommendation is DERIVED from the resolved-journal analytics
// (negative-edge groups, miscalibration, edge decay, feature drift/importance) with the supporting
// numbers and a confidence gated by sample size. No black-box claims — the evidence is shown.

export type Severity = "critical" | "warn" | "info";
export interface Recommendation {
  id: string;
  severity: Severity;
  title: string;
  detail: string;
  evidence: string;
  confidence: number; // 0..100, grows with sample size / effect size
  action: string;
}

const pct = (x: number | null | undefined, d = 1) => (x == null ? "—" : `${x >= 0 ? "+" : ""}${x.toFixed(d)}%`);
const sampleConf = (n: number) => Math.round(Math.min(100, (n / 40) * 100));

export function recommend(records: PredictionRecord[]): Recommendation[] {
  const recs = resolved(records);
  const out: Recommendation[] = [];
  const all = summarize(records);

  if (recs.length < 20) {
    out.push({
      id: "collecting",
      severity: "info",
      title: "Still collecting — keep tabs open",
      detail: `${recs.length} prediction${recs.length === 1 ? "" : "s"} resolved so far. Rankings and recommendations stabilise around 20–40 resolved calls; predictions resolve as new price prints into the session series.`,
      evidence: `${records.length} journaled · ${recs.length} resolved · ${records.length - recs.length} open`,
      confidence: sampleConf(recs.length),
      action: "Leave a ticker tab open so the collector records and resolves predictions.",
    });
    if (recs.length < 8) return out;
  }

  // 1) overall edge sign
  if (all.expectancy != null && all.n >= 12) {
    if (all.expectancy <= 0)
      out.push({
        id: "neg-overall",
        severity: "critical",
        title: "Negative realised edge overall",
        detail: `Across all sources the average directional outcome is ${pct(all.expectancy, 2)} per call (hit-rate ${all.hitRate != null ? Math.round(all.hitRate * 100) : "—"}%). The blended signal is not yet additive.`,
        evidence: `n=${all.n} · Sharpe ${all.sharpe?.toFixed(2) ?? "—"} · PF ${all.profitFactor === Infinity ? "∞" : all.profitFactor?.toFixed(2) ?? "—"}`,
        confidence: sampleConf(all.n),
        action: "Lean on the highest-ranked source/regime below and filter out the negative-edge groups.",
      });
  }

  // 2) negative / positive edge groups (source × regime)
  const groups = [
    ...breakdown(records, (r) => `source · ${r.model}`, 6),
    ...breakdown(records, (r) => `regime · ${r.regime}-γ`, 6),
    ...breakdown(records, (r) => `vol · ${r.volRegime}`, 6),
  ];
  for (const g of groups) {
    if (g.summary.expectancy == null) continue;
    if (g.summary.expectancy < -0.03)
      out.push({
        id: `neg-${g.key}`,
        severity: "warn",
        title: `Downweight ${g.key}`,
        detail: `${g.key} has produced a negative realised edge (${pct(g.summary.expectancy, 2)}/call, hit-rate ${g.summary.hitRate != null ? Math.round(g.summary.hitRate * 100) : "—"}%) over ${g.summary.n} resolved calls.`,
        evidence: `n=${g.summary.n} · CI ${g.summary.ci ? `${Math.round(g.summary.ci.lo * 100)}–${Math.round(g.summary.ci.hi * 100)}%` : "—"}`,
        confidence: sampleConf(g.summary.n),
        action: `Reduce size or skip ${g.key} until the edge turns positive.`,
      });
  }
  const best = bestGroup([...breakdown(records, (r) => r.model, 6), ...breakdown(records, (r) => `${r.regime}-γ`, 6)]);
  if (best && best.summary.expectancy != null && best.summary.expectancy > 0.05)
    out.push({
      id: `lean-${best.key}`,
      severity: "info",
      title: `Lean into ${best.key}`,
      detail: `${best.key} is the strongest performer: ${pct(best.summary.expectancy, 2)}/call, hit-rate ${best.summary.hitRate != null ? Math.round(best.summary.hitRate * 100) : "—"}% (Sharpe ${best.summary.sharpe?.toFixed(2) ?? "—"}) over ${best.summary.n} calls.`,
      evidence: `n=${best.summary.n} · PF ${best.summary.profitFactor === Infinity ? "∞" : best.summary.profitFactor?.toFixed(2) ?? "—"}`,
      confidence: sampleConf(best.summary.n),
      action: `Allocate more to ${best.key}; it carries the blended edge.`,
    });

  // 3) calibration
  const cal = calibration(records);
  if (cal.error != null && recs.length >= 16 && cal.error > 0.12) {
    const over = cal.bins.filter((b) => b.predicted - b.realized > 8);
    out.push({
      id: "calibration",
      severity: "warn",
      title: over.length ? "Overconfident — recalibrate" : "Miscalibrated confidence",
      detail: `Stated confidence diverges from realised hit-rate by ${(cal.error * 100).toFixed(0)} pts on average${over.length ? `; e.g. the ${over[0].label} band realised only ${Math.round(over[0].realized)}%.` : "."}`,
      evidence: cal.bins.map((b) => `${b.label}:${Math.round(b.realized)}%(n${b.n})`).join("  "),
      confidence: sampleConf(recs.length),
      action: "Shrink confidence toward realised rates (Platt/temperature scaling) before sizing off it.",
    });
  }

  // 4) edge decay
  const decay = edgeDecay(records);
  if (decay.decaying && decay.delta != null)
    out.push({
      id: "decay",
      severity: "critical",
      title: "Edge is decaying",
      detail: `Recent-half expectancy ${pct(decay.recent, 2)} is below the baseline ${pct(decay.baseline, 2)} (${pct(decay.delta, 2)}). The edge is fading — possible regime change or overfit to stale conditions.`,
      evidence: `n=${decay.n} · baseline ${pct(decay.baseline, 2)} → recent ${pct(decay.recent, 2)}`,
      confidence: sampleConf(decay.n),
      action: "Re-fit thresholds on recent data; widen stops or stand down until edge re-establishes.",
    });

  // 5) feature drift
  for (const d of featureDrift(records).slice(0, 2))
    if (d.drifting)
      out.push({
        id: `drift-${d.feature}`,
        severity: "warn",
        title: `Feature drift: ${d.feature}`,
        detail: `${d.feature} shifted from ${d.baseline.toFixed(2)} to ${d.recent.toFixed(2)} (${d.z >= 0 ? "+" : ""}${d.z.toFixed(1)}σ) between the older and recent journal — the input distribution is moving.`,
        evidence: `z=${d.z.toFixed(1)}`,
        confidence: 60,
        action: "Check whether models tuned on the old distribution still hold; consider re-estimating.",
      });

  // 6) top feature association
  const feats = featureImportance(records);
  if (feats.length && Math.abs(feats[0].corr) >= 0.2)
    out.push({
      id: `feat-${feats[0].feature}`,
      severity: "info",
      title: `Strongest factor: ${feats[0].feature}`,
      detail: `${feats[0].feature} shows the strongest association with winning calls (Pearson ${feats[0].corr >= 0 ? "+" : ""}${feats[0].corr.toFixed(2)} vs directional return) on the recorded sample. Association, not proven causation.`,
      evidence: `r=${feats[0].corr.toFixed(2)} · n=${feats[0].n}`,
      confidence: sampleConf(feats[0].n),
      action: `Weight ${feats[0].feature} more in the directional blend and watch it for decay.`,
    });

  const order: Record<Severity, number> = { critical: 0, warn: 1, info: 2 };
  return out.sort((a, b) => order[a.severity] - order[b.severity] || b.confidence - a.confidence);
}

function bestGroup(groups: Group[]): Group | null {
  return groups.filter((g) => g.summary.n >= 6).sort((a, b) => (b.summary.sharpe ?? -1e9) - (a.summary.sharpe ?? -1e9))[0] ?? null;
}
