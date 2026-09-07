import type { GexSample } from "../gex-history";
import type { HistoryBar, OptionContract } from "../barchart/types";
import {
  atmIv,
  callOiWall,
  callResistance,
  expectedMove1D,
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
} from "./analytics";

// Institutional-grade anomaly intelligence. An ENSEMBLE of robust statistical detectors (z-score,
// modified-z / MAD, EWMA-deviation, CUSUM change-point, EVT tail) scores how anomalous the latest
// move is; dealer-gamma + flow + vol context then classify it bullish/bearish, project price targets
// and a reaction-time window, and score confidence — with an explainability trace.
//
// HONEST SCOPE (free data): order-flow factors (VPIN, cumulative delta, absorption) need a trade
// tape we don't have — they're PROXIED from options flow (put/call, DEX) + volume and labelled as
// such. IV-rank is a SESSION-window percentile (no long IV history). Time-forecast / edge are MODEL
// estimates, not backtested accuracy. Educational — not financial advice.

export type Band = "Weak" | "Moderate" | "Strong" | "Institutional" | "Extreme";

export interface ModelVote {
  name: string;
  vote: number; // 0..1
  detail: string;
}
export interface RankedLevel {
  kind: string;
  price: number;
  strength: number; // 0..1
}
export interface AnomalyIntel {
  timestamp: string;
  symbol: string;
  source: "intraday" | "daily" | "none";
  anomalyType: string;
  strength: number; // 0..100
  band: Band;
  bullish: number; // %
  bearish: number; // %
  neutral: boolean;
  confidence: number; // 0..100
  riskRating: "Low" | "Medium" | "High";
  expectedEdge: string;
  models: ModelVote[];
  anomalyLevel: number | null;
  expectedMove: number | null;
  targets: { label: string; price: number; kind: string }[];
  timeForecast: { window: string; probs: { h: string; p: number }[]; confidence: number; duration: string };
  quant: Record<string, string>;
  confidenceFactors: { label: string; ok: boolean; detail: string }[];
  levels: RankedLevel[];
  why: string[];
  institutional: string;
  methodology: string[];
  json: string;
}

const clamp = (x: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, x));
const mean = (a: number[]) => (a.length ? a.reduce((s, x) => s + x, 0) / a.length : 0);
const std = (a: number[]) => {
  if (a.length < 2) return 0;
  const m = mean(a);
  return Math.sqrt(a.reduce((s, x) => s + (x - m) * (x - m), 0) / (a.length - 1));
};
const median = (a: number[]) => {
  if (!a.length) return 0;
  const s = [...a].sort((x, y) => x - y);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const quantile = (a: number[], q: number) => {
  if (!a.length) return 0;
  const s = [...a].sort((x, y) => x - y);
  return s[clamp(Math.floor(q * (s.length - 1)), 0, s.length - 1)];
};
const bandOf = (s: number): Band => (s >= 80 ? "Extreme" : s >= 60 ? "Institutional" : s >= 40 ? "Strong" : s >= 20 ? "Moderate" : "Weak");
const f2 = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 2 });
const usd = (v: number) => {
  const a = Math.abs(v);
  const s = v < 0 ? "-" : "";
  return a >= 1e9 ? `${s}$${(a / 1e9).toFixed(2)}B` : a >= 1e6 ? `${s}$${(a / 1e6).toFixed(1)}M` : a >= 1e3 ? `${s}$${(a / 1e3).toFixed(0)}K` : `${s}$${Math.round(a)}`;
};

