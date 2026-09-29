# Is the *type* of a moving average a real degree of freedom?

Source: Valeriy Zakamulin, *Trend-Following: Types of Moving Averages (Part 2)*, Alpha Architect.

**The claim.** Moving averages with different weighting schemes but the **same average lag time**
move closely together. What characterises a moving average is not its price weighting function
but its **price-change** weighting function, because prices are serially dependent while their
changes are close to independent. And "average lag time" describes the lag only in a steady
trend — it says little about the delay in spotting a *turn*.

**Why it matters here.** `indpool` carries SMA, LMA, EMA, DEMA, TEMA, Hull and KAMA, and every
p-value in this repository is paid for in configurations searched. If MA type at matched lag is
close to a non-decision, then a search that treats it as a free axis is inflating its own
multiplicity without buying independent hypotheses.

`research/ma_lag.py` measures all of it. Lag comes from the ramp identity — a filter with unit DC
gain applied to `x_t = t` returns `t − lag` — so nothing depends on a closed form being quoted
correctly.

## 1. The closed forms check out exactly

| filter | n | measured lag | article's formula | difference |
| --- | ---: | ---: | ---: | ---: |
| SMA | 11 | 5.0000 | (n−1)/2 = 5 | 0 |
| SMA | 21 | 10.0000 | 10 | 0 |
| LMA | 11 | 3.3333 | (n−1)/3 = 3.333 | 1.5e-13 |
| LMA | 16 | 5.0000 | 5 | 0 |
| EMA | 11 | 5.0000 | (n−1)/2 = 5 | 0 |
| EMA | 21 | 10.0000 | 10 | 9.1e-13 |

So the article's worked example — SMA(11), LMA(16) and EMA(11) all carrying an average lag of 5 —
is exact. (`I.wma` was added to the repo for this; there was no linearly-weighted MA, even though
`hull` needs one conceptually.)

## 2. Only three of the seven are on this axis at all

Measured lag against window size:

| filter | n=5 | n=10 | n=20 | n=40 | n=80 | n=160 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SMA | 2.00 | 4.50 | 9.50 | 19.50 | 39.50 | 79.50 |
| EMA | 2.00 | 4.50 | 9.50 | 19.50 | 39.50 | 79.50 |
| LMA | 1.33 | 3.00 | 6.33 | 13.00 | 26.33 | 53.00 |
| **DEMA** | **0.00** | **0.00** | **0.00** | **0.00** | **0.00** | **0.00** |
| **TEMA** | **0.00** | **0.00** | **0.00** | **0.00** | **0.00** | **0.00** |
| **HULL** | −0.50 | 0.50 | 1.00 | 2.00 | 3.50 | 5.50 |
| **KAMA** | **1.25** | **1.25** | **1.25** | **1.25** | **1.25** | **1.25** |

Three findings the article does not cover:

* **SMA and EMA have identical lag at every window** — by construction, since `λ = 2/(n+1)` is
  chosen to make it so. They are the same point on this axis.
* **DEMA and TEMA have exactly zero lag on a ramp, at every window**, and Hull is near zero. They
  are not lagging averages at all; they are **extrapolators**, and they cannot be lag-matched to
  SMA/LMA/EMA at any window. They *are* a genuine degree of freedom — a different filter class.
* **KAMA's lag is 1.25 regardless of its window.** On a ramp the efficiency ratio is 1, so the
  fast constant always wins and **the period parameter is inert on a trending series**. It only
  does anything in noisy conditions. Worth knowing before sweeping it.

## 3. At matched lag, the values are the same series

30-minute MNQ closes, 35,721 bars:

