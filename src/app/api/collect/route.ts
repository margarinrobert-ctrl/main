import { NextResponse } from "next/server";
import { config } from "@/lib/barchart/config";
import { collectAll } from "@/lib/intel/collect";
import { storeMode } from "@/lib/intel/store";

// Collection endpoint — point a scheduler (Vercel Cron, GitHub Actions, cron-job.org…) at this so the
// intelligence layer keeps recording + resolving predictions even when no browser is open. Protect it
// with CRON_SECRET (sent as `Authorization: Bearer <secret>` or `?key=<secret>`); if unset it's open.

export const dynamic = "force-dynamic";

function authorized(req: Request): boolean {
  const secret = process.env.CRON_SECRET;
  if (!secret) return true; // no secret configured → open (recommend setting CRON_SECRET)
  const url = new URL(req.url);
  return req.headers.get("authorization") === `Bearer ${secret}` || url.searchParams.get("key") === secret;
}

export async function GET(req: Request) {
  if (!authorized(req)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const url = new URL(req.url);
  const one = url.searchParams.get("symbol");
  const symbols = one ? [one.toUpperCase()] : config.optionsWatchlist;
  const results = await collectAll(symbols);
  return NextResponse.json({ ok: true, storeMode: storeMode(), at: new Date().toISOString(), results });
}
