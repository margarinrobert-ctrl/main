# Semivariance asymmetry and efficiency flip, as intraday scalps

*Two requests, one procedure.* Convert the daily semivariance-asymmetry strategy (Baruník,
Kočenda & Vácha, SSRN 2815151) into an intraday scalp; and build a rolling price-efficiency
signal that enters when the market flips from noisy to directional.

*Result: both are null.* Neither beats a matched random entry on the holdout, and adding either to
the book lowers its Sharpe and triples its drawdown.

> **On the attached PDF.** SSRN 4365395 — *Robust Pricing with Asymmetric Distributional
> Information in Valuation* (Chen, He, Qi & Zhang) — is an operations-research paper on
> distributionally robust monopoly pricing. It uses semivariance as a moment constraint on a
> consumer-valuation distribution. It shares a word with the strategy and nothing else, so nothing
> below draws on it. The Pine script's own citation, SSRN 2815151, is the relevant one.

---

## 1. The conversion

The daily signal: split realized variance into the part contributed by up moves (RS+) and by down
moves (RS−); when bad volatility dominated the last W days (rolling SAM = ΣRS+ − ΣRS− < 0), go
long. The intraday scalping version keeps the estimator and changes the unit and the exit:

| | daily original | intraday scalp |
| --- | --- | --- |
| unit | one day | one 15- or 30-minute bar |
| returns inside the unit | 30-minute | 1-minute (`SAMi`) or the bar's own return (`SAMb`) |
| position | held, rebalanced daily | 1R barrier: ATR stop, 1R target, session flatten |
| direction | long only, contrarian | **both sides enumerated** |

Direction is not inherited. NQ rose 89% over this sample, so a long gets paid for existing
(`RESEARCH_PROTOCOL.md` §4c); the paper's direction is a prior, not a permission. Every condition
is scored against the base win rate of **its own side and geometry**, computed from the
population.

The two estimators agree on the sign of SAM 82–83% of the time (rank correlation +0.76 to +0.79),
so the intrabar version carries real extra information rather than being a smoothed copy.

Both the paper's **state** reading (hold while SAM < 0) and a **cross** reading (trade the moment
bad volatility takes over) are enumerated, since a state under a 1R barrier becomes "re-enter
whenever flat and the regime holds".

The efficiency signal is Kaufman's ratio over N bars, |net change| / Σ|step|: 1 for a straight
line, near 0 for noise. It fires when the ratio was below `lo` three bars ago and is above `hi`
now, in the direction of the net change. Median efficiency ratio(20) on this data is 0.21, with
63–67% of bars below 0.3 and 4–6% above 0.6 — so a flip is a genuinely rare event, firing on about
0.6% of bars.

## 2. The sweep

Standard procedure, unchanged: every condition × 18 geometries (6 stop widths × 3 flatten times) ×
both sides × 2 timeframes; research block only; own-side own-geometry base rate; locked read once.

    SAM   4,032 combinations with 40+ research and 15+ locked trades
            193 beat their own base rate and are research-profitable
    EFF   2,204 combinations
            490 beat their own base rate and are research-profitable

### The locked block, read once

**SAM** — the top five by research excess, which are three geometries of one condition:

| condition | tf | dir | trades | locked n | locked win % | base | excess | net $ | locked $ | PF |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SAMi34 crosses above 0 | 30m | long | 846 | 298 | 51.7 | 48.2 | +3.4 | 11,787 | 3,894 | 1.18 |
| SAMi34 crosses above 0 | 30m | long | 858 | 303 | 51.2 | 48.4 | +2.8 | 10,140 | 3,826 | 1.16 |
| SAMb21 crosses above 0 | 30m | short | 1,248 | 396 | 43.4 | 42.8 | +0.6 | −5,335 | −6,164 | 0.93 |
| SAMb21 crosses above 0 | 30m | short | 1,180 | 378 | 44.7 | 42.3 | +2.4 | −4,629 | −4,826 | 0.94 |
| SAMi34 crosses above 0 | 30m | long | 916 | 321 | 50.2 | 48.5 | +1.6 | 8,014 | 2,177 | 1.13 |

Three of five keep a positive excess and positive dollars. Note what won: **`crosses above 0`** —
*good* volatility taking over. That is the opposite of the paper's direction. The best research
excess in the whole family is +7.1 points, against +16 to +22 for every shipped strategy.

**EFF** — 0 of 5 hold. Every one loses money on the locked block:

