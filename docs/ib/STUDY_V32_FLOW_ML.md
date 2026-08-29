# V32 — volume, absorption, exhaustion and anomaly features under XGBoost and LightGBM

**Ask.** Gradient boosting on flow-style confirmation features, for the biggest Sharpe and profit
factor, and a win-rate lift of 5–15%.

**Answer.** The win-rate lift arrives and overshoots — **+25% relative on NQ and +41% on US30, out
of sample, against a same-selectivity control at p 0.010 and p 0.000.** Sharpe and profit factor do
not follow. Across 240 model cells, **not one clears its control on profit factor on NQ**, the
shuffled-label twin outscores the real model in **69% of research cells**, and the win objective
takes p90 of R down at every market and every block while the R objective does not. The lift is
real and it is paid for out of the tail.

---

## 1. What was built

43 new causal columns, five declared families (`research/v32/v32flow.py`), truncation-audit clean:

| family | prefix | what it reads |
| --- | --- | --- |
| volume level | `vlm.` | participation against a trailing median, a z-score, a percentile, and an **expanding per-minute-of-day baseline, shifted** so no bar sees itself |
| absorption | `abs.` | effort without result — large volume, small range; volume against what built the channel |
| exhaustion | `exh.` | climax (volume × range), wick rejection, a breakout made on **falling** volume, signed volume bias |
| anomaly | `ano.` | joint outlier in (return, range, volume), gap, and the residual of the move regressed on the participation |
| flow proxy | `flw.` | close-position-in-bar × relative volume, cumulative, and a divergence. **No feed on this branch carries bid/ask, so this is a proxy and is named one.** |

The prefix is `vlm.` and not `vol.` because `v22vol.build` already owns `vol.` for 71 **volatility**
columns; sharing it made the first family-importance table credit volatility's weight to volume.

