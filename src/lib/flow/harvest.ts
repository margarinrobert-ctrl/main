import type { HistoryBar, OptionContract } from "../barchart/types";
import { atmIv, callWall, expectedMove, gexByStrike, putWall, realizedVol } from "./analytics";

// Option Premium Harvesting / Volatility Risk Premium (VRP) signal engine.
// The edge: implied vol is usually richer than what's realized, so systematically SELLING premium
// (delta-hedged-ish, defined-risk) harvests that spread. This turns the VRP read into concrete,
// sized structures whose short strikes are anchored to price levels (gamma walls / ±1σ, chosen by
// target delta) and whose timing is anchored to DTE/theta. Educational tooling — not advice.

const CONTRACT = 100;
const TRADING_DAYS = 252;
const DELTA_AGGR = 0.3; // ~30Δ short strike (more credit, lower POP)
const DELTA_SAFE = 0.16; // ~16Δ short strike (≈1σ, higher POP)

export type HarvestSide = "neutral" | "bullish" | "bearish";

export interface HarvestLeg {
  action: "sell" | "buy";
  type: "call" | "put";
  strike: number;
  delta: number | null;
  mid: number;
}

export interface HarvestSignal {
  name: string;
  side: HarvestSide;
  legs: HarvestLeg[];
  credit: number; // net per share
  maxProfit: number; // $ per 1 lot
  maxLoss: number | null; // $ per 1 lot (null = undefined/large risk)
  capital: number | null; // capital at risk / margin proxy ($)
  breakevens: number[];
  pop: number | null; // probability of profit estimate (0..1)
  thetaDay: number | null; // $ harvested per day per 1 lot
  rom: number | null; // return on capital for the trade
  romAnnual: number | null; // annualized
  expiration: string;
  dte: number | null;
  rationale: string;
  score: number; // 0..100 conviction
}

export interface HarvestReport {
  regime: "harvest" | "neutral" | "avoid";
  headline: string;
  expiration: string | null;
  dte: number | null;
  iv: number | null;
  rv: number | null;
  vrpRatio: number | null;
  termShape: "contango" | "backwardation" | "flat" | "n/a";
  skew: number | null;
  emExp: number | null; // ~1σ move to the chosen expiration
  callWall: number | null;
  putWall: number | null;
  signals: HarvestSignal[];
  notes: string[];
}

function midOf(c: OptionContract): number {
  if (c.bid != null && c.ask != null && c.ask > 0) return (c.bid + c.ask) / 2;
  return c.last ?? 0;
}

function nearestByDelta(opts: OptionContract[], type: "call" | "put", target: number): OptionContract | null {
  const pool = opts.filter((c) => c.type === type && c.delta != null && midOf(c) > 0);
  if (!pool.length) return null;
  return pool.reduce((p, c) => (Math.abs(Math.abs(c.delta as number) - target) < Math.abs(Math.abs(p.delta as number) - target) ? c : p));
}

function nearestByStrike(opts: OptionContract[], type: "call" | "put", strike: number): OptionContract | null {
  const pool = opts.filter((c) => c.type === type && midOf(c) >= 0);
  if (!pool.length) return null;
  return pool.reduce((p, c) => (Math.abs(c.strike - strike) < Math.abs(p.strike - strike) ? c : p));
}

function strikeStep(opts: OptionContract[]): number {
  const ks = [...new Set(opts.map((c) => c.strike))].sort((a, b) => a - b);
  if (ks.length < 2) return 1;
  const diffs = ks.slice(1).map((k, i) => k - ks[i]).filter((d) => d > 0).sort((a, b) => a - b);
  return diffs[Math.floor(diffs.length / 2)] || 1;
}

/** Pick the expiration best suited to harvesting: closest to ~30 DTE within a 14–50d window, else nearest future. */
export function chooseHarvestExpiration(chain: OptionContract[]): string | null {
  const m = new Map<string, number | null>();
  for (const c of chain) if (!m.has(c.expiration)) m.set(c.expiration, c.dte);
  const exps = [...m.entries()].map(([e, dte]) => ({ e, dte: dte ?? 9999 })).filter((x) => x.dte >= 0);
  if (!exps.length) return [...m.keys()][0] ?? null;
  const win = exps.filter((x) => x.dte >= 14 && x.dte <= 50);
  const pool = win.length ? win : exps;
  return pool.reduce((p, c) => (Math.abs(c.dte - 30) < Math.abs(p.dte - 30) ? c : p)).e;
}

