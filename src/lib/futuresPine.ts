/**
 * Pine v6 generator: 0DTE 1:1 bracket levels for index futures (NQ1! / ES1!).
 *
 * Unlike the GEX export (a baked snapshot), this script is LIVE: every number it draws — session vol,
 * touch probability, resolve probability, win rate — is recomputed by TradingView on each bar from the
 * chart's own price and clock. Only the volatility input is seeded from the site (front ATM IV of the
 * proxy ETF), and it is an editable input.
 *
 * The math it implements is Black-76's world: a futures price is a martingale, so for a symmetric ±R
 * bracket optional stopping forces P(target first) = 1/2 EXACTLY, whatever the level, R or vol. The
 * script says so plainly and derives what actually varies intraday:
 *   • P(touch)     — reflection principle: 2·N(−|ln(L/F)|/σ_rem)
 *   • P(resolve)   — 1 − P(no touch of ±R band) via the reflection series
 *   • Win rate     — 50% at zero drift; tilts only if the trader supplies a session bias.
 */

export interface FuturesPineOptions {
  contract: "NQ1!" | "ES1!";
  step: number; // grid spacing in points (NQ 40, ES 10)
  ivPct: number | null; // seed annualized IV from the proxy ETF, in %
  proxy: string; // where the seed IV came from (QQQ / SPY)
  levels?: number; // grid levels each side
}

export interface FuturesPineResult {
  code: string;
  contract: string;
  step: number;
  ivPct: number | null;
}

