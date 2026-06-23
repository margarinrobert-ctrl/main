import type { HistoryBar, OptionContract } from "../barchart/types";
import {
  atmIv,
  callWall,
  expectedMove1D,
  filterByExpiration,
  gammaFlip,
  gexByStrike,
  maxPain,
  netDex,
  netGex,
  putCallRatio,
  putWall,
  realizedVol,
  secondOrderExposure,
} from "./analytics";
import { buildHarvestReport } from "./harvest";

// Synthesized trade-signal board. Fuses the dealer-gamma map (regime / γ-flip / walls), order-flow
// tilt (net Δ exposure, put/call), second-order flow (vanna/charm), the volatility risk premium
// (IV vs realized), skew and max-pain into ranked, concrete trade ideas — each with entry / target /
// stop *price levels* and a *time* horizon. Standard desk heuristics; educational, not advice.

export type SignalSide = "bullish" | "bearish" | "neutral";
export type SignalCategory = "Directional" | "Volatility" | "Regime" | "Pin/Expiry" | "Squeeze/Tail" | "Skew";

export interface TradeSignal {
  id: string;
  category: SignalCategory;
  side: SignalSide;
  title: string;
  thesis: string;
  trade: string; // the concrete expression
  entry: number | null;
  targets: number[];
  stop: number | null;
  horizon: string;
  score: number; // 0..100
  tags: string[];
}

export interface SignalBoard {
  spot: number | null;
  regime: "long" | "short" | "unknown";
  bias: SignalSide;
  biasScore: number; // -100..100
  expiration: string | null;
  dte: number | null;
  signals: TradeSignal[];
  notes: string[];
}

const clamp = (x: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, x));
const f2 = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 2 });

function nearestFutureExp(chain: OptionContract[]): { exp: string | null; dte: number | null } {
  const m = new Map<string, number | null>();
  for (const c of chain) if (!m.has(c.expiration)) m.set(c.expiration, c.dte);
  const arr = [...m.entries()].map(([exp, dte]) => ({ exp, dte })).filter((x) => (x.dte ?? 0) >= 0).sort((a, b) => (a.dte ?? 0) - (b.dte ?? 0));
  return arr[0] ?? { exp: [...m.keys()][0] ?? null, dte: null };
}

function smaMomentum(bars: HistoryBar[], window = 10): number {
  const closes = bars.map((b) => b.close).filter((x) => x > 0);
  if (closes.length < window + 1) return 0;
  const last = closes[closes.length - 1];
  const sma = closes.slice(-window).reduce((a, b) => a + b, 0) / window;
  return sma > 0 ? (last - sma) / sma : 0;
}

function skew25(opts: OptionContract[]): number | null {
  const puts = opts.filter((c) => c.type === "put" && c.impliedVolatility != null && c.delta != null);
  const calls = opts.filter((c) => c.type === "call" && c.impliedVolatility != null && c.delta != null);
  if (!puts.length || !calls.length) return null;
  const p = puts.reduce((a, b) => (Math.abs(Math.abs(b.delta!) - 0.25) < Math.abs(Math.abs(a.delta!) - 0.25) ? b : a));
  const c = calls.reduce((a, b) => (Math.abs(b.delta! - 0.25) < Math.abs(a.delta! - 0.25) ? b : a));
  return (p.impliedVolatility as number) - (c.impliedVolatility as number);
}

function horizonFor(dte: number | null): string {
  if (dte == null) return "Swing";
  if (dte <= 1) return "Scalp · 0–1 DTE";
  if (dte <= 7) return "Intraday–days";
  return "Swing · weeks";
}

/**
 * Build the ranked signal board. `exp` (from the dashboard selector) scopes the gamma levels; the
 * volatility read auto-picks the best harvest tenor unless a specific expiration is forced.
 */
