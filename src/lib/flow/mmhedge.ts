import type { HistoryBar, OptionContract } from "../barchart/types";
import {
  atmIv,
  callResistance,
  expectedMove1D,
  gammaFlipNearest,
  gexByStrike,
  netDex,
  netGex,
  putCallRatio,
  putSupport,
  secondOrderExposure,
  type StrikeGex,
} from "./analytics";

// Market-maker hedging algo. Dealers who are short/long options must hedge in the underlying, and
// that hedging is mechanical and predictable around big-gamma strikes:
//   • LONG gamma (net GEX > 0): dealers BUY dips / SELL rips → price is PINNED toward the dominant
//     gamma strike (the "magnet"). Trade toward the magnet; breakouts fail.
//   • SHORT gamma (net GEX < 0): dealers SELL dips / BUY rips → moves are AMPLIFIED away from the
//     γ-flip. Trade the continuation; breaks cascade/squeeze.
// Charm (time-decay) and vanna (vol-change) hedging add a secondary buy/sell drift. The algo nets
// these into a single "main pressure" direction and a concrete trade at the active level.
// Standard dealer-gamma mechanics — educational, not financial advice.

export type Pressure = "up" | "down" | "balanced";

export interface MMComponent {
  label: string;
  dir: Pressure;
  weight: number;
  detail: string;
}

export interface MMTrade {
  side: "long" | "short" | "wait";
  entry: number | null;
  target: number | null;
  stop: number | null;
  rationale: string;
}

export interface MMHedge {
  regime: "long" | "short" | "unknown";
  netGex: number | null;
  flip: number | null;
  magnet: number | null;
  callWall: number | null;
  putWall: number | null;
  nearestLevel: { name: string; price: number; distPct: number } | null;
  atLevel: boolean;
  pressure: Pressure;
  pressureScore: number; // -100 (down) .. +100 (up)
  components: MMComponent[];
  trade: MMTrade | null;
  notes: string[];
}

const clamp = (x: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, x));
const f2 = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 2 });
const dirOf = (x: number): Pressure => (x > 0 ? "up" : x < 0 ? "down" : "balanced");

function magnetStrike(by: StrikeGex[]): number | null {
  if (!by.length) return null;
  return by.reduce((m, x) => (Math.abs(x.gex) > Math.abs(m.gex) ? x : m)).strike;
}

/**
 * Run the dealer-hedging algo for a chain at a given spot. `bars` is optional (only used for context).
 * Returns the net hedging pressure and a trade taken in the direction dealers are pushing.
 */
