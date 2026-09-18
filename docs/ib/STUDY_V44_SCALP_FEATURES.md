# V44 — Feature engineering on MFE and MAE, and the 07:00–11:00 scalp it produces

**The brief's two selection criteria are the same axis with opposite signs, the MAE ranking
inverts when you change the unit from ATR to points, and the strategy built from them is positive
on research and negative on locked on both timeframes.**

36 declared causal features (truncation audit clean), NQ 5m and 15m, 07:00–11:00 New York, long
only, entries and exits walked on the **true 1-minute path**. `research/v44/`.

---

## 1. The two criteria, as asked — and why they fight each other

Excursions over a fixed horizon, no barriers, research block. Both units reported because they
disagree.

**NQ 5m, 07:00–11:00, 30-minute horizon.** Baseline over all 23,835 eligible bars: MFE 1.954,
MAE 2.032 ATR.

| TOP 4 BY MEAN MFE | dir | n | MFE (ATR) | MAE (ATR) | **MFE (pts)** | **MAE (pts)** | ATR (pts) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| vlm.rel20 | high | 4,767 | 2.22 | 2.45 | 35.70 | 39.39 | 15.39 |
| vol.rstd20_atr | low | 4,767 | 2.17 | 2.01 | 28.69 | 27.20 | 12.04 |
| loc.d_ema200 | high | 4,767 | 2.13 | 2.08 | 26.76 | 27.01 | 11.17 |
| vol.range_atr | high | 4,767 | 2.12 | 2.28 | 35.54 | 38.52 | 16.20 |

| TOP 4 BY LOWEST MEAN MAE | dir | n | MFE (ATR) | MAE (ATR) | **MFE (pts)** | **MAE (pts)** | ATR (pts) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| vol.atr_pct250 | high | 4,819 | 1.47 | **1.63** | 38.17 | **41.77** | 24.53 |
| vlm.rel20 | low | 4,767 | 1.64 | 1.66 | 26.45 | 26.67 | 14.26 |
| vol.atr_ratio | high | 4,767 | 1.54 | 1.68 | 38.25 | **42.03** | 24.32 |
| vlm.trend | low | 4,767 | 1.69 | 1.71 | 17.18 | **17.67** | 9.39 |

**THE MAE RANKING INVERTS ON THE UNIT.** `vol.atr_pct250 high` has the *lowest* MAE of all 78 cells
in ATR (1.63) and, at 41.77 points, one of the *highest* in points. Its ATR is 24.53 points against
a baseline near 12–15. "Low MAE in ATR" is not a calm entry — **it is a high-ATR bar, and the ATR is
the denominator.** In points the lowest-MAE feature is `vlm.trend low` at 17.67, which does not
appear in the ATR-ranked top spot at all.

**And the two criteria are one axis.** Across the 78 cells, correlation between a cell's mean MFE
and its mean MAE:

| | 5m 30min | 5m 90min | 15m 30min | 15m 90min |
| --- | --- | --- | --- | --- |
| Pearson | +0.617 | **+0.844** | +0.678 | +0.765 |
| Spearman | +0.288 | +0.634 | +0.407 | +0.477 |

At the 90-minute horizon **three of the four features appear in both top-4 lists in OPPOSITE
directions** — `vol.atr_pct250`, `vol.atr_ratio` and `vol.range_exp` are wanted LOW for high MFE and
HIGH for low MAE. Maximising MFE is a bet on volatility; minimising MAE is a bet against it. Asking
for both selects nothing.

**The only criterion where the ATR denominator cancels is the ratio MFE/MAE**, so the strategy is
built on that instead. Baseline ratio is 0.962 (5m) and 0.962 (15m) — below 1, meaning over a fixed
horizon the adverse side of a long slightly exceeds the favourable before any rule is applied.

---

## 2. The strategy

Four features picked on research by MFE/MAE ratio, one per concept family (family before rho — five
of six "independent" picks were all volatility level once on this branch), combined as a count.

| 5m | dir | research ratio | | 15m | dir | research ratio |
| --- | --- | --- | --- | --- | --- | --- |
| vol.rstd20_atr | low | 1.076 | | vol.range_exp | low | 1.090 |
| chp.chop14 | high | 1.042 | | vlm.rel100 | low | 1.071 |
| loc.d_ema200 | high | 1.023 | | chp.chop14 | high | 1.056 |
| vlm.rel100 | low | 1.003 | | loc.d_ema200 | high | 1.034 |

max \|rho\| between picks: **0.414** (5m), **0.701** (15m — high, and a caveat on that row).

