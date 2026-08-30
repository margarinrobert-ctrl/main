# V45 — Engineering the take profit from MFE and MAE: the theory, its bounds, and the practice

**The theory is exact and says less than it looks like it says; the practice is unambiguous.
Across 196 declared (stop, target) cells the target-hit rate is below the break-even win rate in
196 of them, and the best entry filter available closes 29% of a gap that needs 36%.**

NQ 5m and 15m, 07:00–11:00 New York, long, hard flatten at 11:00, every trade walked on the true
1-minute path, real MNQ costs (1.22 points round turn). `research/v45/v45tp.py`.

---

## 1. Theory

For a long with stop **S** and target **T** in points and a round turn of **C**, expectancy is zero
at

```
p*  =  (S + C) / (T + S)                 break-even win rate
PF  =  p(T − C) / [(1 − p)(S + C)]       profit factor at win rate p
```

The tempting step is to read *p* off the MFE distribution. **P(MFE ≥ T) is not a win rate — it is
an upper bound.** MFE and MAE record whether each barrier was reached, never which came first, so
the distributions alone deliver a bracket:

```
p_lower   = P(MFE ≥ T  AND  MAE < S)     the target was reached and the stop never was
p_upper   = P(MFE ≥ T)                   every trade that ever touched the target
ambiguous = p_upper − p_lower            both reached; only the path decides
```

The bracket is verified: **the realised target-hit rate falls inside [p_lower, p_upper] in 49 of 49
cells.** The theory is correct. It is also nearly useless where a scalp lives:

| mean bracket width | by stop | | by target | |
| --- | --- | --- | --- | --- |
| 0.5 ATR | **0.666** | | 0.5 R | 0.593 |
| 1.0 ATR | 0.488 | | 2.0 R | 0.398 |
| 2.0 ATR | 0.275 | | 4.0 R | 0.257 |
| 3.0 ATR | **0.167** | | 5.0 R | 0.212 |

At a 0.5 ATR stop, MFE/MAE alone say the win rate is somewhere between 11.5% and 92.9%. **The
bracket narrows monotonically as the barriers widen, so MFE/MAE-based TP engineering is least
informative exactly at scalping geometry.** This is the same fact `STUDY_EDGELAB` recorded as a
47.4% intrabar-ambiguous share at a 0.25 ATR stop, stated as a bound rather than a tie-break.

One correction worth carrying: **the bound applies to the TARGET-HIT rate, not to the profitable
rate.** A trade flattened at 11:00 in profit is a win that never touched the target, so the
profitable rate can exceed p_upper legitimately — it did in this grid before the comparison was
fixed. And the two-outcome break-even formula is only valid where the flatten share is small: it
runs 1.4–5.0% at a 0.5 ATR stop and **36.2%** at 3.0 ATR / 5 R, where the formula no longer
describes the trade.

---

## 2. Practice — the 49-cell grid

7 stops (0.5–3.0 ATR) × 7 targets (0.5–5.0 R), one position at a time, first touch on the minute.

| | PF > 1 | pts > 0 | best PF | best pts | median pts |
| --- | --- | --- | --- | --- | --- |
| 5m research | **0/49** | 0/49 | 0.942 | −1.11 | −1.35 |
| 5m locked | **0/49** | 0/49 | 0.960 | −1.47 | −2.05 |
| 15m research | **0/49** | 0/49 | 0.957 | −0.65 | −1.35 |
| 15m locked | 1/49 | 1/49 | 1.013 | +0.51 | −1.35 |

The single profitable cell is on the block that did not select it, one of 49 draws.

**Every marginal average on every axis is negative**, on both timeframes — 5m stop −1.23 to −1.56,
5m target −1.30 to −1.47. There is no setting of either axis that is positive on average, so this
is not a case of the optimum sitting outside the grid.

### The arithmetic that explains it

| | hit_tp > p* | mean shortfall | best shortfall |
| --- | --- | --- | --- |
| 5m research | **0 / 49** | −0.088 | −0.050 |
| 5m locked | **0 / 49** | −0.090 | −0.048 |
| 15m research | **0 / 49** | −0.117 | −0.056 |
| 15m locked | **0 / 49** | −0.118 | −0.052 |

**196 of 196 cells fall short of their own break-even win rate.** No (stop, target) pair closes it,
because the shortfall is not a property of the barriers — it is the cost floor against an entry
population with no edge. **The take profit is downstream of the entry, and this proves it
arithmetically rather than by backtest.**

---

## 3. What would it take?

At the best cell on 5m research (stop 0.75 ATR, target 5 R — shortfall −0.050):

```
required lift in the target-hit rate : +0.0499 absolute on a base of 0.1388  =  +36.0% relative
best lift any of 78 feature cells delivers : +0.0401                          =  +28.9% relative
cells beating break-even                   :  0 of 78
```

The best filter in the pool gets **80% of the way** and stops. That is a quantitative answer to
"is a scalping strategy findable here" — not "it fails" but "it fails by seven points of relative
lift, and the pool's best is short of it."

---

## 4. The one candidate, frozen and read once

`loc.d_ema200` in its top research quintile (distance from the EMA200 in ATR — the same family
`STUDY_V40` found was the only one of 17 to earn a place), stop 0.75 ATR, target 5 R, position lock
on, against a random entry in the same window matched on trade count.

| | n | PF | pts/trade | win | control PF | control pts | p |
| --- | --- | --- | --- | --- | --- | --- | --- |
| research | 1,143 | **1.000** | −0.001 | 22.2% | 0.885 | −1.135 | 0.067 |
| locked | 637 | **0.868** | −1.592 | 20.3% | 0.815 | −2.659 | 0.253 |

**It beats its control on both blocks and is unprofitable on both.** The filter does something real
relative to a random entry in the same session — the control loses more, consistently — and it does
not reach the cost floor. Exactly break-even on research is what a rule selected from 78 cells for
being the only one above 1.0 looks like out of sample.

Note the position lock matters: without it the same cell reads PF 1.073 / +0.60 points, with it
1.000 / −0.001. Overlapping signals are not a strategy.

**Ships nothing.**

---

## 5. Timing

| | time to target | time to stop | ratio |
| --- | --- | --- | --- |
| research | 32 min | **6 min** | 5.3× |
| locked | 29 min | **6 min** | 4.8× |

At a 0.75 ATR stop a loser resolves in six minutes and a winner takes half an hour. This is the
same asymmetry `STUDY_V44` measured at 2× on a 1.5 ATR stop, and it sharpens as the stop tightens —
which is the mechanism, not a coincidence: a tight stop is reached by noise almost immediately,
while a 5 R target needs a real move.

## Caveats

One market, long only, one split. 49 barrier cells × 2 timeframes plus 78 feature cells were
scanned; the p-values are draw-shares with no multiplicity correction. The 1-minute path resolves
barrier ordering but the entry still fills at the next bar's open, so nothing here models a limit
entry. NQ's stored levels are synthetic and inflated early in the sample, so point figures are not
comparable across blocks — the ATR-normalised and rate columns are.

## Files

`research/v45/v45tp.py` · `results/v45/v45_tp_grid.csv`, `v45_filter_test.csv`.
