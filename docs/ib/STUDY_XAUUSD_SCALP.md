# XAUUSD intraday trend scalping: NO ROBUST EDGE FOUND

*Brief: discover whether a robust, repeatable, long-side intraday trend-following scalping edge
exists in XAUUSD, using NQ / US100 / US30 as independent context and robustness tests rather than
as four votes for the same strategy. Preserve an untouched final period. Do not manufacture
profitability.*

**Result: `NO ROBUST XAUUSD SCALPING EDGE FOUND`.** The best trend-following configuration
discovered has a **positive gross edge on the research block (+0.0669 R/trade) that halves on
validation, turns negative on test, and is negative on the untouched final period.** It is
negative net of realistic costs on every block including research.

Two structural findings are worth more than the strategy search: **gold's cost floor is roughly
three times the indices'**, and the one lever that helped — the chop filter — helps here too, and
still is not enough.

`research/scalp/`, `research/edgelab/feeds.py`.

---

## 1. Dataset inventory

| | XAUUSD | US30 | US100 | NQ |
| --- | --- | --- | --- | --- |
| file | `XAUUSD_5m.csv` | `US30_1m.csv` / `US30_5m.csv` | `US100_15m.csv` | `NQ_5m.csv` |
| format | semicolon, `Date;OHLC;Volume` | MT tab export | MT tab export | repo ingest |
| timestamp | `YYYY.MM.DD HH:MM`, **ascending** | `…HH:MM:SS`, **descending** | same | ISO-8601 UTC |
| span | **2004-06-11 → 2026-01-30 (21.6y)** | 2016-10-26 → 2025-07-15 | 2016-11-14 → 2025-10-01 | 2022-12-26 → 2025-12-11 |
| rows | 1,443,451 | 2,880,287 / 581,195 | 206,703 | 210,516 |
| volume means | tick count | TickVolume (`Volume` is zero) | TickVolume (`Volume` is zero) | exchange volume |
| bid/ask | **not available** | not available | not available | not available |
| duplicates / OHLC violations | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| **quality score** | **92.5** | 98.0 / 100.0 | 100.0 | 100.0 |

Four different source formats, three different meanings of "volume", two different sort orders.
**No feed's assumptions were inherited by another.** Nothing was deleted: 494 XAUUSD returns beyond
20 robust sigma are flagged and **kept**.

**Bid/ask is unavailable in every feed, so the spread can only be assumed, never measured.** For
gold that assumption turns out to decide the entire result — see §3.

### Pre-2010 XAUUSD is excluded, with cause

| era | bars | median 5m ATR | zero-range bars | median volume |
| --- | ---: | ---: | ---: | ---: |
| **2004–2009** | 336,714 | 0.54 | **10.06%** | **14** |
| 2010–2014 | 336,002 | 0.90 | 0.08% | 227 |
| 2020–2022 | 211,254 | 1.17 | 0.01% | 330 |
| 2025–2026 | 68,235 | 2.72 | 0.00% | 363 |

One bar in ten has no range at all before 2010 and the median five-minute bar sees fourteen ticks.
That is a quote feed idling, not a market, and no barrier result computed on it would mean
anything. Research starts 2010-01-01.

### The clock was derived, not assumed

Gold does not key on the 09:30 cash equity open, so the anchor used for the index feeds is wrong
for it. Two independent checks agree on **New York + 7**:

* the summer peak in mean |5-minute return| falls at raw **15:30**, which is the **08:30 New York
  data release to the minute**;
* `corr(US30, XAUUSD)` — US30's clock being already verified — spikes to **+0.057 at a 7-hour
  shift** against roughly zero at 5, 6 and 8.

After the shift, the peak-volatility minute lands at exactly **08:30 New York**.

### Splits, with an untouched tail

| block | span | bars |
| --- | --- | ---: |
| research | 2010-01-03 → 2017-12-29 | 545,505 |
| validation | 2018-01-02 → 2021-12-31 | 280,414 |
| test | 2022-01-02 → 2024-12-31 | 212,583 |
| **untouched** | **2025-01-01 → 2026-01-30** | **68,235** |

The untouched block was read **once**, at the end, after the rule was frozen.

## 2. Time of day

20-bar Donchian breakout long, research block, by New York hour:

| hour | 00:00 | 03:00 | 07:00 | 08:00 | **09:00** | **10:00** | 11:00 | 15:00 | 20:00 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| E[R] | −1.70 | −1.01 | −0.71 | −0.55 | **−0.35** | **−0.27** | −0.43 | −0.78 | −1.34 |
| win % | 10.2 | 32.4 | 44.8 | 46.1 | 48.2 | 49.6 | 44.0 | 42.2 | 19.5 |