function thetaHarvest(legs: HarvestLeg[], src: OptionContract[]): number | null {
  let t = 0;
  let any = false;
  for (const leg of legs) {
    const c = src.find((x) => x.type === leg.type && x.strike === leg.strike);
    if (!c || c.theta == null) continue;
    any = true;
    // seller benefits from decay: short leg harvests −theta, long leg pays it.
    t += (leg.action === "sell" ? 1 : -1) * -c.theta * CONTRACT;
  }
  return any ? t : null;
}

function skew25(opts: OptionContract[]): number | null {
  const puts = opts.filter((c) => c.type === "put" && c.impliedVolatility != null && c.delta != null);
  const calls = opts.filter((c) => c.type === "call" && c.impliedVolatility != null && c.delta != null);
  if (!puts.length || !calls.length) return null;
  const p = puts.reduce((a, b) => (Math.abs(Math.abs(b.delta!) - 0.25) < Math.abs(Math.abs(a.delta!) - 0.25) ? b : a));
  const c = calls.reduce((a, b) => (Math.abs(b.delta! - 0.25) < Math.abs(a.delta! - 0.25) ? b : a));
  return (p.impliedVolatility as number) - (c.impliedVolatility as number);
}

function clamp(x: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, x));
}

/**
 * Build the premium-harvesting report for a chosen expiration (or the best harvest tenor when none
 * is forced). Returns ranked, fully-specified credit structures with strikes (price), DTE/theta
 * (time), credit, breakevens, POP, return-on-capital and a VRP-weighted conviction score.
 */
