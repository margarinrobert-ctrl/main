# Conformalized quantile regression and a regularised random forest on the Donchian 55/30 cell

`research/inst/run_conformal.py`, `results/inst/conformal.txt`. The second attempt to improve the
Edge Finder's cell (NQ 15m RTH, Donchian 55/30, 1.5 adaptive ATR, no target, swing hold, MA200
floor ≥ 2 ATR, CHOP ≤ 40: research 192 trades PF 2.495, locked 105 PF 1.916) with a model, chosen
to target the failure the first attempt exposed. `STUDY_AUTOBNN` failed on **calibration** — its
posterior means shifted between blocks and a research threshold kept 105 of 105 locked trades.
Split-conformal prediction gives a distribution-free coverage guarantee whatever the model, so the
keep rule can be "calibrated lower bound of R > 0" with no threshold chosen on research at all.

Three things were done to give it a fair chance that the AutoBNN run did not have: **training on
the whole Donchian-55 family** (2,693 RTH breakout bars with the cell's exit geometry, R per bar
from the tensor, the cell being a 960-bar subset) rather than the cell's 192 trades, with López
de Prado uniqueness weights (mean concurrency 2.0) because overlapping labels are not independent;
the **37 truncation-audited features** from `research/ema48` plus V61's three, rather than eight;
and V28's best model, a **regularised random forest**, beside the gradient-boosted quantile pair.
Purged and embargoed sequential folds; the calibration set is the last 30% of each training window
in time; shuffled-label twins on every model; a same-size random subset as the null.

## Verdict

**No improvement.** The conformal machinery works exactly as advertised — coverage 0.79–0.91 per
fold against a 0.90 target, 0.89 on the locked block — and what it certifies is that **no trade of
this strategy is predictably profitable at 90% confidence**: the calibrated interval on a trade's R
is about **±4.6 R** wide (Q = 3.4–5.5 per fold, 4.62 on locked), so the lower bound is below zero,
and below −1 R, on every trade in both blocks. The median predicted R is negative on every trade
too, which is simply the 23% win rate stated back: the edge is in the tail, and the tail is not
where the features point.

| rule | research (cell trades) | random subset, same size | shuffled twin | locked |
|---|---|---|---|---|
| base | 192, PF 2.495 | — | — | 105, PF 1.916, +8.02% |
| CQR lower bound > 0 (no research cut) | **0 trades** | — | 0 | **0 trades** |
| CQR lower bound > −1 R | 0 | — | 0 | 0 |
| q50 (median R) > 0 | 0 | — | 0 | — |
| q50 top 60% | 115, PF 2.201 | median 2.448, p 0.703 | 1.841 | — |
| RF top 60% | 115, **PF 3.038** | median 2.506, **p 0.138** | 1.817 | (descriptive) 52, PF 2.293, **+5.17%** |
| RF > 0 | 14, PF 8.008 | median 1.981, p 0.043 | 2.181 (n 136) | **4 trades**, +4.15% |

Out-of-fold IC on the cell's research trades: q50 **−0.093** (twin −0.024), CQR lower bound
−0.060 (twin −0.043), **random forest +0.118** (twin −0.127) — the one positive reading. On the
locked block the forest's IC is **+0.027**. Its top-60% rule reads PF 3.04 on research against a
random subset's 2.51 (p 0.138, not significant) and, read descriptively on locked as a second read,
raises PF 1.92 → 2.29 while cutting total return **+8.02% → +5.17%** — the familiar exchange of
count for ratio, not an improvement. Its "> 0" rule keeps 4 of 105 locked trades. Sizing by the
forest's rank (0.5×–1.5×) moves the locked total +8.02% → +8.40% and the research total
+19.54% → +18.06%: noise either way.

The forest's top features are the time-of-day volume ratio (0.19), bars since the 13/48 cross,
the 3-bar ATR-normalised return, the MA200 distance — every one of them a family this branch has
already measured as null or inverting on breakout bars.

## What this settles

- **Calibration was not the problem; predictability was.** With the calibration guaranteed, the
  interval that results is wider than any trade's expected R by an order of magnitude. A model
  that cannot bound a trade's R inside ±4 R has nothing to select on.
- **More data did not help.** Training on 2,693 family bars instead of 192 trades, with proper
  uniqueness weights, produced the same shape as every meta-label on this branch: a research-block
  IC that a shuffled twin can match or that decays to ~0.03 out of sample.
- **The forest is the best of a null lot for the third time** (V28, EMA48, here), and its best
  rule still trades total return for profit factor.
- The cell stands as measured. A model that filters it does so by removing trades, and this
  strategy's return lives in the trades a filter removes.
