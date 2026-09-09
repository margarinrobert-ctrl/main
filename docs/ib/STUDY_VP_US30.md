# Volume profile on US30 — the feature family is clean, the pool binds, and nothing clears a control

Two sources: Max Anderson's *Volume Profile Analysis* (67pp; mechanical content is pages 1–21) and a
combined US30 study guide synthesising Forthmann, Whalestrader and Anderson. Data: the uploaded
`us30_20162025_15m_data1.csv`, sha256 `24dcf2e1c7ba398f` — **byte-identical to `US30_LONG_15m`**,
already in the registry, so both blocks below are second reads.

## Part 0 first, because it decides what the rest can mean

`Volume` is **zero on 100% of rows**. `TickVolume` is the real activity column (correlation with the
bar's own range **+0.7661**, against `Volume`'s undefined). Every profile here is therefore a **tick
count** profile, not a volume profile.

The study guide reaches the same conclusion independently and states it more strongly than I would:
on CFD data the order-flow half — footprint, delta, absorption, stacked imbalance — "is not merely
degraded. It is meaningless, because those tools read the aggressor side of each executed trade,
which a CFD feed does not have." That is correct, and it removes Part 6 of the guide from testing
entirely. A second degradation: the finest US30 data on disk is **15 minutes**, so each bar's tick
count is spread uniformly across its high–low range. The NQ volume-profile work on this branch used
a 1-minute source mapped onto 15m bars and had no such gap.

## What was built

**2,246 RTH session profiles**, bins scale-free at 0.10 × session ATR, value area 70%, HVN/LVN as
local extrema of the histogram. Sanity: the POC lands inside the value area on **100.0%** of
sessions.

**52 causal features** — 22 volume-profile (distance to POC/VAH/VAL in ATR, above/inside/below
value, nearest HVN and LVN above and below, stacked-POC counts at 5 and 20 sessions, the book's
bullish/bearish/neutral distribution taxonomy, developing intraday POC) plus 30 advanced quant
(Parkinson and Garman–Klass volatility, realised vol, vol-of-vol, ATR ratio and rank; the same
quantities against a **causal time-of-day baseline**; fractional differencing at d = 0.2 chosen by
ADF on the research block only; a Baum–Welch HMM read **filtered**, never smoothed; momentum; and
structure).

**Truncation audit: 3/3 clean on the profiles, 0 mismatches of 23 on the rolling quant features.**
`ffd.` and `hmm.` are excluded by design — their parameters are block-scoped, so a truncated refit
is a different estimator rather than a leak.

**Base rates on the trigger's own bars — the pool binds.** No feature passes >95% of trigger bars;
the largest lift is `inside_va` at 2.92× on HVN events, which is mechanically expected. This is the
first feature family this session where the base-rate check did *not* find the trigger restated.

## Gate 1 — five primaries, stop 1.5×ATR, no target, flat at the RTH close, 2.29 pts round turn

| primary | block | n | /yr | win | PF | gross PF | %/trade | control PF | p |
|---|---|---|---|---|---|---|---|---|---|
| HVN retracement | research | 1,163 | 174 | .4394 | 1.008 | 1.057 | +0.0015 | 0.981 | 0.440 |
| | holdout | 406 | 182 | .4113 | 1.045 | 1.088 | +0.0066 | 0.994 | 0.440 |
| LVN breakout | research | 1,156 | 173 | .4273 | 1.054 | 1.104 | +0.0094 | 0.979 | 0.200 |
| | holdout | 440 | 197 | .4409 | 1.086 | 1.128 | +0.0130 | 1.036 | 0.340 |
| **POC shift** | research | 1,200 | 180 | .4258 | **0.907** | 0.961 | −0.0142 | 0.947 | **0.620** |
| | holdout | 380 | 171 | .4816 | 1.186 | 1.246 | +0.0206 | 1.008 | 0.120 |
| **Naked POC** | research | 1,006 | 150 | .4155 | **1.124** | 1.177 | +0.0220 | 1.013 | **0.200** |
| | holdout | 327 | 147 | .4404 | **1.273** | 1.321 | +0.0396 | 0.961 | **0.100** |
| Open rejection reverse | research | 376 | 56 | .3910 | 1.021 | 1.066 | +0.0041 | 1.021 | 0.500 |
| | holdout | 109 | 49 | .3761 | 1.034 | 1.065 | +0.0068 | 0.922 | 0.260 |

**0 of 10 tests clear p ≤ 0.05, against 0.5 expected by chance.** Best anywhere is naked POC at
p 0.100 on the holdout.

**The guide's headline claim does not hold.** It calls POC shift "the best trend-entry signal in the
book"; it is the **only negative primary on the research block** (PF 0.907, control p 0.620) and
positive only on the holdout — growth out of sample, the wrong shape, for the 14th time here.

**Cost is not the objection.** The round turn is 2.1–2.6% of a 1.5×ATR stop and every primary is
gross-positive. Where these fail, they fail on the signal.

## Gate 2 — the advanced quant layer, on both viable primaries

Purged embargoed folds, objective the **R earned** (a win/lose objective is a win-rate optimiser and
trims the tail), each model beside a **shuffled-label twin**, and the filter scored as a **veto**
re-simulated end to end rather than as a subset of realised trades.

| primary | best model | OOF IC | twin | twins winning | keep 0.70 | 0.50 | 0.30 |
|---|---|---|---|---|---|---|---|
| LVN | ridge | +0.0294 | −0.0052 | 1 of 4 | −0.0035 | −0.0005 | −0.0255 |
| Naked POC | random forest | +0.0621 | −0.1300 | **2 of 4** | −0.0409 | −0.0379 | −0.0087 |

**Every uplift at every keep fraction on both primaries is negative.** Random-veto p ranges
0.420–0.700; the bootstrap 0.525–0.688. Nothing clears anything.

The holdout reads confirm it and add a calibration failure:

| primary | holdout base | holdout kept-50% | kept share vs 0.50 target |
|---|---|---|---|
| LVN | R/ev +0.0215, PF 1.044 | **−0.0525, PF 0.899** | 0.600 |
| Naked POC | R/ev +0.1065, PF 1.221 | **+0.0620, PF 1.123** | 0.575 |

The filter makes both primaries **worse** out of sample, and the research threshold does not mean
the same thing on the holdout (0.575–0.600 kept against 0.50 asked) — a milder form of
`STUDY_AUTOBNN`'s failure. Deflated Sharpe on the LVN chain **0.1015** at 14 counted trials.

## Verdict

The feature engineering is sound and that is worth stating separately from the result: the profiles
are causal and audit clean, the pool binds rather than restating the trigger, and cost is not the
binding constraint. **What fails is everything downstream.** Five primaries drawn from two books
produce ten control tests and zero passes; the 30-feature advanced quant layer — volatility,
time-of-day-normalised participation, fractional differencing, a filtered HMM, momentum, structure —
**subtracts from both primaries at every selectivity, on both blocks**, with its shuffled twin
winning half the model ladder on the better primary.

Naked POC is the only thing worth naming: positive on both blocks, gross-positive, p 0.200 / 0.100.
It grows out of sample rather than decaying, both blocks are second reads of a file this branch has
used many times, and it does not clear a random entry. That is a candidate to watch, not a strategy.

This is the third volume-profile result on this branch and it agrees with the first two.
`STUDY_AUCTION` found 7 of 172 auction-condition tests passing on research (fewer than chance) and 0
surviving the holdout; `STUDY_VP_TPO_NEXT` found the one VP feature that ever worked on NQ scoring
PF 0.927 against a 0.973 base **on this exact US30 file**. Do not re-run this family.
