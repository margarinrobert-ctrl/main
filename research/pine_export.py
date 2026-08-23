"""Turn any generated rule into a TradingView strategy and a companion indicator.

Every condition in the generator has an exact Pine expression here, written to match the Python
definition rather than to look like it. Two differences bit this repository badly enough to be
worth restating at the top of every file this emits:

  * ATR is an EMA of true range with alpha 2/15. Pine's `ta.atr` is Wilder's RMA at alpha 1/14
    and would move every stop.
  * Pine's bare `hour` and `minute` are in the EXCHANGE timezone -- America/Chicago for CME --
    while the research is New York time. Every clock condition goes through an explicit timezone.
"""
from __future__ import annotations

# Shared prelude expressions, emitted once and referenced by the conditions below.
PRELUDE = """
// ---- primitives, defined to match the research exactly -------------------------------------
tzIn   = input.string("America/New_York", "Timezone for clock conditions",
     options = ["America/New_York", "America/Chicago", "Europe/London", "exchange"],
     group = "Setup", tooltip = "Pine's bare hour/minute are in the EXCHANGE timezone, which is " +
     "Chicago for CME. The research is New York time. Getting this wrong runs the strategy an " +
     "hour late -- it has happened here before.")
barMin = tzIn == "exchange" ? hour * 60 + minute : hour(time, tzIn) * 60 + minute(time, tzIn)

atrV   = ta.ema(ta.tr(true), 14)          // NOT ta.atr -- see the header
ema10  = ta.ema(close, 10)
ema20  = ta.ema(close, 20)
ema50  = ta.ema(close, 50)
ema100 = ta.ema(close, 100)
ema200 = ta.ema(close, 200)
sma10  = ta.sma(close, 10)
sma20  = ta.sma(close, 20)
sma50  = ta.sma(close, 50)
sma100 = ta.sma(close, 100)
sma200 = ta.sma(close, 200)
rsi14  = ta.rsi(close, 14)
rsi7   = ta.rsi(close, 7)
stK    = ta.stoch(close, high, low, 14)
stD    = ta.sma(stK, 3)
[macdL, macdS, _mh] = ta.macd(close, 12, 26, 9)
cci20  = ta.cci(hlc3, 20)   // typical price, matching the research -- NOT ta.cci(close, 20)
wr14   = ta.wpr(14)
mfi14  = ta.mfi(hlc3, 14)
[dip, dim, adx14] = ta.dmi(14, 14)
bbBasis = ta.sma(close, 20)
bbDev   = 2.0 * ta.stdev(close, 20)
bbUpper = bbBasis + bbDev
bbLower = bbBasis - bbDev
bbWidth = 2.0 * bbDev / bbBasis
kcBasis = ta.ema(close, 20)
kcRange = ta.ema(ta.tr(true), 20)
kcUpper = kcBasis + 1.5 * kcRange
kcLower = kcBasis - 1.5 * kcRange
atrMean20 = ta.sma(atrV, 20)
volMean20 = ta.sma(volume, 20)
volSd20   = ta.stdev(volume, 20)
barRange  = math.max(high - low, syminfo.mintick)
bodyFrac  = math.abs(close - open) / barRange
newDay    = ta.change(time("D")) != 0
var float sVwapNum = 0.0
var float sVwapDen = 0.0
if newDay
    sVwapNum := 0.0
    sVwapDen := 0.0
sVwapNum := sVwapNum + hlc3 * volume
sVwapDen := sVwapDen + volume
sVwap = sVwapDen > 0 ? sVwapNum / sVwapDen : na
var float pdHigh = na
var float pdLow  = na
var float pdClose = na
var float curH = na
var float curL = na
if newDay
    pdHigh := curH
    pdLow  := curL
    pdClose := close[1]
    curH := high
    curL := low
else
    curH := math.max(nz(curH, high), high)
    curL := math.min(nz(curL, low), low)
obvV   = ta.obv
trixV  = ta.roc(ta.ema(ta.ema(ta.ema(close, 15), 15), 15), 1)
lr20   = ta.linreg(close, 20, 0) - ta.linreg(close, 20, 1)
lr50   = ta.linreg(close, 50, 0) - ta.linreg(close, 50, 1)
"""

# name -> Pine boolean expression. Keys match research/alpha_factory2.build_conditions exactly.
P = {}
for n in (10, 20, 50, 100, 200):
    P[f"close>EMA{n}"] = f"close > ema{n}"
    P[f"close>SMA{n}"] = f"close > sma{n}"
for a, b in ((10, 20), (20, 50), (50, 100), (50, 200), (20, 200)):
    P[f"EMA{a}>EMA{b}"] = f"ema{a} > ema{b}"
