import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DaySnapshot } from "./intel/snapshot";
import { appendLocalSnapshot, localSnapshotDays, readLocalSnapshot, readLocalSnapshots } from "./snapshot-local";

// minimal localStorage for the node test env
beforeEach(() => {
  const store = new Map<string, string>();
  vi.stubGlobal("window", {});
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  });
});

const snap = (day: string, t: number, strikes = 3): DaySnapshot => ({
  day, t, spot: 100, gex: 1e9, dex: 2e8, flip: 99, iv: 0.2, pcr: 1,
  strikes: Array.from({ length: strikes }, (_, i) => ({ k: 95 + i * 5, g: 1e8, d: 1e7, co: 100, po: 200 })),
});

describe("snapshot-local", () => {
  it("persists a snapshot and reads it back by day", () => {
    appendLocalSnapshot("SPY", snap("2026-08-08", 10));
    expect(readLocalSnapshots("SPY").length).toBe(1);
    expect(readLocalSnapshot("SPY", "2026-08-08")?.strikes.length).toBe(3);
    expect(localSnapshotDays("SPY")).toEqual(["2026-08-08"]);
  });

  it("keeps one entry per day (latest write wins) and accumulates distinct days", () => {
    appendLocalSnapshot("SPY", snap("2026-08-08", 10));
    appendLocalSnapshot("SPY", snap("2026-08-08", 20, 5)); // same day, later
    appendLocalSnapshot("SPY", snap("2026-08-09", 30));
    expect(localSnapshotDays("SPY")).toEqual(["2026-08-08", "2026-08-09"]);
    expect(readLocalSnapshot("SPY", "2026-08-08")?.strikes.length).toBe(5);
  });

  it("keeps symbols separate and tolerates a null build", () => {
    appendLocalSnapshot("SPY", snap("2026-08-08", 10));
    appendLocalSnapshot("QQQ", snap("2026-08-08", 10));
    expect(readLocalSnapshots("SPY").length).toBe(1);
    expect(readLocalSnapshots("QQQ").length).toBe(1);
    expect(appendLocalSnapshot("SPY", null).length).toBe(1); // no-op, keeps what's there
  });

  it("returns null / empty for days and symbols never recorded", () => {
    expect(readLocalSnapshot("SPY", "2026-01-01")).toBeNull();
    expect(readLocalSnapshots("NVDA")).toEqual([]);
  });
});
