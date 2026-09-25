# V42 — 1,152,000 Turtle configurations, scored by the median of their walk-forward folds

**The three configurations the search chose fail their random-entry control on both held-back
markets. The one it did not choose — the preset the script already ships — clears at p 0.005 on
all three.**

## What was run, and the four choices that framed it

Chosen by the user before any code was written: the objective is the **median across walk-forward
folds**, the search runs on **US100 with US30 and NQ held back**, the ML is a **surrogate over the
grid** with its fit quality reported, and the **pyramid ladder is a swept axis**.

| | |
| --- | --- |
| nominal cells | 1,843,200 |
| **effective cells** | **1,152,000** |
| scorable (≥ 6 of 8 folds with ≥ 8 trades) | 1,131,227 |
| runtime | 192 s on 4 cores |

The gap between nominal and effective is an **inert-axis interaction**: the ladder is off whenever
`pyramid_step == 0` **or** `max_units == 1`, and in that state the other axis does nothing. Of the
16 (step, units) pairs, 7 are ladder-off and collapse to one.

**The cached-exit-tensor trick does not apply here.** `core.run` re-anchors the stop to each new
fill, so a trade's outcome depends on the whole add sequence, not just its signal bar and geometry.
Every cell is a full walk. Measured at 0.131 ms per config on 240-minute bars, which is the only
reason a seven-figure sweep is affordable.

## 1. The shape of the grid, before any ranking

```
median-of-folds > 0 : 97.9%        aggregate R > 0 : 99.5%
q50 +0.3041   q90 +0.6871   q99 +1.2182   q99.9 +1.7694   max +2.8461
cells with ALL 8 folds positive: 271,936  (24.0%)
```

**97.9% of the space is positive on the objective.** The best cell is the maximum of roughly 1.1
million positive draws.

## 2. The surrogate, fit quality first

`STUDY_V30_BAYES_OPT` fitted a surrogate to this branch's search space and it explained the
research block at 0.96 while predicting the holdout at 0.07. So this is reported before anything
the model says:

| measurement | R² |
| --- | ---: |
| in-sample | 0.8765 |
| random-row 80/20 | 0.8759 |
| **held out: `tf`** | **0.3455** |
| held out: `units` | 0.6488 |
| held out: `atr_mult` | 0.7407 |
| held out: `entry1` | 0.7840 |
| held out: `exit1` | 0.8068 |

The random-row number is near-interpolation — on a dense grid every held-out cell has neighbours in
training — and it is 0.876, indistinguishable from the in-sample fit. **Removing a whole axis value
is the question that matters, and there the fit falls to 0.35 for timeframe.** The surrogate maps
the region it was shown; it does not extrapolate to parameter settings it has not seen.

Permutation importance, in order: `tf` **0.475**, `exit2` 0.311, `units` 0.264, `entry1` 0.244,
`exit1` 0.243, `atr_mult` 0.230, `pyr` 0.208, `adx≥25` 0.203, `ext≥3.0` 0.187.

## 3. The four frozen configurations

| | tf | e1 | e2 | x1 | x2 | ATR | pyr | units | ADX | ext | skip |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TOP-MEDIAN | 240 | 40 | 40 | 5 | 30 | 2.0 | 0.25 | 4 | ≥20 | <3.193 | yes |
| SURROGATE | 240 | 40 | 40 | 20 | 30 | 2.0 | 0.25 | 4 | <22 | <3.964 | no |
| NEIGHBOURHOOD | 240 | 40 | 40 | 20 | 30 | 2.0 | 0.25 | 4 | ≥20 | <3.964 | yes |
| **SPEC (preset T1)** | 240 | 20 | 55 | 10 | 20 | 2.0 | 0.5 | 4 | <22 | <3.964 | yes |

The three search-derived picks converge — `entry1 = 40`, `entry2 = 40`, `exit2 = 30`, 2.0N,
`pyr = 0.25`, 4 units, 240m. The fourth is what the script already ships and the search never
selected.

