# What a trend-following scalp actually needs — 31 conditions, two geometries, one experiment

`research/scalpreq/sr_core.py`, `run_sr.py`, `run_sr2.py`. Output `results/scalpreq/report.txt`,
`arithmetic.txt`, `conditions.csv`, `summary.csv`.

The question "which indicators does a profitable trend-following scalp need" is not answerable by
listing indicators. It is answerable by taking one trend-following trigger and asking of every
candidate condition: what fraction of the trigger's own signals does it even remove, what does it
contribute at SCALP geometry, and what does it contribute at SWING geometry. The third column is
what makes the answer honest.

**Design.** Two triggers (a Donchian 20 breakout; an EMA 13/34/89 stack no more than 30 bars old),
31 declared conditions in six families, two geometries — **scalp** = 0.75 ATR stop / 1.5 ATR target
/ 24-bar cap, **swing** = 2.5 ATR stop / no target / 480-bar cap — on six feed-timeframes (NQ 5m
and 30m, US100 15m and 60m, US30 15m and 60m) across every block. Same bars, same costs, one
position at a time.

---

## 1. The trigger alone, before any indicator

| trigger | geometry | blocks positive | n | %/trade |
|---|---|---|---|---|
| Donchian 20 breakout | **scalp** | **4/16** | 39,309 | **−0.0033** |
| Donchian 20 breakout | swing | 12/16 | 4,679 | **+0.0948** |
| EMA 13/34/89 stack | **scalp** | **3/16** | 36,545 | **−0.0052** |
| EMA 13/34/89 stack | swing | 14/16 | 3,665 | **+0.1191** |

Same signals, same bars, same costs. **The geometry flips the sign.** Any indicator search that
starts from the scalp row is trying to climb out of a hole the geometry dug.

## 2. The arithmetic, which decides the answer before any indicator

Cost expressed as a **fraction of risk** — the only way to compare it across instruments:

| feed | median ATR | round turn | cost / risk at 0.75N | break-even at 2R | cost / risk at 2.5N | break-even at 2R |
|---|---|---|---|---|---|---|
| NQ 5m | 12.15 | 2.22 | **24.4%** | **41.5%** | 7.3% | 35.8% |
| NQ 30m | 33.05 | 2.22 | 9.0% | 36.3% | 2.7% | 34.2% |
| US100 15m | 15.79 | 1.70 | 14.4% | 38.1% | 4.3% | 34.8% |
| US100 60m | 36.77 | 1.70 | 6.2% | 35.4% | 1.8% | 33.9% |
| US30 15m | 30.40 | 3.20 | 14.0% | 38.0% | 4.2% | 34.7% |
| US30 60m | 66.90 | 3.20 | 6.4% | 35.5% | 1.9% | 34.0% |

The driftless break-even at a 2:1 payoff is 33.3%. Every point above it is the round turn. On NQ
5-minute bars at a scalping stop the round turn is **24.4% of the risk** and pushes the requirement
to **41.5%**.

**And the trigger delivers 34.3% and 33.6%** — within a point of the free bound. So the raw
trend-following trigger has essentially **no directional edge at a 2R payoff on a scalping barrier
pair**, before costs are charged at all.

| trigger | geometry | net | **gross (zero cost)** | the cost | win | needs |
|---|---|---|---|---|---|---|
| Donchian 20 | scalp | −0.0033 | **+0.0039** | +0.0073 | 34.3% | 33.3% |
| Donchian 20 | swing | +0.0948 | +0.1025 | +0.0077 | 16.5% | — |
| EMA stack | scalp | −0.0052 | **+0.0023** | +0.0075 | 33.6% | 33.3% |
| EMA stack | swing | +0.1191 | +0.1276 | +0.0085 | 17.0% | — |

**The scalp fails twice over: a gross edge of +0.002 to +0.004, and a cost of +0.007 to +0.009 that
exceeds it.** Run the zero-cost variant before blaming execution — here it says the geometry is
wrong, not the fills.

## 3. What each indicator actually contributes

Percent of price per trade over the unfiltered trigger, averaged across all cells, with the share
of cells improved. Sorted by the swing column.

| family | condition | keeps | **scalp edge** | helps | **swing edge** | helps |
|---|---|---|---|---|---|---|
| trend | **(close−SMA200)/ATR ≥ 1** | 77.2% | +0.0064 | 78% | **+0.0662** | 72% |
| regime | **ADX ≥ 25** | 45.4% | **−0.0006** | 59% | **+0.0587** | 78% |
| momentum | RSI(14) ≥ 65 | 44.2% | +0.0066 | 69% | +0.0469 | 75% |
| regime | efficiency ratio ≥ 0.3 | 49.1% | +0.0031 | 69% | +0.0460 | 78% |
| regime | **ATR ≥ its 50-bar mean** | 43.6% | +0.0044 | 72% | +0.0431 | 72% |
| trend | close > SMA200 | 84.1% | +0.0041 | 69% | +0.0407 | 69% |
| location | (close−VWAP)/ATR ≥ 0.5 | 72.9% | +0.0025 | 78% | +0.0277 | 75% |
| regime | CHOP ≤ 45 | 47.9% | +0.0020 | 66% | +0.0274 | 62% |
| trend | close > EMA50 | 93.7% | +0.0025 | 88% | +0.0258 | 81% |
| trend | EMA 13>34>89 stacked | 83.8% | +0.0035 | 50% | +0.0228 | 34% |
| clock | 09:30-11:00 New York | 8.8% | +0.0072 | 56% | +0.0082 | 56% |
| clock | 09:30-16:00 New York | 34.3% | **+0.0080** | 78% | +0.0068 | 69% |
| location | close > prior RTH high | 52.4% | +0.0049 | **81%** | +0.0075 | 62% |
| volume | **volume ≥ 1.5× its t-o-d mean** | 25.2% | **+0.0093** | 61% | **−0.0549** | 33% |
| location | close in top 30% of bar | 42.1% | +0.0019 | 56% | −0.0062 | 47% |

