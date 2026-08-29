# V39 — a Monte Carlo mean for every individual indicator rule, on three markets

**40 indicator rules × 3 markets × 2 blocks. 1,000-draw day-block bootstrap for the edge, 1,000
permutations for the path, and a 400-draw same-selectivity control on every cell.**

```
market   block       rules clearing the control at p<=0.05      expected by chance
NQ       research    0 of 40                                    2.0
NQ       LOCKED      0 of 40                                    2.0
US30     research    0 of 39                                    2.0
US30     LOCKED      0 of 39                                    2.0
US100    research    1 of 39                                    2.0
US100    LOCKED      0 of 39                                    2.0
```

**One cell out of 236 clears, where twelve are expected by chance.** Indicators clear their own
control *less often than random filters do*. The best control p anywhere is 0.087.

## Why the bootstrap mean alone would say the opposite

Almost every rule has a positive bootstrap mean. On NQ's locked block the median rule reads
**+$34.81/trade** and 30 of 40 have P(mean ≤ 0) below 0.35. Read that column alone and this looks
like forty edges.

It is one edge — the base geometry — measured forty times. The base with **no filter at all** reads
+$17.31 research and +$37.65 locked on NQ, and the filtered rules are drawing from those same
trades. A same-selectivity control (a random filter keeping the same number of breakout signals)
is what separates the two readings, and it is the column that says no.

## The two Monte Carlos, kept apart

- **Bootstrap** resamples whole *days with their trades attached* — triggers cluster, so 326 trades
  here are ~230 independent days — and answers the **edge** question.
- **Permutation** reorders the realised trades and answers the **path** question only. Its endpoint
  is invariant by construction and is never reported.

Base configuration, both Monte Carlos:

| market | block | MC mean $/trade | P(mean ≤ 0) | realised DD | MC p99 DD |
| --- | --- | ---: | ---: | ---: | ---: |
| NQ | research | +$17.31 | 0.129 | $2,956 | **$6,943** |
| NQ | LOCKED | +$37.65 | 0.110 | $3,338 | **$5,674** |
| US30 | research | +$85.64 | 0.021 | $21,889 | **$34,631** |
| US30 | LOCKED | +$14.38 | **0.395** | $19,325 | **$42,659** |
| US100 | research | −$4.09 | 0.726 | $7,619 | $13,441 |
| US100 | LOCKED | +$16.21 | 0.124 | $3,570 | $9,391 |

**MC p99 drawdown runs 1.7–2.2× the realised drawdown on every cell.** That is the sizing number,
and it is the most directly usable output of this study. US30's research block is the only cell
whose bootstrap excludes zero — and it decays to P(≤0) = 0.395 on the holdout.

## The full table, pooled across the three markets by locked bootstrap mean