/** Robust-statistics ensemble on a return series: each detector returns a 0..1 "anomalousness" vote. */
function ensemble(rets: number[]): ModelVote[] {
  if (rets.length < 10) return [];
  const last = rets[rets.length - 1];
  const base = rets.slice(-61, -1); // trailing window excluding the last
  const m = mean(base);
  const sd = std(base);
  const med = median(base);
  const mad = median(base.map((x) => Math.abs(x - med))) || sd || 1e-9;
  const absR = base.map(Math.abs);
  const q90 = quantile(absR, 0.9);
  const q99 = quantile(absR, 0.99);

  // 1) classic z-score
  const z = sd > 0 ? (last - m) / sd : 0;
  // 2) modified z (MAD) — robust to outliers in the baseline
  const mz = (0.6745 * (last - med)) / mad;
  // 3) EWMA deviation (Kalman-like) — recency-weighted mean/var
  let em = rets[0];
  let ev = sd * sd || 1e-9;
  const lam = 0.94;
  for (let i = 1; i < rets.length - 1; i++) {
    const d = rets[i] - em;
    em = em + (1 - lam) * d;
    ev = lam * ev + (1 - lam) * d * d;
  }
  const ez = Math.sqrt(ev) > 0 ? (last - em) / Math.sqrt(ev) : 0;
  // 4) CUSUM change-point — accumulated standardized drift over the recent window
  let sp = 0;
  let sm = 0;
  let cmax = 0;
  for (const r of rets.slice(-30)) {
    const zr = sd > 0 ? (r - m) / sd : 0;
    sp = Math.max(0, sp + zr - 0.5);
    sm = Math.max(0, sm - zr - 0.5);
    cmax = Math.max(cmax, sp, sm);
  }
  // 5) EVT tail — peak-over-threshold exceedance of the 90th pct of |returns|
  const a = Math.abs(last);
  const evt = a <= q90 ? 0 : clamp((a - q90) / (q99 - q90 || sd || 1e-9), 0, 1);

  return [
    { name: "Z-score", vote: clamp((Math.abs(z) - 2) / 2.5, 0, 1), detail: `${z >= 0 ? "+" : ""}${z.toFixed(1)}σ vs trailing mean` },
    { name: "Modified-Z (MAD)", vote: clamp((Math.abs(mz) - 3) / 3, 0, 1), detail: `${mz.toFixed(1)} robust score` },
    { name: "EWMA / Kalman", vote: clamp((Math.abs(ez) - 1.5) / 2.5, 0, 1), detail: `${ez.toFixed(1)}σ vs EWMA` },
    { name: "CUSUM change-pt", vote: clamp(cmax / 6, 0, 1), detail: `${cmax.toFixed(1)} accumulated drift` },
    { name: "EVT tail", vote: evt, detail: evt > 0 ? `beyond ${(q90 * 100).toFixed(2)}% tail` : "within tail bounds" },
  ];
}

function buildReturns(samples: GexSample[], daily: HistoryBar[]): { rets: number[]; source: "intraday" | "daily" | "none" } {
  const spots = samples.filter((s) => s.spot != null).map((s) => s.spot as number);
  if (spots.length >= 15) {
    const r: number[] = [];
    for (let i = 1; i < spots.length; i++) if (spots[i] > 0 && spots[i - 1] > 0) r.push(Math.log(spots[i] / spots[i - 1]));
    if (r.length >= 10) return { rets: r, source: "intraday" };
  }
  const closes = daily.map((b) => b.close).filter((x) => x > 0);
  if (closes.length >= 12) {
    const r: number[] = [];
    for (let i = 1; i < closes.length; i++) r.push(Math.log(closes[i] / closes[i - 1]));
    return { rets: r, source: "daily" };
  }
  return { rets: [], source: "none" };
}

