# Deep learning on the meta layer — 65 features lose to 7, and the one that ranks on research inverts

`research/v66/`. NQ 15-minute, mechanism-first architecture, objective = the R earned.

## Where the deep learning was put, and why not on PIN

The obvious target was the PIN posterior, but `STUDY_PIN_BAYES` had just failed it at Gate 1 on
both constructions, and this branch has twice measured that a meta layer cannot rescue a Gate-1
failure (`STUDY_EMA48_VWAP_DL`, `STUDY_VWANOM`: a filter makes a dead base less bad, never alive).
So the model work went on a primary that passes, and the PIN machinery went where the architecture
says objects like it belong — the meta layer, where it can score events and can never create one.

**Four primaries were declared and Gate 1 run on all of them, research only, against a matched
random entry** (identical geometry, exits, costs and position lock; signals forced through `ent_hi`;
picks sorted, per `STUDY_V59`):

| primary | n research | /yr | pct/event | PF | control p |
|---|---|---|---|---|---|
| P1 cvd15 gated | 225 | 117 | 0.0697 | 1.546 | **0.020** |
| P2 cvd15 ungated | 905 | 470 | 0.0129 | 1.091 | 0.530 |
| **P3 bayesopt rth** | **680** | **353** | 0.0616 | 1.353 | **0.030** |
| P4 don30 ungated | 432 | 225 | 0.0357 | 1.173 | 0.525 |

Two of four are eligible. P3 wins on the criterion that actually binds: `STUDY_V61_FEATURES_15M`
built the strongest meta layer on this branch on P1 and concluded that 125 locked events cannot
separate a +0.05 uplift from noise, and that **the fix is more events**. P3 has three times as many.

P3's locked block was opened in `STUDY_BAYESOPT_DONCHIAN`, so every locked number below is a
**second read and is descriptive**, not a test.

## The features

51 features in V61's seven declared families, plus a new `pin` family of 14 built from the Bayesian
mixture — the fitted parameters, the posterior's own credible-interval width (the thing an MLE
cannot supply at all), the latent-state posterior at the bar, the buy/sell dispersion `STUDY_PIN_BAYES`
showed PIN is actually tracking, and the plain signed imbalance as the control. 65 features, 8
families, 996 events with a complete row (659 research / 337 locked).

Truncation audit: **0 mismatches over 1,020 comparisons**; the PIN family's causality is structural
and was checked directly (0 of 12 probe sessions show the fitted parameters moving *inside* the
session they are used in).

**The base-rate table already says something.** Mean |lift − 1| on the trigger's own bars, by
family: volu 0.730, ffd 0.458, mom 0.456, struct 0.431, vol 0.407, regime 0.263, trend 0.197 —
and **pin 0.087, the lowest of the eight**. A session-level statistic barely distinguishes a
breakout bar from any other bar.

## The ladder — capacity is not the constraint

Purged + embargoed folds, uniqueness weights, every model beside a shuffled-label twin:

| model | IC real | IC shuffled | twin wins |
|---|---|---|---|
| ridge | −0.0494 | −0.0078 | yes |
| **rf** | **+0.1021** | +0.0397 | no |
| lgbm | +0.0703 | −0.0438 | no |
| xgb d3 | +0.0352 | −0.0693 | no |
| xgb d6 | +0.0442 | −0.0254 | no |
| mlp 2×32 | −0.0015 | −0.0747 | no |
| mlp 2×64 | −0.0235 | +0.0173 | yes |
| mlp 4×128 | +0.0196 | −0.0289 | no |

The **regularised random forest wins for the fifth time on this branch** (V28, EMA48, conformal,
S3, here). Ridge is negative, the deepest net reaches +0.020, and there is no gradient in depth —
capacity is not what is limiting this. The shuffled twin wins **2 of 8 (25%)**, which is the best
noise-floor reading here yet (S3 58%, VWANOM 71%), so there *is* signal above the floor.

## Feature engineering is subtractive, and that is the finding

The family ablation over **8 seeds** (seed noise sd 0.004, so these are not fit artefacts):

