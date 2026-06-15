import type { OptionContract } from "./barchart/types";
import { callWall, expectedMove, gammaFlip, gexByStrike, putWall } from "./flow/analytics";

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
  callRes: number | null;
  putSup: number | null;
  hvl: number | null;
  strikes: number;
}

/**
 * Generate a TradingView Pine v6 indicator with named GEX levels (MenthorQ-style):
 * Call Resistance (call wall), Put Support (put wall), HVL (gamma flip), their 0DTE
 * variants, a GEX 1..N ladder (top strikes by |GEX|), and 1D Max/Min (expected range).
 * Values are baked in — re-generate from the site to refresh.
 */
export function buildGexPine(symbol: string, chain: OptionContract[], spot: number | null, ladderN = 10): PineResult {
  const exp = nearestExpiration(chain);
  const sub = exp ? chain.filter((c) => c.expiration === exp) : chain;
  const byAll = gexByStrike(chain, spot);
  const by0 = gexByStrike(sub, spot);

  const callRes = callWall(byAll);
  const putSup = putWall(byAll);
  const hvl = gammaFlip(byAll);
  const callRes0 = callWall(by0);
  const putSup0 = putWall(by0);
  const em = exp ? expectedMove(chain, spot, exp) : null;

  const s = spot ?? byAll[Math.floor(byAll.length / 2)]?.strike ?? 0;
  const dmax = em ? s + em.abs : s;
  const dmin = em ? s - em.abs : s;

  // GEX ladder: top strikes by |net GEX|, ranked (GEX 1 = largest).
  const ladder = byAll
    .filter((x) => x.gex !== 0)
    .sort((a, b) => Math.abs(b.gex) - Math.abs(a.gex))
    .slice(0, ladderN);
  const gexk = ladder.length ? ladder.map((x) => fmt(x.strike)).join(", ") : fmt(s);

  const v = (x: number | null) => fmt(x ?? s);
  const asOf = new Date().toISOString().slice(0, 16).replace("T", " ");

  const code = `//@version=6
// OptionsFlow — GEX levels for ${symbol}  (0DTE/front exp ${exp ?? "n/a"}, generated ${asOf} UTC)
// Paste into TradingView: Pine Editor -> paste -> Save -> Add to chart. Re-generate to refresh.
indicator("OptionsFlow GEX • ${symbol}", overlay = true, max_lines_count = 300, max_labels_count = 300)

show0dte = input.bool(true, "Show 0DTE levels")
showGex  = input.bool(true, "Show GEX 1..N ladder")
showRange = input.bool(true, "Show 1D Max/Min")
lw       = input.int(2, "Key line width", minval = 1, maxval = 5)

callRes  = input.float(${v(callRes)}, "Call Resistance")
putSup   = input.float(${v(putSup)}, "Put Support")
hvl      = input.float(${v(hvl)}, "HVL (gamma flip)")
callRes0 = input.float(${v(callRes0)}, "Call Resistance 0DTE / Gamma Wall 0DTE")
putSup0  = input.float(${v(putSup0)}, "Put Support 0DTE / HVL 0DTE")
oneDMax  = input.float(${fmt(dmax)}, "1D Max")
oneDMin  = input.float(${fmt(dmin)}, "1D Min")

var float[] gexK = array.from(${gexk})

var line[]  _ln = array.new_line()
var label[] _lb = array.new_label()

clearAll() =>
    while array.size(_ln) > 0
        line.delete(array.pop(_ln))
    while array.size(_lb) > 0
        label.delete(array.pop(_lb))

addLevel(price, col, txt, w, st) =>
    array.push(_ln, line.new(bar_index, price, bar_index + 1, price, color = col, width = w, extend = extend.both, style = st))
    array.push(_lb, label.new(bar_index, price, txt, style = label.style_label_left, textcolor = col, color = color.new(color.black, 100), size = size.small))

if barstate.islast
    clearAll()
    if showGex
        for i = 0 to array.size(gexK) - 1
            addLevel(array.get(gexK, i), color.teal, "GEX " + str.tostring(i + 1), 1, line.style_solid)
    if showRange
        addLevel(oneDMin, color.orange, "1D Min", 1, line.style_dotted)
        addLevel(oneDMax, color.orange, "1D Max", 1, line.style_dotted)
    if show0dte
        addLevel(callRes0, color.red,  "Call Resistance 0DTE / Gamma Wall 0DTE", lw, line.style_dashed)
        addLevel(putSup0,  color.blue, "Put Support 0DTE / HVL 0DTE", lw, line.style_dashed)
    addLevel(putSup,  color.green, "Put Support", lw, line.style_solid)
    addLevel(hvl,     color.blue,  "HVL", lw, line.style_solid)
    addLevel(callRes, color.red,   "Call Resistance", lw, line.style_solid)
`;

  return { code, expiration: exp, callRes, putSup, hvl, strikes: ladder.length };
}
