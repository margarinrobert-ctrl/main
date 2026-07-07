/**
 * Cross-sectional volatility factor — the AQR-style discipline applied to the vol surface.
 *
 * No single vol signal is strong, but a DIVERSIFIED, market-neutral portfolio of weak signals across many
 * names is a documented, durable edge: you are long the cheapest vol and short the richest, so the shared
 * "short convexity" beta nets out and what remains is the cross-sectional mispricing. Each period we
 * z-score every name on a few orthogonal-ish vol characteristics, combine into a composite oriented so
 * HIGH = vol RICH (a short-vol candidate), rank, and build a dollar-neutral long/short book.
 *
 *     composite = 0.60·z(VRP)  +  0.20·z(skew)  −  0.20·z(termSlope)
 *       z(VRP)      high  → implied rich vs forecast realized → sell
 *       z(skew)     high  → downside insurance overpriced      → sell/fade
 *       z(termSlope) low  → backwardation (front event premium) → sell front
 *
 * Honesty: a real factor book ranks hundreds of names so the cross-section is statistically meaningful;
 * over a ~7-name watchlist the z-scores are noisy and this is illustrative of the METHOD, not a sized
 * portfolio. Pure — unit-tested. Educational — not advice.
 */

export interface SymbolMetrics {
  symbol: string;
  vrpRatio: number | null; // IV / HAR-RV forecast (>1 rich)
  termSlope: number | null; // back IV − front IV (vol points); negative = backwardation
  skew: number | null; // 25Δ put − call IV (higher = pricier downside)
  gammaRegime?: number | null; // net GEX ($/1%), context only (not in composite)
  ivRank?: number | null; // 0..1, context only
}

export type FactorSide = "short-vol" | "long-vol" | "neutral";

export interface FactorRow {
  symbol: string;
  z: { vrp: number | null; skew: number | null; term: number | null };
  composite: number; // higher = richer vol (short-vol candidate)
  rank: number; // 1 = richest vol
  side: FactorSide;
  weight: number; // market-neutral weight (+ long / − short); Σ|w| ≈ 1, Σw ≈ 0
  gammaRegime: number | null;
  ivRank: number | null;
}

export interface FactorReport {
  rows: FactorRow[]; // ranked, richest vol first
  n: number; // symbols scored
  notes: string[];
}

const mean = (a: number[]) => (a.length ? a.reduce((s, x) => s + x, 0) / a.length : 0);
function std(a: number[]): number {
  if (a.length < 2) return 0;
  const m = mean(a);
  return Math.sqrt(a.reduce((s, x) => s + (x - m) * (x - m), 0) / a.length);
}

/** Cross-sectional z-scores for one field; null where the field is missing. σ≈0 ⇒ all z = 0. */
function zScores<T>(items: T[], get: (t: T) => number | null): (number | null)[] {
  const present = items.map(get);
  const vals = present.filter((v): v is number => v != null && Number.isFinite(v));
  const m = mean(vals);
  const s = std(vals);
  return present.map((v) => (v == null || !Number.isFinite(v) || s === 0 ? (v == null ? null : 0) : (v - m) / s));
}

export function volFactor(metrics: SymbolMetrics[]): FactorReport {
  const items = metrics.filter((x) => x.vrpRatio != null || x.termSlope != null || x.skew != null);
  if (items.length < 3) {
    return { rows: [], n: items.length, notes: ["Need ≥3 symbols with vol data to form a cross-section."] };
  }

  const zVrp = zScores(items, (x) => x.vrpRatio);
  const zSkew = zScores(items, (x) => x.skew);
  const zTerm = zScores(items, (x) => x.termSlope);

  // composite: HIGH = vol rich (short-vol candidate)
  const scored = items.map((x, i) => {
    const parts: number[] = [];
    if (zVrp[i] != null) parts.push(0.6 * (zVrp[i] as number));
    if (zSkew[i] != null) parts.push(0.2 * (zSkew[i] as number));
    if (zTerm[i] != null) parts.push(-0.2 * (zTerm[i] as number));
    const composite = parts.length ? parts.reduce((s, v) => s + v, 0) : 0;
    return { x, i, composite };
  });

  scored.sort((a, b) => b.composite - a.composite); // richest vol first

  // Sides: top third short-vol (sell the rich), bottom third long-vol (buy the cheap), middle neutral.
  const n = scored.length;
  const cut = Math.max(1, Math.floor(n / 3));
  const shorts = scored.slice(0, cut);
  const longs = scored.slice(n - cut);

  // Dollar-neutral weights: each side scaled to 0.5 gross by |composite|.
  const shortDen = shorts.reduce((s, r) => s + Math.abs(r.composite), 0) || 1;
  const longDen = longs.reduce((s, r) => s + Math.abs(r.composite), 0) || 1;
  const weightOf = (idxInScored: number, composite: number): number => {
    if (idxInScored < cut) return -0.5 * (Math.abs(composite) / shortDen); // short the rich
    if (idxInScored >= n - cut) return 0.5 * (Math.abs(composite) / longDen); // long the cheap
    return 0;
  };
  const sideOf = (idxInScored: number): FactorSide => (idxInScored < cut ? "short-vol" : idxInScored >= n - cut ? "long-vol" : "neutral");

  const rows: FactorRow[] = scored.map((r, rankIdx) => ({
    symbol: r.x.symbol,
    z: { vrp: zVrp[r.i], skew: zSkew[r.i], term: zTerm[r.i] },
    composite: r.composite,
    rank: rankIdx + 1,
    side: sideOf(rankIdx),
    weight: weightOf(rankIdx, r.composite),
    gammaRegime: r.x.gammaRegime ?? null,
    ivRank: r.x.ivRank ?? null,
  }));

  const notes = [
    `Ranked ${n} names by composite vol richness. Short the top ${cut} (rich vol), long the bottom ${cut} (cheap vol) — dollar-neutral.`,
    n < 15 ? "Small cross-section — z-scores are noisy; this shows the method, not a sized book. Real factor portfolios rank hundreds of names." : "",
  ].filter(Boolean);

  return { rows, n, notes };
}
