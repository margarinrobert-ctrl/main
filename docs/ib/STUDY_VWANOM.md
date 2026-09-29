# Feature engineering and deep learning on the VWAP-EMA event stream

`research/vwanom/anomfeat.py`, `a2lib.py`, `run_a1.py`…`run_a3.py`, `plot_a.py`.
Results in `results/vwanom/`, figure `vwanom_summary.png`.
Run under the mechanism-first architecture (skill `mechanism-first-alpha`), whose two gates decide
what any of the modelling is allowed to claim.

## 1. Phase 0 — the mechanism, stated before any code

The architecture asks who is on the other side, what forces them to trade anyway, and what would
end it. **Bhatti's rule names nobody.** It is a pullback to an EMA inside a VWAP-filtered session
with a volume spike and a candle shape; the paper offers no constrained flow and no risk transfer.
Family: neither. Free parameters: ten, all tuned.

So this is a fitted pattern, not a mechanism-derived primary, and it carries the **full** deflation
burden rather than escaping it. Recorded in the module docstring before a line of feature code.

## 2. Gate 1 — the primary alone, before any feature exists

Every event, no filter, no sizing, costs in, scored in percent of entry price with the skill's own
`primary_gate`:

| feed | cell | block | n | % of price | bootstrap p | verdict |
|---|---|---|---|---|---|---|
| US100 | SHORT | research | 431 | +0.0816 | **0.013** | PASS |
| US100 | LONG | research | 939 | +0.0335 | **0.025** | PASS |
| US30 | LONG | research | 722 | +0.0302 | 0.083 | PASS |
| US30_ISO | LONG | forward | 325 | +0.0326 | 0.117 | MARGINAL |
| US30 | SHORT | research | 348 | +0.0243 | 0.150 | MARGINAL |
| US30 | LONG | LOCKED | 430 | +0.0120 | 0.269 | MARGINAL |
| US100 | LONG | LOCKED | 603 | +0.0057 | 0.379 | MARGINAL |
| US100 | SHORT | LOCKED | 244 | **−0.0029** | 1.000 | **FAIL** |
| US30_ISO | SHORT | forward | 193 | −0.0321 | 1.000 | **FAIL** |
| US30 | SHORT | LOCKED | 198 | −0.0662 | 1.000 | **FAIL** |

**The primary passes on every block it was chosen on and on none of the others.** By the
architecture's rule that is a Gate 1 failure: a meta-labeller trades recall for precision and
cannot create direction skill. Everything below is measured to find out what a meta layer *does*
to such a primary, not to rescue it.

## 3. The feature layer

**51 causal features in nine declared prefixes** — `vol. trn. reg. vlm. str. clk. hst. ffd. anm.`
Separate prefixes so a family-importance table cannot credit one family's weight to another
(`STUDY_V32`: `vol.` already owned 71 volatility columns, so volume had to become `vlm.`).

Three construction decisions that matter more than the list:

- **Volatility and participation are measured against a CAUSAL TIME-OF-DAY baseline** — the
  expanding mean at this minute-of-day over prior sessions — not a trailing mean. On a 24-hour tape
  an RTH bar clears its own 50-bar trailing ATR mean ~99% of the time simply because RTH is busier
  (`STUDY_VWAP_STOCH_ATR`). A trailing ratio is a clock.
- **The HMM is read FILTERED, never smoothed**, and validated on a simulated chain first (means
  −0.907 / +0.837 against a true −0.9 / +0.8; diagonals 0.945 / 0.950 against 0.95).
- **Every unsupervised model is fitted on the research block only** — autoencoder, isolation
  forest, Mahalanobis covariance, HMM, and the fractional-differencing order `d` (ADF, research
  only; d = 0.2 on the LONG feeds, 0.1 on the ISO feed).

**A recursive filter that returns all-NaN reads as "no signal", not as an error.** The first HMM
came back with a NaN posterior on every bar: 15-minute log returns are ~1e-4, so the Gaussian
emission density reached ~400 and the scaled backward recursion divided by a scale that had
underflowed to 1e-300 on one outlier bar. Standardising inside the fit makes it scale-invariant —
the same series at 1e-4 now returns exactly 1e-4× the unscaled means. Same failure class as the
KAMA that returned 99.9% NaN.

**Truncation audit: 0 mismatches / 40 probes.** The fitted models are excluded from that probe on
purpose — refitting them on a truncated block changes the *model*, not the causality — and their
causality is enforced structurally instead.