for n in (20, 50, 200):
    P[f"EMA{n} rising"] = f"ema{n} > ema{n}[1]"
P["LR slope20>0"] = "lr20 > 0"
P["LR slope50>0"] = "lr50 > 0"
P["close>session VWAP"] = "close > sVwap"
P["close<session VWAP"] = "close < sVwap"
P["close>Donchian20 high"] = "close > ta.highest(high, 20)[1]"
P["close<Donchian20 low"] = "close < ta.lowest(low, 20)[1]"
P["RSI14<30"] = "rsi14 < 30"; P["RSI14>70"] = "rsi14 > 70"
P["RSI14>50"] = "rsi14 > 50"; P["RSI14<50"] = "rsi14 < 50"
P["RSI14 rising"] = "rsi14 > rsi14[1]"
P["RSI7<25"] = "rsi7 < 25"; P["RSI7>75"] = "rsi7 > 75"
P["Stoch K<20"] = "stK < 20"; P["Stoch K>80"] = "stK > 80"; P["Stoch K>D"] = "stK > stD"
P["CCI>100"] = "cci20 > 100"; P["CCI<-100"] = "cci20 < -100"
P["Williams%R<-80"] = "wr14 < -80"; P["Williams%R>-20"] = "wr14 > -20"
P["MFI<20"] = "mfi14 < 20"; P["MFI>80"] = "mfi14 > 80"
P["ROC10>0"] = "ta.roc(close, 10) > 0"; P["ROC20>0"] = "ta.roc(close, 20) > 0"
P["TRIX>0"] = "trixV > 0"
P["MACD>signal"] = "macdL > macdS"; P["MACD>0"] = "macdL > 0"
P["MACD rising"] = "macdL > macdL[1]"
P["ATR>1.2x mean"] = "atrV > 1.2 * atrMean20"
P["ATR>1.5x mean"] = "atrV > 1.5 * atrMean20"
P["ATR<0.8x mean"] = "atrV < 0.8 * atrMean20"
P["ATR rising"] = "atrV > atrV[1]"
P["ATR falling"] = "atrV <= atrV[1]"
P["close>BB upper"] = "close > bbUpper"; P["close<BB lower"] = "close < bbLower"
P["BB width>mean"] = "bbWidth > ta.sma(bbWidth, 50)"
P["BB squeeze"] = "bbWidth < 0.7 * ta.sma(bbWidth, 50)"
P["close>Keltner upper"] = "close > kcUpper"; P["close<Keltner lower"] = "close < kcLower"
P["range>1.5xATR"] = "(high - low) > 1.5 * atrV"
P["range<0.5xATR"] = "(high - low) < 0.5 * atrV"
P["3-bar contraction"] = "(high - low) < (high - low)[1] and (high - low)[1] < (high - low)[2]"
P["ADX>20"] = "adx14 > 20"; P["ADX>25"] = "adx14 > 25"; P["ADX>30"] = "adx14 > 30"
P["ADX rising"] = "adx14 > adx14[1]"; P["+DI>-DI"] = "dip > dim"
for n in (5, 10, 20, 50):
    P[f"close>{n}-bar high"] = f"close > ta.highest(high, {n})[1]"
    P[f"close<{n}-bar low"] = f"close < ta.lowest(low, {n})[1]"
P["inside bar"] = "high < high[1] and low > low[1]"
P["outside bar"] = "high > high[1] and low < low[1]"
P["bullish engulfing"] = "close > open[1] and open < close[1] and close > open"
P["bearish engulfing"] = "close < open[1] and open > close[1] and close < open"
P["body>60%"] = "bodyFrac > 0.6"; P["body<30%"] = "bodyFrac < 0.3"
P["upper wick>50%"] = "(high - math.max(close, open)) / barRange > 0.5"
P["lower wick>50%"] = "(math.min(close, open) - low) / barRange > 0.5"
P["bullish bar"] = "close > open"
P["2 up closes"] = "close > close[1] and close[1] > close[2]"
P["3 up closes"] = "close > close[1] and close[1] > close[2] and close[2] > close[3]"
P["2 down closes"] = "close <= close[1] and close[1] <= close[2]"
P["gap up"] = "open > close[1]"; P["gap down"] = "open < close[1]"
P["vol>1.5x mean"] = "volume > 1.5 * volMean20"
P["vol>2x mean"] = "volume > 2.0 * volMean20"
P["vol<0.7x mean"] = "volume < 0.7 * volMean20"
P["vol<0.5x mean"] = "volume < 0.5 * volMean20"
P["vol rising"] = "volume > volume[1]"
P["OBV rising"] = "ta.ema(obvV, 10) > ta.ema(obvV, 10)[1]"
P["vol z>1"] = "(volume - volMean20) / math.max(volSd20, 1e-9) > 1"
P["first hour"] = "barMin >= 570 and barMin < 630"
P["second hour"] = "barMin >= 630 and barMin < 690"
P["midday"] = "barMin >= 690 and barMin < 810"
P["last hour"] = "barMin >= 900 and barMin < 960"
P["overnight"] = "barMin < 570 or barMin >= 960"
for i, nm in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri")):
    P[nm] = f"dayofweek(time, tzIn) == {[dayname for dayname in ['dayofweek.monday','dayofweek.tuesday','dayofweek.wednesday','dayofweek.thursday','dayofweek.friday']][i]}"
