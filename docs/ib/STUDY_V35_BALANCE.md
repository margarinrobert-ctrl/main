# V35 — the Initial Balance reverse-engineered, and generalised to every hour

**Ask.** Reverse-engineer why the IB strategy works, with feature engineering and deep learning, and
apply the same science to other hours of the day.

**Correction to the premise.** It doesn't work. `research/ib_features.py` settled that: 14 causal IB
features × 8 pre-declared candidates, matched control as the gate, BH at FDR 0.10 — 3 passed
research, 2 *lost money* on the holdout, the third decayed to the do-nothing baseline.

**So the question was re-posed as a mechanism question**, which had never been asked: the IB is one
arbitrary window. Does range-formation-then-resolution exist at *other* hours, and is 09:30 special?

**Answer.** No, at three levels. A booster predicts which side breaks first at **AUC 0.86** — and
that is entirely geometry: **the nearer edge breaks first 78.6% of the time**, and a single feature
beats the whole 25-feature model. The 80% rule is not 80%; **93.7% of breaks return inside the range
before the close**, at every hour and every length. And swept across the day, **0 of 38 windows beat
their control on research where 1.9 are expected by chance**, the apparent midday shape does not
reproduce, and its **sign is kept in only 44.7% of cells out of sample** — worse than a coin flip.

---

## 1. The design: the control is the whole study

"Price moves after 10:30" is not a finding; every hour is followed by movement. The null here is **a
window of the same length starting at a random time in the same session**, with the same minimum
tail remaining. That holds range width, volatility, drift and time-of-day fixed and asks the only
question that matters: does *this* window's range predict better than *any* window's range?

44 declared cells — 11 starts (09:30 … 14:30) × 4 lengths (30/60/90/120m), 38 scorable — each
against 150 control draws. Break trade: next bar's open after the first break of either edge, 2.0N
stop, held to a 15:55 flatten. NQ 5-minute, 599 research sessions / 323 locked. Every feature closes
at the window's end; nothing reads a bar that has not closed.

## 2. Reverse-engineering the direction signal: AUC 0.86, and it is worthless

XGBoost and LightGBM on 25 causal window features predict **which side breaks first** at
**AUC 0.8599 / 0.8575** against a 0.495 base rate. That is far too high for a market prediction, so
the question is what the model is reading.

| single feature, alone | AUC |
| --- | --- |
| **`f_close_pos`** — where the window closed inside its own range | **0.8766** |
| `f_body` | 0.8342 |
| `f_vol_bal` | 0.7894 |
| `f_dir` | 0.7617 |
| `f_hi_when` | 0.7471 |
| **"the high is nearer than the low", stated as pure geometry** | **0.8703** |

**One feature beats the entire 25-feature model.** And the mechanism is arithmetic: if the window
closes near its high, the high is a few ticks away and the low is a full range away, so the high
breaks first. Measured: **the nearer edge breaks first 78.6% of the time.** Removing all seven
position features only drops the model to 0.822–0.833, because *when* the extremes formed and the
volume balance encode position indirectly.

**It is worth nothing to trade, and that is measurable too.** The distance from the window close to
the edge that actually broke has a median of **0.779 ATR** — the level is already at price. Sorting
the break trades by that distance:

| quartile (Q1 = nearest edge) | n | mean R | PF |
| --- | --- | --- | --- |
| Q1 | 116 | +0.1182 | 1.212 |
| Q2 | 116 | **+0.2780** | 1.572 |
| Q3 | 115 | **−0.1334** | 0.770 |
| Q4 | 116 | −0.0756 | 0.859 |

Non-monotone. Knowing the break direction with 79% accuracy does not produce a profitable trade,
because the accuracy comes from proximity and proximity is not edge.

## 3. The 80% rule is not 80%

Reversion — price returns inside the range after breaking, before the flatten:

| | rate |
| --- | --- |
| across all 38 research cells | **mean 0.937**, min 0.715, max 1.000 |
| the classic IB 09:30–10:30 | **0.969** |
| random same-length control windows | 0.968 |

