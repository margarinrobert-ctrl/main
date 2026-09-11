# V27 — A Hidden Markov regime model, and the two things that kill it

**Both answers are negative, and both are arithmetic rather than opinion.**

1. **The published HMM recipe leaks.** Fitting on the whole series and reading the smoothed state
   gives locked PF **1.351**; the causal version of the identical model and rule gives **0.973**.
   Same data, same trades attempted — only the information set moves.
2. **The Markov apparatus collapses to the state label.** The one-step forecast, the n-step forecast
   and the signal `p_bull − p_bear` are all deterministic row lookups on the current state. Measured:
   **3 distinct values across 35,701 bars**, and a **Jaccard overlap of 1.0000** between
   "state == Bull" and "signal > 0.3". The stationary distribution has **one value for the entire
   series** and so cannot be a signal at all.

## 0. What was built, and how it differs from the code supplied

The snippets supplied define states by **thresholding** a rolling return (bull above +2%, bear below
−2%) and count transitions. That is a **visible**-state Markov chain: the state is a deterministic
function of data already in hand, so estimating it is labelling.

A **hidden** Markov model infers the states and the parameters jointly. Hand-rolled here
(`hmmlearn` is not installed, and hand-rolling is better: the causal boundary is auditable rather
than a library flag one hopes is set). Diagonal-covariance Gaussian HMM, Baum–Welch, forward and
backward passes written out.

**Validated on a simulated 3-state chain with known parameters:**

| | recovered | true |
| --- | --- | --- |
| means | +0.796, −0.003, −0.896 | +0.8, 0.0, −0.9 |
| std devs | 0.501, 0.297, 0.894 | 0.5, 0.3, 0.9 |
| state accuracy, **smoothed** | **97.5%** | — |
| state accuracy, **filtered** | **93.8%** | — |

That 3.7-point gap is exactly what reading the future buys, on data where the truth is known.

Observation vector is 2-D and causal: the 20-bar mean log return divided by its own dispersion, and
the log of that dispersion — direction and magnitude as separate columns, because a model given only
returns cannot tell a quiet regime from a flat one.

## 1. The fitted model (NQ 30m and US30 30m, fitted on research bars only)

**NQ 30m**, 23,301 research bars:

| state | drift | per-bar vol |
| --- | --- | --- |
| Bull | +0.323 | 0.092% |
| Bear | −0.245 | 0.111% |
| Sideways | +0.032 | 0.097% |

| from ↓ to → | Bull | Bear | Sideways |
| --- | --- | --- | --- |
| Bull | 0.937 | 0.000 | 0.063 |
| Bear | 0.000 | 0.938 | 0.062 |
| Sideways | 0.040 | 0.042 | 0.918 |

Stationary: Bull 0.274, Bear 0.292, Sideways 0.433. Expected durations 16, 16, 12 bars.
**Bull and Bear never transition directly** — every regime change passes through Sideways, which is
economically sensible and is learned, not imposed.

**US30 30m**, 62,323 research bars, is nearly identical: drifts +0.295 / −0.240 / +0.024, diagonal
0.940 / 0.940 / 0.912, stationary 0.306 / 0.289 / 0.404. Two independent instruments, one structure.

## 2. The leak

Donchian 30/20 + CHOP ≤ 40 on NQ 30m, gated on `state == Bull`:

| variant | research n | research PF | research Sharpe | locked n | **locked PF** | **locked Sharpe** |
| --- | --- | --- | --- | --- | --- | --- |
| **LEAKY** — fit on all bars, smoothed decode | 194 | 1.467 | 1.12 | 111 | **1.351** | **1.00** |
| **CAUSAL** — fit on research, filtered decode | 194 | 1.303 | 0.77 | 109 | **0.973** | **−0.10** |

The leaky version looks like a working regime filter. The causal one loses money. Note the trade
counts are almost identical (194/194, 111/109) — **the leak is invisible in the trade count and
shows only in which bars got labelled Bull.**

Fitting parameters on the whole series leaks even if you then decode causally, because the means and
the transition matrix learned the future. A causal HMM needs *both* fixes: parameters from a
training block that ends before the labelled bar, and the **filtered** posterior P(s_t | data up to
t), never the smoothed one or Viterbi.