export function anomalyIntel(symbol: string, chain: OptionContract[], spot: number | null, daily: HistoryBar[], samples: GexSample[]): AnomalyIntel {
  const ts = new Date().toISOString();
  const { rets, source } = buildReturns(samples, daily);
  const models = ensemble(rets);
  const strength = models.length ? Math.round(clamp((0.25 * v(models, "Z-score") + 0.25 * v(models, "Modified-Z (MAD)") + 0.2 * v(models, "EWMA / Kalman") + 0.1 * v(models, "CUSUM change-pt") + 0.2 * v(models, "EVT tail")) * 100, 0, 100)) : 0;
  const band = bandOf(strength);
  const lastRet = rets.length ? rets[rets.length - 1] : 0;
  const moveDir = Math.sign(lastRet);

  // ── dealer / vol / flow context ──
  const by = gexByStrike(chain, spot);
  const ngex = netGex(chain, spot);
  const gross = by.reduce((s, x) => s + Math.abs(x.gex), 0) || 1;
  const regime = ngex == null ? "unknown" : ngex >= 0 ? "long" : "short";
  const flip = gammaFlipNearest(by, spot);
  const cw = callResistance(by, spot);
  const pw = putSupport(by, spot);
  const so = secondOrderExposure(chain, spot);
  const ndex = netDex(chain, spot);
  const pcr = putCallRatio(chain).vol;
  const exps = [...new Set(chain.map((c) => c.expiration))].sort();
  const front = exps.find((e) => (chain.find((c) => c.expiration === e)?.dte ?? -1) >= 0) ?? exps[0];
  const iv = front && spot ? atmIv(chain, spot, front) : null;
  const rv20 = realizedVol(daily, 20);
  const rv5 = realizedVol(daily, 5);
  const em = expectedMove1D(spot, iv)?.abs ?? (spot ? spot * 0.008 : null);
  const magnet = by.length ? by.reduce((a, b) => (Math.abs(b.gex) > Math.abs(a.gex) ? b : a)).strike : null;
  const ivRegime = rv5 != null && rv20 ? (rv5 / rv20 >= 1.4 ? "expansion" : rv5 / rv20 <= 0.7 ? "compression" : "normal") : "n/a";
  const relVol = relativeVolume(daily);
  // session IV percentile (no long IV history → within-session only)
  const ivHist = samples.map((s) => s.iv).filter((x): x is number => x != null && x > 0);
  const ivPctile = iv != null && ivHist.length >= 8 ? Math.round((ivHist.filter((x) => x <= iv).length / ivHist.length) * 100) : null;

  // ── classification: bullish vs bearish ──
  const reactionDir = regime === "long" ? -moveDir : moveDir; // long-γ fades, short-γ continues
  const cFlip = flip != null && spot && em ? clamp((spot - flip) / em, -1, 1) : 0;
  const cPcr = pcr != null ? clamp((1 - pcr) / 0.3, -1, 1) : 0;
  const cVanna = so.vanna != null ? Math.sign(so.vanna) * 0.4 : 0;
  const cCharm = so.charm != null ? (so.charm >= 0 ? -0.3 : 0.3) : 0;
  const cDex = ndex != null ? Math.sign(ndex) * 0.2 : 0;
  const convict = clamp(strength / 60, 0.25, 1);
  const dir = clamp(0.5 * reactionDir * convict + 0.2 * cFlip + 0.15 * cPcr + 0.1 * cVanna + 0.05 * cCharm + cDex * 0.1, -1, 1);
  const bullish = Math.round(clamp(50 + dir * 50, 2, 98));
  const bearish = 100 - bullish;
  const neutral = strength < 25 || Math.abs(dir) < 0.12;

  const anomalyType = classifyType(strength, regime, ivRegime, moveDir, so);

  // ── price targets (in the expected-reaction direction) ──
  const levels = rankLevels(by, spot, { cw, pw, flip, magnet, em, chain, front });
  const dirSign = neutral ? 0 : bullish >= 50 ? 1 : -1;
  const targets = buildTargets(spot, dirSign, em, levels);

  // ── time forecast (modeled) ──
  const timeForecast = forecastTime(regime, strength, ivRegime);

  // ── confidence engine ──
  const regimeClarity = clamp(Math.abs(ngex ?? 0) / gross / 0.25, 0, 1);
  const optAgree = agreementWith(dir, [cFlip, cPcr, cVanna, cDex]);
  const volConf = ivRegime === "expansion" ? 1 : ivRegime === "compression" ? 0.5 : 0.3;
  const volumeConf = clamp((relVol - 1) / 1.5, 0, 1);
  const dataQ = chain.length ? chain.filter((c) => c.gamma != null && c.delta != null && c.impliedVolatility != null).length / chain.length : 0;
  const confidence = Math.round(clamp(0.3 * (strength / 100) + 0.2 * regimeClarity + 0.2 * optAgree + 0.15 * volConf + 0.15 * dataQ, 0, 1) * 100);
  const confidenceFactors = [
    { label: "Regime clarity", ok: regimeClarity >= 0.5, detail: `net γ ${ngex != null ? usd(ngex) : "—"} (${Math.round(regimeClarity * 100)}% concentration)` },
    { label: "Options confirmation", ok: optAgree >= 0.5, detail: `flow ${optAgree >= 0.5 ? "agrees with" : "diverges from"} the directional read` },
    { label: "Volatility confirmation", ok: volConf >= 0.6, detail: `vol regime: ${ivRegime}` },
    { label: "Volume confirmation", ok: volumeConf >= 0.4, detail: `relative volume ${relVol.toFixed(2)}×` },
    { label: "Data quality", ok: dataQ >= 0.8, detail: `${Math.round(dataQ * 100)}% greeks coverage` },
  ];

  const riskRating: AnomalyIntel["riskRating"] = regime === "short" || band === "Extreme" ? "High" : strength >= 40 ? "Medium" : "Low";
  const expectedEdge = neutral ? "Neutral — no directional edge yet" : confidence >= 60 ? `Favorable ${bullish >= 50 ? "long" : "short"} edge` : confidence >= 40 ? "Modest edge — confirm with price" : "Low-confidence — stand aside";

  const quant: Record<string, string> = {
    "GEX (net γ/1%)": ngex == null ? "—" : usd(ngex),
    "DEX (net Δ)": ndex == null ? "—" : usd(ndex),
    "VEX (vanna $/vol-pt)": so.vanna == null ? "—" : usd(so.vanna),
    "CEX (charm $/day)": so.charm == null ? "—" : usd(so.charm),
    "γ-flip": flip == null ? "—" : f2(flip),
    "Call/Put wall": `${cw ?? "—"} / ${pw ?? "—"}`,
    "ATM IV": iv == null ? "—" : `${(iv * 100).toFixed(1)}%`,
    "Realized (20d)": rv20 == null ? "—" : `${(rv20 * 100).toFixed(1)}%`,
    "Vol regime": ivRegime,
    "IV %ile (session)": ivPctile == null ? "n/a" : `${ivPctile}%`,
    "Relative volume": `${relVol.toFixed(2)}×`,
    "Put/Call": pcr == null ? "—" : pcr.toFixed(2),
    "Order flow (proxy)": pcr == null ? "—" : pcr < 0.8 ? "buy-tilted" : pcr > 1.2 ? "sell-tilted" : "balanced",
  };

  const why = buildWhy(models, regime, moveDir, ivRegime, relVol, dir, neutral);
  const institutional = buildInstitutional(regime, dir, neutral, magnet, flip, so);
  const methodology = [
    "Ensemble: Z-score · Modified-Z (MAD) · EWMA/Kalman · CUSUM change-point · EVT tail (majority-weighted).",
    "Order-flow factors are PROXIES from options flow (put/call, DEX) + volume — no trade tape (VPIN/cumulative-delta/absorption unavailable).",
    "IV %ile is session-window (no long IV history). Targets, time-forecast and edge are MODEL estimates, not backtested accuracy.",
    "Educational — not financial advice.",
  ];

  const out = {
    timestamp: ts,
    symbol,
    source,
    anomalyType,
    strength,
    band,
    bullish,
    bearish,
    neutral,
    confidence,
    riskRating,
    expectedEdge,
    anomalyLevel: spot,
    expectedMove: em,
    targets,
    timeForecast,
    quant,
    levels,
    institutional,
  };
  const json = JSON.stringify(out, null, 2);

  return { ...out, models, confidenceFactors, why, methodology, json } as AnomalyIntel;
}

