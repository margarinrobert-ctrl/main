# US30 15m, movement not price: an anomaly family that is not volatility, and no decision it improves

Asked to attack US30 15-minute data a different way — feature engineering for anomalies and
inefficiencies, predicting *moves* rather than prices. Four runs. The movement/direction split
replicates on this instrument and the anomaly finding strengthens to **12 of 12 cells**; neither
converts into a decision that beats its own noise twin on the reserved forward block.

Blocks: **A** US30L 2016-10 .. 2022-12, **B** US30L 2023-01 .. 2025-07, **C** `US30_ISO_15m` after
US30L ends — a **different provider**, no search here has touched it. 100 causal features: 71
volatility columns plus a declared **inefficiency family** — Lo-MacKinlay variance ratios at four
lags × three windows (VR > 1 trending, < 1 mean-reverting, = 1 efficient), rolling AR(1), Roll's
implied effective spread from the same serial covariance, Amihud illiquidity, volatility-clustering
persistence, and bar shape against causal time-of-day baselines. **Truncation audit 0 mismatches
of 120.**

## 1. The null is the method: every circular shift at once

Each reported |IC| is the **maximum over 100 features**, which no single shuffled twin can price,
and the targets are built on overlapping windows so a free permutation is far too easy — `STUDY_V67`
measured its p95 sitting at ~0.014 for every target regardless of persistence, with 32 of 32 cells
clearing it including direction.

A **circular shift** of the target preserves its entire autocorrelation function exactly (it is the
same vector) and destroys only its alignment. And every shift can be evaluated at once: the circular
cross-correlation of two standardised series is `irfft(conj(rfft(x)) · rfft(y))/n`, so one FFT per
feature gives that feature's IC at **all n shifts**. Taking the max over features at each shift is
the exact null distribution of the statistic actually being reported — ~180,000 draws instead of a
few hundred, cheaper than the naive loop. Shifts within ±5,000 bars of zero are excluded.

## 2. Movement is forecastable on US30. Direction is not.

Best |IC| over the pool against that null, averaged over three horizons (1h / 4h / 12h):

| target | best &#124;IC&#124; | trailing baseline | null p95 | ratio | clears |
|---|---|---|---|---|---|
| mfe (upside envelope) | 0.2529 | 0.0471 | 0.0833 | **3.03** | 3/3 |
| rng (range expansion) | 0.4375 | 0.2163 | 0.1478 | **2.96** | 3/3 |
| ttb (time to ±1 ATR) | 0.2243 | — | 0.0784 | **2.86** | 3/3 |
| mae (downside envelope) | 0.2093 | 0.0453 | 0.0758 | **2.76** | 3/3 |
| rv (realised vol) | 0.7270 | 0.6332 | 0.2717 | **2.68** | 3/3 |
| mag (net magnitude) | 0.4632 | 0.2698 | 0.1767 | **2.62** | 3/3 |
| er (straightness) | 0.0318 | 0.0087 | 0.0263 | 1.21 | 2/3 |
| **dir (the control)** | **0.0295** | 0.0108 | 0.0289 | **1.02** | 1/3 |

`STUDY_V67`'s split reproduces on a second instrument: **how far and how fast is forecastable, which
way is not.** Direction's single "pass" is an IC of 0.0270 at the shortest horizon — statistically
distinguishable from a shift and far too small to pay a round turn. Note also every movement target
clears its own **trailing realisation**, which is the bar `STUDY_V28` set and which nothing had
beaten on the forward efficiency ratio.

## 3. The anomaly family is *not* a volatility rename

Four unsupervised detectors — PCA reconstruction error, Mahalanobis distance, isolation forest and a
small autoencoder — all fitted on block A only, none ever seeing a label. Against the obvious
objection, measured on the trigger's own bars:

| detector | ρ with ATR percentile |
|---|---|
| pca | +0.0994 |
| maha | +0.1793 |
| iforest | +0.2301 |
| ae | +0.1299 |

This branch has caught its own pool duplicating **seven times**; here it does not. The detectors are
a genuinely independent second reading of a bar, which is what made the rest worth running.

## 4. An unusual bar is a worse bar to trade — 12 of 12

`STUDY_VWANOM` found this in 9 of 10 cells at mean ρ −0.093. On US30, Donchian-20 long, 2 ATR stop,
no target, ρ(detector, trade % of price):

