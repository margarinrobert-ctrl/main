import type { HistoryBar, OptionContract } from "../barchart/types";
import { atmIv, putCallRatio, realizedVol } from "./analytics";

// Performance Anomaly Detection. Computes a panel of behavioural features from the daily bars + the
// options chain and flags the ones that deviate from their own trailing baseline (z-score) or break a
// regime threshold. Surfaces a composite anomaly score, a calm/watch/anomalous state and the ranked
// anomalies with direction + interpretation. Pure statistics — educational, not financial advice.

export type Severity = "elevated" | "extreme";
export type AnomState = "calm" | "watch" | "anomalous";

export interface Anomaly {
  metric: string;
  value: string;
  z: number | null; // standard deviations from baseline (or a regime-scaled pseudo-z)
  severity: Severity;
  direction: "up" | "down" | "neutral";
  detail: string;
}

export interface AnomalyReport {
  score: number; // 0..100 composite intensity
  state: AnomState;
  sampleDays: number;
  anomalies: Anomaly[];
  notes: string[];
}

const mean = (a: number[]) => (a.length ? a.reduce((s, x) => s + x, 0) / a.length : 0);
const std = (a: number[]) => {
  if (a.length < 2) return 0;
  const m = mean(a);
  return Math.sqrt(a.reduce((s, x) => s + (x - m) * (x - m), 0) / (a.length - 1));
};
const clamp = (x: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, x));
const pct = (x: number) => `${(x * 100).toFixed(1)}%`;
const sev = (z: number): Severity => (Math.abs(z) >= 3 ? "extreme" : "elevated");

/** z-score of `last` vs a baseline window (null if not enough data or zero variance). */
function zOf(last: number, base: number[]): number | null {
  if (base.length < 8) return null;
  const s = std(base);
  if (s <= 0) return null;
  return (last - mean(base)) / s;
}

/**
 * Detect performance/behaviour anomalies. `bars` are daily OHLCV (Stooq EOD); `chain` adds the
 * options-derived VRP and put/call. Needs ~25+ bars for stable baselines.
 */