export function buildHarvestReport(
  chain: OptionContract[],
  spot: number | null,
  bars: HistoryBar[],
  exp?: string | null,
): HarvestReport {
  const empty: HarvestReport = {
    regime: "neutral",
    headline: "Not enough data to model premium harvesting.",
    expiration: null,
    dte: null,
    iv: null,
    rv: null,
    vrpRatio: null,
    termShape: "n/a",
    skew: null,
    emExp: null,
    callWall: null,
    putWall: null,
    signals: [],
    notes: [],
  };
  if (!spot || !chain.length) return empty;

  const chosen = exp && exp !== "ALL" && chain.some((c) => c.expiration === exp) ? exp : chooseHarvestExpiration(chain);
  if (!chosen) return empty;
  const opts = chain.filter((c) => c.expiration === chosen);
  if (!opts.length) return empty;
  const dte = opts.find((c) => c.dte != null)?.dte ?? null;

  const iv = atmIv(chain, spot, chosen);
  const rv = realizedVol(bars, 20) ?? realizedVol(bars, 10);
  const vrpRatio = iv != null && rv ? iv / rv : null;
  const skew = skew25(opts);

  // term shape (front vs back ATM IV)
  const exps = [...new Set(chain.map((c) => c.expiration))].sort();
  const frontIv = exps.length ? atmIv(chain, spot, exps[0]) : null;
  const backIv = exps.length ? atmIv(chain, spot, exps[exps.length - 1]) : null;
  let termShape: HarvestReport["termShape"] = "n/a";
  if (frontIv != null && backIv != null && exps.length > 1) {
    const d = (backIv - frontIv) / frontIv;
    termShape = d > 0.03 ? "contango" : d < -0.03 ? "backwardation" : "flat";
  }

  const emExp = iv != null && dte != null ? spot * iv * Math.sqrt(Math.max(dte, 1) / TRADING_DAYS) : null;
  const by = gexByStrike(opts, spot);
  const cw = callWall(by);
  const pw = putWall(by);
  const strad = expectedMove(chain, spot, chosen);

  const regime: HarvestReport["regime"] =
    vrpRatio == null ? (termShape === "backwardation" ? "harvest" : "neutral") : vrpRatio >= 1.1 ? "harvest" : vrpRatio <= 0.95 ? "avoid" : "neutral";

  // VRP-weighted base conviction (0..1): richer IV vs RV → sell more confidently.
  const vrpScore = vrpRatio == null ? 0.5 : clamp((vrpRatio - 0.9) / (1.6 - 0.9), 0, 1);

  const step = strikeStep(opts);
  const wingW = Math.max(step, Math.round(((emExp ?? step * 2) * 0.4) / step) * step);

  const signals: HarvestSignal[] = [];
  const annual = (rom: number | null) => (rom != null && dte && dte > 0 ? rom * (365 / dte) : null);

  const mkScore = (pop: number | null, rom: number | null, confluence: number, sideOk: number) => {
    const popPart = pop == null ? 0.5 : clamp((pop - 0.5) / 0.45, 0, 1); // 50%→95%
    const romPart = rom == null ? 0.3 : clamp(rom / 0.25, 0, 1); // 25% ROM caps
    return Math.round(100 * clamp(0.45 * vrpScore + 0.25 * popPart + 0.15 * romPart + 0.1 * confluence + 0.05 * sideOk, 0, 1));
  };

  // ── Cash-Secured Put (bullish premium) ── short ~30Δ put, anchored to put support
  const csp = nearestByDelta(opts, "put", DELTA_AGGR);
  if (csp) {
    const m = midOf(csp);
    const k = csp.strike;
    const be = k - m;
    const pop = clamp(1 - Math.abs(csp.delta as number), 0, 1);
    const capital = (k - m) * CONTRACT;
    const rom = capital > 0 ? (m * CONTRACT) / capital : null;
    const legs: HarvestLeg[] = [{ action: "sell", type: "put", strike: k, delta: csp.delta, mid: m }];
    const confl = pw != null && k <= pw ? 1 : pw != null && k <= pw * 1.01 ? 0.6 : 0.2;
    signals.push({
      name: "Cash-Secured Put",
      side: "bullish",
      legs,
      credit: m,
      maxProfit: m * CONTRACT,
      maxLoss: (k - m) * CONTRACT,
      capital,
      breakevens: [be],
      pop,
      thetaDay: thetaHarvest(legs, opts),
      rom,
      romAnnual: annual(rom),
      expiration: chosen,
      dte,
      rationale: `Sell the ${k}P (~${Math.round(Math.abs((csp.delta as number) * 100))}Δ) into rich IV. Strike ${
        pw != null && k <= pw ? "sits at/below the put wall — dealer support reinforces it" : "is below spot"
      }. Keep the premium above ${be.toFixed(2)}; willing to own shares there.`,
      score: mkScore(pop, rom, confl, 1),
    });
  }

  // ── Covered Call / short call (bearish premium) ── short ~30Δ call at call resistance
  const sc = nearestByDelta(opts, "call", DELTA_AGGR);
  if (sc) {
    const m = midOf(sc);
    const k = sc.strike;
    const pop = clamp(1 - Math.abs(sc.delta as number), 0, 1);
    const capital = spot * CONTRACT; // covered by 100 shares
    const rom = capital > 0 ? (m * CONTRACT) / capital : null;
    const legs: HarvestLeg[] = [{ action: "sell", type: "call", strike: k, delta: sc.delta, mid: m }];
    const confl = cw != null && k >= cw ? 1 : cw != null && k >= cw * 0.99 ? 0.6 : 0.2;
    signals.push({
      name: "Covered Call",
      side: "bearish",
      legs,
      credit: m,
      maxProfit: m * CONTRACT,
      maxLoss: null,
      capital,
      breakevens: [k + m],
      pop,
      thetaDay: thetaHarvest(legs, opts),
      rom,
      romAnnual: annual(rom),
      expiration: chosen,
      dte,
      rationale: `Sell the ${k}C (~${Math.round((sc.delta as number) * 100)}Δ) against stock. ${
        cw != null && k >= cw ? "Strike is at/above the call wall — heaviest gamma caps upside there." : "Caps upside above the strike."
      } Income on flat-to-down drift.`,
      score: mkScore(pop, rom, confl, 1),
    });
  }

  // ── Iron Condor (defined-risk, neutral) ── ~16Δ short strikes outside ±1σ, wings `wingW` out
  const sp = nearestByDelta(opts, "put", DELTA_SAFE);
  const scd = nearestByDelta(opts, "call", DELTA_SAFE);
  if (sp && scd) {
    const lp = nearestByStrike(opts, "put", sp.strike - wingW);
    const lc = nearestByStrike(opts, "call", scd.strike + wingW);
    if (lp && lc && lp.strike < sp.strike && lc.strike > scd.strike) {
      const credit = midOf(sp) - midOf(lp) + (midOf(scd) - midOf(lc));
      const widthP = sp.strike - lp.strike;
      const widthC = lc.strike - scd.strike;
      const width = Math.max(widthP, widthC);
      if (credit > 0) {
        const pop = clamp(1 - Math.abs(sp.delta as number) - Math.abs(scd.delta as number), 0, 1);
        const maxLoss = (width - credit) * CONTRACT;
        const capital = maxLoss;
        const rom = capital > 0 ? (credit * CONTRACT) / capital : null;
        const legs: HarvestLeg[] = [
          { action: "sell", type: "put", strike: sp.strike, delta: sp.delta, mid: midOf(sp) },
          { action: "buy", type: "put", strike: lp.strike, delta: lp.delta, mid: midOf(lp) },
          { action: "sell", type: "call", strike: scd.strike, delta: scd.delta, mid: midOf(scd) },
          { action: "buy", type: "call", strike: lc.strike, delta: lc.delta, mid: midOf(lc) },
        ];
        const outside = emExp != null && sp.strike <= spot - emExp && scd.strike >= spot + emExp ? 1 : 0.5;
        signals.push({
          name: "Iron Condor",
          side: "neutral",
          legs,
          credit,
          maxProfit: credit * CONTRACT,
          maxLoss,
          capital,
          breakevens: [sp.strike - credit, scd.strike + credit],
          pop,
          thetaDay: thetaHarvest(legs, opts),
          rom,
          romAnnual: annual(rom),
          expiration: chosen,
          dte,
          rationale: `Sell the ~16Δ ${sp.strike}P / ${scd.strike}C and buy ${lp.strike}P / ${lc.strike}C wings. Short strikes ${
            outside === 1 ? "sit OUTSIDE the ±1σ expected move" : "straddle the expected move"
          }${emExp != null ? ` (≈ ${(spot - emExp).toFixed(0)}–${(spot + emExp).toFixed(0)})` : ""}. Defined risk; max profit if price stays between the shorts.`,
          score: mkScore(pop, rom, outside, 1),
        });
      }
    }
  }

  // ── Short Strangle (undefined risk, neutral) ── ~16Δ both sides
  if (sp && scd) {
    const credit = midOf(sp) + midOf(scd);
    const pop = clamp(1 - Math.abs(sp.delta as number) - Math.abs(scd.delta as number), 0, 1);
    const capital = 0.2 * spot * CONTRACT; // rough reg-T margin proxy
    const rom = capital > 0 ? (credit * CONTRACT) / capital : null;
    const legs: HarvestLeg[] = [
      { action: "sell", type: "put", strike: sp.strike, delta: sp.delta, mid: midOf(sp) },
      { action: "sell", type: "call", strike: scd.strike, delta: scd.delta, mid: midOf(scd) },
    ];
    signals.push({
      name: "Short Strangle",
      side: "neutral",
      legs,
      credit,
      maxProfit: credit * CONTRACT,
      maxLoss: null,
      capital,
      breakevens: [sp.strike - credit, scd.strike + credit],
      pop,
      thetaDay: thetaHarvest(legs, opts),
      rom,
      romAnnual: annual(rom),
      expiration: chosen,
      dte,
      rationale: `Naked ~16Δ ${sp.strike}P / ${scd.strike}C. Maximum theta and the purest VRP harvest, but undefined tails — size small and manage at ~21 DTE / 50% profit. Margin is a proxy.`,
      score: mkScore(pop, rom, 0.6, 1) - 6,
    });
  }

  // ── Bull Put Spread (defined-risk, bullish) ── ~30Δ short put at support
  if (csp) {
    const longK = csp.strike - wingW;
    const lp = nearestByStrike(opts, "put", longK);
    if (lp && lp.strike < csp.strike) {
      const credit = midOf(csp) - midOf(lp);
      const width = csp.strike - lp.strike;
      if (credit > 0) {
        const pop = clamp(1 - Math.abs(csp.delta as number), 0, 1);
        const maxLoss = (width - credit) * CONTRACT;
        const rom = maxLoss > 0 ? (credit * CONTRACT) / maxLoss : null;
        const legs: HarvestLeg[] = [
          { action: "sell", type: "put", strike: csp.strike, delta: csp.delta, mid: midOf(csp) },
          { action: "buy", type: "put", strike: lp.strike, delta: lp.delta, mid: midOf(lp) },
        ];
        const confl = pw != null && csp.strike <= pw ? 1 : 0.4;
        signals.push({
          name: "Bull Put Spread",
          side: "bullish",
          legs,
          credit,
          maxProfit: credit * CONTRACT,
          maxLoss,
          capital: maxLoss,
          breakevens: [csp.strike - credit],
          pop,
          thetaDay: thetaHarvest(legs, opts),
          rom,
          romAnnual: annual(rom),
          expiration: chosen,
          dte,
          rationale: `Defined-risk version of the CSP: sell ${csp.strike}P / buy ${lp.strike}P${
            pw != null && csp.strike <= pw ? ", short strike at/below the put wall" : ""
          }. Caps the tail for far less capital.`,
          score: mkScore(pop, rom, confl, 1),
        });
      }
    }
  }

  // ── Bear Call Spread (defined-risk, bearish) ── ~30Δ short call at resistance
  if (sc) {
    const longK = sc.strike + wingW;
    const lc = nearestByStrike(opts, "call", longK);
    if (lc && lc.strike > sc.strike) {
      const credit = midOf(sc) - midOf(lc);
      const width = lc.strike - sc.strike;
      if (credit > 0) {
        const pop = clamp(1 - Math.abs(sc.delta as number), 0, 1);
        const maxLoss = (width - credit) * CONTRACT;
        const rom = maxLoss > 0 ? (credit * CONTRACT) / maxLoss : null;
        const legs: HarvestLeg[] = [
          { action: "sell", type: "call", strike: sc.strike, delta: sc.delta, mid: midOf(sc) },
          { action: "buy", type: "call", strike: lc.strike, delta: lc.delta, mid: midOf(lc) },
        ];
        const confl = cw != null && sc.strike >= cw ? 1 : 0.4;
        signals.push({
          name: "Bear Call Spread",
          side: "bearish",
          legs,
          credit,
          maxProfit: credit * CONTRACT,
          maxLoss,
          capital: maxLoss,
          breakevens: [sc.strike + credit],
          pop,
          thetaDay: thetaHarvest(legs, opts),
          rom,
          romAnnual: annual(rom),
          expiration: chosen,
          dte,
          rationale: `Sell ${sc.strike}C / buy ${lc.strike}C${
            cw != null && sc.strike >= cw ? ", short strike at/above the call wall" : ""
          }. Fades strength into resistance with a capped tail.`,
          score: mkScore(pop, rom, confl, 1),
        });
      }
    }
  }

  signals.sort((a, b) => b.score - a.score);

  const headline =
    regime === "harvest"
      ? `VRP favors SELLING premium — IV ${(iv! * 100).toFixed(1)}% vs RV ${rv != null ? (rv * 100).toFixed(1) + "%" : "n/a"}${
          vrpRatio != null ? ` (${vrpRatio.toFixed(2)}×)` : ""
        }. Harvest theta with defined risk.`
      : regime === "avoid"
        ? `IV is CHEAP vs realized${vrpRatio != null ? ` (${vrpRatio.toFixed(2)}×)` : ""} — premium selling has little edge here. Prefer long gamma / debit structures; if selling, stay tight & small.`
        : `VRP roughly fair${vrpRatio != null ? ` (${vrpRatio.toFixed(2)}×)` : ""} — selectively harvest the richest strikes; lean on levels & POP.`;

  const notes: string[] = [];
  if (termShape === "backwardation")
    notes.push("Backwardated term structure → front-month IV is bid (event/stress). Selling the front or a calendar (sell front / buy back) harvests the crush — but a gap through your strike is the risk.");
  if (termShape === "contango") notes.push("Contango term structure → calm regime; front theta decays cleanly but pays less. Don't over-reach for yield in the back months (more vega risk).");
  if (skew != null && skew > 0.03) notes.push(`Steep put skew (+${(skew * 100).toFixed(1)} pts) → downside puts are richest. Put-spreads / jade-lizards finance well; avoid naked puts into the skew.`);
  if (dte != null && dte <= 1) notes.push("0DTE selected: pure theta but max gamma — tiny size, hard stops, no overnight risk. Manage actively; one gap can erase weeks of credit.");
  if (regime === "harvest") notes.push("Management: take profits at ~50% of max, roll/close tested sides near 21 DTE, and size for the worst gap day — short vol wins often and loses big.");
  notes.push("Credits/POP/ROM are estimates from ~15-min delayed mid prices, delta-as-probability, and r=q=0. Educational — not financial advice.");

  return { regime, headline, expiration: chosen, dte, iv, rv, vrpRatio, termShape, skew, emExp, callWall: cw, putWall: pw, signals, notes };
}
