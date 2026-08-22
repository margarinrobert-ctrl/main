import { orb, volBreakout } from "./orb";
import { sweepReversal, vwapFade } from "./reversion";
import { timeOfDayControl, trendPullback } from "./trend";
import type { Strategy } from "../types";

/** The candidate universe. Order is fixed so seeded studies are reproducible run to run. */
export const STRATEGIES: Strategy[] = [orb, volBreakout, vwapFade, sweepReversal, trendPullback, timeOfDayControl];

/** Candidates only — the control is excluded from portfolio construction by design. */
export const ALPHA_CANDIDATES = STRATEGIES.filter((s) => s.id !== "tod-control");

export function strategy(id: string): Strategy {
  const s = STRATEGIES.find((x) => x.id === id);
  if (!s) throw new Error(`unknown strategy ${id} (known: ${STRATEGIES.map((x) => x.id).join(", ")})`);
  return s;
}

export { orb, volBreakout, vwapFade, sweepReversal, trendPullback, timeOfDayControl };
