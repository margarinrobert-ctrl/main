# V25 — A linear-regression 9/21 cross on the best Donchian breakout

**It does not add PF, Sharpe, or edge. The literal 9/21 value cross is the worst reading in the
study: it takes locked PF from 1.318 to 0.853 and locked Sharpe from +0.98 to −0.43.**

## The base

V24's winner, unchanged: **NQ 30m, Donchian 30 entry / 20-bar channel exit, 2.0×ATR(14) stop, no
take profit, one unit, long, CHOP(14) ≤ 40** — locked PF **1.318**, Sharpe **0.98**, +0.1542 R/trade,
11.6 R drawdown, return/DD 1.67. It contains no moving average because V24 found none earns a place.

## 0. The prior, from the lag axis V24 measured

`ta.linreg(close, n, 0)` is the endpoint of an OLS fit. On a straight line it fits exactly:

| window | **LINREG** | SMA | EMA | HMA | DEMA | TEMA |
| --- | --- | --- | --- | --- | --- | --- |
| 9 | **0.00** | 4.00 | 4.00 | 0.00 | 0.00 | 0.00 |
| 21 | **0.00** | 10.00 | 10.00 | 1.00 | 0.00 | 0.00 |
| 50 | **0.00** | 24.50 | 24.50 | 2.50 | 0.00 | 0.00 |

**Zero ramp lag at every window** — it sits with DEMA and TEMA, which were the worst two MA types on
the locked block in V24. The grid starts from behind, and it does not overturn the prior.

## The grid

Declared before running: 6 pairs — `(9,21)` as asked plus `(5,13) (7,17) (11,26) (13,34) (21,55)` so
9/21 is scored against its own neighbourhood — × 5 readings (VALUE state, VALUE cross, SLOPE state,
SLOPE cross, FORECAST state) × 4 R² floors (off, ≥0.2, ≥0.4, ≥0.6) + off = **121**, × 2 CHOP × 2
timeframes = **484 cells**, all scorable.

## 1. The headline

```
LINREG CELLS THAT BEAT THEIR OWN BASELINE ON LOCKED
    on PROFIT FACTOR: 197 of 478 = 41%   (chance 50%)   mean -0.048
    on SHARPE:        162 of 478 = 34%   (chance 50%)   mean -0.26
research PF vs locked PF correlation across the grid: +0.025
```

Worse than chance on both metrics, and **notably worse on Sharpe than on PF** — the regression is
buying profit factor, where it buys anything, by trading less rather than by trading better.

## 2. Is 9/21 special? Its own neighbourhood says no

| pair | cells | research PF | LOCKED PF | LOCKED Sharpe | LOCKED R | LOCK DD | edge PF | % beat |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 21/55 | 80 | 1.125 | 1.146 | 0.42 | +0.0799 | 18.2 | −0.015 | 54% |
| **9/21** | 80 | 1.156 | **1.139** | **0.51** | +0.0742 | 22.1 | **−0.026** | **55%** |
| 7/17 | 80 | 1.114 | 1.126 | 0.47 | +0.0684 | 23.0 | −0.039 | 51% |
| 11/26 | 80 | 1.125 | 1.112 | 0.38 | +0.0581 | 22.8 | −0.053 | 35% |
| 5/13 | 80 | 1.096 | 1.095 | 0.36 | +0.0527 | 27.1 | −0.069 | 28% |
| 13/34 | 80 | 1.176 | 1.076 | 0.22 | +0.0315 | 23.2 | −0.089 | 24% |

9/21 is the **best pair in the set** — and its mean edge is still **−0.026 PF**. It is the least bad,
not good. Spread across all six pairs is **0.070 PF**, so the pair is not a lever.

## 3. By reading — and the R² gate, which is the one thing an MA cannot do

| reading | cells | research PF | LOCKED PF | LOCKED Sharpe | avg n | edge PF | % beat |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **SLOPE state** | 96 | 1.112 | **1.173** | **0.62** | 210 | **+0.008** | **58%** |
| FORECAST state | 96 | 1.125 | 1.163 | 0.59 | 213 | −0.002 | 57% |
| VALUE state | 96 | 1.126 | 1.162 | 0.58 | 210 | −0.003 | 50% |
| SLOPE cross | 96 | 1.118 | 1.058 | 0.15 | 140 | −0.105 | 18% |
| **VALUE cross** | 96 | **1.181** | **1.021** | **0.02** | 135 | **−0.142** | **22%** |