Overnight gold is catastrophic for a breakout — the spread is unchanged while the range collapses.
**09:00–11:00 is the only viable part of the day**, and the briefed 07:00–12:00 window includes two
hours (07:00, 08:00) that are materially worse. All work below uses **09:00–13:00**, and the
briefed window is reported alongside.

## 3. The cost floor, which is the real story

Break-even at 1:1 is `(1 + cost_R) / 2`. On XAUUSD, 09:00–13:00, 20-bar breakout:

| stop | stop in USD | cost as fraction of R | **win rate needed** | actual |
| --- | ---: | ---: | ---: | ---: |
| 0.35×ATR | 0.51 | **1.016** | **100.8%** | 30.7% |
| 0.50×ATR | 0.73 | 0.711 | 85.6% | 42.0% |
| 0.75×ATR | 1.10 | 0.474 | 73.7% | 46.0% |
| 1.00×ATR | 1.46 | 0.356 | 67.8% | 45.8% |
| 3.00×ATR | 4.38 | 0.119 | 55.9% | 38.7% |
| 6.00×ATR | 8.77 | 0.059 | 53.0% | 38.2% |

**At a true scalping stop the break-even win rate is above 100%** — the assumed 0.30 USD/oz spread
equals the entire stop distance. This is far worse than the indices, where the same table tops out
around 0.13 of R, because gold's five-minute ATR (~1.5 USD) is barely five times its spread.

**No stop distance closes the gap.** The best cell is 6×ATR at −0.054, and there the requirement is
53.0% against an actual 38.2%.

## 4. It is not a cost problem — the signal is absent gross

Zero-cost expectancy, research block, 09:00–13:00:

| entry | 0.75×ATR | 1.5×ATR | 3.0×ATR |
| --- | ---: | ---: | ---: |
| Donchian breakout 10 | −0.061 | −0.035 | −0.016 |
| Donchian breakout 20 | −0.052 | −0.030 | −0.015 |
| Donchian breakout 60 | −0.034 | −0.006 | +0.003 |
| breakout + ADX > p85 | −0.022 | +0.001 | +0.009 |
| **breakout + not-chop p95** | −0.034 | **+0.067** | +0.062 |
| continuation: 2 up closes | −0.049 | −0.020 | −0.010 |
| pullback then reclaim EMA20 | −0.040 | −0.020 | −0.014 |
| *off the 10-bar low (mean reversion)* | *+0.021* | *+0.025* | *+0.007* |
| every bar (baseline) | −0.011 | −0.005 | −0.003 |

**Every trend-following entry is negative gross at a scalping stop.** Only the chop-filtered
breakout turns positive, and only at 1.5×ATR or wider.

**The failure is symmetric, not directional.** The mirrored short side is also negative gross
(20-bar breakdown −0.047, 60-bar −0.020), so this is not a long-only bias — the breakout signal is
simply absent on gold intraday.

*(The counter-trend entry is positive gross and is reported for completeness only; the brief
excludes mean reversion by instruction, not by measurement.)*

## 5. The chop filter works here too, and still is not enough

The lever that helped on the indices helps on gold, monotonically — best gates on the research
block, net of the assumed spread, against a −0.2412 base:

| gate | n | E[R] | vs base |
| --- | ---: | ---: | ---: |
| negated Choppiness(28) > p95 | 624 | −0.0825 | **+0.159** |
| efficiency ratio(50) > p95 | 879 | −0.1014 | +0.140 |
| VHF(28) > p95 | 727 | −0.1030 | +0.138 |
| ADX > p95 | 702 | −0.1193 | +0.122 |

**A +0.16 R rescue, and 0 of 46 gates reach positive net expectancy.** Same shape as the index
study: chop filtering closes the cost gap, it does not open one.

## 6. The frozen rule, and the untouched block

```
entry    20-bar Donchian high breakout, LONG
regime   negated Choppiness(28) > -34.507   (research p95: the least choppy 5%)
window   09:00-13:00 New York, flat at window end
stop     1.5 x ATR(14)      target 1.0R      max hold 12 bars (60 min)
```

Every parameter fixed on research 2010–2017. Nothing re-optimised afterwards.

| block | n | days | win % | **GROSS E[R]** | NET E[R] | PF | max DD | excess vs control | p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| research | 624 | 210 | 50.0 | **+0.0669** | −0.0825 | 0.82 | 53.4 R | +0.1488 | **0.003** |
| validation | 392 | 94 | 49.7 | **+0.0421** | −0.1207 | 0.76 | 56.5 R | +0.1108 | 0.050 |
| test | 340 | 85 | 46.5 | **−0.0163** | −0.1274 | 0.75 | 45.2 R | +0.0259 | 0.360 |
| **untouched** | **125** | **29** | **52.8** | **−0.0199** | **−0.0880** | 0.81 | 26.7 R | **−0.0352** | **0.637** |