One caveat on the diagnostic: `STUDY_HP_FILTER`'s surface test (a real edge is a ridge, a leak is a
plateau) could not be applied across random seeds here — the quantile-based initialisation makes EM
converge to the same solution every time, so the seed spread is 0.000 for both variants. The leak is
demonstrated by the causal/leaky contrast, not by a surface.

## 3. The collapse

`P[current_state]` is a row lookup. So for a 3-state model:

| signal | distinct values over 35,701 bars | the values |
| --- | --- | --- |
| 1-step `p_bull − p_bear` | **3** | −0.938, −0.002, +0.937 |
| 5-step | **3** | −0.728, −0.007, +0.721 |
| 12-step | **3** | −0.469, −0.012, +0.453 |
| 24-step | **3** | −0.225, −0.016, +0.199 |
| stationary distribution | **1** | Bull 0.274, Bear 0.292, Sideways 0.433 |

Any threshold on a 3-valued signal partitions the same three groups. Measured directly:
`state == Bull` versus `signal > 0.3` gives **Jaccard overlap 1.0000** on 2,852 signals each.
**They are the same filter wearing two names.** The multi-step forecasting machinery, the matrix
powers and the stationary distribution add no information beyond the current state label.

## 4. The 07:00–11:00 window, both sides, direction set by the regime

Letting the regime choose the side spends no degrees of freedom on direction — this branch has
eleven times watched a free search pick long because every sample rose. `ctlp` is the p-value
against a random filter of the same selectivity.

| window | side / regime | res n | res PF | res ctlp | lk n | **lk PF** | **lk Sharpe** | **lk ctlp** |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 07:00–11:00 | LONG, regime Bull | 103 | 1.181 | 0.13 | 61 | **0.836** | −0.50 | **1.00** |
| 07:00–11:00 | SHORT, regime Bear | 98 | 0.991 | 0.29 | 50 | **0.824** | −0.48 | **0.97** |
| 07:00–11:00 | LONG, no regime | 139 | 1.075 | — | 78 | 1.155 | 0.45 | — |
| 07:00–11:00 | SHORT, no regime | 112 | 0.969 | — | 58 | 1.252 | 0.54 | — |
| 09:30–11:00 | LONG, regime Bull | 72 | **1.683** | **0.00** | 42 | **0.916** | −0.20 | **1.00** |
| 09:30–11:00 | SHORT, regime Bear | 74 | 1.119 | 0.16 | 36 | 1.701 | 0.99 | 0.97 |
| 09:30–11:00 | LONG, no regime | 95 | 1.277 | — | 57 | 1.381 | 0.87 | — |
| 09:30–11:00 | SHORT, no regime | 84 | 1.055 | — | 42 | 2.503 | 1.66 | — |
| all hours | LONG, regime Bull | 194 | 1.303 | **0.00** | 109 | 0.973 | −0.10 | **1.00** |
| all hours | LONG, no regime | 238 | 1.184 | — | 125 | **1.318** | **0.98** | — |

**The regime filter is worse than no filter on the locked block in every single cell**, and its
control p-value on locked is 0.95–1.00 throughout — a random filter of the same selectivity beats it
essentially always. The all-hours long cell is the sharpest illustration: **research control p 0.00,
locked control p 1.00.**

Two things confirm rather than break: **07:00–11:00 is worse than 09:30–11:00 on every comparable
row**, replicating `STUDY_TREND_PULLBACK`'s finding that the pre-open block is subtractive — and the
cost model does not widen the pre-RTH spread, so the true penalty is larger than shown. And the
09:30–11:00 short at locked PF 2.503 on 42 trades has **control p 1.00**, so it is selectivity, not
edge.

## 5. Verdict

Nothing from the HMM ships. The recommended configuration is unchanged: **30m, Donchian 30/20,
2.0×ATR stop, no target, CHOP ≤ 40, all hours, long** — locked PF 1.318, Sharpe 0.98.

The durable output is two reusable facts: **an HMM read the standard way is a two-sided filter and
must be fitted forward and decoded filtered**, and **a transition-matrix signal on K states carries
exactly K values, so it cannot be a richer filter than the state label it is computed from.**

## Files

| file | what it does |
| --- | --- |
| `research/v27/v27hmm.py` | hand-rolled Gaussian HMM: forward, backward, Baum–Welch, smoothed vs filtered |
| `research/v27/v27run.py` | the fit, the transition matrix and forecasts, the leak diagnostic, the collapse proof |
| `research/v27/v27win.py` | 07:00–11:00 both sides with the regime setting direction, control-gated |
