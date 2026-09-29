# V64 — Optuna on the V61 CVD rule: 6,000 trials, nothing beaten

`research/v64/`, `results/v64/`. NQ, 15/30/60-minute, research block only until section F.

## Verdict

**6,000 TPE and NSGA-II trials over a continuous space the exhaustive grid could not reach found
nothing that beats the shipped presets out of sample.** Research total return climbed
**+18.88% → +40.93% → +55.40%** as the search got harder and the box got wider; locked total went
**+12.14% → +8.62% → +16.34%**, against the shipped 15-minute preset's **+17.91%**. The optimiser
bought research score and nothing else.

Three things came out of it that are worth keeping, and none is a new configuration:

1. **The walk-forward objective transferred *worst*.** Optimising the median of eight folds — the
   objective this branch adopted precisely because raw return fails — produced research +26.43%
   and locked **−0.07%**, the only finalist that loses money. It bought a 63-trade cell.
2. **Widen the box and the optimum runs to the new ceiling.** stop 7.61 of an 8.0 limit, target
   10.35 of 12.0. That is the no-take-profit / wide-stop finding arriving through the back door:
   the optimiser is asking for a stop that cannot bind and a target that is never reached.
3. **fANOVA says which axes to stop tuning.** Timeframe 0.48 and the CVD recency window *w* 0.21
   carry the objective. Pivot half-width *k* **0.006**, prior-session-high **0.003**, adaptive
   stop **0.005**, maximum hold **0.012** are noise.

## Why an Optuna study on this rule needed a reason

`STUDY_V61_CVD_OPTIMISED` already searched **725,760 effective cells exhaustively**. A sampler
cannot beat an exhaustive search on the same space — it can only reach the same maximum with fewer
evaluations. So the study is only worth running if it asks something the grid could not, and there
were exactly three such questions: the **continuum** between the grid's rungs, whether a
**transfer-aware objective** transfers better, and **interaction-aware importance** (the grid
answered importance only through one-axis marginals).

**Parity first.** The continuous evaluator reproduces the published grid to the cent on both
blocks — research n 157, +0.1203 %/trade, +18.88% total; locked n 85, +0.1428 %/trade, +12.14%.
The end-of-data cutoff is held fixed at the search space's maximum hold so no trial can buy extra
sample with a shorter hold.

## The three studies

| Study | Trials | Scorable | % profitable on research | Median total % | Best objective |
| --- | ---: | ---: | ---: | ---: | ---: |
| TPE / research return | 1,500 | 1,488 | **99.1%** | +27.83 | +40.89 |
| TPE / median of 8 folds | 1,500 | 1,458 | 99.4% | +21.55 | +0.68 |
| NSGA-II / return vs drawdown | 1,500 | 1,444 | 96.1% | +12.61 | +29.36 |

**99% of the sampled population is profitable on research**, which is what TPE concentrating in a
good region looks like — and it means the best trial is the maximum of ~1,480 positive draws, the
same caution the grid needed.

## Parameter importance (fANOVA)

| Axis | TPE / return | TPE / fold median |
| --- | ---: | ---: |
| timeframe | **0.477** | 0.149 |
| CVD window *w* | **0.209** | **0.423** |
| CHOP threshold | 0.080 | 0.078 |
| exit channel | 0.040 | 0.009 |
| take profit | 0.039 | 0.041 |
| stop | 0.033 | 0.050 |
| entry channel | 0.022 | 0.027 |
| max hold | 0.012 | 0.008 |
| pivot *k* | **0.006** | 0.149 |
| adaptive stop | 0.005 | 0.010 |
| prior session high | **0.003** | **0.000** |

The two objectives disagree about *k* (0.006 vs 0.149) and agree that the prior-session-high gate,
the adaptive stop and the maximum hold move nothing. The maximum-hold reading independently
confirms V61's own inert-axis accounting.

## The continuum — and the box edges

Top-50 trials sit a mean **0.839** from the nearest grid rung on the stop axis, where a uniform
draw on [1, 4] would average 0.19 — because they pile up at the ceiling. Entry and exit channels
in the top 50 run **59–80** against the grid's maxima of 55 and 30.

So the box was widened (channels to 150, stop to 8.0, target to 12.0, *w* to 120) and 1,500 more
trials run:

| Axis | Box | Top-50 median | Top-50 p90 | At the ceiling? |
| --- | --- | ---: | ---: | --- |
| entry channel | [10, 150] | 17.00 | 23.20 | no |
| exit channel | [10, 150] | 105.50 | 114.10 | no |
| **stop** | [1.0, 8.0] | **7.61** | **7.89** | **YES** |
| **take profit** | [0.0, 12.0] | **10.35** | **10.82** | **YES** |
| CVD window | [3, 120] | 68.00 | 71.10 | no |
| max hold | [120, 960] | 453.00 | 519.70 | no |