| feature set | k | mean IC | Δ vs all | improves in | t |
|---|---|---|---|---|---|
| ALL | 65 | 0.0983 | — | — | — |
| drop regime | 57 | 0.1171 | **+0.0188** | 8/8 | +6.82 |
| drop mom | 57 | 0.1150 | +0.0167 | 8/8 | +10.13 |
| drop struct | 56 | 0.1147 | +0.0164 | 8/8 | +6.49 |
| drop ffd | 61 | 0.1129 | +0.0145 | 8/8 | +7.51 |
| drop trend | 55 | 0.1051 | +0.0068 | 6/8 | +2.62 |
| drop volu | 60 | 0.1010 | +0.0027 | 5/8 | +0.95 |
| drop pin | 51 | 0.0923 | −0.0061 | 2/8 | −2.60 |
| drop vol | 58 | 0.0409 | **−0.0574** | 0/8 | **−17.77** |
| pin alone | 14 | −0.0087 | −0.1070 | 0/8 | −84.04 |

**Six of eight families make the model worse.** Removing them is an improvement at t +2.6 to +10.1.
Pushed to its conclusion:

| feature set | k | mean IC |
|---|---|---|
| **vol + pin** | 21 | **0.1762** |
| `vol.parkinson` alone | **1** | **0.1501** |
| vol only | 7 | 0.1407 |
| everything | 65 | 0.0983 |
| everything minus vol | 58 | 0.0409 |

**Seven features beat sixty-five by +0.0424 at t +17.08, and a single Parkinson volatility estimator
beats all sixty-five on its own.** With 659 events and 65 columns the model is fitting noise, and
every family added past volatility costs more than it brings. The deep-learning answer to "maximise
this" is to delete most of the inputs.

## PIN earns a meta place after failing as a primary

This was the sharp test of the paper, and it comes out positive:

* adding PIN to volatility alone: **+0.0355, t +16.68**
* adding PIN to everything else: +0.0061, t +2.60
* PIN alone: **−0.0087** — negatively informed by itself

And it is not a volatility duplicate: the mean |ρ| of a `pin.*` feature to its nearest volatility
feature is **0.161** (max 0.307, `pin.dispS` vs `vol.rv96`). Its single strongest overlap anywhere
is `pin.imb` to `trend.d_ema50` at 0.68 — the plain imbalance, not the mixture.

So the demotion was right and the machinery is not worthless: as a *primary* PIN is a dispersion
statistic dressed as a probability, and as a *conditioning variable* on top of volatility it adds
something volatility does not already carry. That is precisely the mechanism-first prescription for
fracdiff and HMM states, arriving at a third object.

## And none of it survives

Gate 2 on the best set (vol + pin, 21 features, seed-averaged score), research block:

| keep | n | R/event | uplift | boot p | rand p | PF | target hit |
|---|---|---|---|---|---|---|---|
| base | 659 | 0.0754 | — | — | — | 1.249 | 42.9% |
| 0.80 | 527 | 0.0941 | +0.0187 | 0.290 | 0.104 | 1.331 | 43.6% |
| 0.50 | 330 | 0.1372 | +0.0618 | 0.072 | 0.010 | 1.547 | 44.5% |
| **0.30** | 198 | 0.1611 | **+0.0857** | **0.050** | **0.027** | **1.709** | 43.9% |

One cell clears both nulls. Then the locked read:

| keep | n kept | kept % | R/event | uplift | PF |
|---|---|---|---|---|---|
| base | 337 | 100% | 0.0447 | — | 1.133 |
| 0.60 | 200 | 59.3% | 0.0173 | −0.0274 | 1.051 |
| 0.50 | 170 | 50.4% | 0.0354 | −0.0094 | 1.105 |
| 0.40 | 128 | 38.0% | 0.0246 | −0.0201 | 1.070 |
| **0.30** | 89 | 26.4% | **−0.0174** | **−0.0621** | **0.952** |

**Every rung is negative, and the rung that scored best on research is the worst out of sample** —
the harder it filters, the worse it does, monotonically. PF 1.709 → 0.952.

The one thing that *did* transfer is the calibration: the score keeps 26.4% when asked for 30%
(largest gap 0.036), so the research threshold means the same thing on both blocks — the opposite of
`STUDY_AUTOBNN`, where a research threshold kept 105 of 105. **The score is calibrated and the
ranking is not.** That is a cleaner failure than an uncalibrated one, and it rules out the
explanation people usually reach for.