function v(models: ModelVote[], name: string): number {
  return models.find((m) => m.name === name)?.vote ?? 0;
}
function relativeVolume(daily: HistoryBar[]): number {
  const vols = daily.map((b) => b.volume).filter((x) => x > 0);
  if (vols.length < 6) return 1;
  const base = vols.slice(-21, -1);
  const m = mean(base);
  return m > 0 ? vols[vols.length - 1] / m : 1;
}
function agreementWith(dir: number, comps: number[]): number {
  if (Math.abs(dir) < 1e-6) return 0.5;
  const s = Math.sign(dir);
  const agree = comps.filter((c) => Math.sign(c) === s && Math.abs(c) > 0.05).length;
  const active = comps.filter((c) => Math.abs(c) > 0.05).length || 1;
  return agree / active;
}
function classifyType(strength: number, regime: string, ivRegime: string, moveDir: number, so: { charm: number | null }): string {
  if (strength < 20) return "No significant anomaly";
  if (ivRegime === "expansion") return regime === "short" ? "Volatility expansion (short-γ trend)" : "Volatility expansion";
  if (ivRegime === "compression") return "Volatility compression (coiled)";
  if (regime === "short" && moveDir !== 0) return moveDir > 0 ? "Short-γ upside acceleration" : "Short-γ downside cascade risk";
  if (regime === "long") return moveDir > 0 ? "Long-γ overshoot up (fade)" : "Long-γ overshoot down (fade)";
  return "Statistical outlier";
}
function rankLevels(by: { strike: number; gex: number }[], spot: number | null, ctx: { cw: number | null; pw: number | null; flip: number | null; magnet: number | null; em: number | null; chain: OptionContract[]; front: string | null }): RankedLevel[] {
  if (spot == null) return [];
  const oi = oiByStrike(ctx.chain);
  const gross = by.reduce((s, x) => s + Math.abs(x.gex), 0) || 1;
  const at = (p: number) => Math.abs(by.find((x) => x.strike === p)?.gex ?? 0) / gross;
  const raw: (RankedLevel | null)[] = [
    ctx.cw != null ? { kind: "Call wall (resistance)", price: ctx.cw, strength: clamp(at(ctx.cw) + 0.4, 0, 1) } : null,
    ctx.pw != null ? { kind: "Put wall (support)", price: ctx.pw, strength: clamp(at(ctx.pw) + 0.4, 0, 1) } : null,
    ctx.flip != null ? { kind: "Gamma flip (pivot)", price: ctx.flip, strength: 0.6 } : null,
    ctx.magnet != null ? { kind: "Gamma magnet (pin)", price: ctx.magnet, strength: clamp(at(ctx.magnet) + 0.5, 0, 1) } : null,
    ctx.front ? wrap("Max pain", maxPain(ctx.chain, ctx.front), 0.45) : null,
    wrap("Call OI wall", callOiWall(oi), 0.4),
    wrap("Put OI wall", putOiWall(oi), 0.4),
    ctx.em != null ? { kind: "Expected-move high", price: spot + ctx.em, strength: 0.35 } : null,
    ctx.em != null ? { kind: "Expected-move low", price: spot - ctx.em, strength: 0.35 } : null,
  ];
  const tol = spot * 0.0008;
  const out: RankedLevel[] = [];
  for (const l of raw) if (l && Number.isFinite(l.price) && !out.some((u) => Math.abs(u.price - l.price) <= tol)) out.push(l);
  return out.sort((a, b) => Math.abs(a.price - spot) - Math.abs(b.price - spot));
}
const wrap = (kind: string, price: number | null, strength: number): RankedLevel | null => (price != null ? { kind, price, strength } : null);