P["first half of month"] = "dayofmonth(time, tzIn) <= 15"
P["month end (last 3d)"] = "dayofmonth(time, tzIn) >= 27"
P["dist EMA200>1 ATR"] = "math.abs(close - ema200) / atrV > 1.0"
P["dist EMA200>2 ATR"] = "math.abs(close - ema200) / atrV > 2.0"
P["dist EMA200<0.5 ATR"] = "math.abs(close - ema200) / atrV < 0.5"
P["close>prior day high"] = "close > pdHigh"
P["close<prior day low"] = "close < pdLow"
P["prior day up"] = "pdClose > pdClose[1]"
P["prior day range>20d"] = "(pdHigh - pdLow) > ta.sma(pdHigh - pdLow, 20)"
P["5-bar momentum>0"] = "close > close[5]"
P["20-bar momentum>0"] = "close > close[20]"


def missing(names):
    return [n for n in names if n not in P]


# ---- emitters ---------------------------------------------------------------------------------
_HEADER = '''//@version=6
// =============================================================================================
// {title}
//
// Generated by research/pine_export.py from a rule the strategy generator found:
//
//     {human}
//
// EXIT GEOMETRY: stop {am} x ATR, target {tp} x that risk{flat}. Both are measured from
// the FILL -- the open of the bar after the signal -- using the ATR of the signal bar.
// DIRECTION: {sidetxt}.
//
// MEASURED ON MNQ, {tf}-minute bars, 2022-12 to 2025-12, 1 contract, $1.00 commission per round
// turn, 1 tick spread + 1 tick slip each side, 1 extra tick on stops:
{stats}
//
// TWO DEFINITIONS THAT ARE EASY TO GET WRONG, AND WERE, HERE, BEFORE:
//   * ATR is ta.ema(ta.tr(true), 14) -- an EMA of true range at alpha 2/15. Pine's ta.atr is
//     Wilder's RMA at alpha 1/14 and would move every stop in this script.
//   * Clock conditions go through an explicit timezone input. Pine's bare hour and minute are in
//     the EXCHANGE timezone, America/Chicago for CME, while the research is New York time.
//
// Pine built-ins are used for RSI, Stochastic, CCI (on hlc3), Williams %R, MFI, DMI/ADX, OBV,
// linreg and Bollinger. Their definitions were checked against the research implementations, but
// they are library code and have not been executed side by side.
//
// NOT COMPILED BY TRADINGVIEW. The logic is transcribed from a verified engine; the syntax is not
// verified. A compiler error is a typo, not a changed strategy.
//
// Research tooling for education and analysis. Not financial advice.
// =============================================================================================
'''


def _stats_block(st):
    if not st:
        return "//     (no measured figures supplied)"
    return "\n".join(f"//     {k:<28}{v}" for k, v in st.items())


def _cond_block(rule):
    """Column 0, always. These assignments sit at global scope, and Pine reads a leading space
    at global scope as a line continuation -- CE10013, "expecting end of line without line
    continuation". That is what shipped once."""
    lines = [f"c{i} = {P[nm]}    // {nm}" for i, nm in enumerate(rule)]
    return "\n".join(lines), " and ".join(f"c{i}" for i in range(len(rule)))


def _f(x):
    return f"{float(x):.1f}" if float(x) == int(float(x)) else f"{float(x)}"


