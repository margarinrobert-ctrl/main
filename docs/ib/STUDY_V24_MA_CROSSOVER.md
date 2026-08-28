# V24 — MA crossovers on the simplest Donchian + CHOP breakout, with drawdowns

**The answer: don't add one.** 45% of MA configurations beat the no-MA baseline out of sample where
chance is 50%, and the mean profit-factor change from adding a crossover is **+0.015**.

The best configuration is the one with no moving average in it: **NQ 30m, Donchian 30/20,
2.0×ATR stop, no target, CHOP ≤ 40** — locked PF **1.318**, +0.1542 R/trade, **11.6 R** drawdown,
return/DD **1.67**.

## The base and the grid

Simplest thing on the branch: Donchian 30 entry, 20-bar channel exit, 2.0×ATR(14) stop, **no take
profit** (it has beaten every target tested here eight times), one unit, long only, market order at
the next open, plus CHOP — the one regime filter that clears a same-selectivity control on both
blocks (V21/V23, locked p 0.048).

Declared before running: **7 MA types × 9 pairs × 2 modes (+ MA off) = 127**, × 4 CHOP settings × 2
timeframes = **1,016 cells**, of which 1,009 clear a 30-trade floor.

**One market.** A container recycle left NQ as the only feed.

## 0. Which of these columns are actually the same column?

Average lag against a unit ramp:

| window | SMA | EMA | WMA | HMA | DEMA | TEMA | KAMA |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 9 | 4.00 | 4.00 | 2.67 | 0.00 | 0.00 | 0.00 | 1.25 |
| 21 | 10.00 | 10.00 | 6.67 | 1.00 | 0.00 | 0.00 | 1.25 |
| 50 | 24.50 | 24.50 | 16.33 | 2.50 | 0.00 | 0.00 | 1.25 |

**SMA and EMA are identical at every window** — `STUDY_MA_LAG` replicating exactly. DEMA, TEMA and
HMA sit at zero: they are extrapolators, a genuinely separate axis. KAMA is flat at 1.25 regardless
of window, so its period is nearly inert.

## 1. The population, before any ranking

```
scorable cells 1,009 of 1,016
share with research PF > 1: 83.2%      share with LOCKED PF > 1: 82.5%
research PF vs locked PF correlation: -0.097
```

**A ranking of this grid does not transfer.** Everything below is a description of the research
block unless the locked column says otherwise.

## 2. The no-MA baseline — what every crossover has to beat

| tf | CHOP | n | RES PF | RES R | RES DD | ret/DD | n | **LOCK PF** | **LOCK R** | **LOCK DD** | ret/DD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 15m | ≤40 | 412 | 1.168 | +0.1048 | 15.9 | 2.72 | 235 | 1.027 | +0.0162 | 38.1 | 0.10 |
| 15m | ≤45 | 552 | 1.017 | +0.0115 | 41.1 | 0.15 | 291 | 1.072 | +0.0426 | 31.2 | 0.40 |
| 15m | ≤50 | 668 | 0.947 | −0.0368 | 47.6 | −0.52 | 345 | 1.114 | +0.0679 | 29.1 | 0.81 |
| 15m | off | 781 | 0.978 | −0.0146 | 60.0 | −0.19 | 385 | 1.158 | +0.0939 | 29.8 | 1.21 |
| **30m** | **≤40** | 238 | 1.184 | +0.1053 | 12.8 | 1.96 | 125 | **1.318** | **+0.1542** | **11.6** | **1.67** |
| 30m | ≤45 | 311 | 1.182 | +0.1104 | 16.1 | 2.13 | 163 | 1.116 | +0.0622 | 15.3 | 0.66 |
| 30m | ≤50 | 377 | 1.112 | +0.0698 | 27.2 | 0.97 | 190 | 1.123 | +0.0676 | 15.0 | 0.86 |
| 30m | off | 435 | 1.155 | +0.0926 | 26.5 | 1.52 | 226 | 1.156 | +0.0873 | 24.6 | 0.80 |

## 3. By MA type — and the gradient is LAG, not type

| type | lag@21 | cells | research PF | LOCKED PF | LOCKED R | LOCK DD (R) | ret/DD | avg n | % PF>1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SMA | 10.00 | 140 | 1.133 | **1.208** | +0.1005 | 18.1 | 1.15 | 157 | 84% |
| EMA | 10.00 | 143 | 1.107 | 1.183 | +0.0851 | 18.4 | 0.98 | 160 | 82% |
| WMA | 6.67 | 143 | 1.094 | 1.161 | +0.0818 | 19.3 | 1.00 | 168 | 83% |
| KAMA | 1.25 | 143 | 1.209 | 1.138 | +0.0697 | 18.6 | 0.75 | 153 | 80% |
| DEMA | 0.00 | 144 | 1.113 | 1.131 | +0.0669 | 21.8 | 0.72 | 170 | 80% |
| HMA | 1.00 | 144 | 1.118 | 1.115 | +0.0621 | 21.2 | 0.76 | 175 | 78% |
| TEMA | 0.00 | 144 | 1.152 | 1.114 | +0.0615 | 21.0 | 0.68 | 175 | 83% |

