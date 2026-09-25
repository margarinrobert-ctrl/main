# V64 — Monte Carlo perturbation on the three V61 presets

`research/v64/run_mc.py`; `results/v64/mc.txt`. NQ, locked block.

## Verdict

**The rule is not sitting on a knife edge, and its weakest link is sample size, not robustness.**
Jitter every bar's OHLC by up to two ticks and recompute the ATR, both Donchian channels and the
CVD pivot structure from the jittered bars, and **the sign is kept in 100% of 250 draws at every
noise level for all three presets**. Draw slippage from U(0, 2× assumed) and cost from
U(0.5×, 2×) and P(total ≤ 0) is **0.000**. Drop 40% of fills and all three are still positive.

What does bite is the **day-block bootstrap against zero**: on the locked block the incumbent's
P(mean ≤ 0) is **0.110** on 85 trades, and the 15m preset and Pareto cell reach 0.027 and 0.026
through sample size rather than through a bigger edge. That is the same split
`STUDY_V15_BOOK` recorded — **clearing a matched control and clearing zero are different
questions** — and it reproduces here: the WFO control read p 0.000 against a random entry, and the
bootstrap against zero does not clear on the incumbent.

## Which Monte Carlo answers which question

| | Question | Method |
| --- | --- | --- |
| **Perturbation** | does the result survive the world being slightly different? | re-run the strategy on jittered prices / fills / parameters |
| **Permutation** | how bad could the path have been? | reorder the realised trades; **cannot change the endpoint** |
| **Bootstrap** | is the edge distinguishable from zero? | resample trades with replacement |

The branch has conflated these before (an earlier `validate.monte_carlo` printed an endpoint
distribution from a permutation, which is meaningless). All three are run and labelled below.

**The caveat that stays attached** (`STUDY_ATME_LIVE`): a perturbation prices execution and data
noise **on the trades you selected**. It can never price the selection. A P(total ≤ 0) of 0.000
here is not evidence the rule was not fitted.

## The realised results being perturbed

| Preset | res n | res tot% | lock n | lock tot% | lock %/t | lock PF | lock DD% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| incumbent 30m | 157 | +18.88 | 85 | +12.14 | +0.1428 | 1.596 | −7.83 |
| 15m preset | 409 | +25.70 | 208 | +17.91 | +0.0861 | 1.479 | −5.64 |
| Pareto 15m | 348 | +29.35 | 166 | +14.80 | +0.0891 | 1.513 | −4.23 |

## A. Execution perturbation — 2,000 draws

Slippage U(0, 2× assumed), cost U(0.5×, 2×), applied **inside** the walk so it moves the stop and
target decisions too, not just the P&L.

| Preset | p5 | p50 | p95 | Realised | Worst draw | P(tot ≤ 0) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| incumbent 30m | +11.83 | +12.07 | +12.31 | +12.14 | +11.73 | **0.000** |
| 15m preset | +17.03 | +17.68 | +18.30 | +17.91 | +16.75 | **0.000** |
| Pareto 15m | +13.53 | +14.32 | +15.14 | +14.80 | +13.32 | **0.000** |

The p5–p95 band is **half a percentage point wide** on the incumbent. A 2–3 ATR stop on NQ is
60–90 points against a 1.72-point round turn, so cost is ~2–3% of risk and doubling it changes
nothing. This is the least informative of the perturbations and it is reported first so the more
demanding ones are not mistaken for it.

## B. Missed fills

| Preset | drop 5% | 10% | 20% | 40% | Realised |
| --- | ---: | ---: | ---: | ---: | ---: |
| incumbent 30m | +12.09 | +11.71 | +10.64 | +7.44 | +12.14 |
| 15m preset | +17.10 | +16.28 | +14.59 | +10.86 | +17.91 |
| Pareto 15m | +14.29 | +13.62 | +12.13 | +9.03 | +14.80 |

Degradation is roughly linear and nothing crosses zero at a 40% miss rate. **Stated limitation:**
a dropped trade here is only a lost trade — it does not free the position lock, because the lock
lives inside the walk. So this is an upper bound on the damage, not a simulation of a live miss,
where a missed entry would let a later signal in.

## C. Price perturbation — the real test

Every bar's o/h/l/c is jittered independently and the bar repaired (high = max of the four, low =
min), then **ATR(14), both channels and the CVD pivot structure are recomputed from the jittered
bars** — so this moves the *signal*, not only the fill. 250 draws per noise level.

