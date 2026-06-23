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
  // Daily OHLC for the same date (joined from price history). Used to map the day's off-exchange
  // volume onto a price range → the dark-pool volume-by-price profile / levels. Optional: the ratio
  // and sentiment metrics don't need it.
  open?: number | null;
  high?: number | null;
  low?: number | null;
  close?: number | null;
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

// ── Dark-pool price levels (off-exchange volume-by-price) ───────────────────────────────────────
// FINRA off-exchange data is volume-only (no print prices), so true per-print levels need a paid
// real-time feed. The honest free approximation: take each day's REAL off-exchange volume and spread
// it across that day's REAL price range (its high–low), then aggregate into a volume-by-price profile.
// Its peaks are the prices that absorbed the most dark volume — dark-pool support/resistance — and the
// heaviest bin is the dark-pool Point of Control. Daily resolution; a proxy, not an intraday tape.

export interface DarkPoolLevel {
  price: number; // bin-center price
  volume: number; // off-exchange volume mapped to this level
  share: number; // volume / total profile volume (0..1)
  rank: number; // 1 = heaviest
}

export interface DarkPoolProfile {
  available: boolean;
  poc: number | null; // point of control — heaviest off-exchange price
  vah: number | null; // value-area high (≈70% of dark volume)
  val: number | null; // value-area low
  priceLo: number | null;
  priceHi: number | null;
  levels: DarkPoolLevel[]; // distinct top dark-pool S/R levels
  bins: { price: number; volume: number }[]; // full histogram (for a profile viz)
}

const EMPTY_PROFILE: DarkPoolProfile = {
  available: false,
  poc: null,
  vah: null,
  val: null,
  priceLo: null,
  priceHi: null,
  levels: [],
  bins: [],
};

const dayLo = (d: DarkPoolDay) => (d.low != null ? d.low : d.close != null ? d.close : null);
const dayHi = (d: DarkPoolDay) => (d.high != null ? d.high : d.close != null ? d.close : null);

/** Build the off-exchange volume-by-price profile and extract dark-pool levels (POC, value area, peaks). */
export function darkPoolLevels(days: DarkPoolDay[], opts: { bins?: number; topN?: number } = {}): DarkPoolProfile {
  const binCount = Math.max(8, opts.bins ?? 48);
  const topN = Math.max(1, opts.topN ?? 6);
  const rows = days.filter((d) => d.offExchangeVolume > 0 && dayLo(d) != null && dayHi(d) != null);
  if (!rows.length) return EMPTY_PROFILE;

  const lo = Math.min(...rows.map((d) => dayLo(d) as number));
  const hi = Math.max(...rows.map((d) => dayHi(d) as number));

  if (!(hi > lo)) {
    const volume = rows.reduce((s, d) => s + d.offExchangeVolume, 0);
    return { available: true, poc: lo, vah: lo, val: lo, priceLo: lo, priceHi: hi, levels: [{ price: lo, volume, share: 1, rank: 1 }], bins: [{ price: lo, volume }] };
  }

  const width = (hi - lo) / binCount;
  const vol = new Array<number>(binCount).fill(0);
  for (const d of rows) {
    const dl = dayLo(d) as number;
    const dh = dayHi(d) as number;
    if (dh <= dl) {
      vol[Math.min(binCount - 1, Math.max(0, Math.floor((dl - lo) / width)))] += d.offExchangeVolume;
      continue;
    }
    const span = dh - dl;
    const first = Math.max(0, Math.floor((dl - lo) / width));
    const last = Math.min(binCount - 1, Math.floor((dh - lo) / width));
    for (let i = first; i <= last; i++) {
      const binLo = lo + i * width;
      const overlap = Math.min(dh, binLo + width) - Math.max(dl, binLo);
      if (overlap > 0) vol[i] += d.offExchangeVolume * (overlap / span);
    }
  }

  const bins = vol.map((volume, i) => ({ price: lo + (i + 0.5) * width, volume }));
  const total = vol.reduce((s, x) => s + x, 0) || 1;

  let pocIdx = 0;
  for (let i = 1; i < binCount; i++) if (vol[i] > vol[pocIdx]) pocIdx = i;

  // value area: expand out from the POC, always taking the heavier neighbour, until ~70% is covered
  let loIdx = pocIdx;
  let hiIdx = pocIdx;
  let acc = vol[pocIdx];
  const target = total * 0.7;
  while (acc < target && (loIdx > 0 || hiIdx < binCount - 1)) {
    const below = loIdx > 0 ? vol[loIdx - 1] : -1;
    const above = hiIdx < binCount - 1 ? vol[hiIdx + 1] : -1;
    if (above >= below) acc += Math.max(0, vol[++hiIdx]);
    else acc += Math.max(0, vol[--loIdx]);
  }

  // distinct peak levels: greediest-volume bins kept ≥ minGap apart so they don't cluster on the POC
  const minGap = Math.max(width * 1.5, ((lo + hi) / 2) * 0.004);
  const picked: { price: number; volume: number }[] = [];
  for (const b of bins.filter((b) => b.volume > 0).sort((a, b) => b.volume - a.volume)) {
    if (picked.length >= topN) break;
    if (picked.some((p) => Math.abs(p.price - b.price) < minGap)) continue;
    picked.push(b);
  }

  return {
    available: true,
    poc: bins[pocIdx].price,
    vah: bins[hiIdx].price,
    val: bins[loIdx].price,
    priceLo: lo,
    priceHi: hi,
    levels: picked.map((b, i) => ({ price: b.price, volume: b.volume, share: b.volume / total, rank: i + 1 })),
    bins,
  };
}
