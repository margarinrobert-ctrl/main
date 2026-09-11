# S3 flow exhaustion on a 10-minute MNQ chart: the full battery

**Verdict: the rule does not survive the move from 5 minutes to 10. It loses on the block permitted
to choose it and wins on the block read once, at EVERY one of 630 geometry cells, and cost is ruled
out in advance.**

NQ 1-minute resampled to 10m, 766 window sessions 2022-12 to 2025-12, 07:00-11:00 New York with an
11:00 flatten, one position at a time, MNQ all-in round turn 1.72 points. Research to 2024-11-27.

## The bar-count question, answered before anything else

`k` and `w` are BAR COUNTS. Carried unchanged from 5m to 10m they DOUBLE their reach in minutes --
k3 goes from a 15-minute pivot to a 30-minute one and w20 from 100 minutes to 200
(`STUDY_V57_REVERSE_ENGINEER` recorded this exact failure in the other direction). So both readings
were declared and both were run:

| reading | k/w | minutes | block | n | pts | PF | Sharpe |
|---|---|---|---|---|---|---|---|
| CARRY | 3/20 | 30/200 | research | 176 | **-7.49** | 0.696 | **-1.34** |
| CARRY | 3/20 | 30/200 | LOCKED | 92 | +5.97 | 1.217 | +0.66 |
| MATCHED | 2/10 | 20/100 | research | 277 | **-3.28** | 0.876 | **-0.59** |
| MATCHED | 2/10 | 20/100 | LOCKED | 136 | +10.63 | 1.352 | +1.24 |
| 5m reference | 3/20 | 15/100 | research | 380 | +2.31 | 1.118 | +0.55 |
| 5m reference | 3/20 | 15/100 | LOCKED | 179 | +11.41 | 1.467 | +1.75 |

Matching the MINUTES is better than carrying the numbers, and both are negative on research. The
trade count roughly halves (89-140/yr against 193) and the median hold falls 100 -> 50 minutes,
because the 07:00-11:00 window is 24 bars at 10m against 48 at 5m and the flatten binds sooner.

**COST IS RULED OUT IN ADVANCE.** Median in-window ATR(14) is 19.56 points at 10m against 15.15 at
5m, so a 3xATR stop is 58.68 against 45.45 and the fixed 1.72-point round turn is **2.93% of risk
at 10m against 3.78% at 5m**. The wider bar is CHEAPER. If 10m fails it is not execution -- and the
execution Monte Carlo confirms it: slippage U(0,2x) and cost U(0.5x,2x) applied inside the walk give
**P(total <= 0) = 1.00** on both 10m research arms.

## Parameter stress: 630 cells, and the inversion is total

Six stops x five targets x three breakevens x three trail arms x three trail distances, with the
inert axis collapsed (the trail distance does nothing when the trail is off), run on both readings.

| | research profitable | LOCKED profitable | corr(research, locked) |
|---|---|---|---|
| CARRY k3/w20 | **0.0% of 630** | 99.2% | **-0.823** Pearson / -0.737 Spearman |
| MATCHED k2/w10 | 6.3% of 630 | 100.0% | +0.278 / +0.226 |

**Every marginal average is negative on research at every setting of every axis, and positive on
locked at every setting of every axis.** The one-rung box around the shipped geometry -- 96 cells --
is **0.0% profitable on research and 100.0% on locked**. That is not a parameter problem that a
better cell fixes; there is no cell. A corr of -0.823 means selecting on research is actively worse
than not selecting.

## The two nulls

| cell | block | rule | random entry | p | coin-flip side | p |
|---|---|---|---|---|---|---|
| 10m CARRY | research | -7.49 | -1.46 | **0.922** | -1.32 | **0.958** |
| 10m CARRY | LOCKED | +5.97 | -0.08 | 0.285 | -1.76 | 0.170 |
| 10m MATCHED | research | -3.28 | -1.25 | 0.678 | -1.26 | 0.735 |
| 10m MATCHED | LOCKED | +10.63 | -0.19 | 0.142 | +1.30 | 0.105 |
| 5m reference | research | +2.31 | -1.58 | 0.102 | -2.36 | **0.042** |
| 5m reference | LOCKED | +11.41 | -1.55 | **0.018** | -0.75 | **0.008** |

At 10 minutes a random entry with the same geometry BEATS the rule on research, and so does a coin
flip on the rule's own bars -- so the direction call is worth less than nothing there. Only the
5-minute version clears either null, and only on the locked block for Null A.

## Monte Carlo

| cell | block | P(mean<=0) | 95% CI | realised DD | MC p50 | MC p99 | DD percentile |
|---|---|---|---|---|---|---|---|
| 10m CARRY | research | **0.976** | [-15.46, **-0.05**] | 1,428 | 1,547 | 2,067 | 0.250 |
| 10m CARRY | LOCKED | 0.239 | [-10.23, 23.35] | 743 | 602 | 1,101 | 0.774 |
| 10m MATCHED | research | 0.796 | [-10.22, 4.61] | 1,741 | 1,562 | 2,491 | 0.712 |
| 10m MATCHED | LOCKED | 0.103 | [-5.63, 26.79] | 563 | 744 | 1,426 | 0.146 |
| 5m reference | research | 0.256 | [-3.57, 8.28] | 740 | 895 | 1,663 | 0.240 |
| 5m reference | LOCKED | 0.032 | [-0.61, 22.81] | 874 | 638 | 1,249 | 0.866 |

**The 10m carry research CI excludes zero on the NEGATIVE side** -- it is a statistically significant
LOSS, not merely an absence of edge. Neither 10m locked arm separates from zero (0.239, 0.103), so
even the block that looks good does not clear the weaker of the two questions.

