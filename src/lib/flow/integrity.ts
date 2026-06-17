import type { OptionContract } from "../barchart/types";

// Data-integrity assessment. Confirms the chain is genuine CBOE live data (not a silent fixtures
// fallback) and that it's complete enough to trust — greeks/quote coverage, spot, open interest.
// It can't validate values against the exchange tick-for-tick, but it tells you when NOT to trust a
// panel (sample data, stale/zero quotes, missing greeks).

export type DataStatus = "live" | "degraded" | "sample" | "empty";

export interface IntegrityCheck {
  label: string;
  ok: boolean;
  detail: string;
}

export interface IntegrityReport {
  status: DataStatus;
  headline: string;
  source: string;
  asOf: string | null;
  contracts: number;
  greeksPct: number;
  quotesPct: number;
  checks: IntegrityCheck[];
}

const frac = (arr: OptionContract[], pred: (c: OptionContract) => boolean): number =>
  arr.length ? arr.filter(pred).length / arr.length : 0;

/**
 * Assess a loaded chain. `source` is the provider tag from the data layer ("live" = CBOE,
 * "fixtures" = canned sample). `asOf` is CBOE's own timestamp when available.
 */
export function assessChain(
  chain: OptionContract[],
  spot: number | null,
  source: string,
  asOf: string | null = null,
): IntegrityReport {
  const contracts = chain.length;
  const greeksPct = frac(chain, (c) => c.gamma != null && c.delta != null && c.impliedVolatility != null && c.impliedVolatility > 0);
  const quotesPct = frac(chain, (c) => c.bid != null && c.ask != null && c.ask > 0);
  const oi = chain.reduce((s, c) => s + (c.openInterest ?? 0), 0);
  const live = source === "live";

  const checks: IntegrityCheck[] = [
    { label: "Source", ok: live, detail: live ? "CBOE delayed feed (~15 min)" : `Sample / fixtures (${source || "n/a"})` },
    { label: "Contracts", ok: contracts > 0, detail: `${contracts.toLocaleString()} loaded` },
    { label: "Spot", ok: spot != null && spot > 0, detail: spot != null ? `underlying ${spot.toLocaleString()}` : "missing" },
    { label: "Greeks", ok: greeksPct >= 0.8, detail: `${Math.round(greeksPct * 100)}% carry IV/Δ/Γ` },
    { label: "Quotes", ok: quotesPct >= 0.5, detail: `${Math.round(quotesPct * 100)}% have live bid/ask` },
    { label: "Open interest", ok: oi > 0, detail: oi > 0 ? `${oi.toLocaleString()} total (prior-day settle, T+1)` : "none" },
  ];

  let status: DataStatus;
  let headline: string;
  if (contracts === 0) {
    status = "empty";
    headline = "No options data loaded.";
  } else if (!live) {
    status = "sample";
    headline = "Showing SAMPLE data — the live CBOE feed didn't respond (auto-fallback). Don't trade off these numbers.";
  } else if (!(spot != null && spot > 0) || greeksPct < 0.8 || quotesPct < 0.5 || oi === 0) {
    status = "degraded";
    headline = "Live CBOE data, with gaps — some greeks/quotes/OI are missing on this chain.";
  } else {
    status = "live";
    headline = "Verified CBOE data — real exchange quotes, ~15-min delayed.";
  }

  return { status, headline, source, asOf, contracts, greeksPct, quotesPct, checks };
}
