import type { HistoryBar } from "./barchart/types";

/** Resample intraday bars into N-minute OHLC buckets (no-op for minutes ≤ 1). */
export function resampleBars(bars: HistoryBar[], minutes: number): HistoryBar[] {
  if (minutes <= 1 || bars.length === 0) return bars;
  const bucketMs = minutes * 60_000;
  const map = new Map<number, HistoryBar>();
  for (const b of bars) {
    const t = Date.parse(b.timestamp);
    if (!Number.isFinite(t)) continue;
    const k = Math.floor(t / bucketMs) * bucketMs;
    const e = map.get(k);
    if (!e) map.set(k, { timestamp: new Date(k).toISOString(), open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume });
    else {
      e.high = Math.max(e.high, b.high);
      e.low = Math.min(e.low, b.low);
      e.close = b.close;
      e.volume += b.volume;
    }
  }
  return [...map.values()].sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
}
