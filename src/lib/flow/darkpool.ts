// Dark-pool / off-exchange flow analytics.
//
// "Dark pool" in the free-data sense = volume that prints to FINRA's Trade Reporting Facilities (TRFs)
// instead of a lit exchange: ATS/dark-pool crosses PLUS wholesaler internalization of retail flow.
// FINRA publishes it as daily short-sale volume files (per symbol: short, short-exempt and total
// off-exchange volume). Two reads come out of it:
//
//   • Dark-Pool Ratio (DPR) = off-exchange SHORT volume / off-exchange total. The DIX thesis (Squeeze-
//     Metrics) is counterintuitive: a HIGH ratio is *accumulation* — market-makers print SHORT to fill
//     institutional BUY orders off-exchange, so an elevated dark short % marks net buying, not bearishness.
//   • Off-exchange % = off-exchange volume / consolidated (all-venue) volume — how much of the tape
//     printed in the dark.
//
// Educational; daily/T+1. Off-exchange volume is the standard free *proxy* for "dark pool" — it bundles
// true ATS prints with wholesaler internalization, and carries no price, so there are no print levels.

export interface DarkPoolDay {
  date: string; // YYYY-MM-DD
  shortVolume: number;
  shortExemptVolume: number;
  offExchangeVolume: number; // FINRA reported total (off-exchange) for the day
  consolidatedVolume: number | null; // all-venue total volume that day (for off-exchange %)
}

export interface DarkPoolPoint {
  date: string;
  dpr: number; // dark-pool ratio (short / off-exchange)
  offExchPct: number | null; // off-exchange / consolidated
  offExchangeVolume: number;
}

export type DarkPoolBias = "accumulation" | "distribution" | "neutral";
export type DarkPoolTrend = "rising" | "falling" | "flat";

export interface DarkPoolStats {
  available: boolean;
  days: number;
  latest: DarkPoolDay | null;
  dpr: number | null; // latest dark-pool ratio
  dprAvg: number | null; // window mean
  dprZ: number | null; // z-score of latest vs the window
  dprPctile: number | null; // percentile rank of latest within the window (0..1)
  offExchPct: number | null; // latest off-exchange % of consolidated volume
  offExchPctAvg: number | null;
  trend: DarkPoolTrend | null; // DPR slope sign over the window
  bias: DarkPoolBias | null; // DIX-style read from the z-score
  series: DarkPoolPoint[];
}

const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);
const std = (xs: number[]) => {
  if (xs.length < 2) return 0;
  const m = mean(xs);
  return Math.sqrt(xs.reduce((a, b) => a + (b - m) ** 2, 0) / (xs.length - 1));
};

/** Sign of the OLS slope of a series, with a small dead-band so noise reads as "flat". */
function slopeSign(xs: number[]): DarkPoolTrend | null {
  const n = xs.length;
  if (n < 3) return null;
  const xm = (n - 1) / 2;
  const ym = mean(xs);
  let num = 0;
  let den = 0;
  for (let i = 0; i < n; i++) {
    num += (i - xm) * (xs[i] - ym);
    den += (i - xm) ** 2;
  }
  if (den === 0) return "flat";
  const slope = num / den;
  const tol = (Math.abs(ym) || 1) * 0.002; // ~0.2% of the mean per day
  return slope > tol ? "rising" : slope < -tol ? "falling" : "flat";
}

const EMPTY: DarkPoolStats = {
  available: false,
  days: 0,
  latest: null,
  dpr: null,
  dprAvg: null,
  dprZ: null,
  dprPctile: null,
  offExchPct: null,
  offExchPctAvg: null,
  trend: null,
  bias: null,
  series: [],
};

/** Reduce a daily off-exchange series to the dark-pool ratio, off-exchange %, trend and DIX-style bias. */
export function darkPoolStats(rows: DarkPoolDay[]): DarkPoolStats {
  const s = [...rows].filter((r) => r.offExchangeVolume > 0).sort((a, b) => a.date.localeCompare(b.date));
  if (!s.length) return EMPTY;

  const dprs = s.map((r) => r.shortVolume / r.offExchangeVolume);
  const latest = s[s.length - 1];
  const dpr = dprs[dprs.length - 1];
  const dprAvg = mean(dprs);
  const sd = std(dprs);
  const dprZ = sd > 0 ? (dpr - dprAvg) / sd : null;
  const dprPctile = dprs.length > 1 ? dprs.filter((x) => x <= dpr).length / dprs.length : null;

  const offPctOf = (r: DarkPoolDay) =>
    r.consolidatedVolume && r.consolidatedVolume > 0 ? r.offExchangeVolume / r.consolidatedVolume : null;
  const offPcts = s.map(offPctOf).filter((x): x is number => x != null);
  const offExchPct = offPctOf(latest);
  const offExchPctAvg = offPcts.length ? mean(offPcts) : null;

  const bias: DarkPoolBias = dprZ == null ? "neutral" : dprZ > 0.5 ? "accumulation" : dprZ < -0.5 ? "distribution" : "neutral";

  const series: DarkPoolPoint[] = s.map((r) => ({
    date: r.date,
    dpr: r.shortVolume / r.offExchangeVolume,
    offExchPct: offPctOf(r),
    offExchangeVolume: r.offExchangeVolume,
  }));

  return {
    available: true,
    days: s.length,
    latest,
    dpr,
    dprAvg,
    dprZ,
    dprPctile,
    offExchPct,
    offExchPctAvg,
    trend: slopeSign(dprs),
    bias,
    series,
  };
}