**One feature is the trigger restated and the base-rate check caught it**: `trn.above_slow` has a
coefficient of variation of **exactly 0.0000** on the event bars, because `close > EMA200` *is*
condition C1 of the primary. It can never refuse a trade. No exact duplicates otherwise
(|ρ| > 0.999: zero); the most redundant pairs are `clk.since_open`/`clk.to_close` 0.984,
`anm.iso`/`anm.mahal` 0.937, `reg.hmm_bear`/`reg.hmm_side` 0.933.

**Every family's IC beats its own shuffled twin** — unusual for this branch:

| family | mean \|IC\| | shuffled | best |
|---|---|---|---|
| vol. | **0.089** | 0.032 | 0.214 |
| hst. | **0.082** | 0.029 | 0.212 |
| vlm. | 0.068 | 0.033 | 0.219 |
| reg. | 0.064 | 0.035 | 0.189 |
| anm. | 0.060 | 0.022 | 0.114 |
| trn. | 0.051 | 0.029 | 0.159 |
| clk. | 0.041 | 0.037 | 0.064 |
| str. | 0.040 | 0.023 | 0.176 |
| ffd. | 0.039 | 0.030 | 0.081 |

The two strongest single features are the causal time-of-day constructions and both are
**negative**: `vlm.tod_ratio` −0.219 and `vol.atr_tod` −0.214 on US30 long. High participation and
high volatility *relative to what this minute-of-day normally shows* predict a **worse** event —
which points straight at C5, the volume-spike condition the rule requires. `clk.` and `ffd.` sit at
their own noise floor. 204 IC tests, correlated, uncorrected.

## 4. The model ladder — and the models rank backwards

Ridge, a regularised random forest, LightGBM d3, XGBoost d3 and d6, MLP 2×64 and MLP 4×128; purged
and embargoed folds with `label_horizon` = the median hold; **objective = the return, not win/lose**
(`STUDY_V28`/`STUDY_V32`: a win objective is a win-rate optimiser and a trend system earns in the
tail); **every model run beside a SHUFFLED TWIN**.

Out-of-fold Spearman IC, real (twin):

| model | US100 SHORT | US30 LONG |
|---|---|---|
| ridge | −0.007 (−0.056) | −0.094 (−0.087) |
| rf (regularised) | −0.011 (**+0.065**) | −0.038 (−0.052) |
| lightgbm d3 | −0.035 (+0.009) | −0.051 (−0.040) |
| xgboost d3 | −0.073 (+0.012) | −0.020 (−0.059) |
| xgboost d6 | −0.026 (**+0.046**) | +0.015 (−0.043) |
| mlp 2×64 | −0.066 (+0.008) | −0.063 (−0.006) |
| mlp 4×128 | −0.032 (−0.012) | −0.024 (−0.019) |

**13 of 14 real ICs are negative**, and the decisive diagnostic:

> the shuffled twin beats the real model in **71% of cells on IC**, 64% at keep-30%, 50% at
> keep-50%, 21% at keep-70%.

Above 50% the noise floor is higher than the signal. At 71% on IC the models rank events *worse
than random labels do*. **Capacity does not help** — `mlp 4×128` is no better than ridge, which is
the fourth family on this branch to show that.

## 5. Gate 2 — the meta layer's uplift on unsized returns

8 of 42 cells PASS on research, and **all eight are US100 SHORT**, mostly the regularised random
forest — the one arm that beats its own shuffled twin at all three keep fractions (0.187 vs 0.048,
0.162 vs 0.063, 0.136 vs 0.085). Best cell: keep 30%, base +0.0816% → **+0.1868%**, uplift
**+0.105**, bootstrap p **0.028**, and p90 of the kept return rises **1.001 → 1.651**, so the return
objective preserved the tail exactly as intended. 17 MARGINAL, 17 FAIL; every US30 LONG cell is
MARGINAL or FAIL.

**But that arm filters the primary whose own locked block scored p 1.000 at −0.0029% of price.**
A meta layer improving selection inside a base that loses out of sample is `STUDY_EMA48_VWAP_DL`
reproduced on a second family: a filter makes a dead base less bad, never alive.

## 6. The anomaly question, answered directly

The literal ask, and the one part that does not need the primary to work: **do events on bars a
model cannot reconstruct behave differently?** Quintiles of each unsupervised score, on every feed,
cell and block. The autoencoder never sees a label, so this family cannot be accused of fitting the
outcome.

| score | cells | mean ρ | share with ρ > 0 |
|---|---|---|---|
| `anm.ae_err` (autoencoder reconstruction error) | 10 | **−0.093** | **0.10** |
| `anm.mahal` | 10 | −0.074 | 0.10 |
| `anm.joint_z` | 10 | −0.064 | 0.10 |
| `anm.iso` (isolation forest) | 10 | −0.079 | 0.20 |
| `anm.ae_pct` | 10 | −0.048 | 0.30 |
| `anm.resid_move` (move not explained by participation) | 10 | +0.044 | **0.80** |