export function detectAnomalies(bars: HistoryBar[], chain: OptionContract[], spot: number | null): AnomalyReport {
  const closes = bars.map((b) => b.close).filter((x) => x > 0);
  const sampleDays = closes.length;
  const base: AnomalyReport = { score: 0, state: "calm", sampleDays, anomalies: [], notes: [] };
  if (sampleDays < 25) {
    base.notes.push("Not enough history for stable baselines (need ~25+ daily bars).");
    return base;
  }

  const anomalies: Anomaly[] = [];
  const WIN = 20;

  // 1) Daily return vs its trailing distribution
  const rets: number[] = [];
  for (let i = 1; i < closes.length; i++) rets.push(Math.log(closes[i] / closes[i - 1]));
  const lastRet = rets[rets.length - 1];
  const zRet = zOf(lastRet, rets.slice(-WIN - 1, -1));
  if (zRet != null && Math.abs(zRet) >= 2)
    anomalies.push({
      metric: "Daily return",
      value: pct(lastRet),
      z: zRet,
      severity: sev(zRet),
      direction: lastRet >= 0 ? "up" : "down",
      detail: `${Math.abs(zRet).toFixed(1)}σ ${lastRet >= 0 ? "up" : "down"} day vs the last ${WIN} sessions — ${Math.abs(zRet) >= 3 ? "a true outlier (capitulation/blow-off)" : "an outsized move"}.`,
    });

  // 2) Overnight gap (open vs prior close)
  const gaps: number[] = [];
  for (let i = 1; i < bars.length; i++) if (bars[i].open > 0 && bars[i - 1].close > 0) gaps.push(Math.log(bars[i].open / bars[i - 1].close));
  if (gaps.length > WIN) {
    const zGap = zOf(gaps[gaps.length - 1], gaps.slice(-WIN - 1, -1));
    if (zGap != null && Math.abs(zGap) >= 2)
      anomalies.push({
        metric: "Overnight gap",
        value: pct(gaps[gaps.length - 1]),
        z: zGap,
        severity: sev(zGap),
        direction: gaps[gaps.length - 1] >= 0 ? "up" : "down",
        detail: `Gap is ${Math.abs(zGap).toFixed(1)}σ vs normal — a news/overnight shock; watch for continuation vs fade.`,
      });
  }

  // 3) True range (intraday range) vs baseline
  const trs: number[] = [];
  for (let i = 1; i < bars.length; i++) {
    const b = bars[i];
    const pc = bars[i - 1].close;
    trs.push(Math.max(b.high - b.low, Math.abs(b.high - pc), Math.abs(b.low - pc)));
  }
  if (trs.length > WIN) {
    const zTr = zOf(trs[trs.length - 1], trs.slice(-WIN - 1, -1));
    if (zTr != null && zTr >= 2)
      anomalies.push({
        metric: "Range expansion",
        value: trs[trs.length - 1].toFixed(2),
        z: zTr,
        severity: sev(zTr),
        direction: "neutral",
        detail: `Today's range is ${zTr.toFixed(1)}σ above normal — volatility expansion, breakout/trend conditions.`,
      });
  }

  // 4) Volume vs baseline (log volume)
  const vols = bars.map((b) => b.volume).filter((v) => v > 0);
  if (vols.length > WIN + 5) {
    const lv = vols.map((v) => Math.log(v));
    const zVol = zOf(lv[lv.length - 1], lv.slice(-WIN - 1, -1));
    if (zVol != null && Math.abs(zVol) >= 2)
      anomalies.push({
        metric: "Volume",
        value: `${(vols[vols.length - 1] / 1e6).toFixed(1)}M`,
        z: zVol,
        severity: sev(zVol),
        direction: "neutral",
        detail: `Volume is ${zVol.toFixed(1)}σ ${zVol >= 0 ? "above" : "below"} normal — ${zVol >= 0 ? "conviction/participation spike" : "unusually thin tape"}.`,
      });
  }

  // 5) Volatility regime: short vs long realized vol
  const rv5 = realizedVol(bars, 5);
  const rv20 = realizedVol(bars, 20);
  if (rv5 != null && rv20 && rv20 > 0) {
    const ratio = rv5 / rv20;
    if (ratio >= 1.5 || ratio <= 0.6) {
      const z = (ratio - 1) / 0.25;
      anomalies.push({
        metric: "Vol regime",
        value: `${ratio.toFixed(2)}× (5d ${pct(rv5)} / 20d ${pct(rv20)})`,
        z,
        severity: sev(z),
        direction: ratio >= 1.5 ? "up" : "down",
        detail: ratio >= 1.5 ? "Short-term realized vol is spiking vs the baseline — regime shift to high vol." : "Vol has collapsed vs baseline — compression that often precedes an expansion.",
      });
    }
  }

  // 6) Trend extension: price vs its 20d mean in price-σ units
  const win = closes.slice(-WIN);
  const m = mean(win);
  const s = std(win);
  if (s > 0) {
    const zTrend = (closes[closes.length - 1] - m) / s;
    if (Math.abs(zTrend) >= 2)
      anomalies.push({
        metric: "Trend extension",
        value: `${zTrend >= 0 ? "+" : ""}${zTrend.toFixed(1)}σ vs 20d mean`,
        z: zTrend,
        severity: sev(zTrend),
        direction: zTrend >= 0 ? "up" : "down",
        detail: `Price is stretched ${Math.abs(zTrend).toFixed(1)}σ ${zTrend >= 0 ? "above" : "below"} its 20-day mean — extended; prone to mean-reversion.`,
      });
  }

  // 7) Volatility risk premium extreme (options vs realized)
  const exps = [...new Set(chain.map((c) => c.expiration))].sort();
  const iv0 = exps.length ? atmIv(chain, spot, exps[0]) : null;
  if (iv0 != null && rv20 && rv20 > 0) {
    const vrp = iv0 / rv20;
    if (vrp >= 1.6 || vrp <= 0.85) {
      const z = (vrp - 1) / 0.2;
      anomalies.push({
        metric: "VRP",
        value: `${vrp.toFixed(2)}× (IV ${pct(iv0)} / RV ${pct(rv20)})`,
        z,
        severity: sev(z),
        direction: vrp >= 1.6 ? "down" : "up",
        detail: vrp >= 1.6 ? "Implied richly exceeds realized — fear premium; favors selling vol / fade extremes." : "Implied at/below realized — vol underpriced; favors buying gamma.",
      });
    }
  }

  // 8) Put/Call extreme
  const pc = putCallRatio(chain).vol;
  if (pc != null && (pc >= 1.5 || pc <= 0.5)) {
    const z = (pc - 1) / 0.25;
    anomalies.push({
      metric: "Put/Call",
      value: pc.toFixed(2),
      z,
      severity: sev(z),
      direction: pc >= 1.5 ? "down" : "up",
      detail: pc >= 1.5 ? "Extreme put buying — defensive/bearish; a contrarian bounce risk at extremes." : "Extreme call buying — greed/squeeze tilt; watch for exhaustion.",
    });
  }

  anomalies.sort((a, b) => Math.abs(b.z ?? 0) - Math.abs(a.z ?? 0));

  const peak = anomalies.reduce((mx, a) => Math.max(mx, Math.abs(a.z ?? 0)), 0);
  const score = Math.round(clamp((peak / 4) * 60 + anomalies.length * 10, 0, 100));
  const state: AnomState = score >= 60 ? "anomalous" : score >= 30 ? "watch" : "calm";

  const notes = [
    anomalies.length === 0
      ? "No statistical anomalies — behaviour is within normal ranges across return, gap, range, volume, vol-regime, trend, VRP and flow."
      : `${anomalies.length} anomal${anomalies.length === 1 ? "y" : "ies"} flagged; peak ${peak.toFixed(1)}σ. Anomalies cluster around regime shifts — confirm with the dealer-gamma context (MM Hedge / Signals).`,
    "z-scores vs a 20-day trailing baseline on EOD bars (~1-day delayed); VRP/flow from the ~15-min CBOE chain. Educational — not advice.",
  ];

  return { score, state, sampleDays, anomalies, notes };
}