export function mmHedge(chain: OptionContract[], spot: number | null, _bars: HistoryBar[] = []): MMHedge {
  const base: MMHedge = {
    regime: "unknown",
    netGex: null,
    flip: null,
    magnet: null,
    callWall: null,
    putWall: null,
    nearestLevel: null,
    atLevel: false,
    pressure: "balanced",
    pressureScore: 0,
    components: [],
    trade: null,
    notes: [],
  };
  if (!spot || !chain.length) return base;

  const by = gexByStrike(chain, spot);
  if (!by.length) return base;
  const ngex = netGex(chain, spot);
  const flip = gammaFlipNearest(by, spot);
  const cw = callResistance(by, spot);
  const pw = putSupport(by, spot);
  const magnet = magnetStrike(by);
  const so = secondOrderExposure(chain, spot);
  const pc = putCallRatio(chain);
  const ndex = netDex(chain, spot);
  const exps = [...new Set(chain.map((c) => c.expiration))].sort();
  const iv0 = exps.length ? atmIv(chain, spot, exps[0]) : null;
  const em = expectedMove1D(spot, iv0)?.abs ?? spot * 0.005;
  const regime: MMHedge["regime"] = ngex == null ? "unknown" : ngex >= 0 ? "long" : "short";

  // nearest important level
  const cands = [
    { name: "γ-flip", price: flip },
    { name: "Call wall", price: cw },
    { name: "Put wall", price: pw },
    { name: "Gamma magnet", price: magnet },
  ].filter((c): c is { name: string; price: number } => c.price != null);
  const nearest = cands.length
    ? cands.reduce((p, c) => (Math.abs(c.price - spot) < Math.abs(p.price - spot) ? c : p))
    : null;
  const nearestLevel = nearest ? { ...nearest, distPct: ((nearest.price - spot) / spot) * 100 } : null;
  const atLevel = nearest != null && Math.abs(nearest.price - spot) <= em * 0.6;

  // ── pressure components ──
  const components: MMComponent[] = [];
  // 1) gamma/pin (dominant)
  let gammaDir = 0;
  if (regime === "long" && magnet != null) {
    gammaDir = Math.sign(magnet - spot);
    components.push({
      label: "Gamma pin",
      dir: dirOf(gammaDir),
      weight: 50,
      detail: `Long gamma → dealers defend & pin toward the ${f2(magnet)} magnet (buy dips / sell rips).`,
    });
  } else if (regime === "short" && flip != null) {
    gammaDir = Math.sign(spot - flip);
    components.push({
      label: "Gamma (short)",
      dir: dirOf(gammaDir),
      weight: 50,
      detail: `Short gamma → dealers chase the move away from the ${f2(flip)} flip (sell dips / buy rips).`,
    });
  }
  // 2) charm: positive charm exposure → dealers sell over time → down
  const charmDir = so.charm == null ? 0 : so.charm >= 0 ? -1 : 1;
  if (so.charm != null)
    components.push({
      label: "Charm drift",
      dir: dirOf(charmDir),
      weight: 25,
      detail: `Time-decay hedging pushes ${charmDir >= 0 ? "UP" : "DOWN"} (~into expiry).`,
    });
  // 3) put/call flow
  const pcDir = pc.vol == null ? 0 : pc.vol < 0.8 ? 1 : pc.vol > 1.2 ? -1 : 0;
  if (pc.vol != null)
    components.push({
      label: "Order flow",
      dir: dirOf(pcDir),
      weight: 15,
      detail: `Put/Call ${pc.vol.toFixed(2)} — ${pcDir > 0 ? "call-heavy (bullish)" : pcDir < 0 ? "put-heavy (bearish)" : "balanced"}.`,
    });
  // 4) vanna: positive vanna → falling-IV buy bias
  const vannaDir = so.vanna == null ? 0 : so.vanna >= 0 ? 1 : -1;
  if (so.vanna != null)
    components.push({
      label: "Vanna",
      dir: dirOf(vannaDir),
      weight: 10,
      detail: `${vannaDir >= 0 ? "Positive" : "Negative"} vanna — calmer IV ${vannaDir >= 0 ? "supports" : "pressures"} price.`,
    });

  const pressureScore = Math.round(clamp(gammaDir * 50 + charmDir * 25 + pcDir * 15 + vannaDir * 10, -100, 100));
  const pressure = pressureScore > 15 ? "up" : pressureScore < -15 ? "down" : "balanced";

  // ── trade in the direction of dealer pressure ──
  let trade: MMTrade | null = null;
  const side: MMTrade["side"] = pressureScore > 15 ? "long" : pressureScore < -15 ? "short" : "wait";
  if (side === "wait") {
    trade = {
      side: "wait",
      entry: null,
      target: null,
      stop: null,
      rationale: `Dealer pressure is balanced near the ${nearestLevel?.name ?? "level"}. Wait for price to commit through ${flip != null ? f2(flip) : "the flip"} or reach a wall.`,
    };
  } else if (regime === "long" && magnet != null) {
    const entry = atLevel && nearest ? nearest.price : spot;
    const stop = side === "long" ? pw ?? flip : cw ?? flip;
    trade = {
      side,
      entry,
      target: magnet,
      stop,
      rationale: `Long-gamma PIN: dealers hedge by ${side === "long" ? "buying dips" : "selling rips"}, dragging price ${pressure.toUpperCase()} toward the ${f2(magnet)} magnet. ${side === "long" ? "Buy" : "Sell"} ${atLevel ? `at the ${nearestLevel?.name} (${f2(entry)})` : `near ${f2(entry)}`}; target ${f2(magnet)}; invalidate beyond ${stop != null ? f2(stop) : "the opposite wall"}.`,
    };
  } else if (regime === "short" && flip != null) {
    const up = side === "long";
    const target = up ? cw : pw;
    trade = {
      side,
      entry: spot,
      target: target ?? null,
      stop: flip,
      rationale: `Short-gamma MOMENTUM: dealer hedging amplifies the move, pressure ${pressure.toUpperCase()}. Trade the continuation ${up ? "above" : "below"} the ${f2(flip)} flip; target ${target != null ? f2(target) : "the next wall"}; stop back through ${f2(flip)} (regime flips there).`,
    };
  }

  const notes = [
    regime === "long"
      ? "Long-gamma regime: fade extremes into the magnet; breakouts usually fail (dealers lean against them)."
      : regime === "short"
        ? "Short-gamma regime: respect stops — dealer hedging overshoots; reversals are violent at the flip."
        : "Not enough greeks to read dealer positioning.",
    atLevel
      ? `Price is AT the ${nearestLevel?.name} (${nearestLevel ? f2(nearestLevel.price) : ""}) — the highest-conviction spot to act on dealer hedging.`
      : `Price is ${nearestLevel ? Math.abs(nearestLevel.distPct).toFixed(2) + "% from the " + nearestLevel.name : "between levels"} — wait for it to reach a level before pressing.`,
    "Dealer-gamma mechanics with a long-call/short-put convention — educational, not financial advice.",
  ];

  return { regime, netGex: ngex, flip, magnet, callWall: cw, putWall: pw, nearestLevel, atLevel, pressure, pressureScore, components, trade, notes };
}
