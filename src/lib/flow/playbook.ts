import type { OptionContract } from "../barchart/types";
import { callWall, expectedMove, gammaFlip, gexByStrike, maxPain, netGex, putCallRatio, putWall } from "./analytics";

export type Side = "bullish" | "bearish" | "neutral";

export interface Play {
  title: string;
  level: number | null;
  side: Side;
  bias: string; // short tag
  detail: string; // how to scalp it
}

export interface Playbook {
  regime: "long" | "short" | "unknown";
  regimeText: string;
  bias: Side;
  biasText: string;
  spot: number | null;
  netGex: number | null;
  plays: Play[];
  notes: string[];
}

function fmtNum(n: number): string {
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

/**
 * Translate the GEX structure into an intraday/scalping playbook: dealer-gamma regime,
 * an overall bias (spot vs γ-flip), and a bullish/bearish plan at each key level.
 * Heuristics are standard dealer-gamma logic — educational, not financial advice.
 */
export function buildPlaybook(chain: OptionContract[], spot: number | null): Playbook {
  const by = gexByStrike(chain, spot);
  const ngex = netGex(chain, spot);
  const flip = gammaFlip(by);
  const cw = callWall(by);
  const pw = putWall(by);
  const pc = putCallRatio(chain);

  const exps = [...new Set(chain.map((c) => c.expiration))];
  const withDte = exps
    .map((e) => ({ e, dte: chain.find((c) => c.expiration === e)?.dte ?? 9999 }))
    .filter((x) => x.dte >= 0)
    .sort((a, b) => a.dte - b.dte);
  const exp = withDte[0]?.e ?? exps[0] ?? null;
  const mp = exp ? maxPain(chain, exp) : null;
  const em = exp ? expectedMove(chain, spot, exp) : null;

  const regime: "long" | "short" | "unknown" = ngex == null ? "unknown" : ngex >= 0 ? "long" : "short";
  const regimeText =
    regime === "long"
      ? "Positive net dealer gamma → dealers buy dips / sell rips. Expect vol suppression, mean-reversion and pinning. Fade extremes back toward levels; breakouts tend to fail."
      : regime === "short"
        ? "Negative net dealer gamma → dealers sell dips / buy rips. Expect amplified, trending moves. Trade momentum; breakouts run and dips can cascade."
        : "Not enough greeks to classify the dealer-gamma regime.";

  let bias: Side = "neutral";
  let biasText = "Spot vs γ-flip is neutral — wait for a decisive break to pick a side.";
  if (spot != null && flip != null) {
    const d = (spot - flip) / spot;
    if (d > 0.001) {
      bias = "bullish";
      biasText = `Spot is ABOVE the γ-flip (${fmtNum(flip)}) → positive-gamma zone: dips get bought. Lean long on pullbacks toward support while price holds above the flip.`;
    } else if (d < -0.001) {
      bias = "bearish";
      biasText = `Spot is BELOW the γ-flip (${fmtNum(flip)}) → negative-gamma zone: rallies get sold and moves accelerate. Lean short on bounces while price stays below the flip.`;
    } else {
      biasText = `Spot is right at the γ-flip (${fmtNum(flip)}) → regime pivot / chop. Trade the break of the flip, not the level itself.`;
    }
  }

  const plays: Play[] = [];

  if (flip != null) {
    plays.push({
      title: `γ-Flip / HVL · ${fmtNum(flip)}`,
      level: flip,
      side: "neutral",
      bias: "Regime pivot",
      detail:
        "Above = positive gamma (pin/mean-revert → fade pushes, scalp back to prior level/VWAP). Below = negative gamma (momentum → trade breakouts, trail the trend). Reclaiming or losing this line is your bias switch.",
    });
  }
  if (cw != null && spot != null) {
    const above = spot > cw;
    plays.push({
      title: `Call wall / resistance · ${fmtNum(cw)}`,
      level: cw,
      side: above ? "bullish" : "bearish",
      bias: above ? "Reclaimed → squeeze" : "Resistance / magnet",
      detail: above
        ? "Price is above the call wall — thin gamma above can squeeze higher. Buy pullbacks that hold above it; stop on a loss back below."
        : "Heaviest call gamma caps upside. Scalp SHORT the first rejection into it, targeting the flip / put wall. A clean break-and-hold ABOVE flips bullish (dealer short-cover squeeze).",
    });
  }
  if (pw != null && spot != null) {
    const below = spot < pw;
    plays.push({
      title: `Put wall / support · ${fmtNum(pw)}`,
      level: pw,
      side: below ? "bearish" : "bullish",
      bias: below ? "Lost → flush" : "Support / bounce",
      detail: below
        ? "Support is broken — negative-gamma flush risk. Scalp SHORT weak bounces and cover into the next level down."
        : "Heaviest put gamma supports price. Scalp LONG the bounce targeting the flip / call wall. A clean break BELOW turns bearish (puts in play, moves accelerate).",
    });
  }
  if (mp != null && spot != null) {
    const side: Side = Math.abs(spot - mp) / spot < 0.002 ? "neutral" : spot > mp ? "bearish" : "bullish";
    plays.push({
      title: `Max pain · ${fmtNum(mp)}${exp ? ` (${exp})` : ""}`,
      level: mp,
      side,
      bias: spot > mp ? "Pulls down to pain" : spot < mp ? "Pulls up to pain" : "At pain",
      detail:
        "Into expiry, price often gravitates to max pain. Far above → lean fade-down toward it; far below → lean drift-up. Strongest on expiration day, weak early in the cycle.",
    });
  }
  if (em != null && spot != null) {
    plays.push({
      title: `1D expected range · ±${em.abs.toFixed(2)} (±${(em.pct * 100).toFixed(1)}%)`,
      level: null,
      side: "neutral",
      bias: "Scalp targets",
      detail: `Roughly ${fmtNum(spot - em.abs)} to ${fmtNum(spot + em.abs)}. In long-gamma, fade the edges back inside; in short-gamma, edge breaks can extend. Use as profit targets / reversal zones.`,
    });
  }
  if (pc.vol != null) {
    const s: Side = pc.vol > 1.2 ? "bearish" : pc.vol < 0.7 ? "bullish" : "neutral";
    plays.push({
      title: `Put/Call volume · ${pc.vol.toFixed(2)}`,
      level: null,
      side: s,
      bias: pc.vol > 1.2 ? "Put-heavy" : pc.vol < 0.7 ? "Call-heavy" : "Balanced",
      detail:
        pc.vol > 1.2
          ? "Heavy put flow = defensive/bearish tilt (watch for a contrarian bounce at extremes)."
          : pc.vol < 0.7
            ? "Heavy call flow = offensive/bullish tilt (chase risk; watch for exhaustion)."
            : "Balanced two-way flow — no strong skew.",
    });
  }

  const notes = [
    regime === "long"
      ? "Long-gamma session = range/fade bias; size breakout trades down."
      : regime === "short"
        ? "Short-gamma session = trend/momentum bias; respect stops — moves overshoot."
        : "",
    "Levels are ~15-min delayed (free CBOE feed). Educational tooling — not financial advice.",
  ].filter(Boolean);

  return { regime, regimeText, bias, biasText, spot, netGex: ngex, plays, notes };
}
