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
// that hedging is mechanical around big-gamma strikes:
//   • LONG gamma (net GEX > 0): dealers BUY dips / SELL rips → price is PINNED toward the dominant
//     gamma strike (the "magnet"). Trade toward the magnet; breakouts fail.
//   • SHORT gamma (net GEX < 0): dealers SELL dips / BUY rips → moves AMPLIFY away from the γ-flip.
//     Trade the continuation; breaks cascade/squeeze.
// Charm (decay) and vanna (vol-change) hedging add a secondary drift. The algo nets these into a
// "main pressure" direction and a full trade plan — entry zone, layered TPs at the next levels (with
// R multiples) and a structural stop. Dealer-gamma mechanics — educational, not financial advice.

export type Pressure = "up" | "down" | "balanced";

export interface MMComponent {
  label: string;
  dir: Pressure;
  weight: number;
  detail: string;
}

export interface MMLevel {
  name: string;
  price: number;
}

export interface MMTarget {
  price: number;
  label: string;
  r: number | null; // reward in R (multiples of risk)
}

export interface MMTrade {
  side: "long" | "short" | "wait";
  entries: { price: number; label: string }[];
  stop: number | null;
  stopLabel: string;
  targets: MMTarget[];
  risk: number | null; // per unit (|entry − stop|)
  rr: number | null; // to TP1
  rrFinal: number | null; // to last TP
  rationale: string;
  management: string[];
}

