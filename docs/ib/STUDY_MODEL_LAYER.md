# Six model families on NQ: what the tooling found, and what it cost to look

The libraries were added on request — LightGBM, XGBoost, CatBoost, PyTorch, scikit-learn, Optuna,
MLflow, Ray. This is what they produced when pointed at 292,083 RTH 1-minute NQ bars.

**Answer: nothing tradeable, and the run is worth reading anyway** — it reproduces, on real data and
in one table, the specific way a machine-learning result on intraday futures looks like it works
when it does not.

Reproduce: `python3 research/ml/runner.py --trials 20 --splits 5`. Layer documented in
`research/README.md`; 26 tests in `research/ml/test_ml.py`.

## Setup

- **Label:** from each bar, the dollar outcome of a position opened at the next open and closed at a
  $900 stop, a $1,500 target, or 16:00 — whichever comes first. Costs $19.00/round turn.
- **Features:** 36 causal columns — returns over 4 horizons, realised vol, ATR-relative, VWAP
  distance, opening-range position, relative volume, CMF(20), time-of-day, and the SMC set
  (BOS/CHoCH/FVG/order block/sweep/dealing range), each optional signal carrying a presence flag.
- **Validation:** purged + embargoed 5-fold, purge horizon 226 bars (95th percentile of holding
  time), 1% embargo. Locked holdout of 58,292 rows split on session boundaries.
- **Benchmark:** take every bar long — **+$15.49/trade research, −$16.16 holdout.** A model has to
  beat that, not zero.

## The families

```
                          rows     AUC   take-all     thr   picked   $/trade     lift  t(day)
torch_mlp              233,791  0.5234      15.49    0.52   17,949     -8.06    -6.76   -0.28
  ^ shuffled control   233,791  0.4975      15.49      --       --        --       --      --
lightgbm               233,791  0.5182      15.49    0.65    8,072     37.38   -37.83   -1.11
  ^ shuffled control   233,791  0.5006      15.49    0.52      756     40.33   +80.79    1.49
catboost               233,791  0.5253      15.49    0.60    7,002     47.32   -37.95   -0.99
  ^ shuffled control   233,791  0.4985      15.49      --       --        --       --      --
hist_gb                233,791  0.5171      15.49    0.65    5,914     65.09   -59.80   -1.65
  ^ shuffled control   233,791  0.4993      15.49      --       --        --       --      --
xgboost                233,791  0.5172      15.49    0.65    5,030     50.47   -75.53   -1.80
  ^ shuffled control   233,791  0.5001      15.49    0.52      567     54.80   +34.69    0.56
logistic               233,791  0.5309      15.49    0.50   15,706    -37.77   -84.12   -3.09
  ^ shuffled control   233,791  0.4951      15.49      --       --        --       --      --
```

**Read the `$/trade` column and every booster works.** hist_gb selects 5,914 bars paying
**+$65.09/trade** against a take-everything baseline of +$15.49 — a $50 improvement, on 233,791
rows, out of fold, from purged cross-validation. That is a publishable-looking number.

**Read the `lift` column and every one of them inverts.** Measured as a *within-session paired
difference* — the same bar's outcome against the mean of every bar in the same session — hist_gb is
**−$59.80**, xgboost **−$75.53**, logistic **−$84.12 at t = −3.09**. All six families are negative
and the only significant result is significantly bad.

The two columns are not in conflict. The models are learning **which days** to be long on a sample
where NQ rose, and inside those days they pick worse-than-average minutes. Remove the day effect,
which is all the paired estimator does, and the skill is negative.

The AUC column is honest about the size of the real signal: **0.517–0.531 against shuffled controls
at 0.495–0.501.** There is about 0.02 of genuine AUC in these features. It does not convert into
within-day dollars at a $19 round turn.

## Optuna, and the price of 20 trials

```
best lift on research     $2.12/trade, t(day) 0.05
spread across 20 trials   $23.97 (worst trial -$96.77)
hurdle for 20 trials      t > 2.45  ->  DOES NOT CLEAR
```

The tuner's best result is **+$2.12/trade against a $23.97 spread across the trials it searched** —
an order of magnitude smaller than the noise it was selecting from. `deflate()` reports the hurdle
E[max z] ≈ √(2 ln 20) = 2.45 that a best-of-20 search must clear; the result reaches t = 0.05.

## The locked holdout, opened once

```
                          rows     AUC   take-all     thr   picked   $/trade     lift  t(day)
untuned torch_mlp       58,292  0.5492     -16.16    0.55    2,255      9.29   -53.90   -1.09
tuned lightgbm          58,292  0.5129     -16.16    0.60    3,492     16.60  -123.09   -2.47
```

This is the clearest example of the trap in this repository.

**Tuned LightGBM's selected bucket pays +$16.60/trade on the holdout, against a take-everything
benchmark of −$16.16.** Pooled, that is a **+$32.76/trade improvement on data the model never saw** —
by the standard of most published ML-for-trading results, a success.

**Its within-session paired lift is −$123.09 at t = −2.47** — significantly negative. The model beat
the benchmark by choosing which *days* to trade, and within those days it chose worse than random.

Note also that torch_mlp's holdout AUC (0.5492) is *higher* than its research AUC (0.5234) while its
lift is −$53.90. **AUC and dollars disagree completely**, which is why nothing here is scored on AUC.

## What was fixed to get these numbers

Three defects, each of which produced a better-looking wrong answer first:

1. **Rows dropped for absent features.** Requiring every feature non-null demanded an unfilled
   fair-value gap on *both* sides at once and cut 292,908 bars to **4,347** — 1.5% of the sample, and
   a biased 1.5%. Optional features now carry presence flags and sentinels. (The identical mistake
   cut the SMC study to 6,091 bars.)
2. **A mismatched estimator.** Per-session means of the selected rows were compared against a
   *pooled* baseline, which reported positive lifts alongside negative t-statistics. The paired
   within-session form fixes it; a test now pins that a day-selector scores ~$0 while a genuine
   within-day signal scores $285 at t = 78.
3. **A hidden search inside the metric.** `evaluate()` takes the best $/trade across five
   thresholds, and the floor for a usable bucket was 30 rows. The maximum of a noisy mean is itself
   a search: shuffled-label controls were selecting 34- and 78-row buckets and reporting **+$450/trade
   at t = 2.70**, beating every real model in the same table. The floor is now 500 rows *and* 30
   distinct sessions.

After the fix, four of six shuffled controls print `--` because no threshold clears the floor —
which is what a noise model should do.

## Conclusions

1. **No model family produces a within-day edge.** All six have negative paired lift; the only
   significant one is negative.
2. **The features carry ~0.02 of AUC**, real but far below what a $19 round turn needs.
3. **Tuning found nothing.** +$2.12/trade against a $23.97 trial spread, at t = 0.05 versus a 2.45
   hurdle.
4. **The holdout looks like a win and is not.** +$32.76/trade over the benchmark, pooled; −$123.09
   paired, at t = −2.47.
5. **Pooled improvement over a benchmark is not evidence of skill** on a sample with a directional
   drift. The unconditional long earns +$15.49/trade in the research half, so any model that leans
   long clears the benchmark without knowing anything.
6. **Every defect found here flattered the result**, and each was caught by a control rather than by
   inspection — the shuffled labels, the locked holdout, and the paired estimator.
