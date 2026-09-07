# V1: why the negative Sharpe is not real, and why the strategy might be

`ATR>1.5x mean AND BB squeeze AND close<20-bar low` · long · 3.0×ATR stop · 1R · flat 15:00 · 30m

## 1. The negative Sharpe is your account size

TradingView computes Sharpe as `(CAGR − risk_free) / stdev(returns)`. Both terms depend on the
capital you type into the tester, which has nothing to do with the strategy. One MNQ contract
against $500,000 uses about 0.4% of the account, so the returns are a rounding error and the 2%
risk-free deduction dominates.

Same trades, same P&L, varying only the number in the box:

| capital | total return | CAGR | ann vol | Sharpe @ rf=2% | Sharpe @ rf=0 |
| --- | --- | --- | --- | --- | --- |
| $5,000 | 149.8% | 28.44% | 25.25% | **+1.05** | +1.13 |
| $10,000 | 74.9% | 16.51% | 12.63% | **+1.15** | +1.31 |
| $25,000 | 30.0% | 7.43% | 5.05% | **+1.07** | +1.47 |
| $50,000 | 15.0% | 3.89% | 2.53% | +0.75 | +1.54 |
| $100,000 | 7.5% | 1.99% | 1.26% | −0.00 | +1.58 |
| $250,000 | 3.0% | 0.81% | 0.51% | −2.36 | +1.60 |
| **$500,000** | **1.5%** | **0.41%** | 0.25% | **−6.31** | +1.61 |

Your screenshot is the last row: $500,000, +1.16% total, +0.39% CAGR, Sharpe −1.926. **The
strategy made $5,799 with a $1,101 drawdown and a 2.38 profit factor.** It is not a losing
strategy; it is a profitable strategy measured against half a million dollars of idle cash.

**Fix:** set initial capital to $10,000–$25,000 (realistic for one MNQ contract, whose margin is
around $2,000), or set the risk-free rate to 0. Note the right-hand column barely moves with
capital — Sharpe at rf=0 sits at 1.13–1.61 everywhere, which is the strategy's actual property.

## 2. Why 75 trades became 116 with all four boxes ticked

The entries are immune — `barstate.isconfirmed` means they fire at the close and nowhere else.
The **exits** are deliberately not immune, because a resting stop or target genuinely fills when
price touches it. An exit that fills mid-bar leaves the book flat sooner, so a signal that was
previously skipped gets taken.

Measured against real 1-minute paths:

```
A  pessimistic (bar model)          86 trades   $7,492   win 70.9%   PF 2.64
B  true 1-minute path               86 trades   $7,163   win 69.8%   PF 2.62
C  true path + refill on fill       92 trades   $6,629   win 66.3%   PF 2.33
```

Same direction as yours, and this time it is the *realistic* direction — exits filling honestly,
not phantom entries. The immunity fix did what it was supposed to.

## 3. The mechanism: a failed breakdown

**Hypothesis.** `ATR > 1.5× mean` says the bars are **wide**. `BB squeeze` says the **closes are
clustered** — Bollinger width measures dispersion of closing prices, ATR measures true range
including gaps and wicks. Wide bars with clustered closes is churn without follow-through. Then
`close < 20-bar low` breaks the range floor with no trend behind it. Going long fades that break.

**The 2×2 that tests it.** If the *divergence* is the mechanism, the ATR-high/BB-narrow corner
should beat every other corner — and no single condition should work alone.

| volatility state | n | win % | net | PF |
| --- | --- | --- | --- | --- |
| **ATR HIGH + BB NARROW** (the rule) | 86 | **70.9** | **$7,492** | **2.64** |
| ATR high + BB WIDE | 300 | 49.3 | −$4,530 | 0.85 |
| ATR LOW + BB narrow | 58 | 48.3 | −$964 | 0.74 |
| ATR low + BB wide | 55 | 56.4 | −$347 | 0.82 |
| ATR high alone | 436 | 53.0 | $799 | 1.02 |
| BB squeeze alone | 394 | 52.5 | $4,836 | 1.17 |

**Every other corner loses money and neither condition works alone.** That pattern is what
separates a mechanism from a fitted three-way interaction: an overfit interaction shows one
corner winning and the rest wandering around zero, not the rest systematically negative.

**The direct test.** If it is a failed breakdown, price should climb back above the level it broke,
and quickly:

```
back above the broken 20-bar low within  1 bar:  68.6%
                                        2 bars: 75.6%
                                        4 bars: 81.4%
                                        8 bars: 86.0%
never within 24 bars: 14.0%      median recovery: 1 bar

exits: 15% stop, 35% target, 50% time stop      median hold: 6 bars
```

**Two thirds of these trades see the break fail on the very next bar.** That is a snap-back, not
a drift, and it matches a 6-bar median hold with only 15% of trades stopping out.

This is the strongest mechanistic evidence produced on this branch. It does not repair the
data-snooping problem — 27.4 million combinations were searched — but it means the rule describes
something with a name rather than a coincidence with three conditions.

## 4. Matrix correlations across the four versions

```
Pearson                 Spearman rank
      V1    V2    V3    V4          V1    V2    V3    V4
V1     ·  0.05 -0.02  0.14    V1     ·  -0.04 -0.02 -0.07
V2  0.05     · -0.04  0.16    V2  -0.04     · -0.05  0.04
V3 -0.02 -0.04     · -0.05    V3  -0.02 -0.05     · -0.02
V4  0.14  0.16 -0.05     ·    V4  -0.07  0.04 -0.02     ·

largest partial correlation (others held constant)   0.15
research block largest |rho| 0.12    locked block largest |rho| 0.33
```

Rank correlation is at or below |0.07| everywhere — these four are close to independent. The
locked-block figure of 0.33 is higher than research, which is the usual direction and worth
watching, but nothing here is a duplicate.

## 5. How to actually raise Sharpe and Sortino

Not by changing V1. By not trading V1 alone.

| book | Sharpe | **Sortino** | net | maxDD | MAR |
| --- | --- | --- | --- | --- | --- |
| V1 alone | 1.62 | **0.85** | $7,492 | $1,177 | 6.36 |
| V1 + V3 (both long) | 2.17 | 1.70 | $12,837 | $1,177 | 10.91 |
| all four, one lot each | 2.43 | **3.07** | $18,509 | $1,396 | **13.26** |
| all four, AVA (1/σ) | **2.48** | **3.27** | $16,452 | $1,373 | 11.98 |

**Sortino goes from 0.85 to 3.27 — a 3.8× improvement — without touching a single rule.** It comes
entirely from combining four near-uncorrelated legs and letting AVA size them.

Note the split verdict: AVA gives the best Sharpe and Sortino, equal-lot gives the best MAR
(13.26 vs 11.98). AVA suppresses the volatile legs, which flatters the ratios built on standard
deviation and costs total return. If you care about drawdown-adjusted return, use equal lots; if
you care about the ratio, use AVA. Both beat V1 alone by a wide margin.

## One correction

Your screenshots read **Dec 31, 2022 — Dec 23, 2025**, not 2020. That is almost exactly this
repository's research window (2022-12-26 → 2025-12-12) — the data the rule was found on. It is
in-sample and carries no new information. The test that would carry new information is 2018–2021,
if your plan's history reaches it.