## 4. The single read on the held-back markets

Random-entry control: identical ATR stop, channel exit, pyramid ladder, fill convention and costs,
with the entry replaced by a coin flip drawing from the configuration's **own gated population**.

| | US100 *(searched)* | | US30 *(held)* | | NQ *(held)* | |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| | agg R | p | agg R | p | agg R | p |
| TOP-MEDIAN | +2.05 | 0.040 | +1.54 | 0.532 | +1.23 | 0.383 |
| SURROGATE | +2.00 | 0.025 | +0.78 | 0.398 | +1.77 | 0.050 |
| NEIGHBOURHOOD | +2.00 | 0.035 | +1.22 | 0.736 | +1.65 | 0.179 |
| **SPEC (preset T1)** | +1.22 | **0.005** | +0.51 | **0.005** | +1.57 | **0.005** |

**3 of 8 held-back cells clear at p ≤ 0.05, and 2 of those 3 are the SPEC.**

## 5. The mechanism, which is visible in the control column

| config | US100 control | US30 control | NQ control |
| --- | ---: | ---: | ---: |
| TOP-MEDIAN | +0.877 | **+1.660** | +0.952 |
| SURROGATE | +0.840 | +0.684 | +0.410 |
| NEIGHBOURHOOD | +0.833 | **+1.513** | +0.813 |
| **SPEC** | **−0.285** | **−0.228** | +0.111 |

A random entry in the population the *searched* gates admit earns **+0.68 to +1.66 R a trade**. A
random entry in the population the *SPEC's* gates admit **loses money on two of three markets**.

The search did not find a better trigger. It found gate settings that select a regime in which
almost any entry works — and against that null there is nothing left for the breakout to add. The
SPEC's gates select a harder population, so its breakout has something to beat.

## 6. Two harness errors, both caught by a number disagreeing

**The control's entry rate was double.** The first version used
`p_enter = n_target / all_bars × 2.0`; `core.control` uses `n_target / eligible_bars`. The doubled
rate produced more clustered random entries, degraded the control, and made **every configuration
clear at p 0.005**. It was caught because `STUDY_TURTLE` measured the spec on the same market and
timeframe at p 0.475 and that disagreement had to be explained. *(The reconciliation: 0.475 is the
**ungated** spec; preset T1 is that study's own gated row at p 0.010 out of sample, consistent with
the p 0.005 here.)*

**A column named `agg` shadowed `DataFrame.agg`.** Third instance of this class on the branch after
`.first` and `.align`; it raised `'<' not supported between float and method`.

## 7. Caveats attached to the numbers above

- **NQ is thin.** 25 to 56 trades per configuration at 240m under these gates. TOP-MEDIAN and
  NEIGHBOURHOOD produce **no scorable fold at all** (0 of 8 with ≥ 8 trades); their NQ rows are an
  aggregate over 25 and 32 trades.
- **US30's cost is an assumption** — 2.0 points, from a 2-tick spread at a 1.0-point tick. No feed
  here carries bid/ask.
- **US100 is the searched block**, so its p-values are post-selection for three of the four rows.
- The SPEC was never selected by this search, so its p-values are not post-selection *here* — but
  it is the preset of a script on this branch, chosen by an earlier study on this same market.

## Files

| file | what it does |
| --- | --- |
| `research/v42/v42grid.py` | the 1,843,200-cell space, the fold-median objective, the inert-axis accounting |
| `research/v42/run_v42.py` | the parallel sweep, US100 only |
| `research/v42/v42surro.py` | the surrogate, and the held-out-by-axis fit test |
| `research/v42/run_v42b.py` | grid shape, marginals, surrogate report, robust regions |
| `research/v42/run_v42c.py` | the four frozen configs, the single held-back read, the control |
| `results/v42/v42_us100_grid.parquet` | all 1,131,227 scored cells (zstd; 192 MB as CSV, 29 MB here) |
| `results/v42/v42_grid_report.txt`, `v42_frozen_report.txt` | raw output |