Three feature sets are run: FLOW (43), BASE (V28's 141), FLOW+BASE (184). Two models — XGBoost and
LightGBM, both shallow, because V28 found capacity monotonically harmful here. Two objectives — **R
itself** (what PF and Sharpe are made of) and **win/lose** (what was asked for). Six selectivity
rungs. Two markets. That is 240 scorable cells.

Guards, none optional: purged + embargoed folds (a training trade whose `[signal, exit]` interval
touches a test interval ±50 bars is dropped), a **shuffled-label twin for every model**, a
**same-selectivity random control** at every rung, and **the position lock re-applied after
selection** — dropping a signal frees the engine to take the next one, so a conditional split of
realised trades would not be a filter test.

## 2. The win-rate ask, answered directly

| | baseline win | best cell | relative | control p(win) |
| --- | --- | --- | --- | --- |
| NQ research | 0.320 | **0.453** (FLOW+BASE xgb, keep 10%) | **+42%** | 0.000 |
| NQ **locked** | 0.353 | **0.441** (FLOW xgb, keep 10%) | **+25%** | 0.010 |
| US30 research | 0.366 | **0.457** (FLOW+BASE xgb, keep 10%) | **+25%** | 0.000 |
| US30 **locked** | 0.311 | **0.440** (FLOW xgb, keep 10%) | **+41%** | 0.000 |

Trained on win/lose, 24–30 of 30 cells beat the baseline win rate in every market×block, and 6–23
of them clear the same-selectivity control. **The 5–15% target is comfortably exceeded and it
survives the holdout.** The lift is also monotone in selectivity, which is the shape a real
mechanism has: US30 locked runs 0.311 → 0.320 → 0.353 → 0.385 → 0.388 → **0.440** as the model
tightens.

## 3. What it costs

Read the same cells' PF and Sharpe:

| | best win-rate cell | PF vs baseline | Sharpe vs baseline | p90 R | control p(PF) |
| --- | --- | --- | --- | --- | --- |
| NQ research | 0.453 | 1.343 vs 1.180 | **+0.60 vs +0.76** | +1.594 | 0.260 |
| NQ **locked** | 0.441 | **1.092 vs 1.102** | **+0.21 vs +0.45** | +1.185 | 0.352 |
| US30 research | 0.457 | 1.550 vs 1.366 | **+0.93 vs +1.17** | +2.082 | 0.258 |
| US30 **locked** | 0.440 | 1.091 vs 0.990 | +0.22 vs −0.04 | +1.516 | 0.212 |

**Sharpe is lower than the unfiltered rule in three of four cells**, and the fourth is US30 locked,
where the baseline itself is a loser (PF 0.990, Sharpe −0.04) so the model is rescuing a negative,
not improving a positive. **No cell clears its control on profit factor.** Counted over all 30
win-objective cells per market×block, Sharpe beats baseline in 2/30, 1/30, 2/30 and 14/30.

## 4. Why — the tail, exactly as V28 predicted

p90 of R in the selected set, from the loosest rung to the tightest:

| | trained on **win** | trained on **R** |
| --- | --- | --- |
| NQ research | 2.369 → **1.785** | 2.358 → 2.259 |
| NQ locked | 1.788 → **1.558** | 1.775 → **1.999** |
| US30 research | 2.583 → **2.341** | 2.651 → **2.937** |
| US30 locked | 2.069 → **1.696** | 2.213 → **2.263** |

**The win objective sells the right tail in all four cells; the R objective does not sell it in
any.** That is the mechanism `STUDY_V28_ML_CAPACITY` identified, now isolated by running the two
objectives side by side on the same features, folds and rungs. A breakout system earns in its right
tail, so a classifier trained on win/lose optimises against the thing that pays. The win rate it
buys is genuine; the trades it discards to buy it are the ones worth having.

## 5. The diagnostic that settles it

**The shuffled-label twin outscores the real model in 83 of 120 research cells (69%).**

| | shuffled PF ≥ real PF | mean real | mean shuffled |
| --- | --- | --- | --- |
| NQ, trained on R | 24/30 (80%) | 1.099 | 1.139 |
| NQ, trained on win | 22/30 (73%) | 1.128 | 1.242 |
| US30, trained on R | 13/30 (43%) | 1.400 | 1.412 |
| US30, trained on win | 24/30 (80%) | 1.400 | 1.460 |

If the model carried no information the twin would win half the time. Above half means the pipeline
produces a better-looking result from **permuted labels** than from real ones — a selection
artifact, not an edge. The worst individual cases are the very rungs that read best: NQ win xgb at
10% keep scores PF 1.433 against a shuffled **1.671**; LightGBM 1.142 against **1.549**.

## 6. Training on R instead

The obvious fix — train on the objective PF and Sharpe are actually made of — does not rescue it.
On NQ research, every rung sits below the 1.180 baseline (Sharpe beats it in **0 of 30** cells),
control p 0.170–1.000, and FLOW+BASE at 25% keep goes outright negative (PF 0.889, Sharpe −0.38).
US30 looks better (21/30 beat baseline PF) but no cell clears its control on research, and the
shuffled twin's mean PF is 1.412 against the real 1.400. The five US30 locked cells that do clear
at p ≤ 0.05 sit on a baseline of PF 0.990 and are 5 of 30 in a post-selection block.

## 7. Do the new features earn their place? The model underweights them

Importance attributed by **source frame**, LightGBM trained on R, research block only
(`docs/ib/v32_importance.txt`):

| | share of importance | share of columns | ratio |
| --- | --- | --- | --- |
| NQ — BASE (141) | 84.1% | 76.6% | 1.10× |
| NQ — **FLOW (43)** | **15.9%** | 23.4% | **0.68×** |
| US30 — BASE | 88.1% | 76.6% | 1.15× |
| US30 — **FLOW** | **11.9%** | 23.4% | **0.51×** |

**The new columns get less weight than their column count would give them by chance in both
markets.** Inside FLOW the ranking is also informative: the top column in both markets is
`ano.beta_move_vol` — the rolling beta of |return| on log volume, which is a *regime descriptor*,
not a confirmation signal — followed by the cumulative flow proxies. The raw volume-level family
`vlm.` takes **1.6% and 2.4%**, i.e. the model barely reads participation levels at all. That is
consistent with `STUDY_AUCTION` (47 auction conditions, 0 survived the holdout) and with the volume
spike finding in `STUDY_DIVERGENCE_CONFIRM`.

One thing does go the other way: the best out-of-sample win-rate cell in both markets is **FLOW
alone**, not FLOW+BASE. But the objective it wins on is the one that does not pay.

## 8. Verdict

Nothing ships. The honest statement of the result is that **the win-rate target was the wrong
target, and this study is the direct measurement of why**: the same models, features and folds
raise the win rate by 25–41% out of sample and lower Sharpe, because on this system win rate and
expectancy are traded against each other through the right tail. Anyone reporting a win-rate
improvement on a breakout system should print p90 of R beside it.

Reproduce: `python3 research/v32/v32run.py`, then `python3 research/v32/v32sum.py
docs/ib/v32_ml_output.txt`. Feature importance by source frame: `python3 research/v32/v32imp.py`.
Raw output: `docs/ib/v32_ml_output.txt`.