export function buildSignals(chain: OptionContract[], spot: number | null, bars: HistoryBar[], exp?: string | null): SignalBoard {
  const base: SignalBoard = { spot, regime: "unknown", bias: "neutral", biasScore: 0, expiration: null, dte: null, signals: [], notes: [] };
  if (!spot || !chain.length) return base;

  const scoped = !!exp && exp !== "ALL";
  const lvl = scoped ? filterByExpiration(chain, exp) : chain;
  const by = gexByStrike(lvl, spot);
  if (!by.length) return base;

  const ngex = netGex(lvl, spot);
  const flip = gammaFlip(by);
  const cw = callWall(by);
  const pw = putWall(by);
  const dex = netDex(lvl, spot);
  const pc = putCallRatio(lvl);
  const so = secondOrderExposure(lvl, spot);
  const { exp: nExp, dte } = nearestFutureExp(lvl);
  const iv0 = nExp ? atmIv(lvl, spot, nExp) : null;
  const em1 = expectedMove1D(spot, iv0);
  const emAbs = em1?.abs ?? spot * 0.01;
  const mp = nExp ? maxPain(lvl, nExp) : null;
  const rv = realizedVol(bars, 20) ?? realizedVol(bars, 10);
  const vrp = iv0 != null && rv ? iv0 / rv : null;
  const skew = nExp ? skew25(filterByExpiration(chain, nExp)) : null;
  const mom = smaMomentum(bars);
  const regime: SignalBoard["regime"] = ngex == null ? "unknown" : ngex >= 0 ? "long" : "short";

  // ── Composite directional bias (−100..100) ──
  const cFlip = flip != null ? clamp((spot - flip) / emAbs, -1, 1) : 0;
  const cPc = pc.vol != null ? clamp((1.0 - pc.vol) / 0.3, -1, 1) : 0; // call-heavy = bullish
  const cMom = clamp(mom / 0.02, -1, 1);
  const cDex = dex != null ? Math.sign(dex) * 0.5 : 0;
  const cSkew = skew != null ? -clamp(skew / 0.05, 0, 1) : 0; // steep put skew = defensive
  const cPain = mp != null ? clamp((mp - spot) / (emAbs * 2), -1, 1) : 0; // drift toward pain
  const W = { flip: 35, pc: 20, mom: 15, dex: 10, skew: 10, pain: 10 };
  const biasScore = Math.round(cFlip * W.flip + cPc * W.pc + cMom * W.mom + cDex * W.dex + cSkew * W.skew + cPain * W.pain);
  const bias: SignalSide = biasScore > 15 ? "bullish" : biasScore < -15 ? "bearish" : "neutral";

  const signals: TradeSignal[] = [];
  const horizon = horizonFor(dte);

  // ── 1) Directional trade from the bias + levels ──
  if (bias === "bullish") {
    const target = [cw, em1 ? spot + em1.abs : null].filter((x): x is number => x != null);
    signals.push({
      id: "dir-bull",
      category: "Directional",
      side: "bullish",
      title: "Long bias — above the γ-flip",
      thesis: `Spot ${f2(spot)} is above the γ-flip${flip != null ? ` (${f2(flip)})` : ""} in a ${regime}-gamma tape${
        pc.vol != null ? `, call-leaning flow (P/C ${pc.vol.toFixed(2)})` : ""
      }. Dips get bought while it holds.`,
      trade: `Long underlying/calls on pullbacks toward ${flip != null ? f2(flip) : "support"}${
        pw != null ? ` / put wall ${pw}` : ""
      }; or sell a bull put spread under ${pw ?? "support"}.`,
      entry: flip ?? pw ?? null,
      targets: target.length ? target : cw != null ? [cw] : [],
      stop: flip != null ? Math.round((flip - emAbs) * 100) / 100 : pw,
      horizon,
      score: clamp(45 + Math.abs(biasScore) * 0.5 + (cw != null && spot < cw ? 8 : 0), 0, 100),
      tags: ["spot>flip", regime + "-γ", pc.vol != null ? `P/C ${pc.vol.toFixed(2)}` : ""].filter(Boolean),
    });
  } else if (bias === "bearish") {
    const target = [pw, em1 ? spot - em1.abs : null].filter((x): x is number => x != null);
    signals.push({
      id: "dir-bear",
      category: "Directional",
      side: "bearish",
      title: "Short bias — below the γ-flip",
      thesis: `Spot ${f2(spot)} is below the γ-flip${flip != null ? ` (${f2(flip)})` : ""}${
        regime === "short" ? " in short-gamma — moves accelerate" : ""
      }${pc.vol != null ? `, put-leaning flow (P/C ${pc.vol.toFixed(2)})` : ""}. Rallies get sold.`,
      trade: `Short underlying/puts on bounces toward ${flip != null ? f2(flip) : "resistance"}${
        cw != null ? ` / call wall ${cw}` : ""
      }; or sell a bear call spread above ${cw ?? "resistance"}.`,
      entry: flip ?? cw ?? null,
      targets: target.length ? target : pw != null ? [pw] : [],
      stop: flip != null ? Math.round((flip + emAbs) * 100) / 100 : cw,
      horizon,
      score: clamp(45 + Math.abs(biasScore) * 0.5 + (pw != null && spot > pw ? 8 : 0), 0, 100),
      tags: ["spot<flip", regime + "-γ", pc.vol != null ? `P/C ${pc.vol.toFixed(2)}` : ""].filter(Boolean),
    });
  } else {
    signals.push({
      id: "dir-neutral",
      category: "Directional",
      side: "neutral",
      title: "Range / two-way — near the γ-flip",
      thesis: `Spot ${f2(spot)} is balanced around the γ-flip${flip != null ? ` (${f2(flip)})` : ""}. No decisive tilt — trade the edges, not the middle.`,
      trade: `Fade ${pw ?? "support"} long and ${cw ?? "resistance"} short; or sell an iron condor outside ±1σ (${f2(spot - emAbs)}–${f2(spot + emAbs)}).`,
      entry: null,
      targets: [cw, pw].filter((x): x is number => x != null),
      stop: null,
      horizon,
      score: 40,
      tags: ["at flip", regime + "-γ"],
    });
  }

  // ── 2) Regime trade (mean-reversion vs momentum) ──
  signals.push(
    regime === "long"
      ? {
          id: "regime-mr",
          category: "Regime",
          side: "neutral",
          title: "Mean-reversion regime (long gamma)",
          thesis: "Positive net dealer gamma damps moves — dealers buy dips / sell rips. Expect pinning and failed breakouts.",
          trade: `Fade extremes back toward ${flip != null ? f2(flip) : "VWAP"} / prior level; sell premium into spikes. Size breakout trades down.`,
          entry: null,
          targets: flip != null ? [flip] : [],
          stop: null,
          horizon: "Intraday",
          score: clamp(50 + (ngex != null ? clamp(Math.abs(ngex) / 5e9, 0, 1) * 15 : 0), 0, 100),
          tags: ["long-γ", "fade"],
        }
      : {
          id: "regime-mom",
          category: "Regime",
          side: "neutral",
          title: "Momentum regime (short gamma)",
          thesis: "Negative net dealer gamma amplifies moves — dealers sell dips / buy rips. Trends extend; dips can cascade.",
          trade: `Trade breakouts of ${pw ?? "support"} / ${cw ?? "resistance"}, trail the trend, respect stops — moves overshoot.`,
          entry: null,
          targets: [cw, pw].filter((x): x is number => x != null),
          stop: null,
          horizon: "Intraday",
          score: clamp(52 + (ngex != null ? clamp(Math.abs(ngex) / 5e9, 0, 1) * 15 : 0), 0, 100),
          tags: ["short-γ", "momentum"],
        },
  );

  // ── 3) Volatility / VRP trade (reuse the harvest engine) ──
  const hv = buildHarvestReport(chain, spot, bars, exp);
  if (hv.regime === "harvest" && hv.signals.length) {
    const top = hv.signals[0];
    signals.push({
      id: "vol-sell",
      category: "Volatility",
      side: top.side,
      title: `Sell premium — VRP ${hv.vrpRatio != null ? hv.vrpRatio.toFixed(2) + "×" : "rich"}`,
      thesis: `IV ${hv.iv != null ? (hv.iv * 100).toFixed(1) + "%" : "—"} is rich vs realized ${
        hv.rv != null ? (hv.rv * 100).toFixed(1) + "%" : "—"
      }. The volatility risk premium pays sellers.`,
      trade: `${top.name}: ${top.legs.map((l) => `${l.action === "sell" ? "−" : "+"}${l.strike}${l.type === "call" ? "C" : "P"}`).join(" ")} for $${top.credit.toFixed(2)} (POP ${top.pop != null ? Math.round(top.pop * 100) + "%" : "—"}). See Harvest tab.`,
      entry: null,
      targets: top.breakevens,
      stop: null,
      horizon: hv.dte != null ? `${hv.dte}d` : "30d",
      score: clamp(55 + (hv.vrpRatio != null ? clamp((hv.vrpRatio - 1) / 0.6, 0, 1) * 30 : 10), 0, 100),
      tags: ["VRP", hv.expiration ?? ""].filter(Boolean),
    });
  } else if (hv.regime === "avoid") {
    signals.push({
      id: "vol-buy",
      category: "Volatility",
      side: "neutral",
      title: `Buy gamma — IV cheap${hv.vrpRatio != null ? ` (${hv.vrpRatio.toFixed(2)}×)` : ""}`,
      thesis: `IV ${hv.iv != null ? (hv.iv * 100).toFixed(1) + "%" : "—"} is at/below realized ${
        hv.rv != null ? (hv.rv * 100).toFixed(1) + "%" : "—"
      } — options underprice movement.`,
      trade: "Long straddle / calendar (own gamma) and delta-hedge; or buy directional optionality. Avoid naked premium selling.",
      entry: null,
      targets: [spot - emAbs, spot + emAbs],
      stop: null,
      horizon: "days–weeks",
      score: clamp(50 + (hv.vrpRatio != null ? clamp((1 - hv.vrpRatio) / 0.2, 0, 1) * 20 : 0), 0, 100),
      tags: ["IV cheap", "long vol"],
    });
  }

  // ── 4) Pin / expiry trade (only meaningful with little time left) ──
  if (mp != null && dte != null && dte <= 3 && regime === "long" && Math.abs(spot - mp) / spot < 0.03) {
    signals.push({
      id: "pin",
      category: "Pin/Expiry",
      side: "neutral",
      title: `Pin risk toward ${mp}`,
      thesis: `Into expiry (${dte}d) with long dealer gamma, price gravitates to max pain ${mp}${
        so.charm != null ? `; charm ${so.charm >= 0 ? "drags lower" : "lifts"} as decay accelerates` : ""
      }.`,
      trade: `Fade pushes away from ${mp} back toward it; sell expiring wings (condor) straddling ${mp}.`,
      entry: null,
      targets: [mp],
      stop: null,
      horizon: "0–3 DTE",
      score: clamp(60 - Math.abs(spot - mp) / spot / 0.03 * 15, 0, 100),
      tags: ["max pain", "pin"],
    });
  }

  // ── 5) Squeeze / tail-risk trade ──
  if (regime === "short" && flip != null && spot < flip && pw != null) {
    signals.push({
      id: "tail-down",
      category: "Squeeze/Tail",
      side: "bearish",
      title: `Air-pocket risk below ${pw}`,
      thesis: "Short-gamma below the flip — a break of the put wall removes dealer support and moves cascade.",
      trade: `Momentum short on a clean break of ${pw}, target ${f2(spot - emAbs * 2)}. ${
        vrp != null && vrp < 1 ? "IV is cheap — a put/put-spread hedge is well-priced." : "Define risk; reversals are violent."
      }`,
      entry: pw,
      targets: [Math.round((spot - emAbs * 2) * 100) / 100],
      stop: flip,
      horizon,
      score: clamp(50 + Math.abs(biasScore) * 0.3, 0, 100),
      tags: ["short-γ", "tail"],
    });
  }
  if (cw != null && spot < cw && (spot >= cw * 0.985) && pc.vol != null && pc.vol < 0.8) {
    signals.push({
      id: "squeeze-up",
      category: "Squeeze/Tail",
      side: "bullish",
      title: `Gamma-squeeze setup into ${cw}`,
      thesis: `Spot is pressing the call wall ${cw} with call-heavy flow (P/C ${pc.vol.toFixed(2)}). A break forces dealer call-hedging to chase.`,
      trade: `Long on a break-and-hold above ${cw}, target ${f2(cw + emAbs)}; fail back below = fade.`,
      entry: cw,
      targets: [Math.round((cw + emAbs) * 100) / 100],
      stop: Math.round((cw - emAbs * 0.5) * 100) / 100,
      horizon,
      score: 58,
      tags: ["call wall", "squeeze"],
    });
  }

  // ── 6) Skew trade ──
  if (skew != null && skew > 0.04) {
    signals.push({
      id: "skew-put",
      category: "Skew",
      side: "neutral",
      title: `Rich put skew (+${(skew * 100).toFixed(1)} pts)`,
      thesis: "Downside puts are heavily bid (defensive hedging) — the fingerprint of the VRP. Finance the skew rather than buy it.",
      trade: "Put-spread or jade-lizard (sell put + call spread, no upside risk); or risk-reversal (sell put / buy call) for cheap upside if bullish.",
      entry: null,
      targets: [pw, cw].filter((x): x is number => x != null),
      stop: null,
      horizon: "Swing",
      score: clamp(48 + clamp((skew - 0.04) / 0.04, 0, 1) * 14, 0, 100),
      tags: ["skew", "VRP"],
    });
  }

  signals.sort((a, b) => b.score - a.score);

  const notes = [
    `Composite bias ${biasScore > 0 ? "+" : ""}${biasScore} (spot vs γ-flip, put/call, momentum, Δ-exposure, skew, max-pain).`,
    "Levels are ~15-min delayed (CBOE). Signals are model heuristics for education — not financial advice. Confirm with price action & risk limits.",
  ];

  return { spot, regime, bias, biasScore, expiration: nExp, dte, signals, notes };
}

