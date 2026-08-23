# Correlation matrices over the book as shipped

The earlier matrix study (`STUDY_CORR_MATRIX_2.md`) used the marginal-optimal supply/demand
configuration. The script that shipped carries two different ones — **preset A** (4H zones, 60m
chart, buffer 0.50 ATR, 1.5R, 24h) and **preset B** (4H zones, 30m chart, continuation origin,
RTH, 1R) — so the structure had to be measured again on those. Drawdowns here are on **daily**
marks, not per-trade equity, so they differ slightly from the per-trade figures elsewhere.

## 1. Leg × leg

| | BOS 30m | BOS 60m | BOS 30m LONG | BOS 30m SHORT | S/D A | S/D B |
| --- | --- | --- | --- | --- | --- | --- |
| **BOS 30m core** | 1.00 | 0.27 | 0.75 | 0.65 | **0.12** | **0.12** |
| **BOS 60m core** | 0.27 | 1.00 | 0.18 | 0.22 | **0.06** | **0.03** |
| **S/D preset A** | 0.12 | 0.06 | 0.17 | −0.00 | 1.00 | **0.09** |
| **S/D preset B** | 0.12 | 0.03 | 0.06 | 0.09 | 0.09 | 1.00 |

The two supply/demand presets correlate **+0.09 with each other** despite sharing a zone builder,
a symbol and a sample. Changing the confirmation interval, the target, the origin filter and the
session produces something close to a different strategy.

### Preset A is not the long half of something already owned

Preset A earns $26,431 from longs and loses $7,644 on shorts, so the honest test is against the
**long legs specifically**, not against the two-sided books:

| | ρ | shared days |
| --- | --- | --- |
| S/D A vs BOS 30m **LONG** | **+0.17** | 28 of 371 / 79 |
| S/D A vs BOS 60m **LONG** | +0.11 | 15 of 371 / 24 |
| S/D B vs BOS 30m **LONG** | +0.06 | 24 of 263 / 79 |

Even measured against exactly the exposure it is suspected of duplicating, it is not a duplicate.

## 2. How many independent bets

| book | effective bets | PC1 |
| --- | --- | --- |
| BOS alone (30m + 60m) | 1.93 of 2 | 63% |
| BOS + supply/demand **A** | 2.91 of 3 | 44% |
| BOS + supply/demand **B** | 2.91 of 3 | 44% |
| **BOS + both S/D presets** | **3.89 of 4** | **34%** |

Four legs, 3.89 independent bets. For contrast, the original matrix over BOS *parameter variants*
came out as essentially one trade.

## 3. What each leg adds, research and locked kept apart

| book | full $ | DD | Sharpe | research $ | DD | Sharpe | LOCKED $ | DD | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BOS 30m + 60m | 19,253 | 1,912 | 1.43 | 6,419 | 1,912 | 1.00 | 12,834 | 1,713 | 2.00 |
| + supply/demand A | 51,666 | 5,366 | 2.03 | 24,194 | 3,813 | 1.95 | 27,472 | 5,366 | 2.29 |
| + supply/demand B | 33,537 | 4,585 | 1.71 | 12,243 | 2,148 | 1.32 | 21,294 | 4,585 | 2.27 |
| **+ both presets** | **65,950** | 6,202 | **2.19** | **30,018** | 4,362 | **1.98** | **35,931** | 6,202 | **2.59** |
| S/D A alone | 32,413 | 4,631 | 1.62 | 17,775 | 3,748 | 1.69 | 14,638 | 4,631 | 1.62 |
| S/D B alone | 14,284 | 4,930 | 1.10 | 5,825 | 2,691 | 0.87 | 8,459 | 4,930 | 1.44 |

Every block improves, and the diversification is real rather than notional: the four legs carry
individual daily drawdowns of $1,912, $4,631 and $4,930, summing to $11,473, and the combined
book draws down **$6,202**.

**The cost, stated plainly:** locked P&L rises 2.8× (12,834 → 35,931) while the locked drawdown
rises 3.6× (1,713 → 6,202). Return-over-drawdown therefore *falls*, 7.49 → 5.79. Sharpe rises
because daily volatility diversifies; peak drawdown does not diversify as well. Whether that is an
improvement depends entirely on whether the binding constraint is return or drawdown — on a prop
account with a static drawdown limit it is not.

## 4. State × leg — and a correction to the earlier study

| state | BOS 30m | BOS 60m | BOS 30m LONG | S/D A | S/D B |
| --- | --- | --- | --- | --- | --- |
| prior day return | **−0.23\*** | **+0.46\*** | **−0.38\*** | −0.03 | −0.06 |
| 5d vol / 20d vol | **+0.25\*** | +0.21 | +0.26 | **+0.14\*** | +0.02 |
| ATR / 20d mean ATR | **+0.38\*** | −0.25 | **+0.49\*** | +0.11 | −0.02 |
| dist from 200 EMA | −0.19 | +0.16 | −0.17 | −0.09 | +0.02 |
| 20d momentum | −0.10 | **+0.38\*** | −0.06 | −0.05 | −0.06 |

8 survivors of 56 at Benjamini-Hochberg q = 0.10.

The BOS signatures reproduce: 30m is volatility-expansion and buy-the-dip, 60m is momentum
continuation, and the two have opposite signs on prior-day return.

**The supply/demand signature does not.** `STUDY_CORR_MATRIX_2.md` characterised the S/D leg as a
correction trade on the strength of a **−0.45** correlation with distance from the 200-day EMA.
On the configurations that actually shipped, that number is **−0.09** and **+0.02**. It was a
property of the marginal-optimal configuration, not of supply and demand.

Read that as a warning about the method, not just about one number: a per-configuration state
signature is not stable across configurations of the same strategy, so it is evidence about a
particular parameter set and nothing more.

**Preset B has no state signature at all** — every correlation between −0.06 and +0.08, none
significant. It does not care about volatility regime, momentum, or where price sits against its
long average. Combined with its balanced long/short profile ($4,291/$4,241 long and
$3,388/$3,441 short across research and locked), it is the most regime-independent thing measured
on this branch. It is also the smallest earner, which is usually how that trade-off goes.

## Reproduce

```
python3 research/corr_book.py
```