**The more anomalous the bar, the worse the event — negative in 9 of 10 cells for the autoencoder
error, including both reads on the reserved forward block** (ISO long −0.038, ISO short −0.158).
Four of six scores keep a negative sign in 80–90% of cells; `resid_move` is the one that points the
other way, and it is a different construction (a move *not* explained by participation).

Three caveats that stay attached:

- **The quintile means are not monotone.** The consistency lives in the rank correlation, not in
  the ladder — Q1…Q5 jump around at these sample sizes.
- **The 10 cells are not independent.** Six configurations across three feeds, two of which are the
  same US30 data at different block splits, on indices that correlate 0.758 over one calendar. Nine
  of ten is not nine confirmations; the effective count is nearer three.
- **It agrees with the IC screen and with the rule's own construction.** `vlm.tod_ratio` −0.219 and
  `vol.atr_tod` −0.214 say the same thing from the supervised side, and the rule *requires* a volume
  spike (C5), so it is selecting into the region the anomaly scores say is worse. Consistent with
  `STUDY_DIVERGENCE_CONFIRM`, where volume spikes hurt longs monotonically (−2.45 points at 1.5×,
  −17.88 at 2.0×).

## 7. One pre-declared locked read

Model chosen on **research IC**, keep fraction 0.50 declared before the read:

| feed | cell | model | block | n | kept | base | kept | uplift | boot p | p90 base → kept |
|---|---|---|---|---|---|---|---|---|---|---|
| US100 | SHORT | ridge | research | 431 | 50.1% | +0.0816 | +0.1197 | +0.038 | 0.122 | 1.001 → 1.305 |
| US100 | SHORT | ridge | **LOCKED** | 244 | **73.8%** | −0.0029 | +0.0100 | +0.013 | 0.291 | 0.849 → **0.734** |
| US30 | LONG | xgboost d6 | research | 722 | 50.0% | +0.0302 | +0.0427 | +0.013 | 0.324 | 0.420 → 0.477 |
| US30 | LONG | xgboost d6 | **LOCKED** | 430 | **50.7%** | +0.0120 | +0.0315 | **+0.020** | 0.145 | 0.323 → **0.431** |

Both uplifts are positive out of sample and neither is significant. **The kept fraction is the
calibration check and it splits the two cleanly**: US30's score keeps 50.7% against the 50% it was
set for — calibrated, and its p90 rises — while US100's keeps **73.8%**, so its research threshold
does not mean the same thing on the locked block, and its p90 *falls*. `STUDY_AUTOBNN` kept 105 of
105 for the same reason; `STUDY_V61_FEATURES_15M` kept 45% against 40% and that is what calibrated
looks like.

## 8. Deflation

- Candidates evaluated **M = 42**, every return stream kept including the losers.
- Average pairwise correlation **+0.007**, so the trials are near-independent: **effective N = 41.7**.
- `var(trial Sharpes)` = 0.002143 → **E[max Sharpe | pure noise] = 0.1021**.
- Best candidate (US100 SHORT, ridge, keep 30%) Sharpe/event **+0.1936** — above that floor.
- **Deflated Sharpe = 0.895.**
- **White's reality check: p = 0.103 — FAIL.** "A set of worthless candidates searched this hard
  would produce a winner this good at least 5% of the time."

The two disagree, and both are correct about different questions: the DSR deflates one Sharpe
against the trial distribution; the reality check bootstraps the *maximum over candidates* under
the null. On a 42-candidate search that maximum is the relevant statistic.

## 9. Verdict

**Nothing here is tradeable, and one thing is worth keeping.**

Not tradeable: the primary fails Gate 1 out of sample on every block it did not choose; the models
rank backwards (shuffled twin wins 71% of IC cells); the one Gate-2 arm that works filters a base
that loses; and the best candidate fails the reality check at p 0.103.

Worth keeping: **the anomaly direction.** Reconstruction error, Mahalanobis distance and joint
outlierness all say the same thing with the same sign in 9 of 10 cells including the forward block
— *an event on an unusual bar is a worse event* — and the supervised screen agrees through the two
causal time-of-day features at ρ ≈ −0.21. That is a statement about the rule's own C5 volume-spike
condition, not about a new filter, and the honest next step is to test whether **removing** C5
improves the primary rather than adding an anomaly gate on top of it.

What would change the verdict: a primary that clears Gate 1 on a block it did not choose. Feature
work cannot substitute for that.
