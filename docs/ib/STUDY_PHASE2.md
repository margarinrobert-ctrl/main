# Phase 2 — Monte Carlo, out-of-sample, correlation, walk-forward, live simulation

Applied to the **nine shipped strategies**, the only configurations in this repository selected on
the research block that then survived a locked block read once. The trend-following framework
(`STUDY_TREND_BRIEF.md`) did not survive and the limit-entry mechanic failed significance out of
sample, so neither is carried into this phase — a Monte Carlo on a strategy that already failed its
holdout would dress up a null result.

`research/phase2.py`. 100,000 Monte Carlo paths.

## 1. Live simulation — every cost the account would actually pay

| cost regime | trades | net | Sharpe | maxDD |
| --- | ---: | ---: | ---: | ---: |
| research-era model ($1.00 flat) | 1,212 | $55,424 | 3.70 | $1,289 |
| itemised fees ($1.44, bar-dependent slippage) | 1,212 | $54,011 | 3.62 | $1,303 |
| **+ live overlay** | 1,212 | **$53,115** | **3.56** | $1,313 |

The live overlay charges what a flat RTH assumption does not: **+1 tick per side overnight**
(before 09:30 / after 16:00, where MNQ routinely quotes 2 ticks wide), **+1 tick per side in the
first and last 10 minutes of RTH**, and **+1 tick per side when ATR is above its own 80th
percentile**. Those are assumptions about a real book — there is no quote data here to calibrate
them — but they are charged rather than omitted, because omitting them is also an assumption and a
less conservative one.

**Total cost realism costs the book 4.2%.** It survives because these are low-frequency strategies
with a large per-trade edge; the same correction would gut a high-frequency book.

## 2. Out-of-sample

| | research | locked |
| --- | ---: | ---: |
| book | $28,535 | $24,581 |

Per leg, on the live cost model:

| leg | n res | res $ | n lok | lok $ | lok $/tr | shape |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| M1 | 55 | 1,730 | 30 | 1,457 | 48.6 | grew on locked |
| M2 | 76 | 1,785 | 44 | 667 | 15.1 | decays |
| M3 | 59 | 2,146 | 33 | 1,272 | 38.6 | grew on locked |
| M4 | 63 | 6,090 | 25 | 2,725 | 109.0 | grew on locked |
| V1 | 176 | 6,293 | 73 | 2,117 | 29.0 | decays |
| V2 | 125 | 1,684 | 76 | 2,421 | 31.9 | grew on locked |
| V2L | 86 | 4,603 | 53 | 4,758 | 89.8 | grew on locked |
| V3 | 105 | 3,384 | 53 | 7,242 | 136.6 | grew on locked |
| V4 | 53 | 819 | 27 | 1,922 | 71.2 | grew on locked |

**Six of nine legs earn MORE per trade on the locked block than on research.** That is the wrong
shape. It is not leakage — these were selected on research and locked was read once — but it means
the later period was simply kinder to this book, which is the same regime observation the
trend-following study ran into independently. **The locked block is 35% of sessions and produced
46% of the profit.** Treat the book's forward expectation as the *research* figure, not the blend.

## 3. Monte Carlo — 100,000 paths on 1,212 live-costed trades

**(a) Trade-ORDER permutation.** Same outcomes, different sequence — this bounds *path* risk:

| | median | 95th | 99th | worst |
| --- | ---: | ---: | ---: | ---: |
| max drawdown | $1,872 | $2,797 | $3,375 | **$6,206** |
| losing streak | 6 | 9 | 10 | **18** |

The realised drawdown of $1,313 was **luckier than the median ordering**. Plan for $3,400, not
$1,300 — and for a run of 10 consecutive losers, because one in a hundred orderings has one.

**(b) Trade resample with replacement** — a different run of the same strategy: 5th percentile
$42,159, median $53,037, 95th $64,136.

**(c) Stationary block bootstrap on daily P&L** (mean block 5 sessions, so autocorrelation and
volatility clustering survive): net 5th $40,636, median $52,678, 95th $66,839; **Sharpe 5th 2.94,
median 3.59, 95th 4.26**.

**Both bootstraps report 0.00% losing paths, and that is not evidence of anything.** Resampling a
strongly positive sample must produce positive paths — it assumes the edge it is measuring. The
question of whether the edge is real was answered by the holdout and the matched control, and is
not re-asked here.

## 4. Risk of ruin

Fixed fractional, average loss scaled to the stated fraction of starting capital, 20,000 paths:

| risk/trade | P(50% drawdown) | P(30% drawdown) | median maxDD on $50k |
| ---: | ---: | ---: | ---: |
| 0.25% | 0.00% | 0.00% | $1,628 |
| 0.50% | 0.00% | 0.00% | $3,256 |
| 1.00% | 0.00% | 0.16% | $6,512 |
| 2.00% | 0.88% | **28.22%** | $13,023 |
| 4.00% | **56.95%** | 99.80% | $26,047 |

Scale-invariant — the answer depends on risk per trade as a fraction of capital, not on capital.
**1% per trade is the practical ceiling.** At 2% there is a better-than-one-in-four chance of a 30%
drawdown; at 4% a coin-flip chance of losing half the account, on a book whose edge is real.

## 5. Correlation matrix — daily P&L

|  | M1 | M2 | M3 | M4 | V1 | V2 | V2L | V3 | V4 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **M1** | 1.00 | −0.02 | −0.01 | 0.13 | 0.06 | −0.02 | −0.05 | **0.44** | −0.02 |
| **M2** | | 1.00 | 0.16 | −0.06 | −0.05 | **0.58** | −0.01 | −0.03 | 0.16 |
| **M3** | | | 1.00 | −0.01 | −0.01 | 0.10 | −0.01 | −0.03 | 0.15 |
| **M4** | | | | 1.00 | 0.10 | −0.05 | 0.03 | 0.23 | −0.04 |
| **V1** | | | | | 1.00 | −0.09 | 0.08 | −0.01 | −0.03 |
| **V2** | | | | | | 1.00 | −0.01 | −0.04 | 0.24 |
| **V2L** | | | | | | | 1.00 | 0.14 | 0.05 |
| **V3** | | | | | | | | 1.00 | −0.02 |
| **V4** | | | | | | | | | 1.00 |

**mean |ρ| 0.091, max 0.582, min −0.093.**

Only one pair is meaningfully correlated: **M2/V2 at 0.58** — those two are close to the same trade
in different clothes, and the book carries the risk of both. M1/V3 at 0.44 is the next.

**Book Sharpe 3.56 against a best single leg of 2.06. Book maxDD $1,313 against $8,200 if each
leg's worst stretch had coincided — $6,886 saved by them not coinciding.** The diversification is
the largest single contributor to the book's risk-adjusted return, larger than any individual leg's
edge.

## 6. Walk-forward — does chasing recent performance help?

At each of five fold boundaries, keep the **top 4 legs by trailing Sharpe**, scaled to the same
gross exposure as holding all nine so the comparison is about selection and not size:

| fold | sessions | top-4 | all nine |
| ---: | --- | ---: | ---: |
| 1 | 153–307 | 5,251 | 6,775 |
| 2 | 307–461 | **9,338** | 5,111 |
| 3 | 461–614 | 6,992 | 6,817 |
| 4 | 614–768 | 16,906 | 16,225 |
| 5 | 768–922 | **2,118** | 8,229 |

| | net | Sharpe | maxDD |
| --- | ---: | ---: | ---: |
| top-4 by trailing Sharpe | $40,605 | 2.22 | $2,963 |
| **hold all nine** | **$43,157** | **3.36** | **$1,263** |

**Chasing recent performance cost $2,552, cut Sharpe by a third, and more than doubled the maximum
drawdown.** Fold 5 is the tell: the top-4 selection made $2,118 where holding everything made
$8,229 — it had rotated into exactly the legs that were about to stop working.

This replicates the earlier finding on this data that rolling re-optimisation earned $14,580 against
a fixed geometry's $27,253. **The allocation decision is where discretion destroys the most value.**

## Verdict

| test | result |
| --- | --- |
| survives full cost realism | **yes** — 4.2% give-back, Sharpe 3.70 → 3.56 |
| out-of-sample | **yes, but the wrong shape** — 6 of 9 legs grow on locked |
| Monte Carlo path risk | **plan for $3,400 drawdown and a 10-loss streak**, not the realised $1,313 |
| risk of ruin | **safe to 1%/trade**, dangerous at 2%, ruinous at 4% |
| correlation | **mean |ρ| 0.091** — genuine diversification; watch M2/V2 at 0.58 |
| walk-forward | **hold all nine.** Selection cost $2,552 and a third of the Sharpe |

The book is the most robust thing in this repository. The two honest reservations are that the
locked block was kinder than research on six of nine legs, and that everything here is one
instrument in one regime.

Research tooling for education and analysis, not financial advice.
