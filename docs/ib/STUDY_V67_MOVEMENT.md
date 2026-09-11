# Predicting the movement, not the price — and an out-of-sample IC of 0.71 that bought nothing

`research/v67/`. NQ 15-minute, research 46,033 bars / locked 24,652, split 2024-11-28.

## The question, decomposed so it can fail

"Predict the movement, not the price" is only testable once *movement* is broken into separately
measurable targets. Eight were declared before any scoring, over four horizons (1h, 4h, 12h, 1 day),
with **direction included deliberately as the control that prior work says must fail**:

`mag` net magnitude · `rv` realised vol · `rng` range expansion · `er` **straightness** ·
`mfe`/`mae` the excursion envelope · `ttb` **bars to first touch of ±1 ATR** · `dir` **direction**

`ttb` is new here — no duration target has been used on this branch before.

Every target is scored against **its own trailing realisation**, because `STUDY_V28` measured that
nothing ever beat simply reading CHOP(14) today; every t passes through **Newey-West at lag h**,
because `STUDY_V47` measured overlapping horizons deflating the naive t by 1.9–3.2×. The leakage
audit passed **0 mismatches over 852 comparisons** before anything was scored.

## Part A — movement splits cleanly in two

Mean across the four horizons, research block, best of 71 causal volatility features:

| target | trailing baseline | best feature | NW t at h=4 |
|---|---|---|---|
| `rng` | +0.289 | **+0.602** | 62.2 |
| `rv` | +0.342 | **+0.529** | 49.4 |
| `ttb` | — | **+0.437** | −91.4 |
| `mfe` | +0.069 | +0.343 | 36.5 |
| `mae` | +0.063 | +0.343 | 35.2 |
| `mag` | +0.116 | +0.294 | 42.1 |
| `er` | −0.005 | **+0.041** | 4.4 |
| `dir` | −0.005 | **+0.060** | 3.1 |

**How far and how fast is forecastable; which way and how straight is not** — a tenfold gap in IC
and up to thirtyfold in t, on 46,000 bars. That reproduces `STUDY_V22`'s split (the VIX forecasts
the *size* of the next move and not its straightness) on a different instrument and construction.

Note what is *not* claimed: "beats baseline 4/4" is worthless for `dir` and `er`, whose baselines
are ~0.00, so anything beats them. The number that matters is that their best feature reaches 0.06.

## The null I got wrong, and what it cost

Each |IC| above is the **maximum of 71 features**, which one shuffled twin does not price. My first
correction re-ran the whole sweep on **freely permuted** targets, 40 times. It passed **32 of 32
cells** — including direction and straightness. A test everything passes is not a test.

The cause: free permutation destroys the target's autocorrelation, and an IC on 46,000 *overlapping*
observations of a persistent target has a far larger standard error than that null implies. The
symptom was unmistakable — the null's p95 sat at ~0.014 for **every** target regardless of how
persistent it actually was.

The fix is a **circular block permutation**, blocks 20× the horizon, so local structure survives and
only the feature–target alignment is destroyed:

| target | real | free-null p95 | **block-null p95** | clears |
|---|---|---|---|---|
| `rng` | 0.602 | 0.014 | 0.107 | **4/4** |
| `rv` | 0.529 | 0.013 | 0.102 | **4/4** |
| `ttb` | 0.437 | 0.014 | 0.084 | **4/4** |
| `mfe` | 0.343 | 0.014 | 0.076 | **4/4** |
| `mae` | 0.343 | 0.014 | 0.075 | **4/4** |
| `mag` | 0.294 | 0.015 | 0.067 | **4/4** |
| `er` | 0.041 | 0.015 | 0.049 | 2/4 |
| `dir` | 0.060 | 0.014 | 0.060 | **0/4** |

**26 of 32.** Direction fails at every horizon; straightness passes only the two shortest, by a 1.1×
margin, where the six real targets clear by 2.4–5.7×.

**THE FREE NULL'S CRITICAL VALUE AVERAGES 0.0139 AGAINST THE BLOCK NULL'S 0.0774 — A FACTOR OF
5.6.** A naive permutation null on overlapping financial data understates the bar by nearly six
times. That is `STUDY_V47`'s naive-t error reached from the opposite direction, and it is now
measured rather than argued.

## Part B — the HMM is measuring volatility with extra steps

