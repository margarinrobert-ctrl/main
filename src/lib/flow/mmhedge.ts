import type { HistoryBar, OptionContract } from "../barchart/types";
import {
  atmIv,
  callOiWall,
  callResistance,
  deltaCallWall,
  deltaFlip,
  deltaPutWall,
  dexByStrike,
  expectedMove1D,
  exposureProfile,
  flipFromProfile,
  gammaFlipNearest,
  gexByStrike,
  maxPain,
  netDex,
  netGex,
  oiByStrike,
  putCallRatio,
  putOiWall,
  putSupport,
  realizedVol,
  secondOrderExposure,
  type StrikeGex,
  type StrikeOi,
} from "./analytics";
import { probTouch } from "./greeks";
import { optionsFlow } from "./optionsflow";

// Market-maker hedging algo (quant model).
//
// Dealers who warehouse options must hedge in the underlying; that flow is mechanical:
//   • LONG gamma (net GEX > 0): hedging is COUNTER-trend (buy dips / sell rips) → price is pulled to
//     the gamma centre-of-mass (the "magnet") and pinned. Restoring force ∝ net $gamma.
//   • SHORT gamma (net GEX < 0): hedging is WITH-trend (sell dips / buy rips) → moves amplify away
//     from the zero-gamma flip; breaks cascade/squeeze.
// On top of the positional gamma pull, two dealer FLOWS create a directional drift, measured in
// $-notional-delta per day:
//   • Charm  = dealers re-hedge delta decay  → charm$/day.
//   • Vanna  = dealers re-hedge as IV moves  → vanna$/vol-pt × expected ΔIV (from VRP mean-reversion).
// These are normalised by the book's gross delta notional, blended with order flow into a continuous
// −100..+100 pressure, then turned into a full plan (entry zone, layered TPs with BS probability-of-
// touch + a modelled EV in R, structural stop) and a conviction score. Standard dealer-gamma
// mechanics with a long-call/short-put convention — educational, not financial advice.

export type Pressure = "up" | "down" | "balanced";

export interface MMComponent {
  label: string;
  dir: Pressure;
  weight: number; // signed contribution to the −100..100 score (magnitude shown)
  detail: string;
}

export interface MMLevel {
  name: string;
  price: number;
}

export interface LevelPlay {
  name: string;
  price: number;
  distPct: number;
  action: string; // what dealers DO here
  outcome: string; // highest-probability reaction
  bias: Pressure; // direction of that reaction
  pReach: number | null; // BS probability price reaches this level by front expiry
  callOi: number; // open interest at the nearest strike
  putOi: number;
  oiShare: number; // (call+put OI) / total chain OI — how heavily positioned the level is
}

export interface MMTarget {
  price: number;
  label: string;
  r: number | null; // reward in R (multiples of risk)
  pTouch: number | null; // BS probability price touches this level by front expiry
}

export interface MMTrade {
  side: "long" | "short" | "wait";
  entries: { price: number; label: string }[];
  stop: number | null;
  stopLabel: string;
  pStop: number | null; // BS probability of touching the stop
  targets: MMTarget[];
  risk: number | null; // per unit (|entry − stop|)
  rr: number | null; // to TP1
  rrFinal: number | null; // to last TP
  ev: number | null; // modelled expected value in R (prob-weighted, minus stop risk)
  pWin: number | null; // BS probability TP1 is hit before the stop (driftless first-passage)
  anchorLevel: string | null; // the level the plan is anchored to
  rationale: string;
  management: string[];
}

