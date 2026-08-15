import type { OptionContract } from "./barchart/types";
import { dayBands } from "./quant/daybands";
import {
  atmIv,
  callOiWall,
  callResistance,
  deltaCallWall,
  deltaPutWall,
  dexByStrike,
  expectedMove,
  gammaFlipNearest,
  gexByStrike,
  maxPain,
  oiByStrike,
  putOiWall,
  putSupport,
} from "./flow/analytics";

function fmt(n: number): string {
  // Always emit a float literal (with a decimal point) so Pine infers array<float>, not array<int>.
  const s = (Math.round(n * 100) / 100).toString();
  return s.includes(".") ? s : `${s}.0`;
}

// Human-readable price for the visible label (whole numbers for index/futures-scale levels).
function fmtNice(n: number): string {
  return Math.abs(n) >= 1000 ? String(Math.round(n)) : String(Math.round(n * 100) / 100);
}

function kfmt(n: number): string {
  const a = Math.abs(n);
  if (a >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)}k`;
  return String(Math.round(n));
}

// ASCII-only USD formatter (avoid unicode in generated Pine source).
function usd(n: number): string {
  const a = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(0)}K`;
  return `${sign}$${Math.round(a)}`;
}

interface StrikeStat {
  oi: number;
  vol: number;
  gex: number; // net dealer gamma-$ at the strike (calls +, puts −)
  callGex: number;
  putGex: number; // ≤ 0 in the dealer convention
  dex: number; // net delta-$ (signed by delta)
  callDex: number;
  putDex: number; // ≤ 0
}

function strikeStats(contracts: OptionContract[], strike: number | null, spot: number | null): StrikeStat {
  const r: StrikeStat = { oi: 0, vol: 0, gex: 0, callGex: 0, putGex: 0, dex: 0, callDex: 0, putDex: 0 };
  if (strike == null) return r;
  for (const c of contracts) {
    if (c.strike !== strike) continue;
    r.oi += c.openInterest ?? 0;
    r.vol += c.volume ?? 0;
    if (spot && c.openInterest != null) {
      if (c.gamma != null) {
        const g = (c.type === "call" ? 1 : -1) * c.gamma * c.openInterest * 100 * spot * spot * 0.01;
        r.gex += g;
        if (c.type === "call") r.callGex += g;
        else r.putGex += g;
      }
      if (c.delta != null) {
        const d = c.delta * c.openInterest * 100 * spot;
        r.dex += d;
        if (c.type === "call") r.callDex += d;
        else r.putDex += d;
      }
    }
  }
  return r;
}

// A level named for one SIDE of the book must report that side's exposure, not the strike's net —
// a "Put Support" showing the (call-dominated) net GEX as a big positive number misreads the level.
type MetaFocus = "call-gamma" | "put-gamma" | "call-delta" | "put-delta" | "net";

function meta(contracts: OptionContract[], strike: number | null, spot: number | null, focus: MetaFocus = "net"): string {
  const s = strikeStats(contracts, strike, spot);
  const base = `OI ${kfmt(s.oi)} | V ${kfmt(s.vol)}`;
  switch (focus) {
    case "call-gamma":
      return `${base} | Call GEX ${usd(s.callGex)} (net ${usd(s.gex)}) | DEX ${usd(s.dex)}`;
    case "put-gamma":
      return `${base} | Put GEX ${usd(s.putGex)} (net ${usd(s.gex)}) | DEX ${usd(s.dex)}`;
    case "call-delta":
      return `${base} | Call DEX ${usd(s.callDex)} (net ${usd(s.dex)}) | GEX ${usd(s.gex)}`;
    case "put-delta":
      return `${base} | Put DEX ${usd(s.putDex)} (net ${usd(s.dex)}) | GEX ${usd(s.gex)}`;
    default:
      return `${base} | GEX ${usd(s.gex)} | DEX ${usd(s.dex)}`;
  }
}

function nearestExpiration(chain: OptionContract[]): string | null {
  const exps = [...new Set(chain.map((c) => c.expiration))];
  const withDte = exps
    .map((e) => ({ e, dte: chain.find((c) => c.expiration === e)?.dte ?? 9999 }))
    .filter((x) => x.dte >= 0)
    .sort((a, b) => a.dte - b.dte);
  return withDte[0]?.e ?? exps[0] ?? null;
}

interface Lvl {
  price: number;
  short: string; // visible text
  detail: string; // hover tooltip
  color: string; // Pine color token
  style: string; // Pine line.style_* token
  width: number;
}

