import { NextResponse } from "next/server";
import { getEquityOptions } from "@/lib/barchart/endpoints";
import { BarchartError } from "@/lib/barchart/errors";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const symbol = searchParams.get("symbol")?.trim();
  if (!symbol) {
    return NextResponse.json({ error: "Missing ?symbol" }, { status: 400 });
  }

  try {
    const { data, source, asOf } = await getEquityOptions(symbol);
    const spot = data.find((c) => c.underlyingPrice != null)?.underlyingPrice ?? null;
    return NextResponse.json({ chain: data, source, spot, asOf });
  } catch (err) {
    const status = err instanceof BarchartError && err.kind === "BAD_PARAMS" ? 400 : 502;
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status });
  }
}
