import { mergeSnapshots, type DaySnapshot } from "./intel/snapshot";

/**
 * Browser-side per-strike snapshot store.
 *
 * The scheduled collector records snapshots around the clock, but only once its build reaches the
 * branch the schedule runs from — and expired chains can never be re-fetched, so any day missed is lost
 * for good. Recording in the browser as well means every day you actually have the terminal open gets a
 * strike profile immediately, independent of the server job. The two merge on read.
 *
 * Kept deliberately small: a shorter cap than the server store, since localStorage is a shared ~5MB
 * budget across every symbol you visit.
 */

const LOCAL_CAP = 30; // days per symbol
const key = (sym: string) => `gexsnap:${sym.toUpperCase()}`;

export function readLocalSnapshots(sym: string): DaySnapshot[] {
  if (typeof window === "undefined") return [];
  try {
    const v = JSON.parse(localStorage.getItem(key(sym)) ?? "[]");
    return Array.isArray(v) ? (v as DaySnapshot[]) : [];
  } catch {
    return [];
  }
}

/** Merge a freshly-built snapshot into the local store (one per day, latest wins) and return the set. */
export function appendLocalSnapshot(sym: string, snap: DaySnapshot | null): DaySnapshot[] {
  if (typeof window === "undefined") return [];
  const merged = mergeSnapshots(readLocalSnapshots(sym), snap, LOCAL_CAP);
  try {
    localStorage.setItem(key(sym), JSON.stringify(merged));
  } catch {
    // storage full/disabled — drop the oldest half and retry once, else give up silently
    try {
      localStorage.setItem(key(sym), JSON.stringify(merged.slice(-Math.ceil(LOCAL_CAP / 2))));
    } catch {
      /* ignore */
    }
  }
  return merged;
}

/** The locally-recorded snapshot for one day, if any. */
export function readLocalSnapshot(sym: string, day: string): DaySnapshot | null {
  return readLocalSnapshots(sym).find((s) => s.day === day) ?? null;
}

export function localSnapshotDays(sym: string): string[] {
  return readLocalSnapshots(sym).map((s) => s.day);
}
