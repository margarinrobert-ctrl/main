# V28 — Deep learning for parameters and regimes: a capacity ladder with an honest null

**Model capacity buys nothing here, and it makes things worse the more you add.** AUC falls
monotonically with depth in every family. The best model in the study is a *heavily regularised
random forest*, and the second best is *logistic regression*.

**And a classifier that genuinely beats chance can still destroy the strategy.** On NQ every one of
nine models turned a +0.0304 R baseline negative, while scoring AUC 0.52–0.58 out of sample.

## Why it was built as a ladder rather than as "run a deep net"

"Use deep learning to find the best parameters" is a parameter search with more capacity. This
branch has already run very large searches: 110,250 configurations bought **+0.098 R out of sample
against the un-swept starting point's +0.097**; 143,820 configurations produced one survivor of ten
finalists; 16.2M generated strategies and 142.8M SAM combinations were mostly null. The binding
constraint has never been optimiser power — it is signal-to-noise, and a network with more capacity
searches the same noise harder.

So the informative experiment is a **ladder** — constant, linear, trees, shallow net, deep net, on
identical folds and label. If capacity buys nothing, that is a statement about the *data* which no
architecture fixes.

## The setup

- **Label**: not the next return — the **R-multiple of the trade the rule would actually open**
  (Donchian 30 breakout, 2.0N stop, 20-bar channel exit). A model that forecasts returns but not
  trade outcomes cannot be traded through this rule.
- **Features**: 141 causal columns at the signal bar — 71 volatility-state features, the momentum
  pool, CHOP/ADX, the three causal HMM posteriors from V27, plus structure and session.
- **CV**: **purged and embargoed** walk-forward, 6 folds. Trades overlap, so a naive K-fold trains on
  the answer; any training trade whose `[signal, exit]` interval overlaps a test interval (±50 bars)
  is dropped. `STUDY_EDGELAB` recorded what happens without this — scoring bar-wise made 17,121 of
  27,786 tests "pass" BH at q 0.10.
- **The null that matters**: every model is run again on **shuffled labels**. That score is the floor
  the pipeline produces from nothing.

## 1. The ladder (NQ 30m, 4,123 signals, base rate 33.7%, +0.0987 R taking every signal)

| model | AUC | IC | R top50 | R top10 | shuffled AUC | shuffled R top10 |
| --- | --- | --- | --- | --- | --- | --- |
| constant (no model) | 0.5000 | — | +0.0987 | +0.0987 | 0.5000 | +0.0987 |
| logistic regression | 0.5585 | +0.1553 | +0.0186 | +0.0642 | 0.4945 | +0.1668 |
| **random forest 300** | **0.5732** | +0.2377 | +0.0695 | +0.1443 | 0.4791 | +0.0516 |
| LightGBM 400 | 0.5438 | +0.1415 | +0.0843 | +0.0475 | 0.4803 | −0.0173 |
| XGBoost 300 d3 | 0.5603 | +0.1713 | **+0.1359** | +0.0750 | 0.4796 | −0.0615 |
| XGBoost 600 d6 | 0.5347 | +0.1257 | +0.0628 | +0.0556 | 0.4806 | −0.0077 |
| XGBoost 1200 d10 | 0.5233 | +0.1053 | +0.0685 | +0.0442 | 0.4900 | −0.0304 |
| MLP 2×64 | 0.5394 | +0.1027 | +0.0633 | −0.0363 | 0.4850 | +0.0713 |
| MLP 4×128 | 0.5132 | +0.0804 | +0.0482 | −0.0103 | 0.4957 | +0.0720 |
| MLP 6×256 | 0.5060 | +0.0767 | +0.1219 | +0.1683 | 0.5089 | **+0.2633** |

**Capacity is monotonically harmful within every family.** XGBoost 0.5603 → 0.5347 → 0.5233 as depth
goes 3 → 6 → 10. MLP 0.5394 → 0.5132 → 0.5060 as it goes 2×64 → 4×128 → 6×256. The deepest network
lands at 0.5060 — chance.

**And read the last column before believing any "R top10".** The deepest MLP's *shuffled* twin earns
**+0.2633**, more than any model earns on real labels. That statistic is noise-dominated, and the
shuffled control is what reveals it.

## 2. The locked read — trained on research, read once

