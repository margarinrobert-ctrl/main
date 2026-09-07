# Every EMA, every crossover, every trend indicator — 5,723,136 combinations, nothing survives

*Second pass at the same structure, with the pool widened as far as the toolbox goes and the gate
that let the first family through replaced.*

*Result:* **127 rules reached the holdout after beating a time-matched random entry on the research
block. Zero survived. About 6.4 would have passed by chance.** Across three timeframes, in the
right order, with the harder null in front.

---

## 1. What was added

`research/trendind.py` — the trend indicators the shared library lacked, at their published
definitions: **Supertrend, Ichimoku (Tenkan/Kijun/cloud), Parabolic SAR, Hull, KAMA, DEMA, TEMA,
Vortex, Aroon, Heikin-Ashi.** The two recursive ones (PSAR, KAMA) are explicit forward loops
because a vectorised shortcut for either is easy to write and easy to make peek.

`research/trendpool.py` — the pool, per side:

| | n | what is in it |
| --- | --- | --- |
| trend states | **46** | close vs each of 15 EMAs (5, 8, 9, 10, 12, 20, 21, 26, 34, 50, 55, 89, 100, 144, 200); 13 crossover pairs (5/20, 8/21, 9/21, 10/20, 12/26, 20/50, 21/55, 34/89, 50/100, 50/200, 55/200, 89/200, 100/200); Supertrend, Kijun, cloud, PSAR, KAMA, Hull, Vortex, Aroon, MACD, ADX+DI, LR slope; plus the **daily** states |
| pullbacks | **36** | pull below each of 10 EMAs, below EMA20/50 by 0.5 and 1 ATR, below VWAP, at 3/5/10/20-bar low, RSI<35/40/45/50, Stoch<20/30/40, 2/3/4 against-closes, retrace >0.5/1.0/1.5 ATR, below Tenkan, bottom third of the 10-bar range, MACD histogram against, touched EMA20 |
| resumptions | **24** | cross back above EMA9/20/21/50, close beyond prior bar, beyond 2/3/5-bar extreme, engulfing, first and second with-trend close, RSI back above 40/45/50, Stoch back above 20/30, MACD histogram turns, Heikin flip, close in far third, with-trend bar >1 ATR, Tenkan cross, Supertrend flip, PSAR flip, VWAP cross |

46 × 36 × 24 = **39,744 rules per side** × 24 geometries × 2 sides × 3 timeframes =
**5,723,136 combinations**. Entries 07:00–11:00 New York throughout. Direction dictated by the
daily trend. No mean reversion is expressible: the pullback is always against the trend and the
entry always with it.

## 2. The gate that changed, and why

The first pass gated on excess over the mean win rate of the **rule population**. 1,158 rules
cleared it and the time-matched control then rejected every one — the plain "be long in this
window" baseline was worth more than the rules were. A gate that admits rules a stronger null
then rejects is not a gate, it is a delay.

Two changes:

1. **The base rate is now the WINDOW BASELINE** — what entering at every eligible bar inside
   07:00–11:00 earns under the same side and geometry. A rule must beat *being in the market at
   those times*.
2. **The matched control runs on RESEARCH, as a gate.** Last time it ran only after the holdout
   had been read. Now nothing reaches the holdout without first beating 250–300 random-entry draws
   matched on side, geometry and minute-of-day, on the research block.

**The window baseline is itself negative: 44.8–48.4% win and −$22.3 to −$4.6 per trade.** Entering
at every bar in 07:00–11:00 with these geometries loses money. That is a much harder bar than the
first pass used, and it is worth knowing on its own.

## 3. The funnel

| | 30m | 15m | 5m |
| --- | --- | --- | --- |
| combinations | 1,089,960 × 2 sides | same | same |
| triples with 30+ research trades | 608,457 | — | — |
| beat the window baseline + subset coherence | 9,131 | 18,660 | 33,603 |
| after collapsing rules sharing 2+ conditions | 70 | 60 | 60 |
| **beat the matched control on RESEARCH** | **48** | **46** | **33** |
| expected to pass the holdout by chance | 2.4 | 2.3 | 1.7 |
| **survive Benjamini-Hochberg on the holdout** | **0** | **0** | **0** |

**127 candidates, 6.4 expected by chance, 0 survivors.**

On 5-minute bars exactly two reached raw p < 0.05 on both statistics — `ADX>20 and +DI>-DI +
bottom third of 10-bar range + cross VWAP` (p 0.033 / 0.003) and `Hull rising + retrace >0.5 ATR +
Stoch back above 20` (p 0.033 / 0.027). Against 1.7 expected by chance, two is exactly chance, and
both carry q = 0.548 after correction.

And the shape is right this time. The first pass produced rules that **failed on research and
passed on the holdout**, which is backwards and was the tell. These fail on the holdout after
passing research, which is what an overfit rule is supposed to look like.

## 4. What this does and does not say

**It does say:** on NQ, 2022-12 to 2025-12, in the 07:00–11:00 New York window, no combination of
daily-trend state, pullback and resumption drawn from this toolbox produces an edge that survives
a holdout with a time-matched control in front of it. Fifteen EMA periods, thirteen crossover
pairs and nine other trend indicators do not change that, and the search was large enough
(5.7 million) that if a simple combination worked it would have appeared.

**It does not say** trend-following does not work. It says this *structure*, on this *instrument*,
over *this* sample, at *these* entry times, does not — and three specific limits are worth naming
rather than hiding:

* **81% of bars sit in a daily uptrend, 7% in a downtrend.** The sample contains essentially one
  regime. A trend-following system's whole claim is that it survives regime change, and this data
  cannot test that.
* **07:00–09:30 is pre-RTH** and the cost model does not widen the spread there. Every pre-market
  figure in this study is optimistic by an unmodelled amount.
* **Three years is short** for a daily-trend system. The daily EMA200 alone consumes 200 of 765
  sessions before it is defined.

## 5. The recommendation that survives both passes

**Trade 09:30–11:00, not 07:00–11:00.** Measured in the first pass and unchanged: the same rule
returns $4.2 per trade on research in the cash-session half against $1.1 across the full window and
$1.9 in the pre-market half, on 44% fewer trades and with nearly all of the locked dollars. Every
candidate showed the same split individually. That is a window choice backed by measurement, not
an edge claim.

## 6. What would actually move this forward

Ranked by how much they would change the answer per unit of work:

1. **More history.** Ten years of NQ would contain 2018, 2020 and 2022 — three regime changes the
   current sample lacks. This is the single biggest constraint and everything else is second.
2. **Cross-asset files.** ES, DX, ZN and VX bars on the same clock in `data/`. Trend-following
   systems are usually rescued by *confirmation* across correlated instruments, and that family is
   currently unbuildable (`features3.NEEDS_DATA`).
3. **A second instrument to test the same structure on.** A rule that works on NQ and ES and CL is
   a different object from one that works on NQ.

## Files

| | |
| --- | --- |
| `research/trendind.py` | Supertrend, Ichimoku, PSAR, Hull, KAMA, DEMA, TEMA, Vortex, Aroon, Heikin-Ashi |
| `research/trendpool.py` | 46 trend states × 36 pullbacks × 24 resumptions per side, window baseline |
| `research/trendpool_search.py` | sweep, window-baseline gate, coherence, matched control on research, then the holdout |

Measured on MNQ, 2022-12-27 → 2025-12-11, one contract, $1.00 commission per round turn, one tick
spread plus one tick slippage each side, one extra tick on stops. **The cost model does not widen
the spread before 09:30.** Research tooling for education and analysis, not financial advice.
