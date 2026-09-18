# V30 — Bayesian optimisation of the Turtle, 07:00–11:00 New York, both sides

**1,600 TPE trials found nothing that survives.** Two of four cells cannot produce 25 trades out of
sample at their own optimum. The other two land at locked Sharpe **−0.767** and **+0.025**.

The un-optimised starting point in this window is catastrophic (Sharpe −2.2 to −3.8), the optimiser
climbs to +0.8/+1.2 on research, and essentially none of that gain survives the split.

## What was asked, and the three measurements that argued against it first

07:00–11:00 New York with a hard flatten at 11:00, both sides, all parameters optimised for Sharpe
and profit factor. Stated before the search ran:

1. **07:00–09:00 is the worst part of the day** on all three indices, −0.18 to −0.43 R/trade, with
   10:00–11:00 the only positive hour. The cost model does not widen the pre-RTH spread, so the
   real penalty is larger than measured.
2. **The Turtle's own header records a cash-session window as harmful** — all hours +0.398 out of
   sample, 09:00–16:00 **−0.017**. This window is tighter than that, and an 11:00 flatten removes
   the multi-day hold the strategy exists for. The intraday constraint has cost ~88% elsewhere.
3. **The breakout does not beat its own random-entry control** — +0.595 R/trade against +0.601 for a
   coin flip with identical exits, ladder and costs.

## The search

Optuna TPE — a Bayesian, model-based sampler — over 10 parameters: both channel lengths, ATR
length and multiple, pyramid step, unit cap, the ADX ceiling, the EMA-extension ceiling, an AO
floor and the skip-after-winner rule. **400 trials per cell**, 2 markets × 2 sides, **research block
only**. The locked block was recorded per trial and never optimised on. 1,391 trials scored.

## A. The population, before any ranking

| market | side | trials | res Sharpe>0 | res PF>1 | **LOCK Sharpe>0** | **LOCK PF>1** |
| --- | --- | --- | --- | --- | --- | --- |
| NQ | long | 393 | 76% | 76% | **38%** | 38% |
| NQ | short | 284 | 83% | 83% | **20%** | 20% |
| US30 | long | 397 | 83% | 83% | **2%** | 2% |
| US30 | short | 317 | 83% | 83% | **71%** | 71% |

76–83% of the space looks profitable on research. On the locked block that falls to 2–71%. The US30
long cell is the clearest: **83% → 2%**.

## B. Transfer

| market | side | Pearson | **Spearman** | top-10% research → mean LOCK Sharpe | all-trial mean |
| --- | --- | --- | --- | --- | --- |
| NQ | long | +0.722 | +0.426 | +0.174 | −0.243 |
| NQ | short | +0.189 | +0.162 | **−0.347** | −0.532 |
| US30 | long | +0.667 | **+0.074** | **−0.780** | −0.887 |
| US30 | short | +0.866 | +0.304 | +0.025 | −0.104 |

Read the **Spearman**, not the Pearson: rank correlation is what a ranking-based search actually
relies on, and it runs +0.074 to +0.426. The decisive column is the fourth — **picking the top
decile on research produces a NEGATIVE mean locked Sharpe in two of four cells**.

## C. The surrogate — the strongest form of the test

XGBoost and LightGBM trained out-of-fold on (parameters → research Sharpe), then the same
predictions correlated against locked Sharpe.

| market | side | model | **fits research** | **predicts LOCKED** |
| --- | --- | --- | --- | --- |
| NQ | long | XGBoost | +0.906 | +0.445 |
| NQ | long | LightGBM | +0.876 | +0.411 |
| NQ | short | XGBoost | +0.503 | −0.143 |
| NQ | short | LightGBM | −0.147 | −0.005 |
| US30 | long | XGBoost | **+0.960** | **+0.074** |
| US30 | long | LightGBM | +0.932 | +0.049 |
| US30 | short | XGBoost | +0.905 | +0.258 |
| US30 | short | LightGBM | +0.860 | +0.254 |

**The boosters learn the research surface almost perfectly — up to +0.960 — and cannot predict the
locked one.** That is a stronger statement than a correlation: a model with the capacity to find
non-linear structure has found the research surface in full detail, and that detail is specific to
the block it was measured on. The surface is real and it is not durable.

## D. The winner, read once, against not searching at all

| market | side | config | res n | res Sharpe | res PF | **lk n** | **lk Sharpe** | **lk PF** |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NQ | long | spec | 377 | −3.842 | 0.469 | 175 | −2.138 | 0.618 |
| NQ | long | **best** | 48 | **+0.990** | 1.749 | — | **under 25 trades** | — |
| NQ | long | robust | 55 | +0.938 | 1.654 | — | under 25 trades | — |
| NQ | short | spec | 302 | −2.212 | 0.598 | 153 | −3.730 | 0.424 |
| NQ | short | **best** | 37 | **+1.227** | 2.609 | — | **under 25 trades** | — |
| US30 | long | spec | 856 | −2.962 | 0.515 | 549 | −3.735 | 0.463 |
| US30 | long | **best** | 479 | +0.795 | 1.270 | 280 | **−0.767** | 0.801 |
| US30 | short | spec | 754 | −3.357 | 0.437 | 497 | −3.246 | 0.467 |
| US30 | short | **best** | 161 | +0.893 | 1.657 | 116 | **+0.025** | 1.013 |

`robust` — the trial with the best **mean** Sharpe over its 20 nearest neighbours, not the best
point — lands within 0.1 Sharpe of `best` everywhere and does not rescue anything. Neighbourhood
scoring is necessary and not sufficient, as this branch has recorded before.

**Two of four optima cannot muster 25 trades out of sample.** Optimising Sharpe in a hostile window
selects configurations that barely trade: the NQ long winner takes 48 research trades out of 377
available. That is not robustness, it is the search finding the smallest possible sample.

## Verdict

Nothing ships. The window is the problem, and no amount of optimiser sophistication fixes a window
whose un-optimised baseline is Sharpe −2.2 to −3.8 on both sides of both markets. **The one cell
that ends positive out of sample is US30 short at Sharpe +0.025 and PF 1.013**, which is
indistinguishable from zero on 116 trades.

The durable output is the surrogate result: **a gradient booster can fit this research surface at
ρ 0.96 and predict the locked surface at ρ 0.07.** Any future parameter search on this branch should
run that test before its top row is read.

## Files

| file | what it does |
| --- | --- |
| `research/v30/v30sim.py` | numba Turtle simulator with a hard session window and both sides |
| `research/v30/v30opt.py` | feature prep, day-based Sharpe, block scoring |
| `research/v30/run_opt.py` | the 1,600-trial TPE search, research only |
| `research/v30/v30analyse.py` | population, transfer, XGBoost/LightGBM surrogates, the locked read |
| `docs/ib/v30_bayes_output.txt` | the raw run |
| `docs/ib/v30_trials.csv` | every trial with its research and locked scores |