**The ablation decides it before the holdout does.** With no feature filter at all, the window and
barriers average **PF 0.865 (5m) and 0.903 (15m)** across the nine barrier cells — 07:00–11:00
loses money before any feature is applied, which is the branch's standing finding about the
pre-open block reproducing again. The stack lifts it to 1.181 at 4-of-4 (5m) and 1.151 at 3-of-4
(15m), but **the 15m ladder is not monotone** (0.903 → 0.868 → 0.881 → **1.151** → 0.955): a spike,
not a plateau.

Barrier axes, read as marginal averages rather than top cells, are **monotone toward wider on both
timeframes and both axes**, with the best setting at the **edge of the declared grid** — stop
0.910/0.973/**1.057**, target 0.916/0.989/**1.035** on 5m. The optimum was not inside the grid.

---

## 3. The frozen read

Chosen on research, locked read once. Control = random entry in the same window, identical
barriers, 1-minute walk, costs, matched on count, 120 draws.

| | n | PF | pts/trade | win | control PF | control pts | p |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **5m research** | 65 | 1.503 | **+3.78** | 44.6% | 0.945 | −1.11 | 0.092 |
| **5m locked** | 38 | **0.555** | **−6.25** | 23.7% | 0.870 | −4.03 | 0.550 |
| **15m research** | 216 | 1.369 | **+4.95** | 41.7% | 0.919 | −1.67 | **0.033** |
| **15m locked** | 124 | **0.798** | **−4.51** | 32.3% | 0.868 | −4.10 | 0.550 |

**Both timeframes invert.** And on locked both lose *more than their own random control*
(−6.25 against −4.03; −4.51 against −4.10), so out of sample the features are worse than not having
them. The 15m research cell clears its control at p 0.033 and that is one cell of a grid in which
only 31% of configurations were profitable, before any multiplicity correction.

**Ships nothing.**

---

## 4. Time to target and time to stop — the part that replicates

Median minutes from fill to barrier, on the 1-minute path.

| | target | stop | ratio | target IQR | stop IQR |
| --- | --- | --- | --- | --- | --- |
| 5m research | 38 min | **19 min** | 2.0× | 18–60 | 8–43 |
| 5m locked | 46 min | **25 min** | 1.8× | 26–68 | 14–42 |
| 15m research | 76 min | 63 min | 1.2× | 59–109 | 37–85 |
| 15m locked | 110 min | 53 min | **2.1×** | 76–123 | 31–85 |

**A stop arrives roughly twice as fast as a target, in all four cells and on both blocks.** This is
the one result here that survives the split, and it is a capital-efficiency fact rather than an
edge: a losing trade ties up the account for half as long as a winning one, so a 2R target with a
1.5 ATR stop spends most of its clock on the trades that work. It is consistent with
`STUDY_INTRADAY_HEAT`'s finding that the few trades ever reaching target drew down just 0.09 R — a
winner here declares itself, but slowly.

In points (MNQ at $2.00), 5m research: median ATR at signal 7.74 pts, stop distance **11.62 pts
($23)**, target 23.23 pts. Winners' median MFE 27.75 pts against MAE 5.00; losers' median MFE 4.88
against MAE 14.12. On 15m research: stop 20.33 pts ($41), target 40.66; winners MFE 47.25 / MAE 6.50,
losers MFE 10.25 / MAE 22.50.

---

## 5. A 09:30–11:00 window cannot carry a 2R target flattened at 11:00

| | target hit | stop hit | 11:00 flatten |
| --- | --- | --- | --- |
| 15m 09:30–11:00 research | **0.0%** | 7.5% | **92.5%** |
| 15m 09:30–11:00 locked | **0.0%** | 9.7% | **90.3%** |

**Not one trade in 169 reached the target.** A 90-minute entry window with a hard flatten at its end
leaves the median trade no room — median time to flatten is **0 minutes**, because entries near
11:00 are closed on the next bar. Setting a 2R target and setting "no target" are the same strategy
here, which is `STUDY_INTRADAY_HEAT`'s finding arriving through a different door. If the 09:30 start
is wanted, the flatten has to move.

---

## Caveats

One market (NQ), long only, one split. The frozen cells are 38 and 124 locked trades. 78 feature
cells were scanned and the top 4 of each list taken, with no multiplicity correction — the p-values
are draw-shares, not corrected tests. The 15m pick set has max \|rho\| 0.701, which is not
independent. The 09:30–11:00 comparison re-picks features inside that window, so it is not the same
rule moved to a different clock. **NQ's stored price levels are synthetic and inflated early in the
sample**, so a points figure from research is not directly comparable to one from locked; the ATR
columns are the ones to use for that comparison.

## Files

`research/v44/v44feat.py` (36 features, truncation audit) · `v44run.py` (excursion scoring, both
units) · `v44build.py` (1-minute walker, barrier grid, ablation) · `v44final.py` (frozen read,
control, timing) · `v44points.py` (points and dollars) · `results/v44/`.
