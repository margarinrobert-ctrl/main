import { clockFor, type ExchangeTz } from "./clock";
import type { Bar, Instrument } from "./types";

// Volume Profile / Market Profile primitives.
//
// A volume profile answers a different question from a price chart: not "where did price go" but
// "where did business get done". Auction-market theory says the market spends most of its time
// rotating around an accepted value area and only briefly outside it, so the levels that matter are
// the ones defined by volume — the point of control and the edges of value — rather than by price
// extremes.
//
// CONSTRUCTION CAVEAT, stated up front because it bounds everything downstream: a true profile is
// built from tick or bid/ask data. From OHLCV bars the standard approximation is to spread each
// bar's volume uniformly across its high-low range. That is right on average and wrong in detail —
// it cannot see that most of a bar's volume traded in its lower third. Expect the POC to be
// approximately right and individual node structure to be noisy, and do not build a strategy that
// depends on fine node resolution.

export interface Profile {
  /** Price of the bin holding the most volume. */
  poc: number;
  /** Value area high / low — the narrowest band around the POC holding `valueAreaPct` of volume. */
  vah: number;
  val: number;
  /** Full extent of trade. */
  high: number;
  low: number;
  totalVolume: number;
  /** Bin price -> volume, ascending by price. */
  bins: { price: number; volume: number }[];
  /** Bins below `lvnThreshold` x the mean bin volume, inside the value area — thin spots. */
  lowVolumeNodes: number[];
  binSize: number;
}

/**
 * Build a volume profile from bars by spreading each bar's volume across its range.
 *
 * `binSizeTicks` trades resolution against noise. Too fine and every bin is a single bar's
 * contribution; too coarse and the value area is quantised into meaninglessness. Four ticks (one
 * NQ point) over a session of a few hundred points is a reasonable default.
 */
export function buildProfile(bars: Bar[], inst: Instrument, binSizeTicks = 4, valueAreaPct = 70): Profile | null {
  if (!bars.length) return null;
  const binSize = binSizeTicks * inst.tickSize;
  let lo = Infinity;
  let hi = -Infinity;
  for (const b of bars) {
    if (b.l < lo) lo = b.l;
    if (b.h > hi) hi = b.h;
  }
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi < lo) return null;

  const first = Math.floor(lo / binSize);
  const count = Math.max(1, Math.floor(hi / binSize) - first + 1);
  if (count > 20_000) return null; // guard against a degenerate bin size
  const vol = new Float64Array(count);

  for (const b of bars) {
    const v = b.v > 0 ? b.v : 1;
    const from = Math.floor(b.l / binSize) - first;
    const to = Math.floor(b.h / binSize) - first;
    const span = to - from + 1;
    // Uniform spread across the bar's range — see the construction caveat above.
    const per = v / span;
    for (let k = from; k <= to; k++) vol[k] += per;
  }

  let pocIdx = 0;
  let total = 0;
  for (let k = 0; k < count; k++) {
    total += vol[k];
    if (vol[k] > vol[pocIdx]) pocIdx = k;
  }
  if (total <= 0) return null;

  // Value area: start at the POC and repeatedly absorb whichever neighbouring bin holds more
  // volume, until the target share of total volume is enclosed. This is the standard construction.
  const target = total * (valueAreaPct / 100);
  let lower = pocIdx;
  let upper = pocIdx;
  let acc = vol[pocIdx];
  while (acc < target && (lower > 0 || upper < count - 1)) {
    const below = lower > 0 ? vol[lower - 1] : -1;
    const above = upper < count - 1 ? vol[upper + 1] : -1;
    if (above >= below) {
      upper++;
      acc += vol[upper];
    } else {
      lower--;
      acc += vol[lower];
    }
  }

  const priceOf = (k: number) => (first + k) * binSize + binSize / 2;
  const mean = total / count;
  const lowVolumeNodes: number[] = [];
  for (let k = lower; k <= upper; k++) if (vol[k] < mean * 0.4) lowVolumeNodes.push(priceOf(k));

  const bins: { price: number; volume: number }[] = [];
  for (let k = 0; k < count; k++) if (vol[k] > 0) bins.push({ price: priceOf(k), volume: vol[k] });

  return {
    poc: priceOf(pocIdx),
    vah: priceOf(upper),
    val: priceOf(lower),
    high: hi,
    low: lo,
    totalVolume: total,
    bins,
    lowVolumeNodes,
    binSize,
  };
}

