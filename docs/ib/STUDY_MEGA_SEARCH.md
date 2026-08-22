# 225,792 configurations, a locked holdout, and three tools that did not find edge

The request was to run the maximum number of combinations, hunt for anomalies to exploit, and add
tools that could improve the edge. All three were done. All three failed to find anything, and the
way they failed is more useful than a win would have been.

Reproduce with `python3 research/mega_sweep.py`, `research/mega_analyse.py`, `research/anomalies.py`
and `research/metalabel.py`.

## 0. The protocol

Seven axes — IB length, retracement, stop, reward-to-risk, direction, break buffer, flatten time —
crossed exhaustively into **225,792 configurations**, run over 292,908 bars of regular-session NQ.
143,536 of them clear 30 trades in every period.

| period | share of bars | role |
| --- | --- | --- |
| research | first 60% | the only data selection is allowed to see |
| validate | next 20% | ranks finalists |
| **locked** | **last 20%** | **opened once, at the end** |

Selection is on **dollars**, following `STUDY_VECTORBT.md`, which showed a mean-R objective converges
on small-denominator configurations and conceals its own failure.

## 1. Search width is monotonically harmful

Draw W configurations, take the best on research, then open the locked holdout.

| search width | median locked P&L | % profitable | locked-holdout percentile |
| --- | --- | --- | --- |
| 1 (a random pick) | −$1,556 | 40% | **51.5** |
| 10 | −$3,242 | 41% | 44.7 |
| 100 | −$6,856 | 27% | 32.1 |
| 1,000 | −$10,490 | 10% | 22.0 |
| 10,000 | −$14,150 | 4% | 14.2 |
| 50,000 | −$14,150 | 0% | 14.2 |
| **143,536 (all)** | **−$14,580** | **0%** | **13.4** |

A random configuration lands at the 51.5th percentile, which is what "random" should mean. Every
increase in search width moves the result **down**, without a single reversal, across five orders of
magnitude. The best of all 143,536 lands at the **13.4th percentile**.

**Rank correlation between research and locked P&L: −0.079.** Not weak — absent, and faintly
negative. Research performance carries no information about what happens next.

This supersedes the narrower result in `STUDY_VECTORBT.md`, which found selection informative up to
a turning point around a fifth of the grid. That turning point was an artifact of a 1,536-cell grid
in which the "best" was still a fairly ordinary configuration. At 143,536 cells there is no rising
section at all. **The curve does not turn over; it was never going up.**

## 2. What the winner looks like

The single best configuration on research earned **$117,230**:

> IB 30 minutes, retracement **0%**, stop 120%, reward-to-risk **1:4**, both sides, break buffer 4
> ticks, flatten at 300 minutes

| period | P&L | trades |
| --- | --- | --- |
| research | **$117,230** | 440 |
| validate | $50,753 | 148 |
| **locked** | **−$14,580** | 147 |

Two periods of spectacular performance, then a loss. Note the geometry: a **0% retracement** is not a
retracement at all — it enters at the break, the thing the whole strategy exists to avoid — paired
with the most extreme reward-to-risk on the grid. The search did not find a better version of the
idea. It found the corner of the parameter space where 2023–24 happened to reward buying breakouts.

Compare the geometry that was pre-specified from mechanism rather than searched:

| | research | validate | locked | locked percentile |
| --- | --- | --- | --- | --- |
| best of 143,536 | $117,230 | $50,753 | **−$14,580** | **13.4** |
| pre-specified v3 | $22,494 | $4,237 | **−$210** | **57.3** |

The pre-specified geometry earns a fifth as much in-sample and beats **57% of all 143,536
configurations** on data nobody looked at. The searched winner beats 13%.

Honest context: the locked period was hostile to this whole family — mean −$2,710, median −$1,922,
only 41.9% of configurations profitable. That is why the percentile column matters more than the
dollar column. Percentile is regime-neutral, and it says the same thing.

## 3. What the axes say

Median locked-holdout P&L by level, across all configurations — a marginal view that no single
search can be fooled by:

| axis | levels (median locked $) |
| --- | --- |
| retracement | **0%: −6,623** · 10%: −3,238 · 20%: −161 · 25%: −534 · 40%: −2,246 · **50%: +118** · **60%: +600** |
| reward-to-risk | **0.75: −945** · 1: −966 · 1.5: −1,650 · 2: −2,286 · 3: −3,047 · **4: −3,342** |
| IB length | 15: −4,442 · 30: −2,356 · 60: −3,648 · **90: +4,847** · 120: +4,084 |
| direction | shorts: −5,454 · both: −2,750 · **longs: +1,273** |

