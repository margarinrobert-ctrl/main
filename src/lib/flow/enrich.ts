import type { OptionContract } from "../barchart/types";
import { bsDelta, bsGamma, impliedVol } from "./greeks";

/**
 * In-house greek backfill.
 *
 * Vendors (CBOE) frequently ship a chain WITHOUT implied vol / delta / gamma — most reliably on 0DTE and
 * expiration day, but also intermittently on thin names. Because the whole dealer-positioning stack (GEX,
 * DEX, gamma flip, call/put walls, ATM IV, VRP, the 3D surface…) reads those first-order greeks off the
 * contract, a chain missing them renders every greek panel blank while OI-based panels still work.
 *
 * This fills the gap: for any contract lacking IV/Δ/Γ but carrying a tradeable price, solve implied vol
 * from the mid (Black-Scholes, r = q = 0), then derive Δ and Γ — flooring time-to-expiry at half a session
 * so 0DTE (T → 0) doesn't blow up gamma. Contracts that already carry greeks pass through untouched;
 * contracts we can't price are left as-is. Pure — unit-tested.
 */

const MIN_T_DAYS = 0.5; // floor so 0DTE gamma/IV stay finite
const CALENDAR_DAYS = 365;

function midPrice(c: OptionContract): number | null {
  if (c.bid != null && c.ask != null && c.ask > 0 && c.bid >= 0 && c.ask >= c.bid) return (c.bid + c.ask) / 2;
  return c.last != null && c.last > 0 ? c.last : null;
}

export function enrichGreeks(chain: OptionContract[], spot: number | null): OptionContract[] {
  if (spot == null || spot <= 0 || !chain.length) return chain;
  let changed = false;
  const out = chain.map((c) => {
    const needIv = c.impliedVolatility == null || c.impliedVolatility <= 0;
    const needDelta = c.delta == null;
    const needGamma = c.gamma == null;
    if (!needIv && !needDelta && !needGamma) return c;

    const tYears = Math.max(c.dte ?? 0, MIN_T_DAYS) / CALENDAR_DAYS;
    let iv = needIv ? null : (c.impliedVolatility as number);
    if (iv == null) {
      const px = midPrice(c);
      if (px != null) iv = impliedVol(c.type, spot, c.strike, tYears, px);
    }
    if (iv == null || iv <= 0) return c; // no IV → can't backfill

    const delta = needDelta ? bsDelta(c.type, spot, c.strike, iv, tYears) : c.delta;
    const gamma = needGamma ? bsGamma(spot, c.strike, iv, tYears) : c.gamma;
    changed = true;
    return {
      ...c,
      impliedVolatility: iv,
      delta: delta ?? c.delta,
      gamma: gamma ?? c.gamma,
    };
  });
  return changed ? out : chain;
}