**Total spread across all seven types: 0.093 PF.** But note the ordering — **locked PF falls
monotonically as lag falls.** The lagging averages beat the extrapolators, and the "responsive" MAs
that a trader would reach for (Hull, TEMA, DEMA) are the worst three. That is the branch's
mean-reversion theme again, and it is the same direction as "chasing a breakout is the single most
reliably destructive choice in the whole search."

SMA and EMA have *identical* lag and differ by 0.025 PF — that is the noise on the 5–10% of triggers
that differ, exactly as `STUDY_MA_LAG` predicted.

## 4. By pair, and by mode

| pair | cells | research PF | LOCKED PF | LOCKED R | LOCK DD (R) | ret/DD | avg n | % PF>1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 50/200 | 105 | 1.209 | **1.242** | +0.1164 | 15.4 | 1.03 | 106 | 71% |
| 13/48 | 112 | 1.107 | 1.166 | +0.0818 | 19.1 | 0.91 | 169 | 86% |
| 9/50 | 112 | 1.117 | 1.162 | +0.0779 | 20.3 | 0.90 | 174 | 82% |
| 12/26 | 112 | 1.101 | 1.149 | +0.0767 | 19.8 | 0.99 | 177 | 86% |
| **9/21** | 112 | 1.110 | 1.146 | +0.0744 | 20.8 | 0.92 | 182 | 84% |
| 21/55 | 112 | 1.165 | 1.138 | +0.0708 | 18.7 | 0.77 | 154 | 83% |
| 10/30 | 112 | 1.101 | 1.134 | +0.0691 | 20.9 | 0.87 | 178 | 84% |
| 5/20 | 112 | 1.116 | 1.119 | +0.0601 | 23.0 | 0.82 | 187 | 76% |
| 20/50 | 112 | 1.171 | 1.107 | +0.0566 | 19.1 | 0.59 | 158 | 79% |

**Total spread across all nine pairs: 0.135 PF.** The 9/21 golden cross from the screenshot sits
fifth of nine, dead mid-table. 50/200 leads — and has the *lowest* share of cells staying positive
(71%) on the *fewest* trades (106), which is the selectivity artifact, not an edge.

| mode | cells | research PF | LOCKED PF | LOCKED R | LOCK DD (R) | avg n | % PF>1 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CROSS (within 5 bars) | 497 | 1.149 | 1.182 | +0.0858 | 16.4 | 108 | 72% |
| STATE (fast > slow) | 504 | 1.115 | 1.118 | +0.0649 | 23.0 | 222 | 91% |

CROSS looks better on PF and drawdown and trades **half as much**. Read those three columns together
and it is the same trade-off as everywhere else in this study.

## 5. The number that decides it

```
MA CELLS THAT BEAT THE SAME-CHOP, SAME-TIMEFRAME NO-MA BASELINE ON LOCKED:
    442 of 988 = 45%.   CHANCE IS 50%.
mean locked PF change from adding an MA: +0.015
mean locked drawdown change:             -4.6 R   on 68% of the trades
```

**The drawdown reduction is not a benefit, it is a description of trading less.** −4.6 R of drawdown
bought with 32% of the trades removed is not risk management, and return-over-drawdown — which
normalises for exactly that — shows no MA type reaching the no-MA 30m/CHOP≤40 baseline's **1.67**.

## 6. The top 40, and what happens to them

Mean research PF **1.623** → mean locked PF **1.167**. That 0.46 gap is the selection premium on a
1,009-cell grid. Of the 40, **22 of 36** readable cells beat their own baseline — 61%, on cells
chosen for having the highest research PF in the grid.

The best research cell in each timeframe, against a same-selectivity control:

| | n | PF | control PF | p | DD (R) |
| --- | --- | --- | --- | --- | --- |
| 15m `WMA 50/200 CROSS` + CHOP≤40, research | 54 | 1.919 | 1.140 | **0.013** | 7.9 |
| 15m same, **locked** | 39 | **0.858** | 1.085 | **0.685** | 8.5 |
| 30m `KAMA 50/200 CROSS`, research | 44 | **3.190** | 1.228 | **0.000** | 6.1 |
| 30m same, **locked** | — | — | — | — | under 30 trades |

A research PF of 3.190 at p 0.000 that cannot muster 30 trades out of sample is the clearest
statement of what this grid is.

## 7. What ships

**Nothing.** The recommended configuration is unchanged and contains no moving average:
**30 minutes, Donchian 30/20, 2.0×ATR stop, no target, CHOP ≤ 40, one unit, long.**

Caveats: one market, two timeframes; the research→locked PF correlation is −0.097, so even the
negative conclusion rests on the marginal averages rather than on any cell; and realised drawdown is
one path — `STUDY_V11_MARKET` saw it triple out of sample on a rule whose PF barely moved.

## Files

| file | what it does |
| --- | --- |
| `research/v24/v24ma.py` | the 1,016-cell grid, the lag table, marginals by type/pair/mode, top 40 with drawdowns, controls |
| `docs/ib/v24_top40_ma.txt` | the raw top-40 table |