Two of these independently confirm findings reached elsewhere by other means:

- **Deeper retracements are better, and entering at the break is worst.** 0% is the single worst
  level on the entire grid. This is the fourth independent arrival at "pullback entries beat
  breakout entries" — and note that the searched winner used 0%.
- **Higher reward-to-risk is monotonically worse in dollars**, exactly inverting how it looks in R.
  The same mechanism as `STUDY_VECTORBT.md`.

Longs remain positive even here, which is the seventh sighting of NQ's drift. The locked period was
still net-up for the index.

## 4. Anomaly hunt: 29 conditions, nothing survives

A different and safer question: holding the geometry fixed, does its edge concentrate in conditions
knowable *before* entry? Weekday, gap direction, IB range percentile, prior-session range and
result, volume percentile, where the first hour closed inside its own range, how long after the IB
close the entry came, and interactions.

29 conditions, Newey-West t-statistics, Benjamini-Hochberg across all of them.

**Zero survive at q < 0.10. The smallest q is 0.911.** Nothing is remotely close.

The research/holdout columns show why the raw numbers looked promising:

| condition | research $/trade | holdout $/trade |
| --- | --- | --- |
| side == long | +405 | **−150** |
| break agrees with IB close (long) | +406 | **−339** |
| IB closed in upper third | +346 | **−292** |
| IB range percentile ≥ 67 | +255 | **−275** |

Every large research effect changes sign. With 167 trades and 29 tests this search is badly
underpowered, so the honest statement is **"no effect large enough to find here"**, not "no effect".

## 5. Meta-labelling: the tool that should have worked

Meta-labelling keeps the geometry and learns which of its signals to *skip* — a secondary classifier
predicting whether each signal wins, from pre-entry features. It is the one tool in the
López de Prado toolkit aimed at improving an existing edge rather than discovering one, and it does
not touch the parameters at all.

Built properly: gradient boosting on 11 features, **purged and embargoed K-fold** (`research/purged_cv.py`)
so no trade spanning a fold boundary leaks, and a locked holdout the model never sees.

| | AUC | $/trade filtered | $/trade unfiltered | signals kept |
| --- | --- | --- | --- | --- |
| **purged CV** | 0.536 | **$441** | $167 | 36% |

A 2.6× improvement in cross-validation, with leakage controls in place. Then the locked holdout, once:

| threshold | signals kept | $/trade | total |
| --- | --- | --- | --- |
| take everything | 107 | −$173 | −$18,560 |
| ≥ 0.50 | 44 | **−$245** | −$10,784 |
| ≥ 0.55 | 24 | **−$564** | −$13,546 |

**The filter makes it worse, and monotonically worse as it gets more selective.** Its most confident
picks are its worst. Cross-validated $441 became −$245 out of sample.

The lesson is not that meta-labelling never works. It is that **purged, embargoed cross-validation —
the strictest CV in the literature — still overstated by a factor that flipped the sign.** With 418
training signals, no amount of CV hygiene substitutes for held-back data.

## 6. What this changes

1. **Do not run the parameter search.** Not a smaller one — the curve is monotone, so any width is
   worse than none. Pre-specify geometry from mechanism and accept the smaller in-sample number.
2. **Percentile against a full grid is a better report than P&L.** It survives a hostile regime, and
   it is how the pre-specified geometry's 57.3 was distinguishable from the winner's 13.4 when both
   lost money.
3. **A cross-validated improvement is not evidence.** Purged CV with an embargo said $441/trade and
   the truth was −$245. Only locked data settled it.
4. **The three findings that keep recurring** — pullback beats breakout, dollars beat R, direction
   cannot be a free parameter — arrived again here from a completely different direction. Those are
   the ones to trust.

## Caveats

- One instrument, three years, one regime, and a locked period that was hostile to the whole family.
- The sweep covers one strategy family. "Search is harmful" is demonstrated for this grid; the
  mechanism (selection fitting period-specific noise) is general, the magnitude is not.
- Meta-labelling was tested on one feature set and one classifier at one sample size. A different
  primary with thousands of signals is a genuinely open question.