By family:

| family | conditions | keeps | **scalp edge** | helps | **swing edge** | helps |
|---|---|---|---|---|---|---|
| trend | 7 | 85.7% | +0.0032 | 71% | **+0.0287** | 66% |
| regime | 9 | 48.1% | +0.0008 | 56% | **+0.0259** | 63% |
| momentum | 7 | 77.9% | +0.0016 | 54% | +0.0197 | 65% |
| location | 4 | 53.5% | +0.0032 | 70% | +0.0106 | 64% |
| **clock** | 2 | 21.5% | **+0.0076** | 67% | +0.0075 | 62% |
| volume | 2 | 39.5% | +0.0056 | 65% | −0.0197 | 39% |

### The four things this table says

**1. Every family is worth roughly a TENTH as much at scalp geometry as at swing.** Trend +0.0032
against +0.0287; regime +0.0008 against +0.0259; momentum +0.0016 against +0.0197. Indicators are
not the missing ingredient in a scalp — the payoff structure is.

**2. The clock is the only family where scalp ≈ swing, and at scalp geometry it is the LARGEST
contributor of any family** (+0.0076 against trend's +0.0032). For a scalp, *when* matters more
than *which indicator*. That is consistent with ten prior measurements here that the pre-open block
is subtractive and a 09:30 start rescues an intraday window.

**3. Two conditions invert between the geometries, and both inversions are mechanical.**
`ADX ≥ 25` is the second-best swing condition (+0.0587, 78% of cells) and is **negative** at scalp
(−0.0006) — a trend-strength filter needs a trade long enough for the trend to pay. `Volume ≥ 1.5×
its time-of-day mean` is the **best scalp condition (+0.0093)** and the **worst swing condition
(−0.0549)** — a participation spike marks a move that is resolving now and over soon.

**4. Most of the popular ones are the trigger restated.** `close > EMA50` passes **93.7%** of
signals, `MACD > 0` 93.2%, `ROC(20) > 0` 91.0%, `EMA13 > EMA48` 90.9%, `Aroon osc ≥ 0` 88.1%. They
cannot filter what they already agree with. This is the fifth independent measurement of that
mechanism here (RSI 94.7%, Aroon 100.0%, MACD 99.8–100.0%, MFI 91.7%).

## 4. The answer

**A profitable trend-following scalp needs, in order of measured contribution:**

1. **A session filter** — 09:30–16:00 New York, and 09:30–11:00 if you want concentration. Largest
   scalp contributor of any family (+0.0080 / +0.0072) and the only one that does not shrink when
   the geometry tightens.
2. **A participation filter** — volume at or above 1.5× its own time-of-day mean (+0.0093), which
   is the single best scalp condition measured and is *actively harmful* at swing geometry.
3. **A volatility floor** — ATR at or above its 50-bar mean (+0.0044, 72%). Cost is a fraction of
   risk, so a scalp must not trade when risk is small.
4. **A trend location, expressed as a DISTANCE** — `(close − SMA200)/ATR ≥ 1` (+0.0064, 78%), not
   `close > SMA200` (+0.0041). It is a floor, not support.
5. **A structural level** — close above the prior completed RTH session high (+0.0049, and the
   highest consistency in the table at **81%** of cells).

**And it still does not clear.** The base is −0.0033 to −0.0052 and the gross edge is +0.002 to
+0.004. These conditions overlap heavily — you cannot sum them — and the best single one delivers
+0.0093 at 61% consistency. That makes a scalp arithmetically **marginal**, not comfortable: you
need essentially the best condition in the table working at full strength just to reach zero.

**What actually changes the answer is the geometry, not the indicator list.** The same triggers,
same bars and same conditions at swing geometry earn +0.0948 and +0.1191 with 12/16 and 14/16
blocks positive. That is the thirteenth independent confirmation on this branch that the intraday
scalping constraint is what fails.

**If a scalp is a requirement rather than a preference**, the arithmetic says where to spend:
move to the instrument and timeframe where the round turn is the smallest fraction of the stop
(US100 60m at 6.2%, against NQ 5m at 24.4% — nearly four times), and get a **measured** spread
instead of an assumed one, since bid/ask is unavailable in every feed here and the cost term is
larger than the entire gross edge.