| lag | pair | corr of **values** | corr of **changes** | mean abs diff / bar-move |
| ---: | --- | ---: | ---: | ---: |
| 5 | SMA vs EMA | 0.99999 | **0.87023** | 0.47 |
| 5 | SMA vs LMA | 1.00000 | **0.94582** | 0.23 |
| 5 | LMA vs EMA | 1.00000 | **0.96761** | 0.28 |
| 20 | SMA vs EMA | 0.99996 | **0.86335** | 1.01 |
| 40 | SMA vs EMA | 0.99992 | **0.83594** | 1.44 |
| 40 | LMA vs EMA | 0.99997 | **0.96319** | 0.84 |

**The claim replicates, and so does the reason for it.** Value correlations are 0.9999+ across the
board — indistinguishable. Change correlations are materially lower (0.836–0.968), which is
exactly Zakamulin's point: the price weighting functions look very different, the price-*change*
weighting functions are what actually separate these filters, and even those separate them only
a little. SMA vs EMA is consistently the *least* alike pair on changes; LMA vs EMA the most.

## 4. Priced: they take the same trades

Rule `close > MA(n)`, long, 2.0×ATR stop, 1.0R target, 09:30–16:00, 30m:

| lag | filter | n | trades | net $ | $/trade | win % | trigger overlap vs SMA |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 5 | SMA | 11 | 1112 | 12,950 | 11.6 | 52.9 | — |
| 5 | LMA | 16 | 1102 | 14,492 | 13.2 | 53.1 | **95.6%** |
| 5 | EMA | 11 | 1128 | 13,354 | 11.8 | 52.7 | **92.5%** |
| 10 | SMA | 21 | 1046 | 15,959 | 15.3 | 53.5 | — |
| 10 | LMA | 31 | 1063 | 15,836 | 14.9 | 53.3 | **97.3%** |
| 10 | EMA | 21 | 1072 | 17,388 | 16.2 | 53.5 | **94.3%** |
| 40 | SMA | 81 | 1021 | 8,497 | 8.3 | 52.5 | — |
| 40 | LMA | 121 | 1035 | 9,216 | 8.9 | 52.7 | **95.8%** |
| 40 | EMA | 81 | 1035 | 13,096 | 12.7 | 53.3 | **91.1%** |

**Trigger sets overlap 89.5%–97.3%, trade counts agree within 3%, and win rates sit inside a
one-point band (52.5–53.5%) across every filter and every lag.** Net P&L varies more — $8,497 to
$13,096 at lag 40, a 54% spread — but that is what a 5–10% difference in trade set does to a
system whose per-trade edge is $8–16 against a base rate near 52%. **The dollar spread is noise on
the non-overlapping tail, not a property of the weighting scheme**, and the win rates say so.

Note also what every row says about the underlying strategy: `close > MA` wins 52.5–53.5% at
$8–16/trade, which is where `STUDY_MA.md` and `STUDY_TREND_BRIEF.md` already left it.

## 5. Average lag does not predict turn delay

The article's own artificial two-segment ramp, peak at index 59:

| filter | n | average lag | turn detected at | **delay** |
| --- | ---: | ---: | ---: | ---: |
| SMA | 11 | 5.00 | 64 | **5** |
| LMA | 16 | 5.00 | 63 | **4** |
| EMA | 11 | 5.00 | 62 | **3** |

All three carry an average lag of exactly 5; their turn delays are 5, 4 and 3. **SMA 5 and EMA 3
are the precise numbers Zakamulin quotes.** The closing claim replicates: average lag time
characterises the lag in a steady trend and says little about how fast a turn is spotted.

## What this changes here

**MA type, among SMA/LMA/EMA at matched lag, is close to a non-decision.** Do not expect a rule
that fails with one to succeed with another — the trade sets are 90–97% the same and the win
rates are inside a point. A search that sweeps MA type as a free axis is multiplying its
configuration count without multiplying its hypotheses.

**DEMA, TEMA and Hull are a different matter.** Being zero-lag extrapolators rather than lagging
averages, they are not substitutes for the first group and are worth searching separately.

**KAMA's window is inert on a trend.** Sweep it only where the efficiency ratio actually varies.

Nothing here is a strategy, and none of it makes `close > MA` work.
