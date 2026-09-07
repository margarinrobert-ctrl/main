import { mulberry32, normal, studentT } from "./rng";
import type { Bar } from "./types";

// SIMULATED market generator — for ENGINE CALIBRATION ONLY.
//
// Read this before using any number that comes out of it: a backtest on simulated bars tells you
// nothing about whether an edge exists in gold or crude. What it CAN do, and what it is here for,
// is verify the machinery:
//
//   * Null calibration — on a martingale with realistic costs, every strategy in the library must
//     come out unprofitable and statistically insignificant. If one looks good here, the finding is
//     a BUG (look-ahead, cost model, exit ordering), not an alpha.
//   * Power check — inject a known mean-reversion or momentum coefficient and confirm the pipeline
//     detects it, and that the detection strength scales with the coefficient.
//
// The process is deliberately realistic where realism matters for those two jobs: GARCH-style vol
// clustering, a U-shaped intraday vol profile, Student-t innovations, and a path-consistent OHLC
// built from micro-steps inside each bar.

export interface SynthConfig {
  /** Starting price — set it to the instrument's real level so ATR-scaled stops are realistic. */
  start: number;
  /** Annualised volatility, e.g. 0.16 for gold, 0.35 for crude. */
  annualVol: number;
  days: number;
  barsPerDay: number;
  /** Bar length in minutes; used to lay bars out on the clock. */
  minutesPerBar: number;
  /** First bar's UTC hour each day. */
  sessionStartUtc: number;
  seed: number;
  /** AR(1) coefficient on bar returns. >0 injects momentum, <0 injects mean reversion. 0 = martingale. */
  ar1?: number;
  /** OU pull of price back to a slow anchor, per bar. >0 injects range/mean-reverting behaviour. */
  ouPull?: number;
  /** Degrees of freedom for Student-t innovations (lower = fatter tails). */
  tailDf?: number;
  /** GARCH persistence (alpha + beta). 0 disables vol clustering. */
  garchPersistence?: number;
  /** Micro-steps per bar used to build a coherent high/low. */
  subSteps?: number;
}

export const SYNTH_PRESETS: Record<string, Partial<SynthConfig>> = {
  XAUUSD: { start: 2400, annualVol: 0.16, sessionStartUtc: 7, barsPerDay: 168, minutesPerBar: 5 },
  GC: { start: 2400, annualVol: 0.16, sessionStartUtc: 7, barsPerDay: 168, minutesPerBar: 5 },
  CL: { start: 78, annualVol: 0.35, sessionStartUtc: 13, barsPerDay: 84, minutesPerBar: 5 },
  ES: { start: 5600, annualVol: 0.14, sessionStartUtc: 13, barsPerDay: 96, minutesPerBar: 5 },
  NQ: { start: 20000, annualVol: 0.2, sessionStartUtc: 13, barsPerDay: 96, minutesPerBar: 5 },
};

/** U-shaped intraday volatility: busy on the open and the close, quiet in the middle. */
function seasonality(k: number, n: number): number {
  const u = n > 1 ? k / (n - 1) : 0;
  return 0.75 + 1.25 * (Math.exp(-8 * u) + Math.exp(-8 * (1 - u)));
}

export function synthBars(cfg: SynthConfig): Bar[] {
  const rand = mulberry32(cfg.seed);
  const sub = cfg.subSteps ?? 12;
  const df = cfg.tailDf ?? 5;
  const ar1 = cfg.ar1 ?? 0;
  const ou = cfg.ouPull ?? 0;
  const persistence = cfg.garchPersistence ?? 0.9;

  const barsPerYear = cfg.barsPerDay * 252;
  const baseVar = (cfg.annualVol * cfg.annualVol) / barsPerYear;
  // Student-t with df dof has variance df/(df-2); rescale so realised vol matches the target.
  const tScale = df > 2 ? Math.sqrt((df - 2) / df) : 1;

  const alpha = persistence > 0 ? 0.08 : 0;
  const beta = persistence > 0 ? persistence - alpha : 0;
  const omega = baseVar * (1 - alpha - beta);

  let variance = baseVar;
  let lastEps = 0;
  let logP = Math.log(cfg.start);
  let anchor = logP;
  let prevRet = 0;

  const bars: Bar[] = [];
  // Start on a Monday so weekday-of-week effects are interpretable.
  let day = Date.UTC(2023, 0, 2) / 86_400_000;

  for (let d = 0; d < cfg.days; d++) {
    const dow = new Date(day * 86_400_000).getUTCDay();
    if (dow === 0 || dow === 6) {
      day++;
      d--;
      continue;
    }
    const dayStart = day * 86_400_000 + cfg.sessionStartUtc * 3_600_000;
    for (let k = 0; k < cfg.barsPerDay; k++) {
      variance = omega + alpha * lastEps * lastEps + beta * variance;
      const barVol = Math.sqrt(Math.max(variance, 1e-16)) * seasonality(k, cfg.barsPerDay);
      const stepVol = barVol / Math.sqrt(sub);

      const o = Math.exp(logP);
      let hi = o;
      let lo = o;
      let barRet = 0;
      for (let s = 0; s < sub; s++) {
        const shock = (df > 2 ? studentT(rand, df) * tScale : normal(rand)) * stepVol;
        const drift = (ar1 * prevRet) / sub - (ou * (logP - anchor)) / sub;
        logP += drift + shock;
        barRet += drift + shock;
        const px = Math.exp(logP);
        if (px > hi) hi = px;
        if (px < lo) lo = px;
      }
      lastEps = barRet / Math.max(seasonality(k, cfg.barsPerDay), 1e-9);
      prevRet = barRet;
      // The OU anchor drifts slowly, so mean reversion is intraday rather than a global magnet.
      anchor += 0.02 * (logP - anchor);

      const c = Math.exp(logP);
      const volume = Math.round(1000 * seasonality(k, cfg.barsPerDay) * (0.6 + 0.8 * rand()));
      bars.push({ t: dayStart + k * cfg.minutesPerBar * 60_000, o, h: Math.max(hi, o, c), l: Math.min(lo, o, c), c, v: volume });
    }
    day++;
  }
  return bars;
}

/** Preset-driven helper: `syntheticSeries("CL", { days: 500, seed: 7 })`. */
export function syntheticSeries(preset: keyof typeof SYNTH_PRESETS | string, over: Partial<SynthConfig> = {}): Bar[] {
  const base: SynthConfig = {
    start: 100,
    annualVol: 0.2,
    days: 250,
    barsPerDay: 78,
    minutesPerBar: 5,
    sessionStartUtc: 13,
    seed: 1,
    ...(SYNTH_PRESETS[preset] ?? {}),
    ...over,
  };
  return synthBars(base);
}
