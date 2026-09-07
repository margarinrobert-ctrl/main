# A neural network on the S3 order-flow scalp

**NQ 5m, 07:00-11:00 New York, flat at 11:00. Research block only; the locked block was never
opened, because nothing cleared Gate 2 on research.**

## Why this candidate

Of the five scalp designs in `STUDY_SCALP_FIVE`, S3 (order-flow exhaustion: a confirmed price
pivot against a CVD pivot of the opposite sign) is the only one positive on both blocks and the
only one whose matched-control p is under 0.11. It is the strongest primary this window has, which
is the point: a meta layer on a dead primary produces a filter that makes a losing base less bad,
which this branch has now recorded four times (`STUDY_EMA48_VWAP_DL`, `STUDY_VWANOM`,
`STUDY_XAU_TWO_LAYER`, `STUDY_V32_FLOW_ML`).

Gate 1, before a feature exists:

| cell | block | n | /yr | pts | PF | win | Sharpe | p90 R |
|---|---|---|---|---|---|---|---|---|
| k3/w20 | research | 380 | 193 | +2.31 | 1.118 | 0.524 | +0.55 | 1.376 |
| k3/w20 | LOCKED | 179 | 168 | +11.41 | 1.467 | 0.603 | +1.75 | 1.477 |

## Two setup defects the checks caught before any model ran

**`ctx.atr_rank_day` failed the truncation audit at 20 of 900 probes.** It ranked each bar's ATR
against the whole session, so a mid-morning bar saw the rest of the morning. Rewritten as an
EXPANDING within-session rank the audit is **0 mismatches / 900**.

**THE TRAINING SET WAS 380 ROWS AGAINST 45 FEATURES, AND WIDENING THE SIGNAL WINDOW DID NOT FIX
IT** -- w=60 gives 383 research events, three more than w=20, because the recency window is not
what limits the count. The fix is to drop the POSITION LOCK for labelling only: the lock is an
execution constraint deciding which events one account can act on, not which events have a
well-defined outcome. Unlocked labelling over k in {2,3} at w=40 gives **1,672 events / 1,140
research**, and it is what makes the labels genuinely overlap -- mean 1.62 concurrent, uniqueness
min 0.340, **effective n 960** -- so uniqueness weights and purged folds stop being decoration.
The strategy still runs locked at inference; only the model's training rows are unlocked.

## The ladder

Eight models, ridge to a four-layer net, 5 purged embargoed folds, uniqueness weights, objective =
**the R the trade earned**, each run again on SHUFFLED labels. Purging costs only 0.3% of the
available training rows -- with an 11:00 flatten the labels are short, so overlap binds only at
fold boundaries.

Unfiltered base: R +0.0141, PF 1.034, win 0.519, p90 1.395.

| model | IC | IC shuffled | PF@50 | shuffled PF@50 | p90@50 |
|---|---|---|---|---|---|
| ridge | -0.012 | -0.074 | 0.960 | 0.944 | 1.354 |
| rf | -0.095 | -0.069 | 0.810 | 1.016 | 1.163 |
| lgbm | -0.080 | -0.071 | 0.777 | 1.019 | 1.081 |
| xgb d3 | -0.102 | -0.056 | 0.738 | 0.983 | 0.994 |
| xgb d6 | -0.074 | -0.051 | 0.855 | 0.970 | 1.189 |
| mlp 2x32 | +0.031 | -0.061 | 1.034 | 0.946 | 1.354 |
| mlp 2x64 | -0.014 | -0.066 | 1.040 | 0.974 | 1.406 |
| mlp 4x128 | +0.018 | -0.069 | **1.052** | 0.946 | 1.388 |

**THE SHUFFLED TWIN BEATS THE REAL MODEL IN 14 OF 24 CELLS (58%).** Above 50% the noise floor is
higher than the signal. **Every tree model has a NEGATIVE IC** -- rf, lgbm and both boosters rank
the events backwards, and their top decile loses money (rf@30% is -0.194 R at PF 0.614). Only the
nets are positive at all, and their best cell is +0.018 PF over an unfiltered base.

**CAPACITY IS INERT, WHICH IS NOT V28's FINDING.** V28 measured AUC falling monotonically with
depth; here ridge (-0.012), 2x32 (+0.031), 2x64 (-0.014) and 4x128 (+0.018) are one number with
noise on it. Neither "deeper is worse" nor "deeper is better" -- the architecture axis carries
nothing, which is what a null looks like when you sweep it.

## Gate 2

Two nulls on research: a day-block bootstrap of the kept set, and a **same-selectivity random
filter** keeping the same number of events 1,000 times.

**0 of 24 cells clear either null.** Best control p anywhere **0.348**; best bootstrap p 0.300.
Cells clearing the bootstrap alone: 0 -- so the two nulls agree for once, which they do not always
(`STUDY_V39` had 30 of 40 bootstrap-positive rules and 1 of 236 clearing a control).

**p90 of R falls below the 1.395 baseline in 21 of 24 cells**, on the R objective, which is the
objective chosen precisely to preserve the tail. A filter that keeps fewer events trims the tail
here whatever it was told to optimise -- and a stop-and-trail system earns in the tail.

Ensembling makes it worse, not better: the mlp ensemble reads p 0.537-0.655 and the full ensemble
0.984-0.990, because averaging in five backwards-ranking models inverts the score.

## The win/lose contrast, and the arithmetic of the ask

Both objectives on the SAME folds and features, so the difference is the objective alone. Trained
on win/lose the win rate rises above baseline in 4 of 16 cells and p90 of R falls in 10 of 16; on
R it is 5 of 16 and 13 of 16. Best PF anywhere on either objective is **1.115 at control p 0.258**.
**0 of 16 cells clear the control on either objective**, against 0.8 expected by chance.

Then the arithmetic, which is the durable output. Mean win **+0.824 R**, mean loss **-0.859 R**,
win rate 0.519:

| target PF | win rate needed | lift over base | best delivered |
|---|---|---|---|
| 1.5 | 0.610 | +0.091 | +0.030 |
| 2.0 | 0.676 | **+0.157** | +0.030 |
| 3.0 | 0.758 | +0.239 | +0.030 |

**PF 2.0 needs +15.7 points of win rate and the best of 99 model cells delivered +3.0** -- one
fifth of the gap, and indistinguishable from a random filter. That holds the win and loss SIZES
fixed, which is the generous reading: a filter that raises the win rate here also cuts p90, so the
real requirement is larger. A PF-3 scalping strategy is not a modelling problem on this event
stream; it is arithmetic that the entry would have to change to satisfy.

Sharpe, over EVERY research trading day zero-filled: base +0.293 on 1,095 events; the best R-model
reaches +0.707 at keep-50% and the best win-model +0.360 at keep-30% -- and neither separates from
a random filter, so the Sharpe is bought by trading less, not by choosing better.

## Verdict

Ship nothing. **99 trials counted, no locked read taken** -- nothing cleared Gate 2 on research, so
the block is unspent and remains available.

What a network could have contributed here it did not: the strongest evidence against it is not a
p-value but the shuffled twin winning 58% of ladder cells and every tree ranking backwards. What
would move it is more events, not more capacity -- 1,140 research rows at ~190 events a year is
six years of one market, and the effect size the ask requires is five times what any model found.

`research/s3nn/`, `results/s3nn/nn_verdict.png`.