| block | pca | maha | iforest | ae |
|---|---|---|---|---|
| A research | −0.1696 | −0.1688 | −0.1736 | **−0.2064** |
| B holdout | −0.0731 | −0.1230 | −0.1135 | −0.1002 |
| **C forward (other provider)** | −0.0275 | −0.0600 | −0.0878 | −0.0385 |

**Negative in 12 of 12.** It also decays across the blocks, which is the right shape. And the caveat
VWANOM attached is the one that decides the study: **the quantile means are not monotone.** On block
C the top-quartile mean is *higher* than the rest (+0.0575 vs +0.0295 for pca, +0.0726 vs +0.0245
for maha) while the rank correlation is negative — so the negative ρ lives in the middle of the
distribution, not in the tail a veto would cut.

## 5. As a veto it fails on the block that chose nothing

Re-simulated end to end — a filter is a **veto**, not a subset (`STUDY_AUCTION`) — against a random
gate keeping the same fraction of signals, also re-simulated:

| block | best cell | uplift | random gate | p |
|---|---|---|---|---|
| A research | ae, keep 60% | **+0.0194** | +0.0223 | 0.030 |
| B holdout | iforest, keep 90% | **+0.0118** | −0.0170 | **0.000** |
| **C forward** | iforest, keep 60% | **+0.0032** | +0.0356 | 0.387 |

On the two US30L blocks it looks real — B clears at p 0.000 on a base that loses money. On the
reserved different-provider block **7 of 8 cells have a negative uplift and none clears**, exactly
as §4's non-monotonicity predicted. The rank correlation is robust; the tail cut is not.

## 6. And the adaptive hold cap loses to its own shuffled forecast

Every hold cap on this branch is a constant, and time-to-touch is the one predictable thing an ATR
stop says nothing about — so a ridge fitted on block A forecasts it (**research IC +0.3344, holdout
IC +0.4150**) and the cap becomes 2× that forecast:

| block | policy | n | mean % | PF | total % |
|---|---|---|---|---|---|
| A research | fixed 96 | 1745 | **+0.0143** | 1.068 | +25.01 |
| A research | adaptive | 5023 | +0.0032 | 1.029 | +16.15 |
| A research | adaptive, **shuffled** | 4998 | −0.0042 | 0.961 | −21.09 |
| C forward | fixed 96 | 355 | **+0.0365** | 1.237 | +12.96 |
| C forward | adaptive | 1046 | +0.0099 | 1.118 | +10.39 |
| C forward | adaptive, **shuffled** | 1070 | **+0.0126** | 1.154 | **+13.50** |

The forecast beats its noise twin where it was fitted and **loses to it on the forward block**, and
the fixed cap beats both everywhere. This is `STUDY_V67` reproduced on a second decision and a second
instrument: there a volatility forecast reading locked IC 0.7065 bought exactly zero in a stop.
Note the trade count nearly triples (1745 → 5023) because shorter caps release the position lock —
the adaptive policy is a *different strategy*, not a better-tuned one, which is why the shuffled arm
is the only honest comparison.

## Verdict

**Movement forecasting on US30 15m is real, large, and buys nothing.**

1. Movement targets clear an exact circular-shift null by **2.6–3.0×** and clear their own trailing
   realisation; direction clears by **1.02×**. The split is now measured on two instruments.
2. The anomaly family is **independent of volatility** (ρ 0.10–0.23) — rare on this branch — and its
   rank correlation with trade outcome is negative in **12 of 12** cells across three blocks and two
   providers.
3. Neither converts. The veto fails on the reserved forward feed because ρ and the tail disagree;
   the adaptive hold cap loses to its own shuffled twin there.

The pattern across V67 and this study is one statement: **a movement forecast can only pay where it
prices something the ATR does not already price, and both candidates for that — the stop width and
the hold cap — turn out to be already priced.** What is left is the sizing fact `STUDY_MR30`
recorded, and that is a risk statement rather than an edge.

What would move it: a decision that is genuinely downstream of duration rather than of size — which
on this data means an instrument where holding *time* is itself priced, and futures on a 15-minute
bar is not that.

`research/mv30/`, `run_m1.py` … `run_m4.py`.