export interface MMHedge {
  regime: "long" | "short" | "unknown";
  netGex: number | null;
  flowPer1pct: number | null; // $ delta dealers must hedge per 1% move (= net GEX at spot)
  flip: number | null;
  magnet: number | null; // largest single |GEX| strike
  com: number | null; // gamma centre-of-mass (the pin target)
  callWall: number | null;
  putWall: number | null;
  deltaCallWall: number | null; // heaviest call delta-exposure above spot (delta-weighted resistance)
  deltaPutWall: number | null; // heaviest put delta-exposure below spot (delta-weighted support)
  netDex: number | null; // aggregate notional delta of OI (calls +, puts −) — directional book weight
  flowNetPremium: number | null; // bullish − bearish $ premium (today's tape)
  flowDeltaImbalance: number | null; // call+put delta-weighted volume (signed)
  deltaFlip: number | null; // delta-neutral pivot strike
  charmFlow: number | null; // $/day
  vannaFlow: number | null; // $/day (vanna × expected ΔIV)
  frontIv: number | null; // front-expiry ATM IV (for level probabilities)
  frontT: number; // front horizon in years
  em: number; // 1-day expected move ($) used for plan buffers
  levels: MMLevel[];
  levelPlays: LevelPlay[];
  nearestLevel: { name: string; price: number; distPct: number } | null;
  atLevel: boolean;
  pressure: Pressure;
  pressureScore: number; // -100 (down) .. +100 (up)
  conviction: number; // 0..100
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

/** Gamma centre-of-mass: |GEX|-weighted mean strike — the price gamma hedging pulls toward. */
function centreOfMass(by: StrikeGex[]): number | null {
  let num = 0;
  let den = 0;
  for (const x of by) {
    const w = Math.abs(x.gex);
    num += x.strike * w;
    den += w;
  }
  return den > 0 ? num / den : null;
}

function greeksCoverage(chain: OptionContract[]): number {
  if (!chain.length) return 0;
  const ok = chain.filter((c) => c.gamma != null && c.delta != null && c.impliedVolatility != null && c.impliedVolatility > 0).length;
  return ok / chain.length;
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

/** What the dealer wants to do at each key level, and the highest-probability reaction there. */
function buildLevelPlays(
  spot: number,
  regime: "long" | "short" | "unknown",
  raw: MMLevel[],
  iv: number | null,
  tYears: number,
  oiRows: StrikeOi[],
  totalOi: number,
): LevelPlay[] {
  const oiAt = (price: number): { callOi: number; putOi: number; oiShare: number } => {
    if (!oiRows.length) return { callOi: 0, putOi: 0, oiShare: 0 };
    const o = oiRows.reduce((p, c) => (Math.abs(c.strike - price) < Math.abs(p.strike - price) ? c : p));
    return { callOi: o.callOi, putOi: o.putOi, oiShare: totalOi > 0 ? (o.callOi + o.putOi) / totalOi : 0 };
  };
  const seen: { price: number; name: string }[] = [];
  for (const l of raw) {
    if (l.price == null || !Number.isFinite(l.price)) continue;
    const hit = seen.find((s) => Math.abs(s.price - l.price) <= Math.max(0.01, spot * 0.0008));
    if (!hit) seen.push({ price: l.price, name: l.name });
    // a GEX-ladder node coinciding with a named level just tags that level's rank (no duplicate row)
    else if (/^GEX /.test(l.name) && !/GEX/.test(hit.name)) hit.name += ` · ${l.name}`;
  }
  const longG = regime === "long";
  return seen
    .map(({ name, price }) => {
      const n = name.toLowerCase();
      const above = price >= spot;
      let action = "";
      let outcome = "";
      let bias: Pressure = "balanced";
      if (n.includes("flip") || n.includes("hvl")) {
        action = "Pivot — dealers stabilise above, amplify below";
        outcome = above ? "Reclaim → calmer" : "Lose → trend";
        bias = "balanced";
      } else if (n.includes("magnet") || n.includes("centre") || n.includes("pain")) {
        action = longG ? "Magnet — hedging / expiry pull" : "Weak pull (short γ)";
        outcome = longG ? "Pin / gravitate" : "Drifts past";
        bias = dirOf(price - spot);
      } else if (above) {
        // resistance: a level above spot
        action = longG ? "SELL into it — defend resistance" : "BUY the break — chase";
        outcome = longG ? "Reject ↓" : "Squeeze ↑ through";
        bias = longG ? "down" : "up";
      } else {
        // support: a level below spot
        action = longG ? "BUY it — defend support" : "SELL the break — cascade";
        outcome = longG ? "Bounce ↑" : "Flush ↓ through";
        bias = longG ? "up" : "down";
      }
      return { name, price, distPct: ((price - spot) / spot) * 100, action, outcome, bias, pReach: iv != null ? probTouch(spot, price, iv, tYears) : null, ...oiAt(price) };
    })
    .sort((a, b) => Math.abs(a.price - spot) - Math.abs(b.price - spot))
    .slice(0, 24);
}

interface PressureBook {
  regime: MMHedge["regime"];
  com: number | null;
  flip: number | null;
  ngex: number | null;
  grossGex: number;
  dflip: number | null;
  ndex: number | null;
  grossDex: number;
  em: number;
  charmFlow: number;
  vannaFlow: number;
  deltaNotional: number;
  hasCharm: boolean;
  hasVanna: boolean;
  dVolPts: number;
  vrp: number | null;
  flowS: { netPremium: number; bullPremium: number; bearPremium: number; deltaImbalance: number };
  pcr: { vol: number | null; oi: number | null };
}

/**
 * Build the signed pressure components + score at a REFERENCE price. The book (greeks/walls/flows) is
 * fixed; only the gamma-pin and delta directions re-evaluate vs `ref`, so the same book yields the
 * breakdown at spot or at any selected level. Convention: positive contribution = bullish.
 */
function buildPressure(ref: number, b: PressureBook): { components: MMComponent[]; pressureScore: number; pressure: Pressure } {
  const components: MMComponent[] = [];
  let gammaComp = 0;
  if (b.regime === "long" && b.com != null) {
    const pinStrength = clamp(Math.abs(b.ngex ?? 0) / b.grossGex / 0.25, 0, 1);
    gammaComp = Math.sign(b.com - ref) * pinStrength * 40;
    components.push({ label: "Gamma pin", dir: dirOf(gammaComp), weight: Math.round(Math.abs(gammaComp)), detail: `Long γ pulls to centre-of-mass ${f2(b.com)} (pin strength ${Math.round(pinStrength * 100)}%).` });
  } else if (b.regime === "short") {
    const r = b.flip ?? b.com;
    if (r != null) {
      const force = clamp(Math.abs(b.ngex ?? 0) / b.grossGex / 0.25, 0, 1);
      gammaComp = Math.sign(ref - r) * force * 40;
      components.push({ label: "Gamma (short)", dir: dirOf(gammaComp), weight: Math.round(Math.abs(gammaComp)), detail: `Short γ amplifies away from ${b.flip != null ? "the flip" : "COM"} ${f2(r)} (force ${Math.round(force * 100)}%).` });
    }
  }
  // Delta / DEX (16): direction = ref vs delta-flip pivot; magnitude = net-DEX concentration.
  let deltaComp = 0;
  const dexConc = b.grossDex > 0 && b.ndex != null ? clamp(b.ndex / b.grossDex / 0.4, -1, 1) : 0;
  if (b.dflip != null && b.grossDex > 0 && b.ndex != null && b.em > 0) {
    const prox = clamp(Math.abs(ref - b.dflip) / b.em, 0, 1);
    const sgn = Math.sign(ref - b.dflip);
    deltaComp = sgn * prox * Math.abs(dexConc) * 16;
    components.push({ label: "Delta (DEX)", dir: dirOf(deltaComp), weight: Math.round(Math.abs(deltaComp)), detail: `Price ${sgn >= 0 ? "above" : "below"} delta-flip ${f2(b.dflip)}; net OI delta ${fmtMoney(b.ndex)} (${Math.round(Math.abs(dexConc) * 100)}% concentration).` });
  } else if (b.grossDex > 0 && b.ndex != null) {
    deltaComp = dexConc * 8;
    components.push({ label: "Delta (DEX)", dir: dirOf(deltaComp), weight: Math.round(Math.abs(deltaComp)), detail: `Net OI delta ${fmtMoney(b.ndex)} (${Math.round(Math.abs(dexConc) * 100)}% call-delta dominant); no delta-flip in range.` });
  }
  const charmComp = clamp(b.charmFlow / (0.02 * b.deltaNotional), -1, 1) * 12;
  if (b.hasCharm) components.push({ label: "Charm flow", dir: dirOf(charmComp), weight: Math.round(Math.abs(charmComp)), detail: `Decay hedging ≈ ${fmtMoney(b.charmFlow)}/day (${charmComp >= 0 ? "buy/up" : "sell/down"}).` });
  const vannaComp = clamp(b.vannaFlow / (0.02 * b.deltaNotional), -1, 1) * 8;
  if (b.hasVanna) components.push({ label: "Vanna flow", dir: dirOf(vannaComp), weight: Math.round(Math.abs(vannaComp)), detail: `IV ${b.dVolPts <= 0 ? "fall" : "rise"} (VRP ${b.vrp != null ? b.vrp.toFixed(2) + "×" : "n/a"}) → ${fmtMoney(b.vannaFlow)}/day.` });
  // Options flow (16): aggressive traded premium.
  let flowComp = 0;
  const flowSpan = b.flowS.bullPremium - b.flowS.bearPremium;
  if (flowSpan > 0) {
    const flowRatio = clamp(b.flowS.netPremium / flowSpan, -1, 1);
    flowComp = (Number.isFinite(flowRatio) ? flowRatio : 0) * 16;
    components.push({ label: "Options flow", dir: dirOf(flowComp), weight: Math.round(Math.abs(flowComp)), detail: `Net ${flowComp >= 0 ? "bullish" : "bearish"} premium ${fmtMoney(b.flowS.netPremium)} of ${fmtMoney(flowSpan)} traded (Δ-imbalance ${fmtMoney(b.flowS.deltaImbalance)}).` });
  }
  // Open interest (8): standing put/call OI lean (call-heavy = bullish).
  let oiComp = 0;
  if (b.pcr.oi != null && b.pcr.oi > 0) {
    const skew = clamp(-Math.log(b.pcr.oi) / Math.log(2), -1, 1);
    oiComp = skew * 8;
    components.push({ label: "Open interest", dir: dirOf(oiComp), weight: Math.round(Math.abs(oiComp)), detail: `P/C OI ${b.pcr.oi.toFixed(2)} — ${b.pcr.oi < 1 ? "call-heavy" : b.pcr.oi > 1 ? "put-heavy" : "balanced"} standing book.` });
  }
  const pressureScore = Math.round(clamp(gammaComp + deltaComp + flowComp + charmComp + vannaComp + oiComp, -100, 100));
  const pressure: Pressure = pressureScore > 15 ? "up" : pressureScore < -15 ? "down" : "balanced";
  return { components, pressureScore, pressure };
}

/**
 * Recompute the dealer-pressure breakdown AT an arbitrary reference price (e.g. a selected level).
 * The book (greeks/walls/flows) is read from the live chain at spot; only the gamma-pin and delta
 * directions are re-evaluated as if price were at `ref`. Returns null without a chain/spot.
 */
export function pressureAt(chain: OptionContract[], spot: number | null, ref: number, bars: HistoryBar[] = []): { components: MMComponent[]; pressureScore: number; pressure: Pressure } | null {
  if (!spot || !chain.length) return null;
  const by = gexByStrike(chain, spot);
  if (!by.length) return null;
  const ngex = netGex(chain, spot);
  const grossGex = by.reduce((s, x) => s + Math.abs(x.gex), 0) || 1;
  const com = centreOfMass(by);
  const flip = flipFromProfile(exposureProfile(chain, spot, 41)) ?? gammaFlipNearest(by, spot);
  const regime: MMHedge["regime"] = ngex == null ? "unknown" : ngex >= 0 ? "long" : "short";
  const dby = dexByStrike(chain, spot);
  const so = secondOrderExposure(chain, spot);
  const exps = [...new Set(chain.map((c) => c.expiration))].sort();
  const frontExp = exps.find((e) => (chain.find((c) => c.expiration === e)?.dte ?? -1) >= 0) ?? exps[0];
  const iv0 = frontExp ? atmIv(chain, spot, frontExp) : null;
  const em = expectedMove1D(spot, iv0)?.abs ?? spot * 0.005;
  const rv = realizedVol(bars, 20) ?? realizedVol(bars, 10);
  const vrp = iv0 != null && rv ? iv0 / rv : null;
  const dVolPts = vrp == null ? 0 : clamp(-(vrp - 1) * 0.5, -2, 2);
  const deltaNotional = chain.reduce((s, c) => s + (c.delta != null && c.openInterest != null ? Math.abs(c.delta) * c.openInterest : 0), 0) * 100 * spot || 1;
  return buildPressure(ref, {
    regime,
    com,
    flip,
    ngex,
    grossGex,
    dflip: deltaFlip(dby, spot),
    ndex: netDex(chain, spot),
    grossDex: dby.reduce((s, x) => s + Math.abs(x.dex), 0),
    em,
    charmFlow: so.charm ?? 0,
    vannaFlow: (so.vanna ?? 0) * dVolPts,
    deltaNotional,
    hasCharm: so.charm != null,
    hasVanna: so.vanna != null,
    dVolPts,
    vrp,
    flowS: optionsFlow(chain, spot).sentiment,
    pcr: putCallRatio(chain),
  });
}

/** Build the entry/TP/stop plan + BS probabilities + modelled EV(R) in the pressure direction. */
function planTrade(
  side: "long" | "short",
  spot: number,
  anchor: { name: string; price: number } | null,
  atLevel: boolean,
  lad: MMLevel[],
  em: number,
  regime: "long" | "short" | "unknown",
  magnet: number | null,
  iv: number | null,
  tYears: number,
  edge: number, // directional conviction 0..1 (|pressureScore|/100) — drift for P(win)/EV
): MMTrade {
  const entry = atLevel && anchor ? anchor.price : spot;
  const buf = Math.max(em * 0.12, entry * 0.0006);
  const long = side === "long";

  const ahead = lad.filter((l) => (long ? l.price > entry + buf : l.price < entry - buf)).sort((a, b) => (long ? a.price - b.price : b.price - a.price));
  const behind = lad.filter((l) => (long ? l.price < entry - buf : l.price > entry + buf)).sort((a, b) => (long ? b.price - a.price : a.price - b.price));

  // Targets first (structural levels ahead, else expected-move multiples) so risk can be sized off them.
  const picks = ahead.slice(0, 3);
  while (picks.length < 2) {
    const mult = picks.length + 1;
    picks.push({ name: `${mult}× EM`, price: long ? entry + em * mult : entry - em * mult });
  }
  const tp1Dist = Math.abs(picks[0].price - entry) || em;

  // Structural invalidation (next level behind, else 0.6× EM), but CAP risk at the first target's
  // distance so the plan is never worse than 1:1 — a far structural stop against a near target is bad
  // risk management. Keep the structural stop only when it's already tighter than 1R.
  const guard = behind[0] ?? null;
  const structuralStop = guard ? (long ? guard.price - buf : guard.price + buf) : long ? entry - em * 0.6 : entry + em * 0.6;
  const structuralRisk = Math.abs(entry - structuralStop);
  let risk = Math.min(structuralRisk, tp1Dist);
  if (!(risk > 0)) risk = Math.min(tp1Dist, em * 0.5);
  const stop = long ? entry - risk : entry + risk;
  const tightened = structuralRisk > tp1Dist + 1e-9;
  const stopLabel = tightened
    ? `${f2(stop)} · risk capped to 1R (${guard ? guard.name : "0.6× EM"} sat wider)`
    : guard
      ? `beyond ${guard.name} ${f2(guard.price)}`
      : `${f2(stop)} (≈0.6× expected move)`;

  const targets: MMTarget[] = picks.map((l, i) => ({
    price: l.price,
    label: `TP${i + 1} · ${l.name}`,
    r: risk > 0 ? r1(Math.abs(l.price - entry) / risk) : null,
    pTouch: iv != null ? probTouch(spot, l.price, iv, tYears) : null,
  }));

  const pStop = iv != null ? probTouch(spot, stop, iv, tYears) : null;

  // P(win) carries the model's DIRECTIONAL edge (dealer-pressure conviction, 0..1) as a drift on the
  // base coin-flip — a driftless 1:1 trade is 0-EV by construction, so EV only turns positive when the
  // model actually reads a direction. EV(R) = scale-out reward (R, weighted) × P(win) − 1R × P(loss).
  const pWin = Math.round(Math.min(0.92, Math.max(0.5, 0.5 + 0.42 * Math.max(0, Math.min(1, edge)))) * 100) / 100;
  const w = [0.5, 0.3, 0.2];
  const rewardR = targets.reduce((s, t, i) => s + (w[i] ?? 0) * (t.r ?? 0), 0);
  const ev = targets.some((t) => t.r != null) ? Math.round((pWin * rewardR - (1 - pWin)) * 100) / 100 : null;

  const entries = [
    { price: entry, label: atLevel && anchor ? `at ${anchor.name}` : "on reach" },
    { price: long ? entry - buf : entry + buf, label: "scale-in" },
  ];

  const rationale = long
    ? regime === "long"
      ? `Long-gamma PIN: dealers buy dips, so press LONG from the ${anchor?.name ?? "level"} (${f2(entry)}) toward the ${magnet != null ? f2(magnet) + " magnet" : "magnet"}. Restoring force — don't chase past it.`
      : `Short-gamma SQUEEZE: a hold above ${anchor?.name ?? "the level"} (${f2(entry)}) forces dealer call-hedging to chase. Long the continuation.`
    : regime === "long"
      ? `Long-gamma FADE: dealers sell rips, so press SHORT from the ${anchor?.name ?? "level"} (${f2(entry)}) back toward the ${magnet != null ? f2(magnet) + " magnet" : "magnet"}.`
      : `Short-gamma FLUSH: a break of ${anchor?.name ?? "the level"} (${f2(entry)}) removes dealer support and cascades. Short the continuation.`;

  const management =
    regime === "long"
      ? ["Scale across the entry zone; don't add beyond it.", "Bank ~half at TP1, trail toward the magnet — the pin caps the move.", "Stop → breakeven after TP1."]
      : ["Enter on the break; add on a failed retest.", "Trail wide — short-gamma overshoots; let TP2/TP3 run.", "Hard stop: regime flips at the γ-flip."];

  return {
    side,
    entries,
    stop,
    stopLabel,
    pStop,
    targets,
    risk: risk || null,
    rr: targets[0]?.r ?? null,
    rrFinal: targets[targets.length - 1]?.r ?? null,
    ev,
    pWin,
    anchorLevel: anchor?.name ?? null,
    rationale,
    management,
  };
}

/** Run the dealer-hedging quant model for a chain at a given spot. `bars` powers the VRP→vanna drift. */
export function mmHedge(chain: OptionContract[], spot: number | null, bars: HistoryBar[] = []): MMHedge {
  const base: MMHedge = {
    regime: "unknown",
    netGex: null,
    flowPer1pct: null,
    flip: null,
    magnet: null,
    com: null,
    callWall: null,
    putWall: null,
    deltaCallWall: null,
    deltaPutWall: null,
    netDex: null,
    flowNetPremium: null,
    flowDeltaImbalance: null,
    deltaFlip: null,
    charmFlow: null,
    vannaFlow: null,
    frontIv: null,
    frontT: 0,
    em: 0,
    levels: [],
    levelPlays: [],
    nearestLevel: null,
    atLevel: false,
    pressure: "balanced",
    pressureScore: 0,
    conviction: 0,
    components: [],
    trade: null,
    notes: [],
  };
  if (!spot || !chain.length) return base;

  const by = gexByStrike(chain, spot);
  if (!by.length) return base;
  const ngex = netGex(chain, spot);
  const grossGex = by.reduce((s, x) => s + Math.abs(x.gex), 0) || 1;
  const com = centreOfMass(by);
  const magnet = magnetStrike(by);
  const cw = callResistance(by, spot);
  const pw = putSupport(by, spot);
  const dby = dexByStrike(chain, spot);
  const dcw = deltaCallWall(dby, spot);
  const dpw = deltaPutWall(dby, spot);
  const ndex = netDex(chain, spot);
  const so = secondOrderExposure(chain, spot);

  // smoother zero-gamma flip from the BS-repriced profile, fallback to the discrete crossing
  const profile = exposureProfile(chain, spot, 41);
  const flip = flipFromProfile(profile) ?? gammaFlipNearest(by, spot);

  // front expiration
  const exps = [...new Set(chain.map((c) => c.expiration))].sort();
  const frontExp = exps.find((e) => (chain.find((c) => c.expiration === e)?.dte ?? -1) >= 0) ?? exps[0];
  const sub = frontExp ? chain.filter((c) => c.expiration === frontExp) : chain;
  const by0 = gexByStrike(sub, spot);
  const cw0 = callResistance(by0, spot);
  const pw0 = putSupport(by0, spot);
  const flip0 = gammaFlipNearest(by0, spot);
  const iv0 = frontExp ? atmIv(chain, spot, frontExp) : null;
  const frontDte = sub.find((c) => c.dte != null)?.dte ?? null;
  const tYears = Math.max(frontDte ?? 1, 0.5) / 365;
  const em = expectedMove1D(spot, iv0)?.abs ?? spot * 0.005;
  const regime: MMHedge["regime"] = ngex == null ? "unknown" : ngex >= 0 ? "long" : "short";

  // dealer DRIFT flows ($/day)
  const rv = realizedVol(bars, 20) ?? realizedVol(bars, 10);
  const vrp = iv0 != null && rv ? iv0 / rv : null;
  // expected ΔIV per day in vol points: rich IV (vrp>1) mean-reverts DOWN.
  const dVolPts = vrp == null ? 0 : clamp(-(vrp - 1) * 0.5, -2, 2);
  const charmFlow = so.charm ?? 0; // $/day
  const vannaFlow = (so.vanna ?? 0) * dVolPts; // $/vol-pt × vol-pts/day = $/day
  const deltaNotional =
    chain.reduce((s, c) => s + (c.delta != null && c.openInterest != null ? Math.abs(c.delta) * c.openInterest : 0), 0) * 100 * spot || 1;

  // ── pressure components (magnitude-aware) ── built at a REFERENCE price so the breakdown can be
  // recomputed at any selected level (gamma/delta direction re-evaluate vs that price).
  const dflip = deltaFlip(dby, spot); // delta-neutral pivot; null if <2 DEX strikes / no crossing
  const grossDex = dby.reduce((s, x) => s + Math.abs(x.dex), 0); // ≥ 0
  const flowS = optionsFlow(chain, spot).sentiment; // never throws; zero gauges on empty/no-volume
  const pcr = putCallRatio(chain); // { vol, oi }; fields may be null
  const book: PressureBook = {
    regime, com, flip, ngex, grossGex, dflip, ndex, grossDex, em,
    charmFlow, vannaFlow, deltaNotional, hasCharm: so.charm != null, hasVanna: so.vanna != null,
    dVolPts, vrp, flowS, pcr,
  };
  const { components, pressureScore, pressure } = buildPressure(spot, book);

  // nearest level + ladder
  const cands = [
    { name: "γ-flip", price: flip },
    { name: "Call wall", price: cw },
    { name: "Put wall", price: pw },
    { name: "Gamma magnet", price: magnet },
  ].filter((c): c is { name: string; price: number } => c.price != null);
  const nearest = cands.length ? cands.reduce((p, c) => (Math.abs(c.price - spot) < Math.abs(p.price - spot) ? c : p)) : null;
  const nearestLevel = nearest ? { ...nearest, distPct: ((nearest.price - spot) / spot) * 100 } : null;
  const atLevel = nearest != null && Math.abs(nearest.price - spot) <= em * 0.6;
  const lad = ladder(
    [
      { name: "Call wall", price: cw as number },
      { name: "Call Res 0DTE", price: cw0 as number },
      { name: "Put wall", price: pw as number },
      { name: "Put Sup 0DTE", price: pw0 as number },
      { name: "γ-flip", price: flip as number },
      { name: "HVL 0DTE", price: flip0 as number },
      { name: "Gamma magnet", price: magnet as number },
      { name: "Centre of mass", price: com as number },
      { name: "Exp Hi", price: spot + em },
      { name: "Exp Lo", price: spot - em },
    ].filter((l) => l.price != null),
    Math.max(em * 0.18, spot * 0.0008),
  );

  // full level set: structural walls, flip/magnet, max pain, OI walls, the 1-day expected range,
  // and the GEX 1..10 ladder (top strikes by |net GEX|).
  const mp = frontExp ? maxPain(chain, frontExp) : null;
  const oi = oiByStrike(chain);
  const totalOi = oi.reduce((s, x) => s + x.callOi + x.putOi, 0);
  const coi = callOiWall(oi);
  const poi = putOiWall(oi);
  const em1d = expectedMove1D(spot, iv0)?.abs ?? null;
  const gexLadder = by
    .filter((x) => x.gex !== 0)
    .sort((a, b) => Math.abs(b.gex) - Math.abs(a.gex))
    .slice(0, 10);
  const levelPlays = buildLevelPlays(
    spot,
    regime,
    [
      { name: "γ-flip", price: flip as number },
      { name: "Gamma magnet", price: magnet as number },
      { name: "Call wall", price: cw as number },
      { name: "Put wall", price: pw as number },
      { name: "Call Res 0DTE", price: cw0 as number },
      { name: "Put Sup 0DTE", price: pw0 as number },
      { name: "Max Pain", price: mp as number },
      { name: "Call OI", price: coi as number },
      { name: "Put OI", price: poi as number },
      { name: "Delta Call Wall", price: dcw as number },
      { name: "Delta Put Wall", price: dpw as number },
      { name: "1D Max", price: em1d != null ? spot + em1d : (null as unknown as number) },
      { name: "1D Min", price: em1d != null ? spot - em1d : (null as unknown as number) },
      ...gexLadder.map((x, i) => ({ name: `GEX ${i + 1}`, price: x.strike })),
    ].filter((l) => l.price != null),
    iv0,
    tYears,
    oi,
    totalOi,
  );

  let trade: MMTrade | null;
  const edge = Math.abs(pressureScore) / 100;
  if (pressureScore > 15) trade = planTrade("long", spot, nearest, atLevel, lad, em, regime, magnet, iv0, tYears, edge);
  else if (pressureScore < -15) trade = planTrade("short", spot, nearest, atLevel, lad, em, regime, magnet, iv0, tYears, edge);
  else
    trade = {
      side: "wait",
      entries: [],
      stop: null,
      stopLabel: "",
      pStop: null,
      targets: [],
      risk: null,
      rr: null,
      rrFinal: null,
      ev: null,
      pWin: null,
      anchorLevel: null,
      rationale: `Dealer pressure is balanced near the ${nearestLevel?.name ?? "level"} (${nearestLevel ? f2(nearestLevel.price) : "—"}). Wait for a commit through ${flip != null ? f2(flip) : "the flip"} or a tag of a wall.`,
      management: ["No edge yet — let price reach a level and the pressure pick a side."],
    };

  // conviction: pressure strength + at-level confluence + modelled EV + greeks coverage + how
  // heavily the in-play level is positioned (more OI = more dealers to hedge = more reliable).
  const cov = greeksCoverage(chain);
  const evPart = trade.ev != null ? clamp(trade.ev, 0, 1) : 0;
  const nearOi = levelPlays[0]?.oiShare ?? 0;
  const conviction = Math.round(
    clamp(0.35 * (Math.abs(pressureScore) / 100) + 0.2 * (atLevel ? 1 : 0.35) + 0.15 * evPart + 0.1 * cov + 0.2 * clamp(nearOi / 0.15, 0, 1), 0, 1) * 100,
  );

  const notes = [
    regime === "long"
      ? "Long-gamma regime: fade extremes into the magnet; breakouts usually fail (dealers lean against them)."
      : regime === "short"
        ? "Short-gamma regime: respect stops — dealer hedging overshoots; reversals are violent at the flip."
        : "Not enough greeks to read dealer positioning.",
    `For a 1% move dealers hedge ≈ ${fmtMoney(Math.abs(ngex ?? 0))} of delta (${regime === "long" ? "stabilising" : "destabilising"}).`,
    atLevel ? `Price is AT the ${nearestLevel?.name} — the highest-conviction spot to act.` : `Price is ${nearestLevel ? Math.abs(nearestLevel.distPct).toFixed(2) + "% from the " + nearestLevel.name : "between levels"} — the plan triggers on reach.`,
    "EV/probabilities are Black-Scholes, driftless, front-expiry. Size so 1R is your max risk. Educational — not advice.",
  ];

  return {
    regime,
    netGex: ngex,
    flowPer1pct: ngex,
    flip,
    magnet,
    com,
    callWall: cw,
    putWall: pw,
    deltaCallWall: dcw,
    deltaPutWall: dpw,
    netDex: ndex,
    flowNetPremium: flowS.netPremium,
    flowDeltaImbalance: flowS.deltaImbalance,
    deltaFlip: dflip,
    charmFlow,
    vannaFlow,
    frontIv: iv0,
    frontT: tYears,
    em,
    levels: lad,
    levelPlays,
    nearestLevel,
    atLevel,
    pressure,
    pressureScore,
    conviction,
    components,
    trade,
    notes,
  };
}

/**
 * Re-anchor the trade plan to a user-selected level. Side follows that level's expected dealer
 * reaction (resistance → short, support → long; pivot/pin → fall back to net pressure).
 */
export function planAtLevel(r: MMHedge, spot: number | null, lp: LevelPlay): MMTrade | null {
  if (spot == null || r.regime === "unknown") return null;
  const side: "long" | "short" = lp.bias === "up" ? "long" : lp.bias === "down" ? "short" : r.pressureScore >= 0 ? "long" : "short";
  return planTrade(side, spot, { name: lp.name, price: lp.price }, true, r.levels, r.em || spot * 0.01, r.regime, r.magnet, r.frontIv, r.frontT, Math.abs(r.pressureScore) / 100);
}

function fmtMoney(v: number): string {
  const a = Math.abs(v);
  const s = v < 0 ? "-" : "";
  if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(0)}K`;
  return `${s}$${Math.round(a)}`;
}