export interface ScanRow {
  symbol: string;
  spot: number | null;
  bias: SignalSide;
  biasScore: number;
  regime: "long" | "short" | "unknown";
  vrp: number | null;
  flip: number | null;
  callWall: number | null;
  putWall: number | null;
  top: TradeSignal | null;
}

/** Compact per-symbol summary for the cross-ticker scanner: composite bias, regime, VRP, key levels and the top signal. */
export function scanRow(symbol: string, chain: OptionContract[], spot: number | null, bars: HistoryBar[], exp?: string | null): ScanRow {
  const board = buildSignals(chain, spot, bars, exp);
  const lvl = exp && exp !== "ALL" ? filterByExpiration(chain, exp) : chain;
  const by = gexByStrike(lvl, spot);
  const { exp: nExp } = nearestFutureExp(lvl);
  const iv0 = nExp ? atmIv(lvl, spot, nExp) : null;
  const rv = realizedVol(bars, 20) ?? realizedVol(bars, 10);
  return {
    symbol,
    spot,
    bias: board.bias,
    biasScore: board.biasScore,
    regime: board.regime,
    vrp: iv0 != null && rv ? iv0 / rv : null,
    flip: gammaFlip(by),
    callWall: callWall(by),
    putWall: putWall(by),
    top: board.signals[0] ?? null,
  };
}