export function buildFuturesPine(o: FuturesPineOptions): FuturesPineResult {
  const { contract, step, ivPct, proxy } = o;
  const levels = o.levels ?? 8;  // 17 grid levels available; at least `minShow` always drawn
  const iv = ivPct != null && ivPct > 0 ? Math.round(ivPct * 10) / 10 : 20;
  const asOf = new Date().toISOString().slice(0, 16).replace("T", " ");
  const dollarsPerPoint = contract === "NQ1!" ? 20 : 50; // NQ $20/pt, ES $50/pt

  const code = `//@version=6
// OptionsFlow — 0DTE 1:1 bracket levels for ${contract}
// ============================================================================
// WHAT THIS IS. A round-number grid (${step} pts) of intraday trade levels, each evaluated as a
// symmetric 1:1 bracket (risk = reward = ${step} pts) for the REMAINDER of today's session only.
//
// THE MODEL — Black-Scholes converted to futures (Black-76). A futures price is already a forward:
// there is no dividend yield and, under the risk-neutral measure, no drift — F is a MARTINGALE:
//     d1 = [ln(F/K) + s^2*T/2] / (s*sqrt(T)),  d2 = d1 - s*sqrt(T)
// THE CONSEQUENCE YOU MUST INTERNALISE: for a symmetric +/-R bracket on a martingale, optional
// stopping gives  p*(L+R) + (1-p)*(L-R) = L  =>  p = 1/2 EXACTLY. Not approximately - exactly, and
// independently of the level, of R, and of volatility. A 1:1 risk-reward bracket therefore has NO
// edge from geometry. 50% is the null hypothesis, and before commissions and slippage the expected
// value is zero. Everything below is about what genuinely DOES vary intraday:
//     P(touch)   - will the level even trade before the close? (a level that never fills is not a trade)
//     P(resolve) - will the bracket finish before the bell, or expire unresolved?
//     Win rate   - 50% unless YOU supply a directional bias in the "Session drift" input.
// Set drift to 0 and every level prints 50% / 0.00R. That is the honest baseline, by design.
// ============================================================================
// Generated ${asOf} UTC. Volatility seeded from ${proxy} front ATM IV (${iv}%) — editable below; every
// probability is recomputed LIVE by TradingView from this chart's price and clock.
// Apply to ${contract} on an intraday timeframe. Educational — not financial advice.

indicator("OptionsFlow 0DTE 1:1 • ${contract}", overlay = true, max_lines_count = 200, max_labels_count = 200, max_boxes_count = 100)

// ── Inputs ───────────────────────────────────────────────────────────────────
grpM = "Model"
ivAnnual  = input.float(${iv}, "Annualized IV (%)", minval = 1, maxval = 300, step = 0.5, group = grpM, tooltip = "Seeded from ${proxy} front ATM IV when generated. Raise it on event days.") / 100
driftPts  = input.float(0.0, "Session drift (pts, your bias)", step = 1, group = grpM, tooltip = "Expected move over the REST of the session. 0 = no view => every win rate is exactly 50% (the martingale null). Only a non-zero view tilts the numbers.")
useSessVol = input.bool(true, "Blend live realized vol into IV", group = grpM, tooltip = "Averages the IV input with realized vol measured from this chart, so the numbers react when the tape gets faster or slower than the options market assumed.")

grpG = "Grid"
step      = input.float(${step}, "Level spacing / bracket size R (pts)", minval = 0.25, step = 0.25, group = grpG, tooltip = "${contract} default ${step} pts. Risk = reward = this, so R:R is 1:1.")
nLevels   = input.int(${levels}, "Levels each side", minval = 1, maxval = 12, group = grpG)
minShow   = input.int(10, "Always mark at least N levels", minval = 1, maxval = 25, group = grpG, tooltip = "The nearest N levels are ALWAYS drawn, even if their touch probability is low. Late in the session sigma collapses and every far level would otherwise be filtered out, leaving the chart bare.")
minTouch  = input.float(5, "Also show farther levels above P(touch) %", minval = 0, maxval = 100, group = grpG, tooltip = "Beyond the guaranteed N nearest, a level is only drawn if it still has this much chance of trading before the close.")

grpS = "Session (0DTE)"
sessSpec  = input.session("0930-1600", "Cash session", group = grpS, tooltip = "The window the 0DTE clock runs over. Probabilities shrink toward the close.")
showTable = input.bool(true, "Show setup table", group = grpS)
showZones = input.bool(true, "Shade the best setup's bracket", group = grpS)

// ── Session clock: how much of today is left? ────────────────────────────────
inSess   = not na(time(timeframe.period, sessSpec))
sessStart = ta.valuewhen(inSess and not inSess[1], time, 0)
var float sessEndEst = na
if inSess and not inSess[1]
    sessEndEst := time + 6.5 * 60 * 60 * 1000  // approx cash session length; refined by the ratio below
minsLeft = inSess ? math.max(0.0, (sessEndEst - time) / 60000.0) : 0.0
fracLeft = math.min(1.0, math.max(0.0, minsLeft / 390.0))   // 390 min = 6.5h cash session

// ── Volatility for the remaining session ─────────────────────────────────────
// sigma_day = IV / sqrt(252); the remaining slice scales with sqrt(time left).
rvAnnual = ta.stdev(math.log(close / close[1]), 60) * math.sqrt(252 * (1440 / math.max(timeframe.in_seconds() / 60, 1)))
ivUse    = useSessVol and not na(rvAnnual) and rvAnnual > 0 ? (ivAnnual + rvAnnual) / 2 : ivAnnual
sigDay   = ivUse / math.sqrt(252)
sigRem   = sigDay * math.sqrt(math.max(fracLeft, 0.0001))   // log-vol over the rest of the session

// ── Probability helpers (normal CDF via Abramowitz-Stegun erf) ───────────────
erf(x) =>
    t = 1.0 / (1.0 + 0.3275911 * math.abs(x))
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t) * math.exp(-x * x)
    x >= 0 ? y : -y
ncdf(x) => 0.5 * (1.0 + erf(x / math.sqrt(2.0)))

// P(price touches 'lvl' before the close) — reflection principle: 2*N(-|ln(lvl/F)|/sigma_rem)
pTouch(lvl) =>
    sigRem <= 0 or lvl <= 0 or close <= 0 ? 0.0 : lvl == close ? 1.0 : math.min(1.0, 2.0 * ncdf(-math.abs(math.log(lvl / close)) / sigRem))

// P(log-price stays inside +/-h for the rest of the session) — reflection series.
pNoTouchBand(h) =>
    float p = 0.0
    if sigRem <= 0
        p := 1.0
    else
        a = h / sigRem
        for k = -4 to 4
            sgn = k % 2 == 0 ? 1.0 : -1.0
            p += sgn * (ncdf((2 * k + 1) * a) - ncdf((2 * k - 1) * a))
    math.max(0.0, math.min(1.0, p))

// P(target hit before stop) for a symmetric +/-h log band with drift.
// theta = 2*mu/sigma^2; p = (e^{theta*h} - 1)/(e^{theta*h} - e^{-theta*h}).  theta -> 0 gives EXACTLY 0.5.
pUpFirst(h) =>
    float p = 0.5
    if sigRem > 0 and driftPts != 0
        muLog = math.log((close + driftPts) / close)
        theta = 2.0 * muLog / (sigRem * sigRem)
        if math.abs(theta * h) > 1e-9
            p := (math.exp(theta * h) - 1.0) / (math.exp(theta * h) - math.exp(-theta * h))
    math.max(0.0, math.min(1.0, p))

// ── Build the grid and evaluate every level ─────────────────────────────────
var line[]  _ln = array.new_line()
var label[] _lb = array.new_label()
var box[]   _bx = array.new_box()
clearAll() =>
    while array.size(_ln) > 0
        line.delete(array.pop(_ln))
    while array.size(_lb) > 0
        label.delete(array.pop(_lb))
    while array.size(_bx) > 0
        box.delete(array.pop(_bx))

var table tb = table.new(position.top_right, 6, ${levels * 2 + 2}, border_width = 1)

if barstate.islast
    clearAll()
    base = math.round(close / step) * step

    // Guarantee a minimum number of marked levels: take the distance of the Nth-nearest grid level and
    // always draw everything inside it, then let the touch filter decide about the rest.
    dists = array.new_float()
    for k = -nLevels to nLevels
        lvl0 = base + k * step
        if lvl0 > 0
            array.push(dists, math.abs(lvl0 - close))
    array.sort(dists, order.ascending)
    distCut = array.size(dists) == 0 ? 0.0 : array.get(dists, math.min(minShow, array.size(dists)) - 1)
    hLog = math.log((base + step) / base)          // bracket half-width in log space
    pResolve = 1.0 - pNoTouchBand(hLog)
    pUp = pUpFirst(hLog)

    if showTable
        table.clear(tb, 0, 0, 5, ${levels * 2 + 1})
        table.cell(tb, 0, 0, "LEVEL", text_color = color.gray, text_size = size.tiny, bgcolor = color.new(color.black, 30))
        table.cell(tb, 1, 0, "SIDE", text_color = color.gray, text_size = size.tiny, bgcolor = color.new(color.black, 30))
        table.cell(tb, 2, 0, "TOUCH", text_color = color.gray, text_size = size.tiny, bgcolor = color.new(color.black, 30))
        table.cell(tb, 3, 0, "WIN", text_color = color.gray, text_size = size.tiny, bgcolor = color.new(color.black, 30))
        table.cell(tb, 4, 0, "RESOLVE", text_color = color.gray, text_size = size.tiny, bgcolor = color.new(color.black, 30))
        table.cell(tb, 5, 0, "E[R]", text_color = color.gray, text_size = size.tiny, bgcolor = color.new(color.black, 30))

    float bestScore = -1e9
    float bestLvl = na
    bool  bestLong = true
    int   row = 1

    for k = -nLevels to nLevels
        lvl = base + k * step
        if lvl > 0
            pt = pTouch(lvl)
            keep = math.abs(lvl - close) <= distCut + 0.0001 or pt * 100 >= minTouch
            if keep
                // Below price you are buying support (long); above price you are selling resistance (short).
                isLong = lvl <= close
                win = isLong ? pUp : 1.0 - pUp
                expR = pResolve * (win - (1.0 - win))
                // Rank by expected R actually captured this session: needs the level to fill AND resolve.
                score = pt * expR
                if score > bestScore
                    bestScore := score
                    bestLvl := lvl
                    bestLong := isLong
                col = isLong ? color.new(color.teal, 0) : color.new(color.red, 0)
                array.push(_ln, line.new(bar_index - 300, lvl, bar_index + 40, lvl, color = color.new(col, 45), width = 1, extend = extend.right, style = math.abs(lvl - base) < 0.001 ? line.style_solid : line.style_dotted))
                txt = str.tostring(lvl, format.mintick) + "  " + (isLong ? "L" : "S") + "  touch " + str.tostring(math.round(pt * 100)) + "%  win " + str.tostring(math.round(win * 100)) + "%"
                array.push(_lb, label.new(bar_index + 40, lvl, txt, style = label.style_label_left, textcolor = col, color = color.new(color.black, 100), size = size.small,
                     tooltip = "Level " + str.tostring(lvl, format.mintick) + "  |  " + (isLong ? "LONG: stop " + str.tostring(lvl - step, format.mintick) + " / target " + str.tostring(lvl + step, format.mintick) : "SHORT: stop " + str.tostring(lvl + step, format.mintick) + " / target " + str.tostring(lvl - step, format.mintick)) +
                       "\\nRisk = reward = " + str.tostring(step) + " pts ($" + str.tostring(step * ${dollarsPerPoint}) + "/contract)" +
                       "\\nP(touch before close) " + str.tostring(math.round(pt * 100)) + "%   P(bracket resolves) " + str.tostring(math.round(pResolve * 100)) + "%" +
                       "\\nWin rate " + str.tostring(math.round(win * 100)) + "%  (exactly 50% at zero drift - the martingale null)" +
                       "\\nE[R] per filled trade " + str.tostring(expR, "#.##") + "R before costs"))
                if showTable and row <= ${levels * 2 + 1}
                    table.cell(tb, 0, row, str.tostring(lvl, format.mintick), text_color = color.new(color.white, 20), text_size = size.tiny)
                    table.cell(tb, 1, row, isLong ? "LONG" : "SHORT", text_color = col, text_size = size.tiny)
                    table.cell(tb, 2, row, str.tostring(math.round(pt * 100)) + "%", text_color = color.new(color.white, 35), text_size = size.tiny)
                    table.cell(tb, 3, row, str.tostring(math.round(win * 100)) + "%", text_color = win > 0.5 ? color.teal : win < 0.5 ? color.red : color.gray, text_size = size.tiny)
                    table.cell(tb, 4, row, str.tostring(math.round(pResolve * 100)) + "%", text_color = color.new(color.white, 35), text_size = size.tiny)
                    table.cell(tb, 5, row, str.tostring(expR, "#.##"), text_color = expR > 0 ? color.teal : expR < 0 ? color.red : color.gray, text_size = size.tiny)
                    row += 1

    // Best setup: shade its bracket so the risk and the reward are the same visual size (1:1).
    if showZones and not na(bestLvl)
        tgt = bestLong ? bestLvl + step : bestLvl - step
        stp = bestLong ? bestLvl - step : bestLvl + step
        array.push(_bx, box.new(bar_index - 60, math.max(bestLvl, tgt), bar_index + 40, math.min(bestLvl, tgt), border_color = color.new(color.teal, 40), bgcolor = color.new(color.teal, 88), extend = extend.right))
        array.push(_bx, box.new(bar_index - 60, math.max(bestLvl, stp), bar_index + 40, math.min(bestLvl, stp), border_color = color.new(color.red, 40), bgcolor = color.new(color.red, 88), extend = extend.right))
        array.push(_lb, label.new(bar_index + 40, bestLvl, "BEST " + (bestLong ? "LONG" : "SHORT") + " " + str.tostring(bestLvl, format.mintick), style = label.style_label_left, textcolor = color.white, color = color.new(bestLong ? color.teal : color.red, 25), size = size.normal,
             tooltip = "Highest P(fill) x E[R] on the grid. With zero drift E[R] is 0 everywhere, so this is simply the level most likely to trade - not a profitable edge."))

// ── Session context readout ─────────────────────────────────────────────────
var table info = table.new(position.bottom_right, 1, 3)
if barstate.islast
    table.cell(info, 0, 0, "0DTE clock: " + str.tostring(math.round(minsLeft)) + " min left (" + str.tostring(math.round(fracLeft * 100)) + "% of session)", text_color = color.new(color.white, 25), text_size = size.tiny, bgcolor = color.new(color.black, 30))
    table.cell(info, 0, 1, "sigma session " + str.tostring(sigRem * 100, "#.##") + "%  (~" + str.tostring(close * sigRem, "#.#") + " pts 1SD)", text_color = color.new(color.white, 35), text_size = size.tiny, bgcolor = color.new(color.black, 30))
    table.cell(info, 0, 2, driftPts == 0 ? "drift 0 => win rate 50% (martingale null)" : "drift " + str.tostring(driftPts) + " pts => tilted", text_color = driftPts == 0 ? color.gray : color.teal, text_size = size.tiny, bgcolor = color.new(color.black, 30))

// ── Alerts ───────────────────────────────────────────────────────────────────
alertcondition(ta.cross(close, math.round(close / ${step}) * ${step}), "Grid level tagged", "{{ticker}} tagged a ${step}-pt 0DTE grid level")
`;

  return { code, contract, step, ivPct };
}