**Price jitter with the pivots, the CVD and the ATR all recomputed** keeps the sign in **100%** of
draws at 0.5, 1 and 2 ticks on every 10m arm. The rule is robust to price noise; it is robustly
negative. (The pivot kernel was vectorised for this -- asserted identical to the reference at
k=1..5 and on three declared cells before use, 200x faster.)

## Correlation matrices

Across 15 (k,w) cells at 10m: median pairwise correlation **+0.349**, only 14.3% of pairs above 0.7,
and 5 of 15 components carry 90% of the variance. So the grid is a genuine family rather than one
rule wearing fifteen names -- which makes 0% research profitability across it harder to dismiss.

Across timeframes, daily P&L: **10m carry vs 5m carry correlate only +0.107 on research and +0.034
on locked.** The two runs are catching largely DIFFERENT trades, so the 10m result is an independent
read on the same idea and it says no. Correlation with always-long in the same window is -0.04 to
+0.08 on every arm, so neither timeframe is drift.

## Real edge or fluke

**Deflated Sharpe.** 30 (k,w) cells x 1 geometry, 630 geometry cells x 2 readings, 2 timeframes and
3 declared cells = **N = 1,295 looks**. The variance of the trial Sharpes (per trade, not
annualised) is 0.004208, giving **E[max Sharpe | pure noise] = 0.2159**.

| cell | block | Sharpe/trade | DSR | beats the noise floor |
|---|---|---|---|---|
| 10m CARRY | research | -0.143 | 0.000 | no |
| 10m CARRY | LOCKED | +0.071 | 0.075 | no |
| 10m MATCHED | LOCKED | +0.111 | 0.110 | no |
| **5m reference** | **LOCKED** | **+0.137** | **0.141** | **no** |

**CORRECTED 2026-09-07 -- THIS DEFLATION WAS WRONG IN TWO WAYS AND BOTH MADE IT TOO HARSH.**
The figure above said no cell clears the noise floor, including the 5-minute version. Two errors
produced that:

1. **It counted VALIDATION looks as SEARCH looks.** 1,260 of the 1,295 cells were the 10-minute
   geometry grid, which was run to falsify the 5-minute result and could never have produced it. A
   test you run on a finished result is not a trial that found it. The honest search count for the
   5m cell is **N = 805** (5 designs x ~800 declared geometry cells, plus 30 (k,w) reads).
2. **`var_trials` was measured on the wrong population** -- the 10-minute (k,w) family, which is
   worse and more dispersed than the family the cell came from. The 5-minute family's trial
   variance is **0.001607 against the 0.004208 used**, a factor of 2.6, and a larger variance makes
   E[max | noise] larger. Same error class as `STUDY_XAU_TWO_LAYER` (too generous) and
   `STUDY_VP_TPO_NEXT` (too harsh); the rule is to state what the variance is over and use the
   population that produced the candidate.

Redone with the 5m variance, as a CURVE over assumed N because the assumption does the work:

| N | E[max \| noise] | research DSR | LOCKED DSR |
|---|---|---|---|
| 30 | 0.0831 | 0.188 | 0.770 |
| 100 | 0.1014 | 0.105 | 0.688 |
| 400 | 0.1196 | 0.052 | 0.595 |
| **805** | **0.1280** | **0.037** | **0.550** |
| 1,295 | 0.1334 | 0.029 | 0.521 |
| 5,000 | 0.1478 | 0.014 | 0.442 |

The cell's per-trade Sharpe is +0.0393 research and **+0.1372 locked**. At the honest N of 805 the
**LOCKED CELL DOES CLEAR THE NOISE FLOOR (0.137 > 0.128)** -- it stays above it out to about
N = 2,000. It is not significant (DSR 0.55), but "clears the noise floor" and "fails it" are
different claims and the first one is the true one. The RESEARCH block does not clear at any N
above 5, which is the real remaining objection.

Non-parametric version, no distributional assumption -- over 600 matched random entries, how often
does the BEST OF 30 draws beat what the rule earned: **locked p 0.346, research p 0.958**. Same
verdict from a different direction: the locked result is not distinguishable from the best of a
30-cell search over noise, but neither is it below the floor.

**White's reality check** over 28 candidates and 497 research sessions, stationary block bootstrap:
**p 0.660 FAIL**. The best of the set does not beat zero once the search is priced.

## Where the sign actually changes

| pts/trade | 2023 | 2024 | 2025 |
|---|---|---|---|
| 10m carry | -10.08 | -5.53 | +6.02 |
| 10m matched | -4.98 | +0.19 | +9.17 |
| 5m carry | -1.82 | +8.45 | +10.32 |

The research block ends 2024-11. At 5 minutes the sign flips during 2024, so roughly a third of the
research block already carries it; at 10 minutes it does not flip until 2025, entirely inside the
locked block. **That is the whole difference between the two timeframes' verdicts**, and it means
the 5m result is substantially a statement about when the regime turned rather than about the bar
size. Both timeframes agree the rule loses in 2023 and wins in 2025.

## What this changes

Do not run this rule on a 10-minute chart -- that part stands unchanged and is not close.

The 5-minute verdict is softer than this study first stated, and `STUDY_S3_EDGE.md` records what
changed: the concentration objection raised here fails its own control, and the deflation above was
too harsh. What survives against the 5m version is that its RESEARCH block does not separate from
zero (bootstrap P(mean<=0) 0.256, DSR 0.037, best-of-30 p 0.958), that the magnitude is strongly
regime-dependent, and that it has never been read on a second market.

`research/s310/`, `results/s310/s310_battery.png`.
