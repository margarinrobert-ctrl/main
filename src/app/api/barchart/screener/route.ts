import { NextResponse } from "next/server";
import { getOptionsScreener, type ScreenerParams } from "@/lib/barchart/endpoints";
import { BarchartError } from "@/lib/barchart/errors";
import { scoreContracts } from "@/lib/flow/heuristic";
import { applyScreenerFilter } from "@/lib/flow/screener-filter";
import { snapshotStore } from "@/lib/persistence/snapshot-store";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const num = (k: string): number | undefined => {
    const v = searchParams.get(k);
    if (v == null || v === "") return undefined;
    const n = Number(v);
    return Number.isFinite(n) ? n : undefined;
  };

  const params: ScreenerParams = {
    minVolume: num("minVolume"),
    minOpenInterest: num("minOpenInterest"),
    minDTE: num("minDTE"),
    maxDTE: num("maxDTE"),
    minVolumeOpenInterestRatio: num("minVoir"),
  };

  try {
    const { data, source } = await getOptionsScreener(params);
    const rows = scoreContracts(applyScreenerFilter(data, params));
    // Snapshot for future flow-over-time ranking (in-memory stub until Postgres lands).
    await snapshotStore.save({ takenAt: new Date().toISOString(), rows });
    return NextResponse.json({ rows, source, count: rows.length });
  } catch (err) {
    const status = err instanceof BarchartError && err.kind === "BAD_PARAMS" ? 400 : 502;
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status });
  }
}
