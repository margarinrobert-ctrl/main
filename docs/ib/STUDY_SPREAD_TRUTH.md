# The first measured spread on this branch, and what it says about the assumed ones

Five studies here end at the same sentence: **bid/ask is unavailable in all four feeds**, so every
cost number is an assumption, and every surviving candidate dies at 1.5× that assumption. That made
"get bid/ask data" the highest-value open thread on the branch — worth more than any further
parameter search, because it is the one input that could move a result rather than re-rank one.

The EURUSD 30-minute feed carries a `spread` column. It is a different asset class, so it cannot
set the index or gold numbers directly. What it **can** do is test the three *structural* claims
the cost model makes about spread, which are not asset-specific.

`research/edgelab/fx.py`, `research/edgelab/spread_truth.py`.

## First, whether the column can be believed

A quoted spread of exactly zero is not a market, it is a missing value, and the contamination is
not stationary:

| period | zero share | median spread |
| --- | ---: | ---: |
| 2003–2013 | 0.0% every year | 50 → 1 points (5.0 → 0.1 pips) |
| 2014–2016 | 0.3–6.3% | 1–7 points |
| **2017** | **25.2%** | 7 points |
| 2018–2019 | 0.0% | 1–3 points |
| **2020 / 2021 / 2022** | **36.0% / 74.6% / 87.7%** | 1 / 0 / 0 points |

Two filters, applied by measurement rather than by eye: whole years above 20% zeros are dropped
(2017, 2020, 2021, 2022), and inside the surviving years individual zero bars are dropped too.
**190,319 of 230,400 bars survive, 82.6%.**

The main reason to believe the column where it *is* populated is the decay itself: 5.0 pips in
2003 falling smoothly to 0.1 by 2018 is the real historical narrowing of retail FX quotes, and
it is not a shape a placeholder produces.

## Claim 1 — spread is a step function of session. **FALSE.**

`Costs.spread_at` charges three tiers, and the assumed steps are large: NQ 0.5 / 1.0 / 1.5 points
and US30 2.0 / 4.0 / 6.0 for RTH / pre / off — a **3× ratio** end to end.

| session | bars | mean spread | spread / ATR |
| --- | ---: | ---: | ---: |
| RTH 09:30–16:00 | 51,727 | 1.51 pips | 0.0865 |
| pre 07:00–09:30 | 19,929 | 1.47 pips | 0.0817 |
| off | 118,663 | 1.52 pips | 0.1183 |

The measured spread is **flat to within 3%** across all three. Hour by hour it moves from 1.46 to
1.62 pips over the entire 24-hour day — a 10% range against an assumed 300%.

## Claim 2 — spread is constant within a session. **TRUE, and more so than assumed.**

Which sets up the finding that matters:

> **The spread barely moves. What moves is ATR.** `spread/ATR` runs from **0.073 at 10:00 New
> York to 0.139 at 22:00** — nearly 2×, and every bit of it comes from the denominator.

So the cost model reaches the right *conclusion* — trading off-session costs far more in R terms —
by the wrong *mechanism*. It is not that the book widens overnight; it is that **the spread stays
put while volatility collapses underneath it.** The correct model is a fixed spread divided by a
varying ATR, not a stepped spread. Anywhere the two are calibrated separately, this matters:
a stepped-spread model tuned on RTH will misprice the overnight by whatever the ATR ratio is, not
by whatever the spread ratio was assumed to be.

## Claim 3 — it is slippage, not spread, that widens in fast bars. **TRUE.**

Bucketing by bar speed (true range over trailing ATR), the same measure `costs.py` uses to scale
slippage:

| bucket | bar speed | spread |
| --- | ---: | ---: |
| Q1 | 0.50× | 1.28 pips |
| Q2 | 0.72× | 1.61 |
| Q3 | 0.89× | 1.66 |
| Q4 | 1.11× | 1.60 |
| Q5 | **1.67×** | **1.40** |

An inverted U, not a monotone widening — the *fastest* bars quote a **tighter** spread than the
middle of the distribution. Scaling spread by bar speed would therefore be wrong, and `costs.py`
does not do it: it scales slippage only. That assumption survives intact.

## What it says about the numbers this branch has been quoting

Measured **spread/ATR = 0.1058**, so a round turn is **0.2116 ATR**, and the break-even win rate
at 1:1 is:

| stop | cost in R | break-even | US100 15m, **assumed** |
| --- | ---: | ---: | ---: |
| 0.25×ATR | 0.847 | **92.3%** | 95.1% |
| 0.50×ATR | 0.423 | **71.2%** | 71.5% |
| 1.00×ATR | 0.212 | **60.6%** | 61.9% |
| 2.50×ATR | 0.085 | **54.2%** | 54.8% |
| 4.00×ATR | 0.053 | **52.7%** | — |

**The assumed index costs were, in ATR terms, close to right.** A real, dated, per-bar spread on a
liquid instrument lands within about one percentage point of the break-even numbers this branch has
been rejecting scalping briefs with. That is the first empirical support those rejections have had,
and it cuts both ways: it does not rescue any candidate, and it removes the excuse that the
rejections were an artifact of a pessimistic guess.

## What it does not settle

EURUSD is not an index and not gold. A retail CFD index spread has no reason to equal an FX one,
and the "every candidate dies at 1.5× the assumed spread" result still rests on assumed index
numbers. What has changed is the *prior*: the assumption's **shape** was wrong in one specific way
(the session step is not real), its **magnitude in ATR units** was about right, and the one place
the model was doing something subtle — scaling slippage but not spread by bar speed — is confirmed.

An index or gold feed carrying bid/ask would still be worth more than any further search.