**The gross edge halves, then dies.** +0.067 → +0.042 → −0.016 → −0.020, with the control excess
following it down from +0.149 to **−0.035** on the untouched block. This is monotone decay across
four chronologically ordered blocks, which is what an overfit parameter looks like, and the
untouched period — the closest thing here to a deployment simulation — is the worst of the four.

**Break-even spread**, research block only:

| spread (USD/oz) | 0.30 | 0.20 | 0.15 | **0.13** | 0.10 | 0.05 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| net E[R] | −0.0825 | −0.0327 | −0.0078 | **+0.0022** | +0.0171 | +0.0420 |

The rule needs roughly **0.13 USD/oz all-in** to break even *on the block it was fitted to*. Since
its gross edge is negative out of sample, no execution improvement rescues it: at zero cost the
untouched block still returns −0.0199.

## 7. Cross-market: `NO RELIABLE LEAD/LAG FOUND`

`corr(other market at t−k, XAUUSD at t)`, 5-minute returns:

| | k=0 | k=1 | k=2 | k=3 |
| --- | ---: | ---: | ---: | ---: |
| US30 | +0.0571 | −0.0010 | −0.0016 | +0.0027 |
| US100 | +0.0604 | +0.0051 | +0.0034 | +0.0068 |
| NQ | +0.0698 | −0.0005 | +0.0002 | −0.0006 |

Every relationship is **contemporaneous only** — the lagged correlations are an order of magnitude
smaller and change sign. No index predicts the next XAUUSD bar.

Worth stating separately: the contemporaneous correlation is only **0.057–0.070**. Gold is
effectively uncorrelated with the three indices intraday, which makes it a genuinely independent
market and makes the brief's design — XAUUSD primary, indices as context — the right one. It also
means the indices cannot vote on a gold strategy, and they were not asked to.

## 8. Overfitting assessment

| factor | reading |
| --- | --- |
| hypotheses tested | ~400 (9 Donchian lookbacks × 9 stops × 6 targets × 5 holds, 46 regime gates, 10 entry families) |
| train → untouched degradation | **+0.0669 → −0.0199 gross**, a full sign change |
| walk-forward consistency | monotone decay across four ordered blocks |
| parameter sensitivity | the p95 chop threshold is at the extreme tail; p85 gives roughly half the effect |
| sample size | 624 research trades, **125 untouched** |
| **overfitting risk** | **HIGH** — the shape is a fitted threshold, not a mechanism |

## 9. Verdict, and what to research next

| claim | status |
| --- | --- |
| A long-side intraday trend-following scalping edge exists in XAUUSD | **REJECTED** |
| The Donchian/Turtle breakout transfers to gold intraday | **REJECTED** — negative gross at every scalping stop, on both sides |
| Chop filtering improves a gold breakout | **SUPPORTED** — +0.16 R, monotone — but 0 of 46 gates reach positive net |
| Another market leads gold | **REJECTED** — `NO RELIABLE LEAD/LAG FOUND` |
| Costs are the binding constraint | **PARTLY** — they are brutal (100.8% break-even at a scalping stop), but the signal is negative even at zero cost |

**What should be researched next**, in order of expected value:

1. **Give up the scalp, keep the filter.** The only positive gross cells in this study are at
   1.5–3.0×ATR stops with 60-minute-plus holds. That is a gold *swing* trade, and it is where the
   chop filter's +0.16 R would actually clear a 0.13-of-R cost floor. The scalping constraint, not
   the trend hypothesis, is what fails.
2. **Get bid/ask data.** Every cost figure here is an assumption, and on gold the assumption
   decides the answer — the difference between 0.30 and 0.13 USD/oz is the difference between
   −0.08 and break-even on the research block. No further parameter search is worth running until
   the spread is measured rather than assumed.
3. **Test the counter-trend result properly.** `off the 10-bar low` is the only entry with positive
   gross expectancy at *every* stop tested. It is excluded by instruction here; it is also, for the
   fifth time on this branch, the thing the data keeps pointing at.

## Files

| | |
| --- | --- |
| `research/edgelab/feeds.py` | four-instrument loader, per-feed clock derivation, XAUUSD parser |
| `research/scalp/inventory.py` | dataset inventory and transparent quality score |
| `research/scalp/core.py` | XAUUSD splits including the untouched block, per-instrument costs |
| `research/scalp/regime.py` | eleven causal chop/trend measures |
| `research/scalp/validate.py` | walk-forward, Monte Carlo, robustness, both statistics |

Measured on XAUUSD 5-minute (2010–2026 usable), with US30 / US100 / NQ as independent context.
Costs assumed, not measured — bid/ask is unavailable in every feed. Research tooling for education
and analysis, not financial advice.
