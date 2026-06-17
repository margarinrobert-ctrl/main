import type { OptionContract } from "./barchart/types";
import {
  atmIv,
  callOiWall,
  callResistance,
  expectedMove,
  expectedMove1D,
  gammaFlip,
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
  gex: number;
  dex: number;
}

function strikeStats(contracts: OptionContract[], strike: number | null, spot: number | null): StrikeStat {
  const r: StrikeStat = { oi: 0, vol: 0, gex: 0, dex: 0 };
  if (strike == null) return r;
  for (const c of contracts) {
    if (c.strike !== strike) continue;
    r.oi += c.openInterest ?? 0;
    r.vol += c.volume ?? 0;
    if (spot && c.openInterest != null) {
      if (c.gamma != null) r.gex += (c.type === "call" ? 1 : -1) * c.gamma * c.openInterest * 100 * spot * spot * 0.01;
      if (c.delta != null) r.dex += c.delta * c.openInterest * 100 * spot;
    }
  }
  return r;
}

function metaFull(contracts: OptionContract[], strike: number | null, spot: number | null): string {
  const s = strikeStats(contracts, strike, spot);
  return `OI ${kfmt(s.oi)} | V ${kfmt(s.vol)} | GEX ${usd(s.gex)} | DEX ${usd(s.dex)}`;
}

function nearestExpiration(chain: OptionContract[]): string | null {
  const exps = [...new Set(chain.map((c) => c.expiration))];
  const withDte = exps
    .map((e) => ({ e, dte: chain.find((c) => c.expiration === e)?.dte ?? 9999 }))
    .filter((x) => x.dte >= 0)
    .sort((a, b) => a.dte - b.dte);
  return withDte[0]?.e ?? exps[0] ?? null;
}

export interface PineResult {
  code: string;
  expiration: string | null;
  callRes: number | null;
  putSup: number | null;
  hvl: number | null;
  strikes: number;
}

/**
 * Generate a TradingView Pine v6 indicator with named GEX levels (MenthorQ-style), each label
 * annotated with OI / Volume / GEX(γ$) / DEX(Δ$) at that strike. Values are a baked snapshot.
 */
