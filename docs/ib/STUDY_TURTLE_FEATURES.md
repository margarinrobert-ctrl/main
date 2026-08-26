# Turtle-derived features for a 1:1 intraday label — and why 65% is not reachable here

`research/turtlefeat/features.py`, `evaluate.py`. 124 causal features: channel geometry, breakout
state/magnitude/persistence/false-breaks/retests at 10/20/55 bars, the N volatility framework,
risk-normalised distance to 1N/2N/3N, trend structure, session and opening-range context, volume,
and a **Kalman local-level-plus-slope state estimator**. No RSI, MACD, Stochastic or CCI — the brief
was to add nothing outside the Turtle concept set without evidence of incremental information.

Truncation audit: recompute every column on history ending at bar *i* and require an exact match.
**936 checks, 0 mismatches.**

## The label was wrong first, and the way it was wrong is the lesson

The natural label — "does price reach +1R before −1R before the 12:00 flatten, with a flatten
counted as a loss" — makes the target a function of **time remaining and bar speed**, not direction.
Measured on that version:

| feature | win, bottom decile | win, top decile |
| --- | ---: | ---: |
| `min_to_close` | **0.00%** | **43.17%** |
| `min_since_open` | 43.17% | 0.00% |
| `rvol_50` | 5.22% | 44.38% |
| `atr_ratio_short_long` | 8.84% | 42.77% |

A bar near the flatten *cannot* reach the target, and a fast bar resolves before the bell — so
anything that speeds resolution inflates the win rate. **64 of 117 features "passed" BH on what was
really a stopwatch.** Corrected: drop bars with under 60 minutes of session left, and label only
**resolved** trades, so the question is "given that this resolves, does it resolve at the target?"

## Redundancy: 124 columns are 47 bets

| | |
| --- | ---: |
| clusters at \|ρ\| ≥ 0.9 | 92 (18 with >1 member, largest 4) |
| principal components for 90% of variance | 32 |
| principal components for 95% | **47** |
| mean \|ρ\| between features | 0.216 |

Tightest clusters are exactly the ones the construction implies: `dist_high20_atr` with
`to_1N/2N/3N_up` (the same distance rescaled), the ATR-over-price family, and the three time-of-day
encodings. Any p-value here is corrected against **47**, not 124.

## The result on the corrected label

Base rate **47.27%** on 3,061 resolved research-block trades — close to the driftless 50%, a little
under it from cost.

| feature | win bottom decile | win top decile | gap | z |
| --- | ---: | ---: | ---: | ---: |
| `atr_pctile_1000` | 43.55% | **58.25%** | +14.70 | 3.70 |
| `atr14_over_price` | 40.39% | 54.40% | +14.01 | 3.51 |
| `chan55_width_pct` | 43.32% | 57.33% | +14.01 | 3.51 |
| `dir_persist_20` | **53.09%** | 42.23% | **−10.86** | −3.42 |
| `or_pos` | 55.05% | 42.02% | −13.03 | −3.26 |
| `ret24_consistency` | 56.05% | 45.12% | −10.93 | −3.08 |

**14 of 124 pass BH at q=0.10; 6 pass Bonferroni at the effective count of 47.** The best single
decile anywhere is **58.25%**, and break-even at 1:1 with a 1.0×ATR stop on this data is **58.36%** —
the best feature's best decile lands *exactly at* the cost floor, in-sample, after selection.

**Directional persistence predicts NEGATIVELY.** `dir_persist_20`, `ret24_consistency`,
`slope_ema200_atr` and `or_break_dist_atr` all separate the wrong way for a trend system: the more
persistent the recent direction, the *lower* the probability of reaching +1R first. That is the same
mean-reversion conclusion this branch has now reached from six independent directions.

## The composite, and the out-of-sample read

Top feature from each of the six largest independent clusters, sign-aligned, summed as z-scores:

| block | n | base | top 10% | top 20% | top 30% |
| --- | ---: | ---: | ---: | ---: | ---: |
| research | 3,052 | 47.38% | **57.19%** | 55.48% | 54.04% |
| **out-of-sample** | 1,634 | 46.45% | **48.78%** | 47.09% | 48.37% |

**+9.8 points in-sample becomes +2.3 out of sample**, and 48.78% is nearly ten points *below* the
58.36% break-even. Textbook selection decay, on a composite built from features chosen on the same
block.

One honest limitation of the redundancy step: five of the six "independent" picks
(`atr_pctile_1000`, `atr14_over_price`, `chan55_width_pct`, `chan20_width_pct`, `atr50_over_price`)
are conceptually **one thing — volatility level**. They correlate below 0.9 pairwise, so a
correlation threshold does not catch them. Conceptual redundancy is not the same as linear
redundancy, and a threshold cannot see the difference.

## The Kalman filter

Added because it is a genuinely different estimator — a state with adaptive lag, not another
smoothing constant — and its innovation (standardised surprise) is something no moving average can
express. Ranks of the seven Kalman features among 124:

| feature | rank | gap | p |
| --- | ---: | ---: | ---: |
| `kf_slope_sign` | 23 | −3.66 | 0.045 |
| `kf_innov_abs` | 27 | +7.49 | 0.061 |
| `kf_slope_persist` | 29 | −3.73 | 0.064 |
| `kf_innov_z` | 39 | +6.51 | 0.106 |
| `kf_dist_atr` | 61 | +4.23 | 0.293 |

**None survives correction for 47 effective tests.** The two slope features separate *negatively*,
consistent with the mean-reversion finding.

`kf_slope_atr` returned z of exactly 0.00, which I first flagged as probably a degenerate scaling.
It is not: the feature has 70,671 unique values, sd 0.118 and a range of −0.60 to +0.84. Both
deciles simply contain **n = 307 with exactly 150 wins each** — 48.8599% against 48.8599%, an exact
tie rather than a bug. Recorded because the wrong guess is the more instructive half: a suspicious
zero deserves the two-minute check before it is either cited or dismissed.

## Verdict

**65% at 1:1 is not reachable from this feature set on this data.** The unconditional resolved base
rate is 47%, break-even is 58.4%, the best in-sample decile is 58.3%, and out of sample the best
composite decile is 48.8%. To hit 65% a model would need to add **18 points** over base; the best
measured, before decay, adds 11 and lands at the cost floor.

What the exercise did establish, and both are worth carrying: **a label that counts a timeout as a
loss measures the clock, not the market** — and **trend persistence is anti-predictive here**, from a
seventh independent direction.