The mechanism is visible in the last column of the research table: the **target-hit rate barely
moves** (42.9% → 43.9%) while PF goes 1.249 → 1.709. The model is not selecting trades that go
further, it is avoiding losers — the win-rate mechanism `STUDY_V32` recorded, and it does not
transfer.

**Deflated Sharpe 0.163 over 134 counted looks**: per-event Sharpe 0.1023 against an expected
best-of-noise of **0.1410**. The primary's own Sharpe is below the noise floor of the search that
examined it. FAIL.

## Two things to carry

**p90 of R is degenerate on a target-capped primary.** P3 has a 3.2 ATR target against a 3.8 ATR
stop, so a winner's R is capped at 0.842 and p90 reads **0.835 for every subset in the study** — the
branch's standard tail diagnostic (`STUDY_V28`, `STUDY_V32`: read p90 of R, not AUC) silently
measures nothing here. On a capped primary the tail question has to be asked as the **target-hit
rate**, which is what the table above reports.

**A join that fails silently produces "no signal", not an error.** `sess_core` labels a session
`YYYYMMDD` as an int; the first PIN feature build used epoch-days. Zero days matched, every `pin.*`
value came back NaN, and the pipeline printed *"events with a complete feature row: 0"* rather than
raising — the same failure class as the all-NaN recursive indicator in `STUDY_V54`, reached through
a different door. Always print the join's overlap count before using it.

## The shippable form, and what it costs

A random forest cannot be written in Pine. Measured on the same seven features, **the ridge beats
the forest** — OOF IC **0.1527 against 0.1407** over 8 seeds — so for once the portable form is the
better one.

All seven univariate ICs point the same way: **higher volatility, higher R** (atr_pct +0.243,
parkinson +0.236, rv96 +0.161, atr_rank250 +0.121, atr_ratio50 +0.101, rv_ratio +0.057, vol_of_vol
+0.010). That agrees with `STUDY_V63`'s floors-positive/ceilings-negative reading and inverts
`STUDY_V28`, whose only survivor of 240 cells was the bottom fifth of ATR — the sixth time a
volatility-state rule's sign has moved on this branch. But **three of the seven ridge coefficients
have the opposite sign to their own univariate IC** (atr_pct, rv_ratio, vol_of_vol) —
multicollinearity exploited conditionally, and the least stable part of the model, so each feature
also ships as a standalone switch.

Two portable gates, both re-simulated as vetoes rather than split out of the base run's trades
(`STUDY_AUCTION`: filter the triggers and re-simulate):

| arm | research n / %-per-event / PF | locked n / %-per-event / PF |
|---|---|---|
| off | 689 / 0.06356 / 1.358 | 337 / 0.07687 / 1.336 |
| ridge keep 0.60 | 479 / 0.07919 / 1.423 | 227 / 0.10039 / 1.385 |
| count ≥ 5 of 7 | 300 / 0.10803 / **1.546** | 130 / 0.20107 / **1.722** |

Both look better under the veto framing than as a subset of realised trades, which is that rule
restated. Neither changes the verdict: on the subset framing the ridge gate beats the base on
**none** of the five locked rungs, and the count gate is **better on locked than on research** at
T ≥ 5 and T ≥ 6 — the wrong shape, which this branch treats as a defect. Both ship **default off**
with their own numbers in the tooltips.

Parity against the engine (`research/v66/v66_parity.py`): research 689 script trades against 680
engine, **96.44% identical exit bars**, correlation 0.9951, script +3.2%; locked **337/337**,
**97.61%**, 0.9974, script −2.8% — conservative. The residual is three irreducible things: the
bracket is priced in ticks because `strategy.exit(loss=)` is, the ratcheting stop starts one bar
after the fill because `strategy.position_avg_price` is `na` there, and the max-hold exit is a
market order filling at the next open. The hard-coded thresholds keep 70.4 / 60.7 / 50.9 / 40.7 /
30.9 percent against targets of 70/60/50/40/30, so the exported constants and the Pine arithmetic
agree.

Ships as `pine/v66/V66_VOL7_DONCHIAN_strategy.pine`.

## What would move it

Not capacity, and not more features — both were swept and both are negative. Events: 659 research
events is where a 21-feature model already overfits, and the research uplift at keep-30 would need
roughly four times the sample to separate from a null. The primary generates 353 a year on one
market, so this is a data problem, and the only lever is more markets with 1-minute bars.
