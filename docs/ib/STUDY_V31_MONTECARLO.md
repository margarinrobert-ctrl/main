# V31 — a Monte Carlo over every reproducible result on this branch, and the mean of them

**Ask.** Run a Monte Carlo on all the data results and see their mean.

**Answer.** The mean is **+0.083 R per trade on research and +0.085 on locked** equal-weighted over
34 declared configurations, and **+0.070 → +0.044** trade-weighted. Both bootstraps exclude zero.
But **one configuration of thirty-two has a locked bootstrap that excludes zero**, and it is the one
that failed research — while **all four rows the bootstrap called significant on research lose their
significance on locked, and the two strongest of them invert outright.** The mean is positive and
almost none of the individual rows can be told apart from it.

---

## 1. Two Monte Carlos, and why they cannot be one

`CLAUDE.md` already records the rule this study is built on: *permuting trades cannot change the
endpoint*. So the two questions are asked with two different resamplers.

| | resampler | answers | reported |
| --- | --- | --- | --- |
| **Bootstrap** | whole DAYS with their trades attached, with replacement, 4,000 draws | how uncertain is the mean R per trade | mean, p05, p95, P(mean ≤ 0) |
| **Permutation** | reorder the realised trades, 4,000 draws | how deep a drawdown this edge can produce | realised DD, MC p50/p95/p99, realised percentile |

Days are the resampling unit because a breakout fires two or three times on the same move; 300
trades here are about 120 days. No endpoint distribution is printed from the permutation.

## 2. The pool

34 declared configurations, every one a result this branch has already tested and reported. Nothing
is searched. Eight families: the regime ladder around the shipped rule (CHOP and ADX rungs), the
same base on 15m, six geometry axes, the five additions that were rejected (RSI, EMA state, EMA
cross, linreg cross, linreg state), four entry windows, the short mirror, V22's adaptive volatility
stop, and four US30 rows. 33 scorable on research, 32 on locked, at a 30-trade floor.

Costs: NQ carries the real MNQ stack (`cost_mult` 1.44). US30 has no itemised model here, so its
multiplier is set to put the round turn at ~2.50 points — the figure `research/v30/run_opt.py` uses.
That is a stated assumption, not a measurement.

**Three things the arithmetic cannot remove, stated before the numbers.** The pool is not a random
sample of strategies — it is the neighbourhood of one family that survived a long search, so its
mean is biased up relative to "a strategy you might have written". The locked block is
post-selection for most rows: a bootstrap prices sampling error inside a block, never the selection
that chose the row. And the rows share trades, so the equal-weight bootstrap treats correlated
experiments as independent.

## 3. The mean of all results

| | equal-weight over configurations | trade-weighted over the pooled set | share positive |
| --- | --- | --- | --- |
| **research** (33 cfg, 11,212 trades) | **+0.0830 R** [+0.0575, +0.1087] P(≤0) 0.000 | **+0.0704 R** [+0.0407, +0.0997] P(≤0) 0.000 | 29 / 33 = 0.879 |
| **locked** (32 cfg, 6,166 trades) | **+0.0846 R** [+0.0573, +0.1123] P(≤0) 0.000 | **+0.0440 R** [+0.0077, +0.0802] P(≤0) 0.022 | 26 / 32 = 0.812 |

Median configuration +0.1048 research, +0.0912 locked. Best +0.2996 / +0.3185, worst −0.1380 /
−0.1173.

**THE WEIGHTING DECIDES THE SIGN OF THE DECAY.** Equal-weighted the mean does not decay at all
(+0.0806 → +0.0846, mean change **+0.0040**). Trade-weighted it falls by a third (+0.0704 →
+0.0440). The difference is US30: four rows out of thirty-two, but a third of the locked trades, and
they invert. This restates the branch's existing warning that trade-weighted and day-weighted
expectancy disagree in sign on an intraday trend system — the unit of weighting is a modelling
choice, and it is doing more work here than any parameter in the pool.

## 4. Nothing in the pool separates from the mean

**Research-to-locked R correlation across the 32 shared configurations: Pearson +0.215, Spearman
+0.088.** Knowing what a configuration earned on research tells you close to nothing about what it
earned on locked. This is the V30 surrogate finding (research surface fitted at ρ 0.96, locked
predicted at ρ 0.07) reproduced across *families* rather than across parameters of one family.

**4b. The four rows the bootstrap called significant on research, read once on locked:**

| configuration | research | locked | |
| --- | --- | --- | --- |
| 30m ADX ≥ 20 | +0.2996, P(≤0) 0.033 | +0.2099, P(≤0) 0.171 | does not hold |
| 30m CHOP ≤ 40, 2R target | +0.1457, P(≤0) 0.025 | +0.1282, P(≤0) 0.099 | does not hold |
| US30 30m base | +0.1763, P(≤0) **0.002** | **−0.0323**, P(≤0) 0.689 | inverts |
| US30 30m CHOP ≤ 40 | +0.2139, P(≤0) **0.007** | **−0.0081**, P(≤0) 0.539 | inverts |

**0 of 4 hold. At α 0.05 on 32 configurations, 1.6 research passes are expected by chance alone —
so four passes is barely above the null, and the two most significant of the four are the two that
invert.** The strength of a research p-value carried no information about survival here; if
anything it ran the wrong way.

**4c. The one row significant on locked** is `30m CHOP ≤ 40, exit channel 10`: research +0.0687 at
P(≤0) 0.215 → locked +0.2144 at P(≤0) 0.045. That is the **wrong shape** — better on the holdout
than on the block it was measured on. This branch has now seen that four times and has treated it as
a defect every time. It is not a candidate.

## 5. The permutation says the two blocks had different paths

A percentile near 0 means the realised equity curve was **smoother** than a random ordering of its
own trades; near 1, rougher.

| block | n | mean percentile | median | share > 0.50 |
| --- | --- | --- | --- | --- |
| research | 33 | **0.254** | 0.180 | 0.121 |
| locked | 32 | **0.647** | 0.645 | 0.688 |

The realised research paths were consistently luckier than a reshuffle of their own trades, and the
locked paths consistently unluckier. Read this cautiously: the rows share trades heavily, so this is
closer to one or two independent observations than to sixty-five, and the two blocks are one sample
each. What it is not is evidence of a broken rule — a drawdown is one draw.

**What it is good for is sizing.** On the locked block the MC p99 runs up to **2.15×** the realised
drawdown (`30m CHOP ≤ 50`, realised 15.0 R → plan for 32.2 R; `15m adaptive`, 23.0 → 46.8;
`08:00-12:00`, 9.4 → 19.1). Size for the p99, as `STUDY_V19_DESTROY` concluded from the other
direction when it found a realised 15.5 R against an MC median of 22.4 and a p99 of 60.8.

## 6. What this changes

Nothing ships and nothing is withdrawn. What the study adds is a number for a question the branch
had never asked directly: **the average tested variant here earns about +0.04 to +0.08 R per trade,
the pooled bootstrap on that mean excludes zero, and no individual row in the pool can be
distinguished from that mean out of sample.** The edge such as it is belongs to the family, not to
any of the choices made inside it — which is the same conclusion the drop-one tests, the
same-selectivity controls and the V30 surrogate all reached by different routes.

Reproduce: `python3 research/v31/v31mc.py`. Raw output: `docs/ib/v31_montecarlo_output.txt`.