function buildTargets(spot: number | null, dirSign: number, em: number | null, levels: RankedLevel[]): { label: string; price: number; kind: string }[] {
  if (spot == null || dirSign === 0) return [];
  const ahead = levels.filter((l) => (dirSign > 0 ? l.price > spot : l.price < spot)).sort((a, b) => (dirSign > 0 ? a.price - b.price : b.price - a.price));
  const picks = ahead.slice(0, 3);
  while (picks.length < 3 && em) picks.push({ kind: `${picks.length + 1}× expected move`, price: spot + dirSign * em * (picks.length + 1), strength: 0.3 });
  return picks.map((l, i) => ({ label: `Target ${i + 1}`, price: Math.round(l.price * 100) / 100, kind: l.kind }));
}

function forecastTime(regime: string, strength: number, ivRegime: string): AnomalyIntel["timeForecast"] {
  // base distribution over horizons; long-γ mean-reverts fast, short-γ trends slower
  let w =
    regime === "long"
      ? { "5m": 0.12, "15m": 0.28, "30m": 0.26, "1h": 0.18, "4h": 0.11, "1d": 0.05 }
      : regime === "short"
        ? { "5m": 0.06, "15m": 0.16, "30m": 0.22, "1h": 0.26, "4h": 0.2, "1d": 0.1 }
        : { "5m": 0.1, "15m": 0.2, "30m": 0.24, "1h": 0.22, "4h": 0.15, "1d": 0.09 };
  if (ivRegime === "expansion") w = { ...w, "5m": w["5m"] + 0.06, "15m": w["15m"] + 0.04 };
  // higher strength → faster reaction (tilt mass earlier)
  const tilt = clamp(strength / 100, 0, 1) * 0.1;
  w = { ...w, "5m": w["5m"] + tilt, "15m": w["15m"] + tilt / 2, "1d": Math.max(0, w["1d"] - tilt) };
  const total = Object.values(w).reduce((s, x) => s + x, 0);
  const probs = Object.entries(w).map(([h, p]) => ({ h, p: Math.round((p / total) * 100) }));
  const win = probs.reduce((a, b) => (b.p > a.p ? b : a));
  const duration = regime === "long" ? "15–45 min (mean-reversion)" : regime === "short" ? "30 min–4 h (trend leg)" : "15 min–1 h";
  const conf = Math.round(clamp(0.4 + (strength / 100) * 0.4 + (regime !== "unknown" ? 0.15 : 0), 0, 1) * 100);
  return { window: win.h, probs, confidence: conf, duration };
}

