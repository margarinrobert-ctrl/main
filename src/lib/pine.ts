import type { OptionContract } from "./barchart/types";
import { callWall, gammaFlip, gexByStrike, putWall } from "./flow/analytics";

function fmt(n: number): string {
  // Always emit a float literal (with a decimal point) so Pine infers array<float>, not array<int>.
  const s = (Math.round(n * 100) / 100).toString();
  return s.includes(".") ? s : `${s}.0`;
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
  flip: number | null;
  callWall: number | null;
  putWall: number | null;
  strikes: number;
}

/**
 * Generate a TradingView Pine v5 indicator that draws the GEX levels (gamma flip, call/put
 * walls, spot, and a per-strike GEX ladder) for the nearest (0DTE/front) expiration.
 * Values are baked in — re-generate from the site to refresh.
 */
export function buildGexPine(symbol: string, chain: OptionContract[], spot: number | null, maxStrikes = 16): PineResult {
  const exp = nearestExpiration(chain);
  const sub = exp ? chain.filter((c) => c.expiration === exp) : chain;
  const by = gexByStrike(sub, spot);
  const flip = gammaFlip(by);
  const cw = callWall(by);
  const pw = putWall(by);

  const top = by
    .filter((x) => x.gex !== 0)
    .sort((a, b) => Math.abs(b.gex) - Math.abs(a.gex))
    .slice(0, maxStrikes)
    .sort((a, b) => a.strike - b.strike);

  const s = spot ?? top[Math.floor(top.length / 2)]?.strike ?? 0;
  const ks = top.length ? top.map((x) => fmt(x.strike)).join(", ") : fmt(s);
  const gs = top.length ? top.map((x) => fmt(Math.round(x.gex))).join(", ") : "0.0";
  const asOf = new Date().toISOString().slice(0, 16).replace("T", " ");

  const code = `//@version=6
// OptionsFlow — GEX levels for ${symbol}  (exp ${exp ?? "n/a"}, generated ${asOf} UTC)
// Paste into TradingView: Pine Editor -> paste -> Save -> Add to chart.
// Levels are a snapshot; re-generate from the site to refresh.
indicator("OptionsFlow GEX • ${symbol}", overlay = true, max_lines_count = 200, max_labels_count = 200)

showLadder = input.bool(true, "Show per-strike GEX ladder")
maxStrikes = input.int(${Math.min(top.length || 1, maxStrikes)}, "Max strikes", minval = 1, maxval = 40)
lw         = input.int(2, "Key line width", minval = 1, maxval = 5)

spot  = input.float(${fmt(s)}, "S • Spot")
gflip = input.float(${flip != null ? fmt(flip) : fmt(s)}, "G • Gamma flip")
cwall = input.float(${cw != null ? fmt(cw) : fmt(s)}, "C • Call wall")
pwall = input.float(${pw != null ? fmt(pw) : fmt(s)}, "P • Put wall")

var float[] ks = array.from(${ks})
var float[] gs = array.from(${gs})

var line[]  _ln = array.new_line()
var label[] _lb = array.new_label()

clearAll() =>
    while array.size(_ln) > 0
        line.delete(array.pop(_ln))
    while array.size(_lb) > 0
        label.delete(array.pop(_lb))

addLevel(price, col, txt, w) =>
    array.push(_ln, line.new(bar_index, price, bar_index + 1, price, color = col, width = w, extend = extend.both))
    array.push(_lb, label.new(bar_index, price, txt, style = label.style_label_left, textcolor = col, color = color.new(color.gray, 90), size = size.small))

if barstate.islast
    clearAll()
    if showLadder
        n = math.min(array.size(ks), maxStrikes)
        if n > 0
            for i = 0 to n - 1
                k = array.get(ks, i)
                g = array.get(gs, i)
                col = g >= 0 ? color.new(color.teal, 50) : color.new(color.red, 50)
                addLevel(k, col, str.tostring(k) + "  " + (g >= 0 ? "+" : "") + str.tostring(g / 1000000.0, "#.##") + "M", 1)
    addLevel(pwall, color.red,    "P • Put wall "   + str.tostring(pwall), lw + 1)
    addLevel(gflip, color.orange, "G • Gamma flip " + str.tostring(gflip), lw + 1)
    addLevel(cwall, color.teal,   "C • Call wall "  + str.tostring(cwall), lw + 1)
    addLevel(spot,  color.white,  "S • Spot "       + str.tostring(spot),  lw)
`;

  return { code, expiration: exp, flip, callWall: cw, putWall: pw, strikes: top.length };
}
