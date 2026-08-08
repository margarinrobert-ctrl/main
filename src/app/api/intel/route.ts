import { NextResponse } from "next/server";
import { config } from "@/lib/barchart/config";
import { loadServerHistory, loadServerJournal, loadServerSnapshots, storeMode } from "@/lib/intel/store";

// Read endpoint for the durable intelligence store. The browser pulls this on open and merges the
// server-collected history + journal into its local copy, so you see everything collected while the
// site was closed.
//
// Snapshots (per-strike positioning, one per day) are large, so they're served on demand:
//   ?symbol=SPY            → history + journal + snapshotDays (just the available day keys)
//   ?symbol=SPY&day=<YYYY-MM-DD> → additionally the full snapshot for that day (with strikes)

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const sym = url.searchParams.get("symbol")?.toUpperCase() || null;
  const all = url.searchParams.get("all") === "1";
  const day = url.searchParams.get("day");
  try {
    const journalAll = await loadServerJournal();
    const journal = sym && !all ? journalAll.filter((r) => r.symbol === sym) : journalAll;
    const history = sym ? await loadServerHistory(sym) : [];
    const snaps = sym ? await loadServerSnapshots(sym).catch(() => []) : [];
    return NextResponse.json({
      storeMode: storeMode(),
      symbol: sym,
      symbols: config.optionsWatchlist,
      history,
      journal,
      snapshotDays: snaps.map((s) => s.day),
      snapshot: day ? (snaps.find((s) => s.day === day) ?? null) : undefined,
    });
  } catch (e) {
    return NextResponse.json(
      { storeMode: storeMode(), symbol: sym, symbols: config.optionsWatchlist, history: [], journal: [], snapshotDays: [], error: e instanceof Error ? e.message : "read failed" },
      { status: 200 },
    );
  }
}
