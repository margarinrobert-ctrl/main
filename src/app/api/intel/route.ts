import { NextResponse } from "next/server";
import { config } from "@/lib/barchart/config";
import { loadServerHistory, loadServerJournal, storeMode } from "@/lib/intel/store";

// Read endpoint for the durable intelligence store. The browser pulls this on open and merges the
// server-collected history + journal into its local copy, so you see everything collected while the
// site was closed.

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const sym = url.searchParams.get("symbol")?.toUpperCase() || null;
  const all = url.searchParams.get("all") === "1";
  try {
    const journalAll = await loadServerJournal();
    const journal = sym && !all ? journalAll.filter((r) => r.symbol === sym) : journalAll;
    const history = sym ? await loadServerHistory(sym) : [];
    return NextResponse.json({ storeMode: storeMode(), symbol: sym, symbols: config.optionsWatchlist, history, journal });
  } catch (e) {
    return NextResponse.json({ storeMode: storeMode(), symbol: sym, symbols: config.optionsWatchlist, history: [], journal: [], error: e instanceof Error ? e.message : "read failed" }, { status: 200 });
  }
}
