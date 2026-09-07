import type { OptionContract } from "../barchart/types";
import { gammaFlipNearest, gexByStrike, netDex, netGex, secondOrderExposure } from "./analytics";

/**
 * Dealer scenario / stress matrix — the institutional risk layer applied to the estimated dealer book.
 *
 * For a grid of (spot move x%, IV shock Δσ vol-points) it computes the DEALER RE-HEDGING FLOW: the $ of
 * delta dealers must transact to stay neutral after the shock, from the net greeks the terminal already
 * estimates:
 *
 *     ΔdealerDelta ≈ GEX·x  +  vanna·Δσ          (GEX = $Δ per 1% move, vanna = $Δ per 1 vol-pt)
 *     hedgingFlow  =  −ΔdealerDelta               (they trade the opposite to flatten)
 *
 * hedgingFlow > 0 → dealers BUY (supports price); < 0 → dealers SELL (pressures price). A cell "amplifies"
 * when the flow runs WITH the spot move (buy into strength / sell into weakness) — the short-gamma regime
 * where hedging destabilizes rather than dampens. Charm (per-day delta drift) is constant across the grid,
 * so it is reported separately rather than shaded into every cell.
 *
 * Pure presentation of existing analytics — no position of the user's is assumed; this is the dealer book.
 */

export interface ScenarioCell {
  spotPct: number; // column: spot move in %
  volPts: number; // row: IV shock in vol-points
  flow: number; // $ dealer hedging flow (+ buy / − sell)
  amplifies: boolean; // flow runs with the spot move (destabilizing)
}

export interface ScenarioReport {
  ok: boolean;
  spotAxis: number[]; // % moves (columns), ascending
  volAxis: number[]; // vol-point shocks (rows), descending (high vol on top)
  cells: ScenarioCell[][]; // [volRow][spotCol]
  netGex: number | null; // $ / 1%  (+ dealers long gamma)
  regime: "long" | "short" | "neutral" | "n/a";
  flip: number | null; // gamma-flip price level
  flipDistPct: number | null; // signed distance spot→flip, in %
  vanna: number | null; // $ / 1 vol-pt
  charm: number | null; // $ / day (constant drift)
  netDex: number | null;
  maxAbsFlow: number; // for color scaling
  worst: { spotPct: number; volPts: number; flow: number } | null; // largest amplifying flow
  stress: { spotPct: number; volPts: number; flow: number } | null; // realistic down-spot / up-vol corner
}

const DEFAULT_SPOT = [-4, -3, -2, -1, 0, 1, 2, 3, 4];
const DEFAULT_VOL = [10, 6, 3, 0, -3, -6];

export function scenarioMatrix(
  chain: OptionContract[],
  spot: number | null,
  opts?: { spotSteps?: number[]; volSteps?: number[] },
): ScenarioReport {
  const spotAxis = opts?.spotSteps ?? DEFAULT_SPOT;
  const volAxis = opts?.volSteps ?? DEFAULT_VOL;
  const empty: ScenarioReport = {
    ok: false, spotAxis, volAxis, cells: [], netGex: null, regime: "n/a", flip: null, flipDistPct: null,
    vanna: null, charm: null, netDex: null, maxAbsFlow: 0, worst: null, stress: null,
  };
  if (!chain.length || spot == null || spot <= 0) return empty;

  const gex = netGex(chain, spot); // $ / 1%
  const so = secondOrderExposure(chain, spot);
  const vanna = so.vanna; // $ / vol-pt
  const charm = so.charm; // $ / day
  const ndex = netDex(chain, spot);
  const flip = gammaFlipNearest(gexByStrike(chain, spot), spot);
  if (gex == null) return empty;

  const gexT = gex;
  const vannaT = vanna ?? 0;

  let maxAbs = 0;
  let worst: ScenarioReport["worst"] = null;
  const cells: ScenarioCell[][] = volAxis.map((dv) =>
    spotAxis.map((x) => {
      // dealer delta change, then negate → the flow they must trade to re-hedge (|| 0 avoids -0)
      const flow = -(gexT * x + vannaT * dv) || 0;
      const amplifies = x !== 0 && Math.sign(flow) === Math.sign(x);
      maxAbs = Math.max(maxAbs, Math.abs(flow));
      if (amplifies && (worst == null || Math.abs(flow) > Math.abs(worst.flow))) {
        worst = { spotPct: x, volPts: dv, flow };
      }
      return { spotPct: x, volPts: dv, flow, amplifies };
    }),
  );

  // Realistic joint stress: the biggest down-move with the biggest vol-up (gaps come with vol spikes).
  const downCol = Math.min(...spotAxis);
  const upVolRow = Math.max(...volAxis);
  const stressFlow = -(gexT * downCol + vannaT * upVolRow);
  const stress = { spotPct: downCol, volPts: upVolRow, flow: stressFlow };

  const regime: ScenarioReport["regime"] = gex > 0 ? "long" : gex < 0 ? "short" : "neutral";
  const flipDistPct = flip != null ? ((flip - spot) / spot) * 100 : null;

  return { ok: true, spotAxis, volAxis, cells, netGex: gex, regime, flip, flipDistPct, vanna, charm, netDex: ndex, maxAbsFlow: maxAbs, worst, stress };
}