**The CROSS readings are the disaster.** `VALUE cross` — the literal "9/21 golden cross" applied to
regression lines — has the *highest research PF of any reading* (1.181) and the *lowest locked PF*
(1.021) with Sharpe collapsing to 0.02 and only 22% of cells beating baseline. The STATE readings
are neutral.

| R² floor | cells | research PF | LOCKED PF | LOCKED Sharpe | avg n | edge PF | % beat |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ≥0.2 | 120 | 1.131 | 1.130 | 0.45 | 190 | −0.035 | 42% |
| off | 120 | 1.124 | 1.123 | 0.46 | 199 | −0.042 | 42% |
| ≥0.4 | 120 | 1.133 | 1.122 | 0.40 | 179 | −0.043 | 41% |
| ≥0.6 | 120 | 1.141 | 1.088 | 0.27 | 160 | −0.075 | 38% |

**Requiring a better fit makes it monotonically worse.** Research PF *rises* with the R² floor
(1.124 → 1.141) while locked PF and Sharpe *fall* (1.123 → 1.088, 0.46 → 0.27). That is a
selection gradient pointing the wrong way, and it kills the one condition a moving average cannot
express.

## 4. The exact thing asked for, against a same-selectivity control

**NQ 30m, CHOP ≤ 40:**

| cell | block | n | PF | ctrl PF | p | Sharpe | ctrl Shp | p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **`LR 9/21 VALUE cross`** | research | 128 | 1.309 | 1.204 | 0.270 | 0.67 | 0.44 | 0.275 |
| | **locked** | 66 | **0.853** | 1.142 | **0.880** | **−0.43** | 0.27 | **0.882** |
| `LR 9/21 SLOPE state` | research | 218 | 1.189 | 1.198 | 0.583 | 0.55 | 0.57 | 0.605 |
| | locked | 116 | 1.370 | 1.307 | 0.295 | 1.08 | 0.90 | 0.270 |
| best research cell `LR 13/34 VALUE cross r2≥0.2` | research | 104 | 1.571 | 1.185 | **0.030** | 0.93 | 0.37 | 0.055 |
| | locked | 60 | 1.411 | 1.139 | 0.152 | 0.80 | 0.26 | 0.207 |

**NQ 15m, CHOP ≤ 40:** `LR 9/21 VALUE cross` goes research PF 1.293 → **locked 0.858**, Sharpe
**−0.52**, control p **0.917**. The best research cell (`LR 11/26 SLOPE cross`, p 0.022/0.035) lands
at locked PF 0.980 and p 0.632.

`9/21 SLOPE state` is the only reading that looks better than baseline on locked (PF 1.370 vs 1.318,
Sharpe 1.08 vs 0.98) — but it **fails research** (p 0.583) and passes locked, which this branch
treats as a defect rather than a result, and it clears no control on either block.

## 5. The top 100

Mean research PF **1.299 → locked 1.129**; mean research Sharpe **0.70 → locked 0.33**. Of the top
100 chosen on research, **35 of 99 beat the baseline's PF and 28 beat its Sharpe** — both below
chance, on cells selected for being the best in a 484-cell grid.

## 6. Verdict

**Nothing ships.** The strategy stays as it is: 30m, Donchian 30/20, 2.0×ATR stop, no target,
CHOP ≤ 40, one unit, long.

The single most useful line in the study is that a zero-lag estimator was predicted to fail from
V24's lag table before this grid was run, and it failed. Caveats: one market, two timeframes;
grid-wide research→locked correlation +0.025, so even the negative conclusion rests on marginal
averages rather than any cell.

## Files

| file | what it does |
| --- | --- |
| `research/v25/v25lr.py` | the 484-cell linreg grid, lag diagnostic, marginals, top 100, controls |
| `docs/ib/v25_top100_linreg.txt` | the raw top-100 table with PF, Sharpe, drawdown and edge |