| Preset | Noise | Trades p50 | p5 | p50 | p95 | Realised | **Sign kept** |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| incumbent 30m | 0.5 tick | 85 | +11.53 | +12.01 | +12.50 | +12.14 | **1.000** |
| | 1.0 tick | 86 | +11.20 | +12.00 | +12.99 | | **1.000** |
| | 2.0 tick | 87 | +10.96 | +12.20 | +13.64 | | **1.000** |
| 15m preset | 0.5 tick | 209 | +17.41 | +18.66 | +19.89 | +17.91 | **1.000** |
| | 1.0 tick | 209 | +17.10 | +18.81 | +21.03 | | **1.000** |
| | 2.0 tick | 211 | +15.95 | +18.58 | +21.65 | | **1.000** |
| Pareto 15m | 0.5 tick | 166 | +13.83 | +15.26 | +16.71 | +14.80 | **1.000** |
| | 1.0 tick | 166 | +13.56 | +15.14 | +16.63 | | **1.000** |
| | 2.0 tick | 166 | +13.35 | +15.17 | +16.83 | | **1.000** |

**750 of 750 draws keep the sign.** Trade counts barely move (85 → 87, 209 → 211, 166 → 166), so
the signal set is not fragile either. The medians sit slightly *above* realised at 2-tick noise on
two presets, which is the extra trades the jitter lets through rather than an improvement.

Zero-noise verification: the perturbed evaluator reproduces the reference **exactly** (n 242,
research +18.88%, locked +12.14%), so the machinery is a faithful re-implementation and not a
second model.

## D. Parameter perturbation — where the three presets differ

One rung on each axis, then a joint jitter on six axes, 500 draws. Locked block.

| Preset | Joint p5 | Joint p50 | Joint p95 | **P(≤ 0)** | **Share of neighbours above it** | Worst single rung |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| incumbent 30m | **+0.71** | +10.93 | +18.42 | **0.036** | **0.41** | **+4.24** |
| 15m preset | +13.59 | +20.97 | +27.65 | 0.000 | **0.75** | +13.48 |
| Pareto 15m | +10.41 | +17.76 | +25.26 | 0.000 | 0.70 | +11.37 |

**This inverts the usual ranking.** The incumbent has the better provenance — it is the only
pre-declared cell that cleared its control on the locked block — and the **worse neighbourhood**:
a joint jitter puts it under water 3.6% of the time, its worst one-rung neighbour is +4.24%
(adding a 1 ATR target costs two-thirds of the result), and only 41% of its jittered neighbours
beat it, so it is near the top of a narrow ridge. The 15m preset and the Pareto cell sit on broad
plateaus and are in the **lower quartile of their own neighbourhoods** — 75% and 70% of jittered
variants beat them — which is what a cell that was *not* cherry-picked from a spike looks like.

Per-axis swings on the incumbent: `w` 8.94, `tp` 7.90, `exN` 5.71, `k` 4.98, `ent` 4.74, `stop`
2.73. On the 15m preset the largest is `w` at 7.52 and `stop` is **0.11** — flat.

**`hold` is exactly inert on both 15m presets (swing 0.00) and 0.18 on the Pareto cell** — the
third independent confirmation, after V61's inert-axis accounting and V64's fANOVA importance of
0.012.

## E. Permutation for the path, bootstrap for the edge

| Preset | Realised DD% | MC DD p50 | p95 | **p99** | Realised percentile | Bootstrap mean 95% CI | **P(mean ≤ 0)** |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| incumbent 30m | −7.83 | 4.93 | 7.76 | **9.31** | **0.95** | [−0.0699, +0.4134] | **0.110** |
| 15m preset | −5.64 | 5.10 | 8.13 | **9.77** | 0.65 | [−0.0026, +0.1768] | 0.027 |
| Pareto 15m | −4.23 | 3.96 | 6.41 | **7.77** | 0.60 | [−0.0006, +0.1861] | 0.026 |

**Size for the p99, not the realised drawdown**: 9.31% / 9.77% / 7.77% of equity, which is
**1.19× / 1.73× / 1.84×** what each preset actually drew down.

**The incumbent's realised path was unlucky** — its drawdown sits at the **95th percentile** of
reshuffles of its own trades, so 95% of orderings would have drawn down less. The other two are at
0.65 and 0.60, mildly unlucky. That is the opposite of the usual finding on this branch, where
research paths were smoother than a reshuffle.

**And the bootstrap is where it gets uncomfortable.** No preset's 95% CI cleanly excludes zero on
the locked block, and the incumbent's **P(mean ≤ 0) is 0.110** on 85 trades. The 15m preset and
Pareto cell reach 0.027 and 0.026 — and they get there on 208 and 166 trades with a *smaller*
per-trade edge, i.e. through sample size.

## What this changes

Nothing about what ships, and two things about how to read it:

1. **The 15m preset's evidence is better than its provenance suggested.** It has descriptive
   p-values (chosen from an ablation read after the locked block), but it has the broad plateau,
   the lower bootstrap P(mean ≤ 0), the 9/9 walk-forward folds and no losing quarter. The
   incumbent has the clean pre-registration, the higher per-trade edge — and a narrow ridge, an
   unlucky realised path, and a bootstrap that cannot separate it from zero.
2. **Execution is not the risk here and never was.** Between the 4% cost-to-stop ratio, the
   flat cost sweep and 750 of 750 price-jitter draws keeping their sign, every remaining doubt
   about this rule is about *sample size and selection*, which no perturbation can address.