export interface MMHedge {
  regime: "long" | "short" | "unknown";
  netGex: number | null;
  flip: number | null;
  magnet: number | null;
  callWall: number | null;
  putWall: number | null;
  levels: MMLevel[];
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
const r1 = (n: number) => Math.round(n * 10) / 10;

function magnetStrike(by: StrikeGex[]): number | null {
  if (!by.length) return null;
  return by.reduce((m, x) => (Math.abs(x.gex) > Math.abs(m.gex) ? x : m)).strike;
}

/** Order-prioritised, near-duplicate-collapsed, price-sorted level ladder. */
function ladder(raw: MMLevel[], tol: number): MMLevel[] {
  const out: MMLevel[] = [];
  for (const l of raw) {
    if (!Number.isFinite(l.price)) continue;
    const hit = out.find((o) => Math.abs(o.price - l.price) <= tol);
    if (hit) hit.name = hit.name.includes(l.name) ? hit.name : `${hit.name} / ${l.name}`;
    else out.push({ ...l });
  }
  return out.sort((a, b) => a.price - b.price);
}

/** Build the full entry/TP/stop plan in the direction of dealer pressure. */
function planTrade(
  side: "long" | "short",
  spot: number,
  anchor: { name: string; price: number } | null,
  atLevel: boolean,
  lad: MMLevel[],
  em: number,
  regime: "long" | "short" | "unknown",
  magnet: number | null,
): MMTrade {
  const entry = atLevel && anchor ? anchor.price : spot;
  const buf = Math.max(em * 0.12, entry * 0.0006);
  const long = side === "long";

  // targets = levels in the trade direction; stop = first level against it (+buffer).
  const ahead = lad.filter((l) => (long ? l.price > entry + buf : l.price < entry - buf)).sort((a, b) => (long ? a.price - b.price : b.price - a.price));
  const behind = lad.filter((l) => (long ? l.price < entry - buf : l.price > entry + buf)).sort((a, b) => (long ? b.price - a.price : a.price - b.price));

  const guard = behind[0] ?? null;
  const stop = guard ? (long ? guard.price - buf : guard.price + buf) : long ? entry - em * 0.6 : entry + em * 0.6;
  const stopLabel = guard ? `beyond ${guard.name} ${f2(guard.price)}` : `${f2(stop)} (≈0.6× expected move)`;
  const risk = Math.abs(entry - stop);

  // up to 3 TPs from the level ladder; fall back to EM extensions if the ladder runs out.
  const picks = ahead.slice(0, 3);
  while (picks.length < 2) {
    const mult = picks.length + 1;
    picks.push({ name: `${mult}× EM`, price: long ? entry + em * mult : entry - em * mult });
  }
  const targets: MMTarget[] = picks.map((l, i) => ({
    price: l.price,
    label: `TP${i + 1} · ${l.name}`,
    r: risk > 0 ? r1(Math.abs(l.price - entry) / risk) : null,
  }));

  const entries = [
    { price: entry, label: atLevel && anchor ? `at ${anchor.name}` : "on reach" },
    { price: long ? entry - buf : entry + buf, label: "scale-in" },
  ];

  const rationale = long
    ? regime === "long"
      ? `Long-gamma PIN: dealers buy dips, so press LONG from the ${anchor?.name ?? "level"} (${f2(entry)}) toward the ${magnet != null ? f2(magnet) + " magnet" : "magnet"}. Fade — don't chase.`
      : `Short-gamma SQUEEZE: a hold above ${anchor?.name ?? "the level"} (${f2(entry)}) forces dealer call-hedging to chase. Long the continuation.`
    : regime === "long"
      ? `Long-gamma FADE: dealers sell rips, so press SHORT from the ${anchor?.name ?? "level"} (${f2(entry)}) back toward the ${magnet != null ? f2(magnet) + " magnet" : "magnet"}.`
      : `Short-gamma FLUSH: a break of ${anchor?.name ?? "the level"} (${f2(entry)}) removes dealer support and cascades. Short the continuation.`;

  const management =
    regime === "long"
      ? [
          "Scale across the entry zone; don't add beyond it.",
          "Bank ~half at TP1, trail the rest toward the magnet — exits at the pin (mean-reversion caps the move).",
          "Move stop to breakeven after TP1.",
        ]
      : [
          "Enter on the break; add on a failed retest of the level.",
          "Trail wide — short-gamma overshoots; let TP2/TP3 run.",
          "Hard stop: the regime flips at the γ-flip, so don't give it back past your stop.",
        ];

  return {
    side,
    entries,
    stop,
    stopLabel,
    targets,
    risk: risk || null,
    rr: targets[0]?.r ?? null,
    rrFinal: targets[targets.length - 1]?.r ?? null,
    rationale,
    management,
  };
}

/** Run the dealer-hedging algo for a chain at a given spot. */
export function mmHedge(chain: OptionContract[], spot: number | null, _bars: HistoryBar[] = []): MMHedge {
  const base: MMHedge = {
    regime: "unknown",
    netGex: null,
    flip: null,
    magnet: null,
    callWall: null,
    putWall: null,
    levels: [],
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

  // front-expiration (0DTE) sub-levels
  const exps = [...new Set(chain.map((c) => c.expiration))].sort();
  const frontExp = exps.find((e) => (chain.find((c) => c.expiration === e)?.dte ?? -1) >= 0) ?? exps[0];
  const sub = frontExp ? chain.filter((c) => c.expiration === frontExp) : chain;
  const by0 = gexByStrike(sub, spot);
  const cw0 = callResistance(by0, spot);
  const pw0 = putSupport(by0, spot);
  const flip0 = gammaFlipNearest(by0, spot);
  const iv0 = frontExp ? atmIv(chain, spot, frontExp) : null;
  const em = expectedMove1D(spot, iv0)?.abs ?? spot * 0.005;
  const regime: MMHedge["regime"] = ngex == null ? "unknown" : ngex >= 0 ? "long" : "short";

  const lad = ladder(
    [
      { name: "Call wall", price: cw as number },
      { name: "Call Res 0DTE", price: cw0 as number },
      { name: "Put wall", price: pw as number },
      { name: "Put Sup 0DTE", price: pw0 as number },
      { name: "γ-flip", price: flip as number },
      { name: "HVL 0DTE", price: flip0 as number },
      { name: "Gamma magnet", price: magnet as number },
      { name: "Exp Hi", price: spot + em },
      { name: "Exp Lo", price: spot - em },
    ].filter((l) => l.price != null),
    Math.max(em * 0.18, spot * 0.0008),
  );

  const cands = [
    { name: "γ-flip", price: flip },
    { name: "Call wall", price: cw },
    { name: "Put wall", price: pw },
    { name: "Gamma magnet", price: magnet },
  ].filter((c): c is { name: string; price: number } => c.price != null);
  const nearest = cands.length ? cands.reduce((p, c) => (Math.abs(c.price - spot) < Math.abs(p.price - spot) ? c : p)) : null;
  const nearestLevel = nearest ? { ...nearest, distPct: ((nearest.price - spot) / spot) * 100 } : null;
  const atLevel = nearest != null && Math.abs(nearest.price - spot) <= em * 0.6;

  // ── pressure components ──
  const components: MMComponent[] = [];
  let gammaDir = 0;
  if (regime === "long" && magnet != null) {
    gammaDir = Math.sign(magnet - spot);
    components.push({ label: "Gamma pin", dir: dirOf(gammaDir), weight: 50, detail: `Long gamma → dealers pin toward the ${f2(magnet)} magnet (buy dips / sell rips).` });
  } else if (regime === "short" && flip != null) {
    gammaDir = Math.sign(spot - flip);
    components.push({ label: "Gamma (short)", dir: dirOf(gammaDir), weight: 50, detail: `Short gamma → dealers chase away from the ${f2(flip)} flip (sell dips / buy rips).` });
  }
  const charmDir = so.charm == null ? 0 : so.charm >= 0 ? -1 : 1;
  if (so.charm != null) components.push({ label: "Charm drift", dir: dirOf(charmDir), weight: 25, detail: `Time-decay hedging drifts ${charmDir >= 0 ? "UP" : "DOWN"} into expiry.` });
  const pcDir = pc.vol == null ? 0 : pc.vol < 0.8 ? 1 : pc.vol > 1.2 ? -1 : 0;
  if (pc.vol != null) components.push({ label: "Order flow", dir: dirOf(pcDir), weight: 15, detail: `Put/Call ${pc.vol.toFixed(2)} — ${pcDir > 0 ? "call-heavy" : pcDir < 0 ? "put-heavy" : "balanced"}.` });
  const vannaDir = so.vanna == null ? 0 : so.vanna >= 0 ? 1 : -1;
  if (so.vanna != null) components.push({ label: "Vanna", dir: dirOf(vannaDir), weight: 10, detail: `${vannaDir >= 0 ? "Positive" : "Negative"} vanna — calmer IV ${vannaDir >= 0 ? "supports" : "pressures"} price.` });
  void netDex(chain, spot);

  const pressureScore = Math.round(clamp(gammaDir * 50 + charmDir * 25 + pcDir * 15 + vannaDir * 10, -100, 100));
  const pressure = pressureScore > 15 ? "up" : pressureScore < -15 ? "down" : "balanced";

  let trade: MMTrade | null;
  if (pressureScore > 15) trade = planTrade("long", spot, nearest, atLevel, lad, em, regime, magnet);
  else if (pressureScore < -15) trade = planTrade("short", spot, nearest, atLevel, lad, em, regime, magnet);
  else
    trade = {
      side: "wait",
      entries: [],
      stop: null,
      stopLabel: "",
      targets: [],
      risk: null,
      rr: null,
      rrFinal: null,
      rationale: `Dealer pressure is balanced near the ${nearestLevel?.name ?? "level"} (${nearestLevel ? f2(nearestLevel.price) : "—"}). Wait for a commit through ${flip != null ? f2(flip) : "the flip"} or a tag of a wall.`,
      management: ["No edge yet — let price reach a level and the pressure pick a side."],
    };

  const notes = [
    regime === "long"
      ? "Long-gamma regime: fade extremes into the magnet; breakouts usually fail (dealers lean against them)."
      : regime === "short"
        ? "Short-gamma regime: respect stops — dealer hedging overshoots; reversals are violent at the flip."
        : "Not enough greeks to read dealer positioning.",
    atLevel
      ? `Price is AT the ${nearestLevel?.name} — the highest-conviction spot to act on dealer hedging.`
      : `Price is ${nearestLevel ? Math.abs(nearestLevel.distPct).toFixed(2) + "% from the " + nearestLevel.name : "between levels"} — the plan triggers when it reaches the entry.`,
    "R multiples assume the structural stop; size so 1R is your max risk. Educational — not financial advice.",
  ];

  return { regime, netGex: ngex, flip, magnet, callWall: cw, putWall: pw, levels: lad, nearestLevel, atLevel, pressure, pressureScore, components, trade, notes };
}