export type OpenLocation = "above value" | "inside value" | "below value";
export type DayType = "trend" | "normal" | "normal variation" | "neutral";

export interface SessionProfile {
  day: number;
  /** Index of the session's first bar, and one past its last. */
  from: number;
  to: number;
  profile: Profile;
  open: number;
  close: number;
  /** The PREVIOUS session's profile — the levels actually tradeable today. */
  prior: Profile | null;
  /** Where today opened relative to yesterday's value area. */
  openLocation: OpenLocation | null;
  /** Gap from the prior close, in points. */
  gap: number;
  /** Session range divided by the initial balance range — the classic day-type discriminator. */
  rangeExtension: number;
  dayType: DayType | null;
  /** Did price close inside the prior value area? */
  closedInPriorValue: boolean | null;
}

/**
 * Per-session profiles with the prior session's levels attached.
 *
 * Everything on a `SessionProfile` that a strategy may condition on at the OPEN — openLocation,
 * gap, the prior profile — is known before the session trades. `dayType` and `rangeExtension`
 * describe the completed session and are for ANALYSIS ONLY; conditioning entries on them would be
 * look-ahead, and the truncation test would not catch it because they are day-level aggregates.
 */
export function sessionProfiles(bars: Bar[], inst: Instrument, binSizeTicks = 4, ibMinutes = 60): SessionProfile[] {
  const clock = clockFor(bars, inst.tz as ExchangeTz);
  const out: SessionProfile[] = [];

  let start = 0;
  for (let i = 1; i <= bars.length; i++) {
    if (i < bars.length && clock.dayIndex[i] === clock.dayIndex[start]) continue;
    const slice = bars.slice(start, i);
    const profile = buildProfile(slice, inst, binSizeTicks);
    if (profile) {
      const ibEnd = inst.session[0] + ibMinutes;
      let ibHi = -Infinity;
      let ibLo = Infinity;
      for (let k = start; k < i; k++) {
        if (clock.minuteOfDay[k] < ibEnd) {
          ibHi = Math.max(ibHi, bars[k].h);
          ibLo = Math.min(ibLo, bars[k].l);
        }
      }
      const ibRange = ibHi > -Infinity && ibHi > ibLo ? ibHi - ibLo : NaN;
      const ext = Number.isFinite(ibRange) && ibRange > 0 ? (profile.high - profile.low) / ibRange : NaN;
      out.push({
        day: clock.dayIndex[start],
        from: start,
        to: i,
        profile,
        open: slice[0].o,
        close: slice[slice.length - 1].c,
        prior: null,
        openLocation: null,
        gap: 0,
        rangeExtension: ext,
        dayType: !Number.isFinite(ext) ? null : ext >= 2.5 ? "trend" : ext >= 1.5 ? "normal variation" : ext >= 1.15 ? "normal" : "neutral",
        closedInPriorValue: null,
      });
    }
    start = i;
  }

  for (let k = 1; k < out.length; k++) {
    const today = out[k];
    const prior = out[k - 1];
    today.prior = prior.profile;
    today.gap = today.open - prior.close;
    today.openLocation = today.open > prior.profile.vah ? "above value" : today.open < prior.profile.val ? "below value" : "inside value";
    today.closedInPriorValue = today.close <= prior.profile.vah && today.close >= prior.profile.val;
  }
  return out;
}
