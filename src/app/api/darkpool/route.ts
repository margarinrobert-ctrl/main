import { NextResponse } from "next/server";
import { readFixtureParsed } from "@/lib/barchart/client";
import { config } from "@/lib/barchart/config";
import { getHistory } from "@/lib/barchart/endpoints";
import { darkPoolLevels, darkPoolStats, type DarkPoolDay } from "@/lib/flow/darkpool";
import { finraDarkPool } from "@/lib/providers/finra";

// Off-exchange (dark-pool) flow for a symbol, from FINRA's free daily short-sale volume files.
// Live on servers with open egress; falls back to the sample fixture (clearly labelled "fixtures"
// in the UI) when the FINRA host is unreachable — e.g. local dev — so the tab never hard-fails.

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const sym = new URL(req.url).searchParams.get("symbol")?.trim().toUpperCase();
  if (!sym) return NextResponse.json({ error: "Missing ?symbol" }, { status: 400 });

  try {
    let rows: DarkPoolDay[] = [];
    let source: "live" | "fixtures" = "live";

    if (config.dataSource === "live") {
      rows = await finraDarkPool(sym).catch(() => []);
    }
    if (!rows.length) {
      rows = await readFixtureParsed<DarkPoolDay[]>(
        [`darkpool.${sym}.json`, "darkpool.SAMPLE.json"],
        (r) => (Array.isArray(r) ? (r as DarkPoolDay[]) : []),
      ).catch(() => []);
      source = "fixtures";
    }

    // Join daily price history: consolidated volume (for off-exchange %) and OHLC (so we can map
    // each day's off-exchange volume onto its price range → the dark-pool volume-by-price levels).
    if (rows.length) {
      try {
        const { data: bars } = await getHistory(sym, { maxRecords: 90 });
        const byDate = new Map(bars.map((b) => [b.timestamp.slice(0, 10), b]));
        rows = rows.map((r) => {
          const b = byDate.get(r.date);
          if (!b) return r;
          return {
            ...r,
            consolidatedVolume: r.consolidatedVolume ?? b.volume ?? null,
            open: r.open ?? b.open,
            high: r.high ?? b.high,
            low: r.low ?? b.low,
            close: r.close ?? b.close,
          };
        });
      } catch {
        /* off-exchange % and price levels just degrade to null */
      }
    }

    return NextResponse.json({ symbol: sym, source, days: rows, stats: darkPoolStats(rows), levels: darkPoolLevels(rows) });
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "dark-pool fetch failed" }, { status: 502 });
  }
}