| condition | tf | dir | trades | locked win % | base | excess | locked $ |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EFF20 flip 0.4→0.6 down | 30m | short | 97 | 45.5 | 44.1 | +1.4 | −343 |
| EFF20 flip 0.4→0.6 down | 30m | short | 105 | 37.1 | 43.3 | −6.2 | −868 |
| EFF20 flip 0.2→0.5 down | 15m | long | 146 | 50.9 | 46.5 | +4.4 | −2,146 |

Research excesses of +15 to +17 points, picked as the maximum over 2,204 combinations, are what
+17 looks like when it is drawn from noise.

## 3. The matched control, which settles it

Random entries with the same side, geometry and minute-of-day distribution as the real rule — the
base rate that prices in drift, costs, barrier width and session timing at once.

| | block | n | win % | control | p | net $ | control $ | p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SAMi34 cross **above** 0, long | research | 548 | 55.3 | 51.4 | 0.005 | 7,893 | 3,643 | 0.090 |
| | **locked** | 298 | 51.7 | 50.4 | **0.299** | 3,894 | −90 | **0.147** |
| SAMi34 cross **below** 0, long *(the paper's direction)* | research | 549 | 52.3 | 51.5 | 0.329 | 2,337 | 3,904 | 0.686 |
| | **locked** | 292 | 49.3 | 50.6 | **0.688** | −973 | −167 | **0.594** |

The surviving SAM variant does not beat a matched random long on the holdout. The paper's own
direction fails on the **research** block, before any holdout is involved. And the research-block
control makes $3,643 by itself — most of SAM's research profit is the drift a long collects for
existing.

Exit split on the survivor: 486% of net at the target, −464% at the stop, 78% at the time stop,
median hold 8 bars. It is a barrier trade rather than a drift hold, but a barrier trade whose
barrier edge is indistinguishable from random.

## 4. Correlation matrix and the book

Per-session P&L, the nine shipped strategies plus the two new signals:

| | V1 | V2 | V3 | V4 | V2L | M1 | M2 | M3 | M4 | SAM | EFF |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **SAM** | 0.08 | −0.06 | 0.25 | −0.02 | 0.02 | 0.21 | −0.01 | −0.03 | 0.07 | 1.00 | −0.03 |
| **EFF** | 0.02 | 0.20 | −0.01 | 0.23 | −0.04 | −0.02 | 0.12 | 0.14 | −0.06 | −0.03 | 1.00 |

Both are decorrelated from the book (max |ρ| 0.25 and 0.23), which is the usual argument for
adding a mediocre leg. It does not survive contact with the numbers:

| book | net $ | locked $ | Sharpe | maxDD $ |
| --- | --- | --- | --- | --- |
| the nine | 55,424 | 25,528 | **3.73** | **1,289** |
| nine + SAM | 67,211 | 29,422 | 3.23 | 3,034 |
| all eleven | 67,830 | 29,079 | 3.20 | 3,509 |

SAM adds $3,894 of locked profit and $1,745 of drawdown, cutting book Sharpe from 3.73 to 3.23.
Decorrelation does not rescue a leg whose own edge is a coin flip — it just adds its variance.

## 5. What to take from this

1. **Neither signal earns a place.** SAM's surviving variant fails the matched control on the
   holdout (p 0.299 / 0.147); EFF fails outright, losing money on the holdout in all five variants.
2. **The paper's direction is the losing one here.** What survived research was `crosses above 0`
   — good volatility dominating — not the contrarian bad-volatility reading. The contrarian
   reading fails on research. A daily equity-index result does not transfer to an intraday futures
   scalp, and this is what that looks like when measured instead of assumed.
3. **A decorrelated leg still has to have an edge.** Adding SAM lowered the book's Sharpe and more
   than doubled its drawdown while raising net profit — exactly the trade a correlation matrix
   alone will talk you into.
4. **+17 points of research excess is not a lot when it is the maximum over 2,204 combinations.**
   EFF's headline numbers were larger than any shipped strategy's and worth nothing.

## Files

| | |
| --- | --- |
| `research/newsignals.py` | SAM (intrabar and bar-return estimators) and the efficiency flip |
| `research/newsignals_test.py` | the standard 1R sweep: own-side base rates, research-only choice |
| `research/oner_anom.py` | the matched control and the exit split used in §3 |
| `research/allstrats.py` | the nine shipped strategies, for the correlation matrix |

Measured on MNQ, 2022-12-26 → 2025-12-12, one contract, $1.00 commission per round turn, one tick
spread plus one tick slippage each side, one extra tick on stops. Research tooling for education
and analysis, not financial advice.