| market | model | n all | R all | n sel | R sel | **delta** | AUC |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NQ | logistic regression | 1444 | +0.0304 | 722 | −0.1194 | **−0.1498** | 0.5165 |
| NQ | random forest 300 | 1444 | +0.0304 | 722 | −0.0090 | **−0.0394** | 0.5779 |
| NQ | XGBoost 300 d3 | 1444 | +0.0304 | 722 | −0.0028 | **−0.0331** | 0.5619 |
| NQ | XGBoost 1200 d10 | 1444 | +0.0304 | 722 | −0.0223 | −0.0526 | 0.5312 |
| NQ | MLP 6×256 | 1444 | +0.0304 | 722 | −0.0476 | −0.0779 | 0.5192 |
| US30 | logistic regression | 3739 | −0.0090 | 1870 | +0.0997 | **+0.1087** | 0.5900 |
| US30 | random forest 300 | 3739 | −0.0090 | 1870 | +0.1086 | +0.1176 | **0.6143** |
| US30 | **LightGBM 400** | 3739 | −0.0090 | 1870 | **+0.1275** | **+0.1365** | 0.5821 |
| US30 | XGBoost 1200 d10 | 3739 | −0.0090 | 1870 | +0.0589 | +0.0679 | 0.5753 |
| US30 | MLP 4×128 | 3739 | −0.0090 | 1870 | +0.0482 | +0.0572 | 0.5374 |

**The markets disagree, and that is the finding.** On NQ all nine models make it worse. On US30 all
nine make it better. Capacity still doesn't help on either: LightGBM 400 beats XGBoost 1200 d10 and
every MLP on US30, and the shallow models lead on NQ too.

**A 0.578 AUC on NQ converts to −0.0394 R.** Ranking wins better than chance and losing money is not
a contradiction — see below.

## 3. The mechanism — a better win-rate classifier is not a better strategy

| market | model | win% all | win% sel | R all | R sel | **p90 R all** | **p90 R sel** |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NQ | random forest 300 | 32.7% | **38.9%** | +0.0304 | −0.0090 | **+1.740** | **+1.340** |
| NQ | XGBoost 300 d3 | 32.7% | 36.4% | +0.0304 | −0.0028 | +1.740 | +1.469 |
| US30 | random forest 300 | 30.7% | **38.7%** | −0.0090 | +0.1086 | +1.872 | **+1.896** |
| US30 | XGBoost 300 d3 | 30.7% | 36.7% | −0.0090 | +0.0926 | +1.872 | +1.882 |

Both markets show the model doing exactly what it was trained to do: **win rate 30–33% → 36–39%.**
The difference is entirely in the tail. On NQ the 90th-percentile R **falls from +1.740 to +1.340** —
the model buys its win rate by discarding the big winners, and a breakout system earns in the tail,
so the net result is negative. On US30 the tail is **preserved** (+1.872 → +1.896) and the same win
rate gain drops straight to the bottom line.

**Train on win/lose and you get a win-rate optimiser.** If the strategy's P&L lives in the tail, that
objective is misaligned with the thing you are trying to improve, and whether it helps or hurts
depends on whether the tail happens to survive — which is not something the model was asked to
protect.

## 4. Caveats that travel with the US30 result

- Its baseline is **negative** (−0.0090). Rescuing a losing baseline to +0.10 is an easier claim than
  improving a winning one, and it is roughly what CHOP alone already achieves.
- 3,739 locked signals against NQ's 1,444, all hours, no CHOP filter.
- The selectivity gate — the model's half against random halves of the same size — is the test that
  decides whether this is edge or restrictiveness. **A filter keeping 50% of signals moves mean R by
  selectivity alone** (`STUDY_V12`), and no result here should be traded before that gate is read.

## 5. Verdict

Nothing ships. The recommended configuration is unchanged: **30m, Donchian 30/20, 2.0×ATR stop, no
target, CHOP ≤ 40, all hours, long.**

Three durable facts came out of it:

1. **Capacity is monotonically harmful on this data.** Every family degrades as it deepens; the
   winners are a regularised forest and logistic regression.
2. **A shuffled-label twin is mandatory.** The deepest network's shuffled twin outscored every real
   model on the headline P&L statistic.
3. **AUC and P&L can point in opposite directions**, and the diagnostic is the p90 of R in the
   selected set. Label on the thing you actually want.

## Files

| file | what it does |
| --- | --- |
| `research/v28/v28data.py` | 141 causal features at signal bars, purged+embargoed folds, US30 bar prep |
| `research/v28/v28ml.py` | the ladder, shuffled null, locked read, mechanism table, selectivity gate |