export function buildGexPine(
  symbol: string,
  chain: OptionContract[],
  spot: number | null,
  ladderN = 10,
  targetExp?: string | null,
): PineResult {
  const exp = targetExp && targetExp !== "ALL" && chain.some((c) => c.expiration === targetExp) ? targetExp : nearestExpiration(chain);
  const sub = exp ? chain.filter((c) => c.expiration === exp) : chain;
  const byAll = gexByStrike(chain, spot);
  const by0 = gexByStrike(sub, spot);

  // Side-aware so resistance sits ABOVE spot and support BELOW it (they can't collapse onto the
  // same ATM strike the way raw max-gamma walls do).
  const callRes = callResistance(byAll, spot);
  const putSup = putSupport(byAll, spot);
  const hvl = gammaFlip(byAll);
  const callRes0 = callResistance(by0, spot);
  const putSup0 = putSupport(by0, spot);
  const mp = exp ? maxPain(chain, exp) : null;
  const oi = oiByStrike(chain);
  const callOi = callOiWall(oi);
  const putOi = putOiWall(oi);
  // True 1-day (1σ) range from front-expiration ATM IV — NOT the to-expiry straddle. Fall back to
  // the straddle only if IV is unavailable so the lines still render.
  const iv0 = exp ? atmIv(chain, spot, exp) : null;
  const em1 = expectedMove1D(spot, iv0) ?? (exp ? expectedMove(chain, spot, exp) : null);

  const s = spot ?? byAll[Math.floor(byAll.length / 2)]?.strike ?? 0;
  const dmax = em1 ? s + em1.abs : s;
  const dmin = em1 ? s - em1.abs : s;

  const ladder = byAll
    .filter((x) => x.gex !== 0)
    .sort((a, b) => Math.abs(b.gex) - Math.abs(a.gex))
    .slice(0, ladderN);
  const gexk = ladder.length ? ladder.map((x) => fmt(x.strike)).join(", ") : fmt(s);
  const gexLblStr = ladder.length
    ? ladder
        .map((x, i) => {
          const st = strikeStats(chain, x.strike, spot);
          return JSON.stringify(`GEX ${i + 1} @${x.strike}  OI ${kfmt(st.oi)} | V ${kfmt(st.vol)} | ${usd(x.gex)}`);
        })
        .join(", ")
    : JSON.stringify("GEX 1");

  const v = (x: number | null) => fmt(x ?? s);
  const crMeta = metaFull(chain, callRes, spot);
  const psMeta = metaFull(chain, putSup, spot);
  const cr0Meta = metaFull(sub, callRes0, spot);
  const ps0Meta = metaFull(sub, putSup0, spot);
  const mpMeta = metaFull(chain, mp, spot);
  const coiMeta = metaFull(chain, callOi, spot);
  const poiMeta = metaFull(chain, putOi, spot);
  const asOf = new Date().toISOString().slice(0, 16).replace("T", " ");

  const code = `//@version=6
// OptionsFlow — GEX levels for ${symbol}  (0DTE/front exp ${exp ?? "n/a"}, generated ${asOf} UTC)
// Paste into TradingView: Pine Editor -> paste -> Save -> Add to chart. Re-generate to refresh.
indicator("OptionsFlow GEX • ${symbol}", overlay = true, max_lines_count = 300, max_labels_count = 300)

show0dte  = input.bool(true, "Show 0DTE levels")
showGex   = input.bool(true, "Show GEX 1..N ladder")
showRange = input.bool(true, "Show 1D Max/Min")
showMag   = input.bool(true, "Show Max Pain & OI walls")
lw        = input.int(2, "Key line width", minval = 1, maxval = 5)
labelSize = input.string("large", "Label size", options = ["small", "normal", "large", "huge"])
sz = labelSize == "huge" ? size.huge : labelSize == "large" ? size.large : labelSize == "normal" ? size.normal : size.small
showVwap = input.bool(true, "Show session VWAP")
showOR   = input.bool(true, "Show opening range (intraday)")
orMin    = input.int(30, "Opening-range minutes", minval = 1, maxval = 240)

callRes  = input.float(${v(callRes)}, "Call Resistance")
putSup   = input.float(${v(putSup)}, "Put Support")
hvl      = input.float(${v(hvl)}, "HVL (gamma flip)")
callRes0 = input.float(${v(callRes0)}, "Call Resistance 0DTE / Gamma Wall 0DTE")
putSup0  = input.float(${v(putSup0)}, "Put Support 0DTE / HVL 0DTE")
oneDMax  = input.float(${fmt(dmax)}, "1D Max")
oneDMin  = input.float(${fmt(dmin)}, "1D Min")
maxPainL = input.float(${fmt(mp ?? s)}, "Max Pain")
callOiL  = input.float(${fmt(callOi ?? s)}, "Call OI wall")
putOiL   = input.float(${fmt(putOi ?? s)}, "Put OI wall")

var float[]  gexK   = array.from(${gexk})
var string[] gexLbl = array.from(${gexLblStr})

var line[]  _ln = array.new_line()
var label[] _lb = array.new_label()

clearAll() =>
    while array.size(_ln) > 0
        line.delete(array.pop(_ln))
    while array.size(_lb) > 0
        label.delete(array.pop(_lb))

addLevel(price, col, txt, w, st) =>
    array.push(_ln, line.new(bar_index, price, bar_index + 1, price, color = col, width = w, extend = extend.both, style = st))
    array.push(_lb, label.new(bar_index, price, txt, style = label.style_label_left, textcolor = col, color = color.new(color.black, 100), size = sz))

if barstate.islast
    clearAll()
    if showGex
        for i = 0 to array.size(gexK) - 1
            addLevel(array.get(gexK, i), color.teal, array.get(gexLbl, i), 1, line.style_solid)
    if showRange
        addLevel(oneDMin, color.orange, "1D Min " + str.tostring(oneDMin), 1, line.style_dotted)
        addLevel(oneDMax, color.orange, "1D Max " + str.tostring(oneDMax), 1, line.style_dotted)
    if showMag
        addLevel(maxPainL, color.yellow, "Max Pain " + str.tostring(maxPainL) + "  ${mpMeta}", 1, line.style_dotted)
        addLevel(callOiL,  color.olive,  "Call OI " + str.tostring(callOiL) + "  ${coiMeta}", 1, line.style_dotted)
        addLevel(putOiL,   color.purple, "Put OI " + str.tostring(putOiL) + "  ${poiMeta}", 1, line.style_dotted)
    if show0dte
        addLevel(callRes0, color.red,  "Call Resistance 0DTE / Gamma Wall 0DTE " + str.tostring(callRes0) + "  ${cr0Meta}", lw, line.style_dashed)
        addLevel(putSup0,  color.blue, "Put Support 0DTE / HVL 0DTE " + str.tostring(putSup0) + "  ${ps0Meta}", lw, line.style_dashed)
    addLevel(putSup,  color.green, "Put Support " + str.tostring(putSup) + "  ${psMeta}", lw, line.style_solid)
    addLevel(hvl,     color.blue,  "HVL " + str.tostring(hvl), lw, line.style_solid)
    addLevel(callRes, color.red,   "Call Resistance " + str.tostring(callRes) + "  ${crMeta}", lw, line.style_solid)

// ── Intraday confluence overlays (computed live by TradingView) ──
// A GEX level that lines up with VWAP or the opening range is higher-conviction.
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
`;

  return { code, expiration: exp, callRes, putSup, hvl, strikes: ladder.length };
}