Best research total **+55.40%** (tf 30, entry 17, exit 106, stop 7.74 ATR, target 10.35 ATR,
hold 451, k 4, w 67) → **locked +16.34%** on 70 trades, still below the shipped 15-minute preset.
A 7.74 ATR stop behind a 106-bar exit channel with a 10.35 ATR target is a stop that cannot bind
and a target that is never reached — the optimiser has rediscovered *no take profit, wide stop*,
which is the finding this branch has now made sixteen times.

## The V30 surrogate test — hold out a whole axis value

| Held out | R² |
| --- | ---: |
| Random 80/20 rows | **+0.8956** |
| timeframe == 60 | **−6.92** |
| adaptive == 1 | +0.6735 |
| prior session high == 1 | −0.2595 |
| CHOP filter on | +0.5675 |

The random-row figure is interpolation on a dense sample and is the number that misleads. Asked
to generalise to a timeframe it has never seen, the surrogate is **worse than predicting the
mean**. Same lesson as `STUDY_V30_BAYES_OPT` (0.96 fits, 0.07 predicts).

## The one locked read — 6,000 trials, seven configurations

Sharpe is on **daily** returns, zero-filled over every session in the block. *(An earlier print of
this table annualised per-trade returns with a per-bar factor and showed 7–12; those figures were
wrong and are superseded by these.)*

| Configuration | res n | res tot% | res Sh | lock n | **lock tot%** | lock %/t | lock PF | **lock Sh** | lock maxDD% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| shipped incumbent (30m) | 157 | +18.88 | 1.37 | 85 | +12.14 | **+0.1428** | **1.596** | 1.19 | −7.83 |
| **shipped 15m preset** | 409 | +25.70 | 1.71 | 208 | **+17.91** | +0.0861 | 1.479 | **1.71** | −5.64 |
| TPE / return best | 180 | +40.93 | 2.81 | 96 | +8.62 | +0.0898 | 1.316 | 0.87 | −7.49 |
| TPE / fold-median best | 63 | +26.43 | 1.93 | 31 | **−0.07** | −0.0022 | 0.996 | −0.01 | −5.76 |
| NSGA-II best return | 348 | +29.35 | 2.11 | 166 | +14.80 | +0.0891 | 1.513 | 1.70 | **−4.23** |
| neighbourhood centre | 178 | +35.46 | 2.54 | 92 | +10.18 | +0.1107 | 1.411 | 1.03 | −7.80 |
| widest-box optimum | — | +55.40 | — | 70 | +16.34 | +0.2334 | — | — | — |

**Research Sharpe rose monotonically with search effort (1.37 → 1.71 → 2.11 → 2.54 → 2.81) and
locked Sharpe did not follow it at all** (1.19, 1.71, 1.70, 1.03, 0.87). The rank correlation
between the two columns across these seven rows is negative.

## Transfer over the whole population

2,496 distinct scorable configurations re-read on the locked block:

- corr(research %/trade, locked %/trade) = **+0.3206 Pearson / +0.2751 Spearman**
- whole population mean locked %/trade **+0.0584**
- top 1% by research total: mean locked **+0.0934**, and **100% of them profitable on locked**

**This is genuinely different from the grid's −0.026**, and the reason is the sampler, not the
market: TPE concentrates in a narrow good region, so the correlation is measured over a restricted
range and both ends of it are positive. It says the sampled neighbourhood is uniformly decent; it
does **not** say research ranking picks winners — the seven-row table above is what says that, and
it says no.

## What ships

**Nothing is promoted to default.** The shipped presets stand. One configuration is added to
`pine/v61/V61_CVD_OPTIMISED_strategy.pine` as a third, non-default preset:

**Pareto 15m** — entry 20, exit 34, stop 3.14 ATR, target 5.38 ATR, hold 255, k 5, w 58 bars
(75 and 870 minutes on a 15-minute chart). Locked: 166 trades, +14.80% total, PF 1.513,
Sharpe 1.70, max drawdown **−4.23%**. Against the 15m preset's +17.91% / 1.479 / 1.71 / −5.64%:
**better return-over-drawdown (3.50 vs 3.18), less total return, the same Sharpe, on 20% fewer
trades.**

It was chosen after 4,500 research trials and read once on the locked block, so **its numbers are
descriptive, not significance**, and its tooltip says so. If you want the pre-registered result,
use the incumbent; if you want the best measured out-of-sample return, use the 15m preset; the
Pareto cell is only worth choosing if drawdown is what binds you.