| rule | research MC | **locked MC** | mean control p | trades |
| --- | ---: | ---: | ---: | ---: |
| ATR pct rank(500) ≤ 0.2 | +43.54 | **+49.58** | 0.362 | 302 |
| **CHOP14 ≤ 40** | +48.56 | **+44.67** | **0.209** | 698 |
| **CHOP14 ≤ 45** | +47.18 | **+41.56** | **0.178** | 878 |
| volume > 1.5× 20-bar mean | +18.42 | +39.66 | 0.132 | 141 |
| vol percentile > 0.5 (fast) | +19.44 | +37.21 | 0.230 | 937 |
| CHOP14 ≤ 35 | +31.41 | +36.02 | 0.222 | 490 |
| CHOP14 ≤ 50 | +37.22 | +32.06 | 0.308 | 1023 |
| linreg(21) slope > 0 | +35.99 | +31.26 | 0.261 | 1062 |
| close > prior 55-bar high | +33.98 | +30.71 | 0.335 | 769 |
| ATR expanding (≥ 1.10× mean) | +24.57 | +30.38 | 0.312 | 991 |
| linreg(50) slope > 0 | +31.22 | +30.22 | 0.397 | 868 |
| body ≥ 60% of range | +35.59 | +30.13 | 0.337 | 1021 |
| BB width > its 20-bar mean | +36.61 | +29.45 | 0.303 | 1013 |
| linreg 9/21 value state | +34.70 | +28.77 | 0.381 | 1091 |
| efficiency ratio(20) ≥ 0.3 | +40.25 | +28.73 | 0.330 | 862 |
| +DI > −DI | +32.32 | +27.80 | 0.328 | 1125 |
| RSI14 ≥ 60 | +37.01 | +27.54 | 0.352 | 1113 |
| ADX14 ≥ 20 | +26.50 | +27.36 | 0.305 | 886 |
| close > SMA200 | +46.69 | +25.89 | 0.428 | 948 |
| efficiency ratio(20) ≥ 0.2 | +33.08 | +25.66 | 0.322 | 1030 |
| MACD histogram > 0 | +34.62 | +24.68 | 0.382 | 1145 |
| close > linreg(50) | +32.51 | +24.47 | 0.378 | 1149 |
| close > EMA50 | +33.21 | +24.30 | 0.398 | 1148 |
| close > linreg(21) | +32.87 | +24.20 | 0.398 | 1149 |
| close > SMA50 | +33.30 | +23.99 | 0.396 | 1150 |
| RSI14 ≥ 50 | +32.95 | +22.74 | 0.377 | 1159 |
| RSI14 ≥ 55 | +32.62 | +22.71 | 0.369 | 1158 |
| linreg(9) slope > 0 | +34.06 | +22.28 | 0.391 | 1152 |
| close > linreg(9) | +30.94 | +22.01 | 0.415 | 1148 |
| ADX14 ≥ 25 | +30.06 | +20.75 | 0.462 | 659 |
| EMA50 > EMA200 | **+56.46** | +20.28 | 0.488 | 777 |
| close > EMA100 | +42.29 | +19.94 | 0.463 | 1082 |
| body ≤ 30% of range | +25.10 | +19.72 | 0.450 | 338 |
| linreg 9/21 slope state | +34.97 | +19.71 | 0.473 | 1098 |
| close > SMA100 | +37.01 | +19.69 | 0.502 | 1053 |
| close > EMA200 | +44.05 | +15.31 | 0.479 | 989 |
| close > Bollinger upper(20,2) | +30.01 | +13.10 | 0.560 | 1053 |
| ADX14 ≥ 30 | +9.43 | +8.14 | 0.612 | 459 |
| vol percentile ≤ 0.5 (calm) | +46.43 | **−9.11** | 0.638 | 640 |
| ATR contracting (≤ 0.90× mean) | +31.56 | **−20.44** | 0.716 | 422 |

## What the table says

**1. CHOP is the best-behaved family and still does not clear.** CHOP ≤ 40 and ≤ 45 hold the two
lowest mean control p-values in the whole table (0.209, 0.178), are positive on both blocks in all
three markets, and are the only family whose ordering is stable. That corroborates the shipped
choice — it does not prove it. `STUDY_V21_ADX_CHOP` found CHOP ≤ 45 clearing at p 0.005/0.015 when
pooled over five markets on a flat-stop base; here on three markets rule-by-rule it does not reach
0.05, which is consistent with a small real effect that needs pooling to see.

**2. ADX is worse the tighter it gets, and inverts.** ADX ≥ 20 → 25 → 30 runs +27.36, +20.75,
+8.14 on locked with control p rising 0.305 → 0.462 → 0.612. On NQ specifically, ADX ≥ 25 and ≥ 30
are the two rules whose research bootstrap *excludes zero* (P(≤0) = 0.038 and 0.050) and both go
**negative** on the holdout (−$0.90 and −$7.67). That is the cleanest single inversion in the study.

**3. Volatility-state rules invert hardest.** "Calm" (+46.43 → −9.11) and "ATR contracting"
(+31.56 → −20.44) are the two worst locked rules and both look strong on research. Their mirrors
— "fast" and "ATR expanding" — are top-five on locked. Note this **contradicts V22's adaptive-stop
direction**, and does not refute it: V22 measured where the *stop* should go given heat in ATR
units, which is a different question from whether the calm state is a profitable *entry filter*.

**4. Moving averages are all the same rule.** Every `close > MA` variant — SMA/EMA at 50/100/200,
`close > linreg` at 9/21/50 — lands between +$19.69 and +$25.89 locked with control p 0.377–0.502
on 1,050–1,150 trades. They keep 99% of the base's signals and change nothing, which is
`STUDY_MA_LAG` and `STUDY_V24_MA_CROSSOVER` restated per-rule.

**5. Research→locked transfer is negative in all three markets.** Pearson −0.516 (NQ), −0.036
(US30), −0.205 (US100). Sign is kept 92.5% / 92.3% of the time on NQ and US30 — because nearly
everything is positive in both blocks — and only **38.5%** on US100. Ranking rules on research
tells you nothing about their order on the holdout, for the fifth independent time on this branch.

## Files

| file | what it does |
| --- | --- |
| `research/v39/v39mc.py` | the 40-rule library, the day-block bootstrap, the permutation, the same-selectivity control |
| `research/v39/run_v39.py` | three markets, both blocks, the full table and the transfer summary |
| `research/v39/v39_mc.csv` | every cell |
| `docs/ib/v39_montecarlo_output.txt` | raw output |
