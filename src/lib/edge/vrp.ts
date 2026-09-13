import type { HistoryBar, OptionContract } from "../barchart/types";
import { atmIv, realizedVol } from "../flow/analytics";
import { harRvForecast, type HarRv } from "./harrv";

/**
 * Variance Risk Premium engine — the most robust, most-documented persistent edge in options.
 *
 * Index (and, more noisily, single-name) implied vol systematically prints ABOVE subsequently realized
 * vol, because end-users pay up for crash protection and convexity. The seller of delta-hedged gamma
 * collects the spread. This engine quantifies it rigorously: forecast near-term realized vol with HAR-RV
 * (harrv.ts) rather than naive trailing RV, then measure implied − forecast.
 *
 *     VRP(vol pts) = IV_ATM − E[RV]          E[RV] from HAR-RV
 *     VRP(ratio)   = IV_ATM / E[RV]
 *     VRP(var)     = IV_ATM² − E[RV]²        the variance premium a var-swap seller earns
 *
 * Honesty: this is a RISK premium, not an anomaly — it pays most of the time and loses badly in the exact
 * regime you can't hedge (vol-of-vol spikes). Positive VRP is compensation for that tail, not free money.
 * Conviction is dampened when the HAR fit is weak or the sample is thin. Educational — not advice.
 */

export type VrpSide = "short-vol" | "long-vol" | "neutral";

export interface VrpRead {
  atmIv: number | null; // front-expiry ATM implied vol (annualized)
  rvForecast: number | null; // HAR-RV near-term realized-vol forecast (annualized)
  rvTrailing: number | null; // trailing 20d realized vol (reference only)
  har: HarRv;
  vrpVol: number | null; // IV − forecast, annualized vol points
  vrpRatio: number | null; // IV / forecast
  vrpVar: number | null; // IV² − forecast² (variance units)
  ivRank: number | null; // 0..1 percentile of current IV vs supplied history (optional)
  impliedDailyMovePct: number | null; // ATM straddle's implied daily move
  forecastDailyMovePct: number | null; // HAR-forecast daily move (the short-vol breakeven reference)
  edgeVolPts: number | null; // headline edge: vol points the seller collects over expected realized
  edgeOnPremiumPct: number | null; // rough expected P&L of a 1-month delta-hedged short straddle, % of premium (ESTIMATE)
  side: VrpSide;
  conviction: number; // 0..100, dampened by fit quality + sample
  notes: string[];
}

const TRADING_DAYS = 252;
const HORIZON_DAYS = 21; // ~1 month
const clamp = (x: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, x));
const pct = (n: number | null) => (n == null ? "—" : `${(n * 100).toFixed(1)}%`);

function frontExpiration(chain: OptionContract[]): string | null {
  const exps = [...new Set(chain.map((c) => c.expiration))].sort();
  return exps.find((e) => (chain.find((c) => c.expiration === e)?.dte ?? -1) >= 0) ?? exps[0] ?? null;
}

function ivRankOf(iv: number | null, history?: number[] | null): number | null {
  if (iv == null || !history || history.length < 12) return null;
  const vals = history.filter((v) => Number.isFinite(v) && v > 0);
  if (vals.length < 12) return null;
  const below = vals.filter((v) => v <= iv).length;
  return below / vals.length;
}

export function vrpEngine(chain: OptionContract[], spot: number | null, bars: HistoryBar[], opts?: { ivHistory?: number[] | null }): VrpRead {
  const front = chain.length ? frontExpiration(chain) : null;
  const iv = front ? atmIv(chain, spot, front) : null;
  const har = harRvForecast(bars);
  const rvForecast = har.forecastVol;
  const rvTrailing = realizedVol(bars, 20);

  const base: VrpRead = {
    atmIv: iv, rvForecast, rvTrailing, har, vrpVol: null, vrpRatio: null, vrpVar: null, ivRank: ivRankOf(iv, opts?.ivHistory),
    impliedDailyMovePct: iv != null ? iv / Math.sqrt(TRADING_DAYS) : null,
    forecastDailyMovePct: rvForecast != null ? rvForecast / Math.sqrt(TRADING_DAYS) : null,
    edgeVolPts: null, edgeOnPremiumPct: null, side: "neutral", conviction: 0, notes: [],
  };

  if (iv == null || rvForecast == null || rvForecast <= 0) {
    base.notes.push(iv == null ? "No front-expiry ATM IV." : "Need ~30+ daily bars for a HAR-RV forecast.");
    return base;
  }

  const vrpVol = iv - rvForecast;
  const vrpRatio = iv / rvForecast;
  const vrpVar = iv * iv - rvForecast * rvForecast;

  // Rough expected P&L of a 1-month delta-hedged short ATM straddle, as % of the straddle premium:
  //   E[P&L] ≈ ½(σ_i² − σ_r²)·T ;  ATM straddle premium ≈ 0.8·σ_i·√T   ⇒   ratio = (σ_i²−σ_r²)·√T / (1.6·σ_i)
  const T = HORIZON_DAYS / TRADING_DAYS;
  const edgeOnPremium = (vrpVar * Math.sqrt(T)) / (1.6 * iv);

  const side: VrpSide = vrpRatio >= 1.1 ? "short-vol" : vrpRatio <= 0.95 ? "long-vol" : "neutral";

  // Conviction: distance of the ratio from 1, scaled, then dampened by HAR fit quality and sample size.
  const magnitude = clamp(Math.abs(vrpRatio - 1) / 0.35, 0, 1); // 35% gap ⇒ full magnitude
  const fitQuality = har.fitted ? clamp(0.5 + (har.r2 ?? 0), 0.4, 1) : 0.5;
  const sampleQuality = clamp(har.n / 120, 0.4, 1);
  const ivRankBoost = base.ivRank == null ? 1 : side === "short-vol" ? clamp(0.7 + base.ivRank * 0.6, 0.7, 1.3) : side === "long-vol" ? clamp(0.7 + (1 - base.ivRank) * 0.6, 0.7, 1.3) : 1;
  const conviction = Math.round(clamp(magnitude * fitQuality * sampleQuality * ivRankBoost, 0, 1) * 100);

  const notes: string[] = [];
  notes.push(
    side === "short-vol"
      ? `Implied ${pct(iv)} is ${vrpRatio.toFixed(2)}× the HAR-RV forecast ${pct(rvForecast)} — vol is RICH; a delta-hedged seller stands to earn ~${(vrpVol * 100).toFixed(1)} vol points IF realized vol matches the forecast. This is risk-premium income, not an anomaly: size for the gap day.`
      : side === "long-vol"
        ? `Implied ${pct(iv)} is only ${vrpRatio.toFixed(2)}× the HAR-RV forecast ${pct(rvForecast)} — vol is CHEAP relative to what the model expects to realize; favors owning gamma / long straddle-and-hedge.`
        : `Implied ${pct(iv)} ≈ HAR-RV forecast ${pct(rvForecast)} — no vol edge; trade direction/levels, not vol.`,
  );
  if (!har.fitted) notes.push("HAR fit was degenerate — using Corsi canonical weights; treat the forecast as coarse.");
  if (base.ivRank != null) notes.push(`IV is at the ${Math.round(base.ivRank * 100)}th percentile of its recent range — ${base.ivRank > 0.6 ? "elevated (favors selling)" : base.ivRank < 0.4 ? "depressed (favors buying)" : "mid-range"}.`);

  return { ...base, vrpVol, vrpRatio, vrpVar, edgeVolPts: vrpVol, edgeOnPremiumPct: edgeOnPremium, side, conviction, notes };
}
