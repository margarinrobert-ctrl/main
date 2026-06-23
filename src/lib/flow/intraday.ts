import type { GexSample } from "../gex-history";

// Live intraday (0DTE) anomaly scan over the client-recorded session series (spot / net-GEX / 0DTE
// ATM IV / put-call). For each new sample it z-scores the tick-to-tick change in spot, dealer gamma
// and implied vol against a trailing window, producing a per-sample anomaly score for the live graph
// plus the current flags. Pure statistics — educational, not advice.

export type IntradaySeverity = "elevated" | "extreme";
export type IntradayState = "calm" | "watch" | "anomalous";

export interface IntradayFlag {
  metric: string;
  z: number;
  severity: IntradaySeverity;
  direction: "up" | "down" | "neutral";
  detail: string;
}

export interface IntradayPoint {
  t: number;
  spot: number | null;
  gex: number | null;
  iv: number | null;
  score: number; // 0..100 anomaly intensity at this sample
  flagged: boolean;
  severity: IntradaySeverity | null;
}

export interface IntradayReport {
  points: IntradayPoint[];
  current: { score: number; state: IntradayState; flags: IntradayFlag[] };
  samples: number;
  rangePct: number | null;
  ivNow: number | null;
  gexNow: number | null;
}

const mean = (a: number[]) => (a.length ? a.reduce((s, x) => s + x, 0) / a.length : 0);
const std = (a: number[]) => {
  if (a.length < 2) return 0;
  const m = mean(a);
  return Math.sqrt(a.reduce((s, x) => s + (x - m) * (x - m), 0) / (a.length - 1));
};
const clamp = (x: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, x));

/** z of series[i] vs its trailing `window` (non-null) values before i. */
function zAt(series: (number | null)[], i: number, window: number): number | null {
  const base: number[] = [];
  for (let j = Math.max(0, i - window); j < i; j++) {
    const v = series[j];
    if (v != null && Number.isFinite(v)) base.push(v);
  }
  if (base.length < 6) return null;
  const s = std(base);
  if (s <= 0) return null;
  const cur = series[i];
  return cur == null ? null : (cur - mean(base)) / s;
}

const ELEVATED = 2.5;
const EXTREME = 3.5;

export function intradayScan(samples: GexSample[], window = 20): IntradayReport {
  const pts = samples.filter((s) => s.spot != null);
  const base: IntradayReport = {
    points: [],
    current: { score: 0, state: "calm", flags: [] },
    samples: pts.length,
    rangePct: null,
    ivNow: pts.length ? pts[pts.length - 1].iv ?? null : null,
    gexNow: pts.length ? pts[pts.length - 1].gex ?? null : null,
  };
  if (pts.length < 2) return base;

  // tick-to-tick change series
  const ret: (number | null)[] = [];
  const dGex: (number | null)[] = [];
  const dIv: (number | null)[] = [];
  for (let i = 0; i < pts.length; i++) {
    if (i === 0) {
      ret.push(null);
      dGex.push(null);
      dIv.push(null);
      continue;
    }
    const a = pts[i];
    const b = pts[i - 1];
    ret.push(a.spot && b.spot ? Math.log(a.spot / b.spot) : null);
    dGex.push(a.gex != null && b.gex != null ? a.gex - b.gex : null);
    dIv.push(a.iv != null && b.iv != null ? a.iv - b.iv : null);
  }

  const points: IntradayPoint[] = pts.map((p, i) => {
    const zr = zAt(ret, i, window);
    const zg = zAt(dGex, i, window);
    const zi = zAt(dIv, i, window);
    const peak = Math.max(Math.abs(zr ?? 0), Math.abs(zg ?? 0), Math.abs(zi ?? 0));
    const flagged = peak >= ELEVATED;
    return {
      t: p.t,
      spot: p.spot,
      gex: p.gex ?? null,
      iv: p.iv ?? null,
      score: Math.round(clamp((peak / 4) * 100, 0, 100)),
      flagged,
      severity: flagged ? (peak >= EXTREME ? "extreme" : "elevated") : null,
    };
  });

  // current flags from the last sample
  const last = pts.length - 1;
  const flags: IntradayFlag[] = [];
  const mk = (metric: string, z: number | null, upTxt: string, dnTxt: string) => {
    if (z == null || Math.abs(z) < ELEVATED) return;
    const dir = z >= 0 ? "up" : "down";
    flags.push({
      metric,
      z,
      severity: Math.abs(z) >= EXTREME ? "extreme" : "elevated",
      direction: metric === "Spot move" ? dir : metric === "IV jump" ? dir : "neutral",
      detail: `${Math.abs(z).toFixed(1)}σ ${z >= 0 ? upTxt : dnTxt} vs the recent session.`,
    });
  };
  mk("Spot move", zAt(ret, last, window), "rally", "drop");
  mk("Gamma shift", zAt(dGex, last, window), "GEX jump", "GEX drop");
  mk("IV jump", zAt(dIv, last, window), "IV spike", "IV crush");

  const score = points[points.length - 1]?.score ?? 0;
  const state: IntradayState = score >= 60 ? "anomalous" : score >= 30 ? "watch" : "calm";

  const spots = pts.map((p) => p.spot as number);
  const lo = Math.min(...spots);
  const hi = Math.max(...spots);
  const rangePct = lo > 0 ? ((hi - lo) / lo) * 100 : null;

  return { points, current: { score, state, flags }, samples: pts.length, rangePct, ivNow: base.ivNow, gexNow: base.gexNow };
}
