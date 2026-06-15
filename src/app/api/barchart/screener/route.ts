import { NextResponse } from "next/server";
import { getOptionsScreener } from "@/lib/barchart/endpoints";
import { BarchartError } from "@/lib/barchart/errors";
import { scoreContracts } from "@/lib/flow/heuristic";
import { snapshotStore } from "@/lib/persistence/snapshot-store";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const { data, source } = await getOptionsScreener({});
    const rows = scoreContracts(data);
    // Snapshot for future flow-over-time ranking (in-memory stub until Postgres lands).
    await snapshotStore.save({ takenAt: new Date().toISOString(), rows });
    return NextResponse.json({ rows, source, count: rows.length });
  } catch (err) {
    const status = err instanceof BarchartError && err.kind === "BAD_PARAMS" ? 400 : 502;
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status });
  }
}
