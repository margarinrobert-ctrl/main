"use client";

/**
 * Where the numbers on screen actually came from.
 *
 * The data layer falls back to canned fixtures whenever a live call fails — deliberately, so the
 * UI never breaks — and it tags the result `source: "fixtures"` when it does. Until this component
 * existed, every consumer threw that tag away: `FlowTable` and `Scanner` both stored it in state
 * and never rendered it, and `DataStatus`, which was written specifically to say "Showing SAMPLE
 * data, don't trade off these numbers", was imported by nothing at all.
 *
 * The net effect was a page that could show canned sample numbers, indistinguishable from live
 * market data, on a screen whose entire purpose is to inform a trade. Everything downstream of
 * that — the flow scores, the GEX levels, the scanner ranks — was arithmetic on made-up input,
 * presented as fact.
 *
 * So: any surface that displays market data renders this, and `provenance.test.ts` fails the build
 * if one stops doing so. A badge is cheap; the alternative is lying.
 */

export type Origin = "live" | "fixtures" | "" | string;

interface Props {
  source: Origin;
  /** The feed's own timestamp, when it publishes one. */
  asOf?: string | null;
  /** What the feed is, for the live case — e.g. "CBOE delayed ~15 min". */
  feed?: string;
  /** Row/contract count, shown when it helps judge completeness. */
  count?: number | null;
  className?: string;
}

const isLive = (s: Origin) => s === "live";

export function Provenance({ source, asOf, feed, count, className = "" }: Props) {
  // An empty source means the fetch never reported one. That is not "probably live" — it is
  // unknown, and it is shown as unknown.
  const state = source === "" ? "unknown" : isLive(source) ? "live" : "sample";

  const tone =
    state === "live"
      ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
      : state === "sample"
        ? "border-red-500/50 bg-red-500/10 text-red-200"
        : "border-amber-500/40 bg-amber-500/10 text-amber-200";
  const dot = state === "live" ? "bg-emerald-400" : state === "sample" ? "bg-red-400" : "bg-amber-400";

  const label =
    state === "live"
      ? `Live${feed ? ` · ${feed}` : ""}`
      : state === "sample"
        ? "SAMPLE DATA — the live feed did not respond. These numbers are canned. Do not trade off them."
        : "Source unknown — could not confirm this is live data.";

  return (
    <div
      role="status"
      data-provenance={state}
      className={`flex flex-wrap items-center gap-2 rounded-lg border px-2.5 py-1.5 font-mono text-[11px] ${tone} ${className}`}
    >
      <span className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} aria-hidden />
      <span>{label}</span>
      {asOf ? <span className="opacity-80">as-of {asOf}</span> : null}
      {typeof count === "number" ? <span className="ml-auto opacity-70">{count.toLocaleString()} rows</span> : null}
    </div>
  );
}