**Essentially every break comes back, at every hour and every length, and no more often than for a
random window.** There is no hour where a break "holds". This reproduces the branch's earlier
measurement (the 80% rule at 50.6% against a time-matched control's 59.9%) from a different
direction.

## 4. Is 09:30 special? No — and neither is anything else

**Research.** The classic IB scores excess **+0.0314 at p 0.353** — it does not beat its own
control, exactly as `ib_features.py` found. **0 of 38 cells clear p ≤ 0.05, against 1.9 expected by
chance.**

There *is* a shape. Windows ending around 13:00–14:00 are consistently the best (excess +0.063 to
+0.090, p 0.087–0.293) and windows ending after 14:30 are consistently the worst (−0.09 to −0.12,
p 0.90–1.00). It is coherent across all four lengths.

**Most of that shape is the clock, not the window.** Time remaining after the window correlates
**+0.693 with extension** and **+0.518 with reversion** — a late window's break simply has no time
to travel before the flatten. But it explains only **9.4%** of the variance in excess, and the
relationship is a cliff rather than a gradient:

| tail remaining | cells | excess | extension | reversion |
| --- | --- | --- | --- | --- |
| ≤ 90 min | 8 | **−0.0970** | 1.51 ATR | 0.863 |
| 90–150 | 8 | +0.0562 | 2.66 | 0.945 |
| 150–210 | 8 | +0.0318 | 2.93 | 0.960 |
| 210–270 | 8 | −0.0163 | 2.64 | 0.950 |
| > 270 | 6 | +0.0073 | 2.91 | 0.976 |

With the linear tail effect removed, the top five residual cells all sit at **11:30–12:30 starts** —
a coherent region, not a scattered maximum. That was the one thing worth reading on the locked
block.

## 5. It does not reproduce

| | |
| --- | --- |
| research → locked excess, Spearman | **+0.185** |
| research → locked excess, Pearson | +0.315 |
| **sign kept** | **0.447** — worse than a coin flip |
| locked cells clearing p ≤ 0.05 | 1 of 38 (1.9 expected by chance) |

The five best research cells, read once on locked:

| window | research excess | locked |
| --- | --- | --- |
| 11:30 + 90m | +0.0895 (p 0.147) | **−0.0113** |
| 12:30 + 30m | +0.0783 (p 0.087) | +0.0220 |
| 12:00 + 60m | +0.0782 (p 0.140) | **−0.0102** |
| 12:30 + 90m | +0.0766 (p 0.200) | **−0.0407** |
| 12:30 + 60m | +0.0744 (p 0.207) | **−0.0143** |

**Five of five decay, four of five go negative.** And the locked block's own best cells sit at
09:30 and 10:30 — the region research called mediocre. The surface moved.

## 6. What the outcome model does

Trained on the R of the break trade, with purged folds and a shuffled-label twin, the selectivity
ladder reads: xgb at 10% keep **+0.4183 R against a shuffled +0.3004**; LightGBM at 25% keep
**+0.1796 against a shuffled +0.2518**, and at 10% **+0.3422 against +0.3751**. The noise floor
wins half the cells — the V32 result again, on a different feature family.

## 7. Verdict

Nothing ships. What the study produced is a mechanism, which is what was asked for:

1. **The only thing a window predicts about its own resolution is which edge is nearer** — 78.6%,
   AUC 0.87 from one feature — and that prediction has no tradeable content because the level is
   0.78 ATR from price.
2. **Extension is governed by the clock, not the window**: time remaining correlates +0.693 with how
   far a break travels. A "balance" formed late is worse purely because the session ends.
3. **Breaks do not hold, anywhere**: 93.7% return inside the range, identical to random windows.
4. **09:30 is not special, and neither is any other hour** — 0 of 38 clear their control on
   research, the midday shape that looked best does not reproduce, and the sign transfers 44.7% of
   the time.

The Initial Balance is a level that price is already touching. That is why it predicts direction and
why the prediction is worth nothing.

Reproduce: `python3 research/v35/v35run.py`, `v35ml.py`, `v35why.py`. Raw output:
`docs/ib/v35_window_sweep.txt`, `v35_ml_output.txt`, `v35_direction_anatomy.txt`.