function buildWhy(models: ModelVote[], regime: string, moveDir: number, ivRegime: string, relVol: number, dir: number, neutral: boolean): string[] {
  const out: string[] = [];
  const fired = models.filter((m) => m.vote >= 0.4);
  if (fired.length) out.push(`Triggered by ${fired.map((m) => m.name).join(", ")} (${fired.map((m) => m.detail).join("; ")}).`);
  else out.push("No detector strongly fired — within normal statistical bounds.");
  out.push(regime === "long" ? "Long-gamma regime: dealer hedging dampens moves → outsized moves tend to mean-revert." : regime === "short" ? "Short-gamma regime: dealer hedging amplifies moves → outsized moves tend to continue." : "Dealer-gamma regime unclear.");
  if (ivRegime !== "normal" && ivRegime !== "n/a") out.push(`Volatility ${ivRegime} — ${ivRegime === "expansion" ? "regime shift / breakout conditions" : "coiled; an expansion often follows"}.`);
  if (relVol >= 1.5) out.push(`Relative volume ${relVol.toFixed(2)}× — conviction/participation behind the move.`);
  if (!neutral) out.push(`Net read leans ${dir >= 0 ? "BULLISH" : "BEARISH"} after weighting regime, flip, put/call, vanna and Δ-exposure.`);
  return out;
}
function buildInstitutional(regime: string, dir: number, neutral: boolean, magnet: number | null, flip: number | null, so: { charm: number | null; vanna: number | null }): string {
  if (neutral) return "No clear institutional footprint — balanced positioning; wait for price to commit through the flip or a wall.";
  const side = dir >= 0 ? "bid / accumulation" : "offer / distribution";
  const mech =
    regime === "long"
      ? `dealers are long gamma and will fade extremes back toward the ${magnet != null ? f2(magnet) : "magnet"} — expect the move to stall/reverse`
      : `dealers are short gamma and must chase, so flows reinforce the move away from the ${flip != null ? f2(flip) : "flip"}`;
  const vn = so.vanna != null && so.vanna > 0 ? " Positive vanna means a vol decline adds a tailwind." : "";
  return `Likely ${side}: ${mech}.${vn}`;
}
