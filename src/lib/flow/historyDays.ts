import type { GexSample } from "../gex-history";

/**
 * Day-slicing for the recorded 24/7 positioning series — powers the History tab's past-day browser.
 * Days are bucketed in the VIEWER's local timezone (the series is browsed in the browser). Pure and
 * unit-tested.
 */

export interface DaySlice {
  key: string; // YYYY-MM-DD (local)
  label: string; // e.g. "Fri, Aug 1"
  samples: GexSample[]; // ascending by t
}

export interface DayStats {
  n: number;
  spotOpen: number | null;
  spotClose: number | null;
  spotChangePct: number | null;
  gexOpen: number | null;
  gexClose: number | null;
  gexMin: number | null;
  gexMax: number | null;
  dexClose: number | null; // last recorded net delta (null on older days recorded before DEX existed)
  ivMin: number | null;
  ivMax: number | null;
  flipClose: number | null;
}

const dayKey = (t: number): string => {
  const d = new Date(t);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

const dayLabel = (t: number): string => new Date(t).toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });

/** Group a (possibly unsorted) series into local-calendar days, oldest day first. */
export function groupByDay(series: GexSample[]): DaySlice[] {
  const m = new Map<string, GexSample[]>();
  for (const s of [...series].sort((a, b) => a.t - b.t)) {
    const k = dayKey(s.t);
    const arr = m.get(k);
    if (arr) arr.push(s);
    else m.set(k, [s]);
  }
  return [...m.entries()].map(([key, samples]) => ({ key, label: dayLabel(samples[0].t), samples }));
}

const firstOf = (xs: (number | null | undefined)[]): number | null => {
  for (const x of xs) if (x != null && Number.isFinite(x)) return x;
  return null;
};
const lastOf = (xs: (number | null | undefined)[]): number | null => firstOf([...xs].reverse());

export function dayStats(samples: GexSample[]): DayStats {
  const spots = samples.map((s) => s.spot);
  const gexs = samples.map((s) => s.gex);
  const ivs = samples.map((s) => s.iv).filter((v): v is number => v != null && Number.isFinite(v));
  const gexVals = gexs.filter((v): v is number => v != null && Number.isFinite(v));
  const spotOpen = firstOf(spots);
  const spotClose = lastOf(spots);
  return {
    n: samples.length,
    spotOpen,
    spotClose,
    spotChangePct: spotOpen != null && spotClose != null && spotOpen !== 0 ? ((spotClose - spotOpen) / spotOpen) * 100 : null,
    gexOpen: firstOf(gexs),
    gexClose: lastOf(gexs),
    gexMin: gexVals.length ? Math.min(...gexVals) : null,
    gexMax: gexVals.length ? Math.max(...gexVals) : null,
    dexClose: lastOf(samples.map((s) => s.dex)),
    ivMin: ivs.length ? Math.min(...ivs) : null,
    ivMax: ivs.length ? Math.max(...ivs) : null,
    flipClose: lastOf(samples.map((s) => s.flip)),
  };
}
