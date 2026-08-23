# 777,600 combinations, and what they actually bought

A request to "do 1,000,000 combinations to find the best version". The full crossing of eleven
axes — timeframe, swing k, EMA length, ATR length, stop multiple, nBos, EMA filter on/off, CHoCH
on/off, max hold, range filter, and side — gives **777,600 cells**, of which 658,003 produce at
least 20 trades. Each was scored separately on a research block (first 65% of sessions) and a
locked block it never saw.

## The search curve — and a result that contradicted this project's own conclusion

Draw K cells at random, keep the best on **research** Sharpe, then look at what that cell earned
on the **locked** block. 200 repeats per K:

| K cells searched | research Sharpe | LOCKED Sharpe | LOCKED net $ | P(locked < 0) |
| --- | --- | --- | --- | --- |
| 1 | 0.01 | 0.09 | 557 | 36% |
| 100 | 1.68 | 0.13 | 312 | 40% |
| 10,000 | 2.14 | 0.27 | 715 | 30% |
| 100,000 | 2.23 | 0.77 | 1,582 | 4% |
| 658,003 | 2.30 | **1.06** | 2,109 | **0%** |

Out-of-sample quality **improved** with search width. That is the opposite of the six earlier
reproductions in this repository, and it needed explaining rather than explaining away.

## What the search was actually finding

Of the 13,817 cells that beat the reasoned spec on **both** blocks:

| axis | value | share of winners | share of all | lift |
| --- | --- | --- | --- | --- |
| **side** | **long only** | **76.5%** | 32.1% | **2.38** |
| side | short only | 0.3% | 32.7% | **0.01** |
| timeframe | 60m | 48.6% | 27.8% | 1.75 |
| swing k | 3 | 34.0% | 20.1% | 1.69 |
| nBos | 2 | 57.1% | 34.7% | 1.64 |
| stop | 2.0 × ATR | 21.5% | 16.7% | 1.29 |

The gain is overwhelmingly **"go long only"** — which on 2022-2025 NQ is being long a bull market.
Short-only essentially never wins (lift 0.01). **The holdout does not catch this**, because the
research and locked blocks sit inside the same regime; a direction bet passes a chronological
split by construction.

Note also that `swing_k = 3`, `n_bos = 2` and `atr_mult = 2.0` — the reasoned spec's values,
chosen before any of this ran — all carry positive lift across 658,003 cells.

## Removing the direction bet inverts the curve

Restricting to cells that trade **both** sides, so the regime bet is unavailable:

| K cells | all cells → LOCKED Sharpe | both-sides only → LOCKED Sharpe | P(locked < 0) |
| --- | --- | --- | --- |
| 100 | 0.17 | 0.06 | 44% |
| 10,000 | 0.25 | **−1.10** | 98% |
| 100,000 | 0.78 | **−1.53** | 100% |
| 231,504 | 0.92 | **−1.54** | **100%** |

With direction held fixed, wide search is **monotonically harmful**, and at large K the
research-block winner loses money out of sample **100% of the time**. The earlier finding stands;
it was masked by a regime bet the split could not detect.

The reasoned spec scores **+1.16** locked Sharpe on the same convention. The best cell the full
search can find averages **−1.54**.

## The honest scoreboard

- Best cell on research (all 658,003): research Sharpe 2.30 → **locked 1.06**, net $2,109.
- Best cell on locked: locked Sharpe 2.43 — but its research Sharpe was **0.76**, so it was
  unfindable without seeing the answer.
- Spearman rho(research Sharpe, locked Sharpe) across all cells = **+0.213**. Weakly positive:
  research ranking carries a little information, nowhere near enough to select on.
- The reasoned spec sits at the **94.5th percentile** of locked Sharpe. 5.47% of the space did
  beat it out of sample, and 13,817 cells beat it on both blocks — so it is **not optimal**, and
  saying otherwise would be wrong. But 76.5% of those are the long-only regime bet, and among
  both-sides cells only 1.38% beat it on both blocks.

**No PBO figure is reported.** A first cut of this script computed one by splitting the *cell
universe* in half and returned 0.000. That is not the CSCV statistic, which requires complementary
train/test splits of the same return series. The number was wrong and has been removed rather than
reported with a caveat.

## Conclusion

A million combinations did not produce a better strategy. It produced two things: confirmation
that the hand-reasoned parameters sit where the winners cluster, and a clean demonstration that
the one thing wide search reliably discovers on this data is the direction of the last three
years. The improvement that *did* survive — the 2R take-profit — came from a barrier-bound
argument over six pre-specified candidates, not from searching.

Reproduce with `python research/mnq_megasearch.py`, then `mnq_searchcurve.py` and `mnq_whatwins.py`.