Causal HMM: parameters from the research block only, **filtered posterior only**, smoothed computed
solely as the leak diagnostic. Fitted structure is sensible and reproduces `STUDY_V27`'s shape —
bear μ −0.0024 with the **highest** volatility (rv 0.137), sideways +0.0011 with the **lowest**
(0.065), bull +0.0028 between; self-transitions 0.964 / 0.990 / 0.985, so expected sojourns of
**28, 100 and 65 bars**. Selloffs are the shortest-lived state and chop the most persistent.

* **Filtered vs smoothed agreement 96.1%**, reproducing V27's 96–97%. Use the smoothed posterior by
  accident and 96% of labels are unchanged, so nothing looks wrong except the results.
* **The collapse test sharpens V27 rather than repeating it.** V27 found Jaccard 1.0000 between the
  state label and a thresholded signal taking **3** distinct values — dismissible as a coarse-signal
  artefact. This signal takes **25,044** distinct values and still overlaps the bare state label at
  **0.9757**. The collapse survives a genuinely continuous signal.
* **0 of 32 cells** where any HMM column beats the best of 71 volatility features. Largest HMM |IC|
  0.478 against volatility's 0.688.

The mechanism is in the columns: `p_bear` scores its largest |IC| against realised vol (+0.428),
`p_side` reaches **−0.478** there and the sojourn feature −0.467 — because the long-sojourn sideways
state **is** the low-volatility state. And the sharpest instance is on the HMM's home question: on
`ttb`, the sojourn feature — the natural duration reading — manages **0.087** where a Parkinson
volatility estimator manages **0.442**, five times better.

Incidental: `ttb` stops depending on the horizon beyond h=16, so a ±1 ATR touch nearly always lands
within four hours and censoring binds only at h=4.

## Part C — the finding: IC 0.71 out of sample, and it changed nothing

An IC table is not a result. `STUDY_V22` names the one place a magnitude forecast should pay: an ATR
stop is **backward-looking** while volatility **mean-reverts**, so heat in ATR units is 1.8–2.2×
larger when volatility sits low in its own distribution. So on the P3 primary that clears Gate 1
(Donchian 11/47, RTH, 3.8N stop, 3.2 ATR target), the trailing ATR setting the stop was replaced by
a **forecast** of forward volatility — a ridge on the seven-feature set, fitted on research only.

The forecast is excellent: **in-sample IC 0.729, locked IC 0.7065**, one of the highest out-of-sample
ICs on this branch. Its multiplier spans 0.54–1.84, so it moves the stop materially.

Four arms, each re-simulated end to end:

| arm | research PF | locked PF | research %/ev | locked %/ev |
|---|---|---|---|---|
| **fixed 3.8N** | **1.358** | **1.344** | 0.0635 | 0.0785 |
| V22 percentile rule | 1.309 | 1.320 | 0.0545 | 0.0725 |
| **forecast-scaled** | 1.310 | 1.299 | 0.0576 | 0.0712 |
| forecast **shuffled** | 1.211 | 1.342 | 0.0391 | 0.0763 |

**The fixed stop wins on both blocks.** Against its own shuffled twin the forecast reads **+0.099 on
research and −0.044 on locked** — it beats its noise twin where it was fitted and loses to it where
it was not, which is the shape of nothing.

**A 0.71 out-of-sample IC bought zero.** That is the study's result, and it is not a contradiction:
the ATR stop already contains the volatility information, so a better estimate of the same quantity
has nothing left to add. Forecast quality and decision value are close to unrelated here.

(V22's own rule also losing to fixed is not a refutation of V22 — that rule was measured on a flat
1.5/2.5N base with no target, and this is a 3.8N stop with a 3.2 ATR target. `STUDY_V52`'s lesson:
a filter is a property of a geometry, not of a market.)

## What to carry

1. **Movement decomposes, and only half of it is forecastable.** Magnitude, envelope and duration:
   |IC| 0.29–0.60, 24 of 24 against a block null. Direction and straightness: 0.04–0.06, 2 of 8.
2. **A permutation null on overlapping data must permute BLOCKS.** The free version understated the
   critical value 5.6× and passed everything.
3. **An HMM's states are volatility states.** 0 of 32 against plain volatility features, and its own
   duration feature is 5× worse than Parkinson at the duration target.
4. **Forecast quality is not decision value.** IC 0.71 out of sample, zero improvement, and the
   shuffled twin is what proves it.
5. **`ttb` is worth keeping** — the most predictable target in the grid and the cheapest honest
   statement about a trade: how long before ±1 ATR resolves. It prices patience, not direction.
