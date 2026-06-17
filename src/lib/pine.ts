import type { OptionContract } from "./barchart/types";
import {
  atmIv,
  callOiWall,
  callResistance,
  expectedMove,
  expectedMove1D,
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

function meta(contracts: OptionContract[], strike: number | null, spot: number | null): string {
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

interface Lvl {
  price: number;
  short: string; // visible text
  detail: string; // hover tooltip
  color: string; // Pine color token
  style: string; // Pine line.style_* token
  width: number;
  prio: number; // lower = more important (kept on merge)
}

/** Merge a level into the list if another sits within tolerance, so stacked labels collapse to one. */
function pushMerged(list: Lvl[], lvl: Lvl, scale: number): void {
  const tol = Math.max(0.01, scale * 0.0006);
  const hit = list.find((l) => Math.abs(l.price - lvl.price) <= tol);
  if (!hit) {
    list.push({ ...lvl });
    return;
  }
  if (lvl.prio < hit.prio) {
    hit.color = lvl.color;
    hit.style = lvl.style;
    hit.prio = lvl.prio;
  }
  hit.width = Math.max(hit.width, lvl.width);
  const name = lvl.short.replace(/\s+[-\d.]+$/, "");
  if (!hit.short.includes(name)) hit.short += ` + ${name}`;
  hit.detail += `  ||  ${lvl.detail}`;
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
 * Generate a TradingView Pine v6 indicator with named GEX levels (MenthorQ-style). Levels are a
 * baked, ~15-min-delayed snapshot. Labels are short (full OI/Vol/GEX/DEX detail is on hover) and the
 * indicator auto-staggers labels that sit close together so they never overlap.
 */
export function buildGexPine(
  symbol: string,
  chain: OptionContract[],
  spot: number | null,
  ladderN = 8,
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
  const oi = oiByStrike(chain);
  const callOi = callOiWall(oi);
  const putOi = putOiWall(oi);
  const iv0 = exp ? atmIv(chain, spot, exp) : null;
  const em1 = expectedMove1D(spot, iv0) ?? (exp ? expectedMove(chain, spot, exp) : null);

  const s = spot ?? byAll[Math.floor(byAll.length / 2)]?.strike ?? 0;
  const dmax = em1 ? s + em1.abs : null;
  const dmin = em1 ? s - em1.abs : null;

  const ladder = byAll
    .filter((x) => x.gex !== 0)
    .sort((a, b) => Math.abs(b.gex) - Math.abs(a.gex))
    .slice(0, ladderN);

  const lvls: Lvl[] = [];
  const add = (price: number | null, name: string, color: string, style: string, width: number, prio: number, detail: string) => {
    if (price == null || !Number.isFinite(price)) return;
    pushMerged(lvls, { price, short: `${name} ${fmtNice(price)}`, detail, color, style, width, prio }, spot ?? price);
  };

  add(callRes, "Call Res", "color.red", "line.style_solid", 2, 0, `Call Resistance (max call gamma above spot) - ${meta(chain, callRes, spot)}`);
  add(putSup, "Put Sup", "color.green", "line.style_solid", 2, 0, `Put Support (max put gamma below spot) - ${meta(chain, putSup, spot)}`);
  add(hvl, "HVL", "color.blue", "line.style_solid", 2, 0, "HVL / gamma flip (zero-gamma nearest spot)");
  add(callRes0, "Call Res 0DTE", "color.red", "line.style_dashed", 2, 1, `Call Resistance 0DTE - ${meta(sub, callRes0, spot)}`);
  add(putSup0, "Put Sup 0DTE", "color.green", "line.style_dashed", 2, 1, `Put Support 0DTE - ${meta(sub, putSup0, spot)}`);
  add(mp, "Max Pain", "color.yellow", "line.style_dotted", 1, 2, `Max Pain ${exp ?? ""} - ${meta(chain, mp, spot)}`);
  add(callOi, "Call OI", "color.olive", "line.style_dotted", 1, 2, `Call OI wall - ${meta(chain, callOi, spot)}`);
  add(putOi, "Put OI", "color.purple", "line.style_dotted", 1, 2, `Put OI wall - ${meta(chain, putOi, spot)}`);
  add(spot, "Spot", "color.gray", "line.style_dotted", 1, 5, `Underlying spot when generated${feedAsOf ? ` (CBOE ${feedAsOf})` : " (~15-min delayed)"} — levels are anchored here; the chart's current price may have moved since.`);
  add(dmax, "1D Max", "color.orange", "line.style_dotted", 1, 3, "1-day +1 sigma expected move (ATM IV)");
  add(dmin, "1D Min", "color.orange", "line.style_dotted", 1, 3, "1-day -1 sigma expected move (ATM IV)");
  ladder.forEach((x, i) => {
    const st = strikeStats(chain, x.strike, spot);
    add(x.strike, `GEX${i + 1}`, "color.teal", "line.style_solid", 1, 4, `GEX ${i + 1} @${fmtNice(x.strike)} - OI ${kfmt(st.oi)} | V ${kfmt(st.vol)} | ${usd(x.gex)}`);
  });

  if (!lvls.length) add(s, "Spot", "color.gray", "line.style_dotted", 1, 9, "spot");
  lvls.sort((a, b) => a.price - b.price);

  const P = lvls.map((l) => fmt(l.price)).join(", ");
  const T = lvls.map((l) => JSON.stringify(l.short)).join(", ");
  const D = lvls.map((l) => JSON.stringify(l.detail)).join(", ");
  const C = lvls.map((l) => l.color).join(", ");
  const LS = lvls.map((l) => l.style).join(", ");
  const W = lvls.map((l) => String(l.width)).join(", ");

  const asOf = new Date().toISOString().slice(0, 16).replace("T", " ");
  const isFut = /^(ES|NQ|RTY|YM)$/.test(symbol.toUpperCase());
  const proxy = isFut
    ? `\n// NOTE: ${symbol} uses the cash index options (ES->SPX, NQ->NDX) as a free proxy. The future trades at a\n// basis to cash, so shift levels by (future - index) if you want them exact on the ${symbol} chart.`
    : "";

  const code = `//@version=6
// OptionsFlow — GEX levels for ${symbol}  (front/target exp ${exp ?? "n/a"})
// APPLY ON THE ${symbol} CHART. These are ${symbol}-scale levels (spot ~${spot != null ? fmtNice(spot) : "n/a"}); they will look
// wrong on a different instrument (e.g. QQQ's ~500 levels do not belong on an NQ ~30000 chart).
// Snapshot: CBOE ${feedAsOf ?? "(time n/a)"} · generated ${asOf} UTC · ~15-min delayed. Re-generate to refresh.
// Short labels; hover a label for full OI/Volume/GEX/DEX. Close levels auto-stagger so they don't overlap.${proxy}
indicator("OptionsFlow GEX • ${symbol}", overlay = true, max_lines_count = 200, max_labels_count = 200)

showMeta  = input.bool(true, "Detail on hover (tooltip)")
laneStep  = input.int(14, "Stagger close labels (bars)", minval = 0, maxval = 80)
labelSize = input.string("normal", "Label size", options = ["small", "normal", "large", "huge"])
sz = labelSize == "huge" ? size.huge : labelSize == "large" ? size.large : labelSize == "normal" ? size.normal : size.small
showVwap = input.bool(true, "Show session VWAP")
showOR   = input.bool(true, "Show opening range (intraday)")
orMin    = input.int(30, "Opening-range minutes", minval = 1, maxval = 240)

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

if barstate.islast
    clearAll()
    rng = ta.highest(high, 120) - ta.lowest(low, 120)
    minGap = na(rng) or rng <= 0 ? close * 0.01 : rng * 0.022
    float prevP = na
    int lane = 0
    base = bar_index
    for i = 0 to array.size(P) - 1
        p = array.get(P, i)
        lane := not na(prevP) and (p - prevP) < minGap ? lane + 1 : 0
        x = base + 1 + lane * laneStep
        col = array.get(C, i)
        array.push(_ln, line.new(base, p, x, p, color = col, width = array.get(W, i), extend = extend.left, style = array.get(LS, i)))
        array.push(_lb, label.new(x, p, array.get(T, i), style = label.style_label_left, textcolor = col, color = color.new(color.black, 100), size = sz, tooltip = showMeta ? array.get(D, i) : ""))
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
`;

  return { code, expiration: exp, callRes, putSup, hvl, strikes: lvls.length };
}