def emit_strategy(rule, side, am, tp, flat, tf=30, stats=None, title=None):
    """side: 1 long only, -1 short only, 0 both directions on the same trigger."""
    title = title or "Generated strategy"
    human = " AND ".join(rule)
    sidetxt = {1: "long only", -1: "short only", 0: "both directions on the same trigger"}[side]
    hdr = _HEADER.format(title=title, human=human, am=am, tp=tp,
                         flat=(f", flat at {flat // 60}:00" if flat else ", no time stop"),
                         sidetxt=sidetxt, tf=tf, stats=_stats_block(stats))
    conds, joined = _cond_block(rule)
    flat_code = ""
    if flat:
        flat_code = ("\nif barMin >= %d and strategy.position_size != 0\n"
                     "    strategy.close_all(comment = \"session cutoff\")\n" % flat)
    parts = [hdr,
             'strategy("%s", overlay = true, initial_capital = 25000,' % title,
             "     default_qty_type = strategy.fixed, default_qty_value = 1,",
             "     commission_type = strategy.commission.cash_per_order, commission_value = 0.50,",
             "     slippage = 2, pyramiding = 0, calc_on_every_tick = false,",
             "     process_orders_on_close = false)",
             PRELUDE,
             'allowLong  = input.bool(%s, "Allow longs", group = "Direction")' % str(side >= 0).lower(),
             'allowShort = input.bool(%s, "Allow shorts", group = "Direction",' % str(side <= 0).lower(),
             '     tooltip = "This rule was selected because it works in BOTH directions on the " +',
             '     "research block. Turning one side off is exactly the direction-fitting the " +',
             '     "selection was designed to avoid.")',
             'atrMult = input.float(%s, "Stop = N x ATR", minval = 0.25, step = 0.25, group = "Risk")' % _f(am),
             'tpR     = input.float(%s, "Target = N x risk", minval = 0.25, step = 0.25, group = "Risk")' % _f(tp),
             "",
             "// ---- the rule -------------------------------------------------------------------",
             conds,
             "trig = " + joined,
             "",
             "ready = not na(atrV) and atrV > 0 and bar_index > 300",
             "isFlat = strategy.position_size == 0",
             "",
             "// The engine measures the stop and target from the FILL -- the open of the bar after",
             "// the signal -- not from the signal bar's close. `loss` and `profit` are in ticks",
             "// relative to the actual entry price, which is the only Pine primitive that matches.",
             "// Whole ticks are the one unavoidable difference: at most half a tick per side.",
             "if trig and ready and isFlat",
             "    riskTicks = math.max(math.round(atrMult * atrV / syminfo.mintick), 1)",
             "    if allowLong",
             '        strategy.entry("L", strategy.long)',
             '        strategy.exit("Lx", "L", loss = riskTicks, profit = tpR * riskTicks)',
             "    if allowShort",
             '        strategy.entry("S", strategy.short)',
             '        strategy.exit("Sx", "S", loss = riskTicks, profit = tpR * riskTicks)',
             flat_code,
             'plotshape(trig and allowLong,  "long",  shape.triangleup,   location.belowbar, color.teal, size = size.tiny)',
             'plotshape(trig and allowShort, "short", shape.triangledown, location.abovebar, color.red,  size = size.tiny)',
             ""]
    return "\n".join(parts)


def emit_indicator(rule, side, am, tp, flat, tf=30, stats=None, title=None):
    title = title or "Generated signal"
    human = " AND ".join(rule)
    sidetxt = {1: "long only", -1: "short only", 0: "both directions"}[side]
    hdr = _HEADER.format(title=title + " (indicator)", human=human, am=am, tp=tp,
                         flat=(f", flat at {flat // 60}:00" if flat else ", no time stop"),
                         sidetxt=sidetxt, tf=tf, stats=_stats_block(stats))
    conds, joined = _cond_block(rule)
    rows = []
    for i, nm in enumerate(rule):
        rows.append('    table.cell(t, 0, %d, "%s", text_size = size.small, text_color = color.gray)' % (i, nm))
        rows.append('    table.cell(t, 1, %d, c%d ? "yes" : "no", text_size = size.small,' % (i, i))
        rows.append('         text_color = c%d ? color.teal : color.gray)' % i)
    parts = [hdr,
             'indicator("%s (signal)", overlay = true)' % title,
             PRELUDE,
             "// ---- the rule -------------------------------------------------------------------",
             conds,
             "trig = " + joined,
             "ready = not na(atrV) and atrV > 0 and bar_index > 300",
             "",
             "risk = %s * atrV" % _f(am),
             "// drawn on the bar AFTER the signal and measured from its open, because that open is",
             "// where the strategy fills -- the same anchor the engine uses.",
             "fired = trig[1] and ready[1]",
             'plot(fired ? open - risk[1] : na, "stop, long side",',
             "     color = color.new(color.red, 0), style = plot.style_circles)",
             'plot(fired ? open + %s * risk[1] : na, "target, long side",' % _f(tp),
             "     color = color.new(color.teal, 0), style = plot.style_circles)",
             'plotshape(trig and ready, "signal", shape.diamond, location.belowbar,',
             "     color.new(color.teal, 0), size = size.tiny)",
             "bgcolor(trig and ready ? color.new(color.teal, 88) : na)",
             "",
             'alertcondition(trig, "Rule fires", "%s")' % human,
             "",
             "var table t = table.new(position.bottom_right, 2, %d, border_width = 1)" % len(rule),
             "if barstate.islast",
             "\n".join(rows),
             ""]
    return "\n".join(parts)