export interface PineResult {
  code: string;
  expiration: string | null;
  callRes: number | null;
  putSup: number | null;
  hvl: number | null;
  deltaCallWall: number | null;
  deltaPutWall: number | null;
  strikes: number;
}

/**
 * Generate a TradingView Pine v6 indicator with named GEX levels (MenthorQ-style). Levels are a
 * baked snapshot. Labels are short (full OI/Vol/GEX/DEX detail is on hover) and the
 * indicator auto-staggers labels that sit close together so they never overlap.
 */
export function buildGexPine(
  symbol: string,
  chain: OptionContract[],
  spot: number | null,
  ladderN = 10,
  targetExp?: string | null,
  feedAsOf?: string | null,
): PineResult {
  const exp = targetExp && targetExp !== "ALL" && chain.some((c) => c.expiration === targetExp) ? targetExp : nearestExpiration(chain);
  const sub = exp ? chain.filter((c) => c.expiration === exp) : chain;
  const byAll = gexByStrike(chain, spot);
  const by0 = gexByStrike(sub, spot);

  const callRes = callResistance(byAll, spot);
  const putSup = putSupport(byAll, spot);
  const hvl = gammaFlipNearest(byAll, spot);
  const callRes0 = callResistance(by0, spot);
  const putSup0 = putSupport(by0, spot);
  const mp = exp ? maxPain(chain, exp) : null;
  // OI walls restricted to a tradeable moneyness band: raw max OI over the whole chain routinely lands
  // on far-dated tail hedges 30%+ away from spot (LEAP puts), which is meaningless as an intraday level.
  const OI_BAND = 0.2;
  const oi = oiByStrike(chain);
  const oiBand = spot != null ? oi.filter((x) => Math.abs(x.strike / spot - 1) <= OI_BAND) : oi;
  const callOi = callOiWall(oiBand.length ? oiBand : oi);
  const putOi = putOiWall(oiBand.length ? oiBand : oi);
  // Delta walls get the same band: far-dated tail strikes carry so much OI that even a 0.05-delta
  // LEAP can out-dollar every tradeable strike.
  const dby = dexByStrike(chain, spot);
  const dbyBand = spot != null ? dby.filter((x) => Math.abs(x.strike / spot - 1) <= OI_BAND) : dby;
  const dCallWall = deltaCallWall(dbyBand.length ? dbyBand : dby, spot);
  const dPutWall = deltaPutWall(dbyBand.length ? dbyBand : dby, spot);
  const iv0 = exp ? atmIv(chain, spot, exp) : null;
  // Day bands from ONE sigma. The ATM straddle is E|move| = 0.798·sigma (a ~57.5% band), NOT 1 sigma —
  // dayBands() converts it (x sqrt(pi/2)) so the straddle path and the IV path mean the same thing.
  const straddle = exp ? (expectedMove(chain, spot, exp)?.abs ?? null) : null;
  const bands = dayBands(spot, straddle, iv0);
  const dteOf = sub.find((c) => c.dte != null)?.dte ?? null;
  const dteLabel = dteOf == null ? "" : dteOf <= 0 ? "0DTE" : `${dteOf}d`;

  const s = spot ?? byAll[Math.floor(byAll.length / 2)]?.strike ?? 0;

  const ladder = byAll
    .filter((x) => x.gex !== 0)
    .sort((a, b) => Math.abs(b.gex) - Math.abs(a.gex))
    .slice(0, ladderN);

  const hvl0 = gammaFlipNearest(by0, spot);

  const lvls: Lvl[] = [];
  // Every level is drawn as its OWN line + label — never merged. Labels that sit close together get
  // staggered horizontally (in the indicator) so all ~20 stay readable. Visible label is the NAME;
  // the indicator appends the actual on-chart price (after any basis shift).
  const add = (price: number | null, name: string, color: string, style: string, width: number, detail: string) => {
    if (price == null || !Number.isFinite(price)) return;
    lvls.push({ price, short: name, detail: `${detail} · strike ${fmtNice(price)}`, color, style, width });
  };

  // Front-expiry levels carry the REAL tenor tag ("0DTE" only when the front actually expires today).
  const frontTag = dteLabel || "front";
  add(callRes, "Call Resistance", "color.red", "line.style_solid", 2, `Call Resistance (largest CALL gamma above spot, ALL expirations) — dealers long these calls sell into strength as price approaches: rallies tend to stall here - ${meta(chain, callRes, spot, "call-gamma")}`);
  add(putSup, "Put Support", "color.green", "line.style_solid", 2, `Put Support (largest PUT gamma below spot, ALL expirations) — hedging of dealer short puts buys into weakness as price approaches: selloffs tend to slow here - ${meta(chain, putSup, spot, "put-gamma")}`);
  add(hvl, "HVL", "color.blue", "line.style_solid", 2, "HVL / gamma flip (net dealer gamma crosses zero, ALL expirations). ABOVE = long-gamma regime: hedging dampens moves (fade extremes). BELOW = short-gamma: hedging amplifies moves (respect momentum, expect expansion).");
  add(callRes0, `Call Res ${frontTag}`, "color.red", "line.style_dashed", 2, `Call Resistance / Gamma Wall for the ${frontTag} expiry only - ${meta(sub, callRes0, spot, "call-gamma")}`);
  add(putSup0, `Put Sup ${frontTag}`, "color.green", "line.style_dashed", 2, `Put Support for the ${frontTag} expiry only - ${meta(sub, putSup0, spot, "put-gamma")}`);
  add(hvl0, `HVL ${frontTag}`, "color.blue", "line.style_dashed", 2, `HVL / gamma flip for the ${frontTag} expiry only`);

  // ── Standard-deviation day bands (0DTE session range) ──────────────────────
  // Every band comes from the same sigma, and each says the coverage it ACTUALLY has. A raw straddle
  // band would be +/-0.798 sigma (~57.5%), which is why it is converted rather than drawn as "1 sigma".
  if (bands) {
    const srcNote = bands.source === "straddle" ? "sigma implied by the ATM straddle (converted: straddle = 0.798*sigma)" : "sigma from ATM implied vol / sqrt(252)";
    const dayTag = dteOf != null && dteOf <= 0 ? "today (0DTE)" : `the ${dteLabel || "front"} expiry`;
    const sd1 = bands.bands.find((b) => b.key === "sd1");
    const p618 = bands.bands.find((b) => b.key === "p618");
    const sd2 = bands.bands.find((b) => b.key === "sd2");
    add(bands.mean, "Day Mean", "color.white", "line.style_dashed", 2, `Day MEAN for ${dayTag} (= spot when generated; with zero drift the expected close IS spot, so this doubles as the spot anchor)`.replace(/\s+$/, "") + ` — centre of the terminal distribution for ${dayTag} — the centre of the terminal distribution. With no drift the expected close IS spot; this is the distribution's centre, not a target. ${srcNote}: 1 sigma = ${fmtNice(bands.sigmaAbs)} (${(bands.sigmaPct * 100).toFixed(2)}%)`);
    if (sd1) {
      add(sd1.hi, "Day Max 1SD", "color.orange", "line.style_solid", 1, `Day MAXIMUM for ${dayTag} — +1 sigma. The close finishes inside +/-1 sigma about ${(sd1.coverage * 100).toFixed(1)}% of the time (so ~16% of days close ABOVE this). ${srcNote}`);
      add(sd1.lo, "Day Min 1SD", "color.orange", "line.style_solid", 1, `Day MINIMUM for ${dayTag} — -1 sigma. The close finishes inside +/-1 sigma about ${(sd1.coverage * 100).toFixed(1)}% of the time (so ~16% of days close BELOW this). ${srcNote}`);
    }
    if (p618) {
      add(p618.hi, "61.8% Hi", "color.aqua", "line.style_dotted", 1, `Upper 61.8% band (z = 0.874) — the close lands inside this band about ${(p618.coverage * 100).toFixed(1)}% of the time. Tighter than 1 sigma by construction.`);
      add(p618.lo, "61.8% Lo", "color.aqua", "line.style_dotted", 1, `Lower 61.8% band (z = 0.874) — the close lands inside this band about ${(p618.coverage * 100).toFixed(1)}% of the time.`);
    }
    if (sd2) {
      add(sd2.hi, "Day Max 2SD", "color.gray", "line.style_dotted", 1, `+2 sigma tail envelope — only ~${(((1 - sd2.coverage) / 2) * 100).toFixed(1)}% of closes finish above this.`);
      add(sd2.lo, "Day Min 2SD", "color.gray", "line.style_dotted", 1, `-2 sigma tail envelope — only ~${(((1 - sd2.coverage) / 2) * 100).toFixed(1)}% of closes finish below this.`);
    }
  }

  // Delta walls — dealer hedgeable-delta resistance/support. Ranked here (ABOVE Max Pain / OI walls) so they
  // are never dropped by the one-level-per-price dedup when a raw-OI wall happens to sit on the same strike.
  add(dCallWall, "Delta Resistance", "color.maroon", "line.style_solid", 2, `Delta Resistance Wall (heaviest CALL delta-exposure above spot, ALL expirations = dealer hedgeable-delta resistance) - ${meta(chain, dCallWall, spot, "call-delta")}`);
  add(dPutWall, "Delta Support", "color.lime", "line.style_solid", 2, `Delta Support Wall (heaviest PUT delta-exposure below spot, ALL expirations = dealer hedgeable-delta support) - ${meta(chain, dPutWall, spot, "put-delta")}`);
  add(mp, "Max Pain", "color.yellow", "line.style_dotted", 1, `Max Pain ${exp ?? ""} (strike minimizing option holders' payout at that expiry; weak pin candidate) - ${meta(chain, mp, spot)}`);
  add(callOi, "Call OI", "color.olive", "line.style_dotted", 1, `Call OI wall (max call open interest within 20% of spot; OI is prior-day T+1) - ${meta(chain, callOi, spot, "call-gamma")}`);
  add(putOi, "Put OI", "color.purple", "line.style_dotted", 1, `Put OI wall (max put open interest within 20% of spot; OI is prior-day T+1) - ${meta(chain, putOi, spot, "put-gamma")}`);
  if (!bands) add(spot, "Spot", "color.gray", "line.style_dotted", 1, `Underlying spot when generated — levels are anchored here; the chart's current price may have moved since.`);
  ladder.forEach((x, i) => {
    const st = strikeStats(chain, x.strike, spot);
    add(x.strike, `GEX ${i + 1}`, "color.teal", "line.style_solid", 1, `GEX ${i + 1} @${fmtNice(x.strike)} — rank-${i + 1} net dealer gamma (ALL exp): a hedging magnet/pin candidate while gamma is positive - OI ${kfmt(st.oi)} | V ${kfmt(st.vol)} | net GEX ${usd(x.gex)}`);
  });

  if (!lvls.length) add(s, "Spot", "color.gray", "line.style_dotted", 1, "spot");

  // ONE level per price: keep the highest-priority (first-added) level at each strike and drop any
  // coincident duplicates, so nothing ever stacks on the same line. Renumber surviving GEX nodes.
  const lv: typeof lvls = [];
  for (const l of lvls) {
    const tol = Math.max(0.01, (spot ?? l.price) * 0.0006);
    if (lv.some((u) => Math.abs(u.price - l.price) <= tol)) continue;
    lv.push(l);
  }
  let gn = 0;
  for (const l of lv) {
    if (/^GEX /.test(l.short)) {
      const n = ++gn;
      l.short = `GEX ${n}`;
      l.detail = l.detail.replace(/^GEX \d+/, `GEX ${n}`);
    }
  }
  lv.sort((a, b) => a.price - b.price);

  const P = lv.map((l) => fmt(l.price)).join(", ");
  const T = lv.map((l) => JSON.stringify(l.short)).join(", ");
  const D = lv.map((l) => JSON.stringify(l.detail)).join(", ");
  const C = lv.map((l) => l.color).join(", ");
  const LS = lv.map((l) => l.style).join(", ");
  const W = lv.map((l) => String(l.width)).join(", ");

  const asOf = new Date().toISOString().slice(0, 16).replace("T", " ");
  const alertInputs = [
    callRes != null ? `kCallRes = input.float(${fmt(callRes)}, "Alert: Call Resistance")` : "",
    putSup != null ? `kPutSup  = input.float(${fmt(putSup)}, "Alert: Put Support")` : "",
    hvl != null ? `kHvl     = input.float(${fmt(hvl)}, "Alert: HVL (gamma flip)")` : "",
    dCallWall != null ? `kDCall   = input.float(${fmt(dCallWall)}, "Alert: Delta Resistance")` : "",
    dPutWall != null ? `kDPut    = input.float(${fmt(dPutWall)}, "Alert: Delta Support")` : "",
  ]
    .filter(Boolean)
    .join("\n");
  const alertLines = [
    callRes != null ? `alertcondition(ta.cross(close, kCallRes * scale), "Price ↔ Call Resistance", "{{ticker}} tagged Call Resistance")` : "",
    putSup != null ? `alertcondition(ta.cross(close, kPutSup * scale), "Price ↔ Put Support", "{{ticker}} tagged Put Support")` : "",
    hvl != null ? `alertcondition(ta.cross(close, kHvl * scale), "Price ↔ HVL", "{{ticker}} crossed HVL / gamma flip")` : "",
    dCallWall != null ? `alertcondition(ta.cross(close, kDCall * scale), "Price ↔ Delta Resistance", "{{ticker}} tagged Delta Resistance Wall")` : "",
    dPutWall != null ? `alertcondition(ta.cross(close, kDPut * scale), "Price ↔ Delta Support", "{{ticker}} tagged Delta Support Wall")` : "",
  ]
    .filter(Boolean)
    .join("\n");

  const convertNote = `\n// CONVERT TO ES / NQ / RTY: to overlay these ${symbol} levels on a futures chart, leave "Convert levels\n// to this chart" on Auto. It reads the LIVE ${symbol} price (request.security on the "Source symbol" input)\n// and this chart's price at the SAME instant, then scales every level by their exact ratio — so the\n// current index divisor AND futures basis are always baked in (QQQ->NQ ~41x, SPY->ES ~10x, IWM->RTY ~10x).\n// The ratio is LOCKED on the last closed bar so levels never move as price ticks; on the ${symbol} chart it is 1.0.`;

  const code = `//@version=6
// OptionsFlow — GEX levels for ${symbol}
// SCOPE: walls/HVL/delta walls span ALL expirations; "${dteLabel || "front"}"-tagged variants, Max Pain and the
// SD day bands are for the front/target expiry ${exp ?? "n/a"} only. OI is prior-day (T+1).
// DAY BANDS: Day Mean / Day Max-Min 1SD (68.3%) / 61.8% band / 2SD envelope, all from ONE sigma. Note an
// ATM straddle is E|move| = 0.798*sigma (~57.5% band), so it is CONVERTED to a true sigma, never drawn as 1SD.
// Built for the ${symbol} chart (spot ~${spot != null ? fmtNice(spot) : "n/a"}). To overlay on ES/NQ, use the
// "Convert levels to this chart" input below (Auto = accurate live-ratio scaling).
// STATIC SNAPSHOT: a Pine script cannot fetch data, so this does NOT auto-update.
// Generated ${asOf} UTC — RE-GENERATE & re-paste for fresh levels.
// Short labels show the on-chart price; hover for full OI/Volume/GEX/DEX. Close levels auto-stagger.${convertNote}
indicator("OptionsFlow GEX • ${symbol}", overlay = true, max_lines_count = 200, max_labels_count = 200)

showMeta  = input.bool(true, "Detail on hover (tooltip)")
laneStep  = input.int(14, "Stagger close labels (bars)", minval = 0, maxval = 80)
convertMode = input.string("Auto (match chart)", "Convert levels to this chart", options = ["Off", "Auto (match chart)"], tooltip = "Auto: rescale these ${symbol} levels onto whatever chart you are on (e.g. NQ / ES / RTY futures) using the LIVE price ratio. Off: draw the exact ${symbol} strikes (use on the ${symbol} chart).")
srcSym      = input.symbol("${symbol}", "Source symbol (these levels are priced in it)", tooltip = "The symbol these levels came from. Auto reads its live price via request.security to build the exact ratio vs this chart. Typical maps: QQQ->NQ, SPY->ES, IWM->RTY, SPX->ES, NDX->NQ.")
manualMult  = input.float(1.0, "Manual x multiplier (fine-tune)", minval = 0.0001, step = 0.01)
snapSpot    = input.float(${fmt(spot ?? 0)}, "Snapshot ${symbol} spot (fallback if source unavailable)")
labelSize = input.string("normal", "Label size", options = ["small", "normal", "large", "huge"])
sz = labelSize == "huge" ? size.huge : labelSize == "large" ? size.large : labelSize == "normal" ? size.normal : size.small
showVwap = input.bool(true, "Show session VWAP")
showOR   = input.bool(true, "Show opening range (intraday)")
orMin    = input.int(30, "Opening-range minutes", minval = 1, maxval = 240)
${hvl != null ? 'showRegime = input.bool(true, "Shade gamma regime (vs HVL)")' : ""}
${alertInputs}

// ── Baked level snapshot (price / label / detail / color / style / width) ──
var float[]  P  = array.from(${P})
var string[] T  = array.from(${T})
var string[] D  = array.from(${D})
var color[]  C  = array.from(${C})
var string[] LS = array.from(${LS})
var int[]    W  = array.from(${W})

var line[]  _ln = array.new_line()
var label[] _lb = array.new_label()

clearAll() =>
    while array.size(_ln) > 0
        line.delete(array.pop(_ln))
    while array.size(_lb) > 0
        label.delete(array.pop(_lb))

// Convert ${symbol} levels onto whatever chart this is applied to. "Auto (match chart)" scales every level
// by the ratio close / srcLive — this chart's price and the SOURCE symbol's price read at the SAME bar via
// request.security — so the current index divisor AND futures basis are exact (QQQ->NQ ~41x, SPY->ES ~10x).
// The ratio is LOCKED once, on the last CLOSED bar before realtime (barstate.islastconfirmedhistory fires a
// single time on a confirmed bar and never on realtime ticks), so it is committed and never recomputed —
// converted levels stay pinned exactly where the data says while price moves. On the ${symbol} chart the
// ratio is 1.0 (exact strikes). Falls back to the snapshot-spot ratio if the source symbol can't be read.
srcLive = request.security(srcSym, timeframe.period, close)
var float frozenScale = na
if na(frozenScale) and (barstate.islastconfirmedhistory or barstate.islast)
    liveRatio = not na(srcLive) and srcLive > 0 ? close / srcLive : (snapSpot > 0 ? close / snapSpot : 1.0)
    frozenScale := convertMode == "Auto (match chart)" ? liveRatio : 1.0
scale = nz(frozenScale, 1.0) * manualMult
${
  hvl != null
    ? `
// ── Gamma regime (the core GEX read) ─────────────────────────────────────────
// Above the HVL dealers are net LONG gamma: their hedging sells strength / buys weakness, dampening
// moves (mean-reversion conditions). Below it they are net SHORT gamma: hedging chases price and
// AMPLIFIES moves (trend / expansion conditions). Shaded live from the chart's own price vs the level.
regimeLong = close >= kHvl * scale
bgcolor(showRegime ? (regimeLong ? color.new(color.teal, 96) : color.new(color.red, 95)) : na, title = "Gamma regime")
var table _rt = table.new(position.top_right, 1, 1)
`
    : ""
}
// ta.* series must be computed on every bar (not inside a conditional) for series consistency.
rngHi = ta.highest(high, 120)
rngLo = ta.lowest(low, 120)

if barstate.islast
    clearAll()
${
  hvl != null
    ? `    table.cell(_rt, 0, 0, regimeLong ? "LONG GAMMA - dealers dampen (fade extremes)" : "SHORT GAMMA - dealers amplify (respect momentum)", text_color = regimeLong ? color.teal : color.red, text_size = size.small, bgcolor = color.new(color.black, 35))
`
    : ""
}    rng = rngHi - rngLo
    minGap = math.max(na(rng) or rng <= 0 ? close * 0.012 : rng * 0.02, close * 0.0015)
    float prevP = na
    int lane = 0
    base = bar_index
    for i = 0 to array.size(P) - 1
        p = array.get(P, i) * scale
        lane := not na(prevP) and (p - prevP) < minGap ? lane + 1 : 0
        x = base + 1 + lane * laneStep
        col = array.get(C, i)
        txt = array.get(T, i) + " " + str.tostring(math.round(p * 100) / 100)
        array.push(_ln, line.new(base, p, x, p, color = col, width = array.get(W, i), extend = extend.both, style = array.get(LS, i)))
        array.push(_lb, label.new(x, p, txt, style = label.style_label_left, textcolor = col, color = color.new(color.black, 100), size = sz, tooltip = showMeta ? array.get(D, i) : ""))
        prevP := p

// ── Intraday confluence overlays (computed live by TradingView) ──
// A level that lines up with VWAP or the opening range is higher-conviction.
plot(showVwap ? ta.vwap : na, "VWAP", color = color.new(color.fuchsia, 0), linewidth = 2)
newDay = ta.change(time("D")) != 0
var float orH = na
var float orL = na
var int orStart = na
if newDay
    orH := high
    orL := low
    orStart := time
if not na(orStart) and time - orStart <= orMin * 60 * 1000
    orH := math.max(orH, high)
    orL := math.min(orL, low)
plot(showOR ? orH : na, "OR High", color = color.new(color.aqua, 0), style = plot.style_stepline)
plot(showOR ? orL : na, "OR Low", color = color.new(color.aqua, 0), style = plot.style_stepline)

// ── Alerts: get pinged when price tags a dealer level (set via TradingView's alert dialog) ──
${alertLines}
`;

  return { code, expiration: exp, callRes, putSup, hvl, deltaCallWall: dCallWall, deltaPutWall: dPutWall, strikes: lv.length };
}
