# Volume alpha on NQ — does the volume column predict anything?

Data `data/NQ_5m.csv`, 58,609 RTH bars at 5m, 2022-12-26 to 2025-12-12.
Split chronologically 70/30: research = bars 0..41026, holdout = 41026..58609.
Round-turn cost **3.80 ticks**. Horizons 5/15/30/60/120 minutes = 1/3/6/12/24 bars.

## 1. Why intraday volume has to be normalised by time of day

| hour (ET) | bars | mean volume | share flagged by trailing-mean rvol >= 2 |
| --- | --- | --- | --- |
| 09:00 | 4585 | 11,663 | 45.0% |
| 10:00 | 9167 | 7,924 | 2.8% |
| 11:00 | 9167 | 5,496 | 0.3% |
| 12:00 | 9168 | 4,242 | 0.8% |
| 13:00 | 8881 | 4,114 | 2.4% |
| 14:00 | 8821 | 4,302 | 4.1% |
| 15:00 | 8820 | 5,309 | 10.6% |

Overall share of bars flagged "high volume": trailing-20-mean 6.7%, time-of-day-median 5.6%.

## 2. Does volume predict RANGE? (non-directional family, BH-controlled)

Forward 30-minute high-low range in ticks, by time-of-day relative volume of the current bar.
Unconditional mean 226.1 ticks in research, 326.3 in holdout.
This family is NOT directional and cannot be traded on its own — it is reported because it is the one place volume carries information, and because it is the control that proves the volume column is not noise.

| rvol bucket | research n | fwd range | lift vs rest | t | q (BH) | holdout n | holdout fwd range | holdout lift | holdout t |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rvol < 0.7 (dry) | 6206 | 174.0 | -62.6 | -39.57 | 0.0000 | 2990 | 223.9 | -125.5 | -33.58 |
| 0.7 - 1.0 | 12341 | 215.7 | -15.6 | -11.19 | 0.0000 | 5185 | 286.2 | -59.0 | -14.33 |
| 1.0 - 1.5 | 12868 | 240.3 | 21.7 | 14.91 | 0.0000 | 5207 | 349.4 | 34.1 | 7.56 |
| 1.5 - 2.5 | 4847 | 260.3 | 39.4 | 18.41 | 0.0000 | 2381 | 449.5 | 144.4 | 16.54 |
| rvol >= 2.5 (heavy) | 815 | 353.1 | 129.8 | 16.70 | 0.0000 | 446 | 551.2 | 231.3 | 10.93 |

## 3. Does volume predict DIRECTION? Twelve conditions x five horizons, research half

60 cells, Benjamini-Hochberg applied across all of them at q <= 0.1.

| cell | n | long% | raw ticks | drift-adj ticks | HAC t | p | q (BH) | net of cost |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| heavy-continuation @ 1 | 1377 | 38% | 5.20 | 5.28 | 2.08 | 0.0380 | 0.190 | 1.48 |
| heavy-continuation @ 3 | 1347 | 38% | 6.28 | 6.51 | 1.32 | 0.1852 | 0.341 | 2.71 |
| heavy-continuation @ 6 | 1274 | 37% | 10.75 | 11.21 | 1.49 | 0.1354 | 0.299 | 7.41 |
| heavy-continuation @ 12 | 1148 | 38% | 25.28 | 26.22 | 2.16 | 0.0305 | 0.189 | 22.42 |
| heavy-continuation @ 24 | 789 | 36% | 29.79 | 32.74 | 2.30 | 0.0216 | 0.162 | 28.94 |
| light-continuation @ 1 | 1186 | 56% | 2.28 | 2.25 | 1.64 | 0.1020 | 0.269 | -1.55 |
| light-continuation @ 3 | 1142 | 56% | 6.12 | 5.99 | 2.59 | 0.0096 | 0.162 | 2.19 |
| light-continuation @ 6 | 1066 | 57% | 6.71 | 6.46 | 1.73 | 0.0834 | 0.263 | 2.66 |
| light-continuation @ 12 | 931 | 57% | 10.17 | 9.63 | 1.56 | 0.1197 | 0.287 | 5.83 |
| light-continuation @ 24 | 699 | 58% | 14.87 | 13.18 | 0.94 | 0.3479 | 0.530 | 9.38 |
| trailing-surge-continuation @ 1 | 1708 | 45% | 2.06 | 2.09 | 0.91 | 0.3620 | 0.530 | -1.71 |
| trailing-surge-continuation @ 3 | 1598 | 44% | 3.14 | 3.25 | 0.77 | 0.4423 | 0.603 | -0.55 |
| trailing-surge-continuation @ 6 | 1551 | 44% | 8.25 | 8.44 | 1.32 | 0.1873 | 0.341 | 4.64 |
| trailing-surge-continuation @ 12 | 1484 | 45% | 23.97 | 24.33 | 2.44 | 0.0146 | 0.162 | 20.53 |
| trailing-surge-continuation @ 24 | 1283 | 46% | 32.86 | 33.75 | 2.59 | 0.0095 | 0.162 | 29.95 |
| heavy-exhaustion-fade @ 1 | 201 | 67% | -13.16 | -13.27 | -1.49 | 0.1372 | 0.299 | -17.07 |
| heavy-exhaustion-fade @ 3 | 198 | 68% | -12.32 | -12.66 | -0.75 | 0.4537 | 0.605 | -16.46 |
| heavy-exhaustion-fade @ 6 | 189 | 67% | -14.97 | -15.59 | -0.54 | 0.5872 | 0.691 | -19.39 |
| heavy-exhaustion-fade @ 12 | 169 | 67% | -63.04 | -64.35 | -1.17 | 0.2417 | 0.414 | -68.15 |
| heavy-exhaustion-fade @ 24 | 82 | 73% | -3.72 | -8.74 | -0.37 | 0.7150 | 0.784 | -12.54 |
| climax-small-body @ 1 | 71 | 70% | -18.79 | -18.92 | -1.46 | 0.1455 | 0.299 | -22.72 |
| climax-small-body @ 3 | 70 | 70% | -39.49 | -39.86 | -1.42 | 0.1546 | 0.299 | -43.66 |
| climax-small-body @ 6 | 69 | 70% | -38.12 | -38.82 | -0.84 | 0.4008 | 0.573 | -42.62 |
| climax-small-body @ 12 | 58 | 67% | -65.19 | -66.48 | -1.27 | 0.2030 | 0.358 | -70.28 |
| climax-small-body @ 24 | 25 | 76% | 65.44 | 59.80 | 1.63 | 0.1030 | 0.269 | 56.00 |
| heavy-close-location @ 1 | 1065 | 44% | 6.87 | 6.91 | 2.31 | 0.0208 | 0.162 | 3.11 |
| heavy-close-location @ 3 | 1043 | 44% | 7.34 | 7.45 | 1.42 | 0.1544 | 0.299 | 3.65 |
| heavy-close-location @ 6 | 992 | 44% | 6.52 | 6.74 | 0.79 | 0.4285 | 0.598 | 2.94 |
| heavy-close-location @ 12 | 889 | 45% | 21.25 | 21.66 | 1.60 | 0.1097 | 0.274 | 17.86 |
| heavy-close-location @ 24 | 608 | 44% | 29.25 | 30.54 | 2.38 | 0.0172 | 0.162 | 26.74 |
| dryup-break @ 1 | 778 | 62% | 1.90 | 1.82 | 1.02 | 0.3100 | 0.503 | -1.98 |
| dryup-break @ 3 | 744 | 63% | -1.94 | -2.18 | -0.64 | 0.5190 | 0.663 | -5.98 |
| dryup-break @ 6 | 706 | 62% | 5.40 | 4.96 | 0.92 | 0.3564 | 0.530 | 1.16 |
| dryup-break @ 12 | 636 | 63% | 18.58 | 17.64 | 1.82 | 0.0685 | 0.242 | 13.84 |
| dryup-break @ 24 | 436 | 62% | 31.97 | 29.43 | 1.64 | 0.1006 | 0.269 | 25.63 |
| pressure-momentum @ 1 | 8984 | 64% | 0.47 | 0.38 | 0.58 | 0.5647 | 0.678 | -3.42 |
| pressure-momentum @ 3 | 8747 | 64% | -0.08 | -0.34 | -0.21 | 0.8374 | 0.852 | -4.14 |
| pressure-momentum @ 6 | 8427 | 64% | 2.57 | 2.07 | 0.71 | 0.4797 | 0.626 | -1.73 |
| pressure-momentum @ 12 | 7699 | 64% | 10.60 | 9.58 | 2.01 | 0.0444 | 0.190 | 5.78 |
| pressure-momentum @ 24 | 6209 | 64% | 10.78 | 7.84 | 1.04 | 0.2988 | 0.498 | 4.04 |
| pressure-divergence @ 1 | 1051 | 56% | -2.60 | -2.64 | -1.43 | 0.1537 | 0.299 | -6.44 |
| pressure-divergence @ 3 | 1015 | 57% | -2.89 | -3.01 | -1.00 | 0.3194 | 0.504 | -6.81 |
| pressure-divergence @ 6 | 965 | 56% | -2.63 | -2.86 | -0.59 | 0.5544 | 0.678 | -6.66 |
| pressure-divergence @ 12 | 866 | 55% | -3.00 | -3.41 | -0.45 | 0.6561 | 0.743 | -7.21 |
| pressure-divergence @ 24 | 638 | 55% | -28.55 | -29.74 | -2.04 | 0.0411 | 0.190 | -33.54 |
| session-delta-divergence @ 1 | 1553 | 73% | -0.31 | -0.46 | -0.25 | 0.8059 | 0.852 | -4.26 |
| session-delta-divergence @ 3 | 1532 | 73% | -0.44 | -0.87 | -0.22 | 0.8275 | 0.852 | -4.67 |
| session-delta-divergence @ 6 | 1506 | 72% | 2.31 | 1.50 | 0.22 | 0.8275 | 0.852 | -2.30 |
| session-delta-divergence @ 12 | 1437 | 71% | 5.96 | 4.37 | 0.36 | 0.7188 | 0.784 | 0.57 |
| session-delta-divergence @ 24 | 1267 | 69% | 13.79 | 9.68 | 0.47 | 0.6357 | 0.734 | 5.88 |
| busy-session-trend @ 1 | 2933 | 24% | 2.81 | 2.99 | 1.95 | 0.0508 | 0.203 | -0.81 |
| busy-session-trend @ 3 | 2865 | 24% | 8.37 | 8.87 | 2.15 | 0.0315 | 0.189 | 5.07 |
| busy-session-trend @ 6 | 2760 | 24% | 14.98 | 15.92 | 2.11 | 0.0350 | 0.190 | 12.12 |
| busy-session-trend @ 12 | 2538 | 23% | 32.17 | 34.17 | 2.42 | 0.0154 | 0.162 | 30.37 |
| busy-session-trend @ 24 | 2051 | 23% | 38.62 | 44.40 | 1.67 | 0.0941 | 0.269 | 40.60 |
| quiet-session-fade @ 1 | 3165 | 41% | 0.06 | 0.11 | 0.12 | 0.9079 | 0.908 | -3.69 |
| quiet-session-fade @ 3 | 3064 | 41% | -1.62 | -1.46 | -0.62 | 0.5336 | 0.667 | -5.26 |
| quiet-session-fade @ 6 | 2932 | 41% | -8.44 | -8.13 | -1.83 | 0.0666 | 0.242 | -11.93 |
| quiet-session-fade @ 12 | 2621 | 41% | -21.87 | -21.20 | -2.57 | 0.0101 | 0.162 | -25.00 |
| quiet-session-fade @ 24 | 2019 | 41% | -26.42 | -24.44 | -1.74 | 0.0816 | 0.263 | -28.24 |

**No cell survives FDR control in the research half.**

**Predictability budget (volume family, research half):** best surviving drift-adjusted edge 0.00 ticks (`none`) against 3.80 ticks of cost — ratio 0.00.

> no tested condition shows a drift-adjusted edge that survives false-discovery control (q <= 0.1) — on this sample and session none of these hypotheses is distinguishable from noise, which does not prove the market is unpredictable, only that these signals do not predict it

## 4. Heavy versus light: the interaction test, stated in advance

The hypothesis this study was built to test: *the same-sized move continues differently on heavy volume than on light volume.*
Both conditions require an identical body (>= 0.5 ATR); the only difference is the volume filter.

| horizon (bars) | heavy n | heavy drift-adj | light n | light drift-adj | difference | t | p |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1377 | 5.28 | 1186 | 2.25 | 3.03 | 1.05 | 0.292 |
| 3 | 1347 | 6.51 | 1142 | 5.99 | 0.52 | 0.10 | 0.919 |
| 6 | 1274 | 11.21 | 1066 | 6.46 | 4.76 | 0.65 | 0.513 |
| 12 | 1148 | 26.22 | 931 | 9.63 | 16.59 | 1.51 | 0.132 |
| 24 | 789 | 32.74 | 699 | 13.18 | 19.56 | 1.12 | 0.263 |

## 4b. Is a "volume surge" a volume filter, or a clock?

A volume filter whose flagged bars cluster at particular hours is partly a clock, and the clock is the first thing to rule out. The controls below use the IDENTICAL body filter with NO volume condition whatsoever; they are not candidates and are not in the FDR family — they can only take a result away, never create one.

| condition | 09:00 | 10:00 | 11:00 | 12:00 | 13:00 | 14:00 | 15:00 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| trailing-surge-continuation | 51% | 8% | 0% | 2% | 7% | 11% | 22% |
| heavy-continuation (time-of-day rvol) | 1% | 9% | 11% | 16% | 20% | 26% | 17% |

| condition | horizon | research n | research drift-adj | research t | holdout n | holdout drift-adj | holdout t |
| --- | --- | --- | --- | --- | --- | --- | --- |
| body-only (any time) | 12 | 12373 | 6.58 | 2.82 | 5304 | 3.96 | 0.84 |
| body-only (any time) | 24 | 10118 | 8.44 | 2.38 | 4376 | 3.43 | 0.45 |
| body-only (first 60 min) | 12 | 3052 | 9.92 | 1.74 | 1293 | 19.55 | 1.83 |
| body-only (first 60 min) | 24 | 3052 | 13.88 | 1.96 | 1293 | 10.42 | 0.87 |
| trailing-surge-continuation | 12 | 1484 | 24.33 | 2.44 | 622 | 40.42 | 2.25 |
| trailing-surge-continuation | 24 | 1283 | 33.75 | 2.59 | 546 | 64.43 | 2.57 |
| heavy-continuation | 12 | 1148 | 26.22 | 2.16 | 583 | 19.05 | 0.93 |
| heavy-continuation | 24 | 789 | 32.74 | 2.30 | 427 | 56.57 | 1.68 |

## 5. Long/short decomposition

Prior studies in this repo found "edges" that were entirely one-sided, i.e. the NQ uptrend. Any condition whose drift-adjusted edge lives on one side only is suspect by default.

| cell / side | n | raw ticks | drift-adj ticks | HAC t |
| --- | --- | --- | --- | --- |
| trailing-surge-continuation @ 24 long | 589 | 43.68 | 32.84 | 2.28 |
| trailing-surge-continuation @ 24 short | 694 | 23.69 | 34.53 | 1.56 |
| light-continuation @ 3 long | 645 | 7.51 | 6.57 | 1.99 |
| light-continuation @ 3 short | 497 | 4.31 | 5.25 | 1.24 |
| quiet-session-fade @ 12 long | 1076 | -9.33 | -13.08 | -0.77 |
| quiet-session-fade @ 12 short | 1545 | -30.60 | -26.85 | -2.41 |
| trailing-surge-continuation @ 12 long | 671 | 18.85 | 15.10 | 1.11 |
| trailing-surge-continuation @ 12 short | 813 | 28.19 | 31.94 | 1.71 |
| busy-session-trend @ 12 long | 591 | 46.19 | 42.44 | 1.36 |
| busy-session-trend @ 12 short | 1947 | 27.91 | 31.66 | 2.00 |

### The same edges with SESSION-clustered standard errors

Several of these conditions are day-level states, not bar-level events: once a session is "busy" or "quiet" the condition fires on most of its bars. The HAC lag inside the event study prices the overlap of the forward windows, not the fact that thousands of events come from a few hundred days. Collapsing each session to one observation prices that too.

| cell | events | sessions | drift-adj ticks (event mean) | HAC t | per-session mean | clustered t |
| --- | --- | --- | --- | --- | --- | --- |
| trailing-surge-continuation @ 24 | 1283 | 474 | 33.75 | 2.59 | 47.98 | 3.32 |
| light-continuation @ 3 | 1142 | 320 | 5.99 | 2.59 | 11.61 | 2.54 |
| quiet-session-fade @ 12 | 2621 | 128 | -21.20 | -2.57 | -28.70 | -2.50 |
| trailing-surge-continuation @ 12 | 1484 | 485 | 24.33 | 2.44 | 27.60 | 2.71 |
| busy-session-trend @ 12 | 2538 | 128 | 34.17 | 2.42 | 26.10 | 1.57 |

## 6. Holdout

Nothing survived stage 3, so there is nothing the holdout is being asked to confirm.

For completeness — the whole grid on the holdout. **This table decided nothing**; it is printed so a reader can see whether the research half was unlucky rather than uninformative.

| cell | n | long% | raw ticks | drift-adj ticks | HAC t | p | q (BH) | net of cost |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| heavy-continuation @ 1 | 691 | 40% | -1.94 | -1.87 | -0.34 | 0.7358 | 0.979 | -5.67 |
| heavy-continuation @ 3 | 674 | 41% | -9.24 | -9.07 | -0.89 | 0.3713 | 0.866 | -12.87 |
| heavy-continuation @ 6 | 649 | 41% | -3.90 | -3.58 | -0.23 | 0.8153 | 0.979 | -7.38 |
| heavy-continuation @ 12 | 583 | 41% | 18.36 | 19.05 | 0.93 | 0.3516 | 0.866 | 15.25 |
| heavy-continuation @ 24 | 427 | 40% | 54.47 | 56.57 | 1.68 | 0.0931 | 0.623 | 52.77 |
| light-continuation @ 1 | 556 | 53% | 0.54 | 0.51 | 0.19 | 0.8481 | 0.979 | -3.29 |
| light-continuation @ 3 | 537 | 53% | 1.52 | 1.47 | 0.32 | 0.7453 | 0.979 | -2.33 |
| light-continuation @ 6 | 513 | 54% | -6.55 | -6.70 | -0.94 | 0.3492 | 0.866 | -10.50 |
| light-continuation @ 12 | 471 | 54% | 0.54 | 0.22 | 0.02 | 0.9846 | 0.985 | -3.58 |
| light-continuation @ 24 | 361 | 55% | -12.96 | -14.01 | -0.78 | 0.4326 | 0.950 | -17.81 |
| trailing-surge-continuation @ 1 | 735 | 43% | 9.25 | 9.29 | 1.92 | 0.0551 | 0.623 | 5.49 |
| trailing-surge-continuation @ 3 | 658 | 41% | 16.06 | 16.22 | 1.50 | 0.1343 | 0.623 | 12.42 |
| trailing-surge-continuation @ 6 | 641 | 42% | 17.93 | 18.22 | 1.22 | 0.2225 | 0.773 | 14.42 |
| trailing-surge-continuation @ 12 | 622 | 42% | 39.83 | 40.42 | 2.25 | 0.0247 | 0.493 | 36.62 |
| trailing-surge-continuation @ 24 | 546 | 42% | 62.76 | 64.43 | 2.57 | 0.0103 | 0.493 | 60.63 |
| heavy-exhaustion-fade @ 1 | 115 | 72% | -3.50 | -3.65 | -0.31 | 0.7553 | 0.979 | -7.45 |
| heavy-exhaustion-fade @ 3 | 115 | 72% | 5.98 | 5.56 | 0.18 | 0.8570 | 0.979 | 1.76 |
| heavy-exhaustion-fade @ 6 | 106 | 72% | -29.12 | -29.90 | -0.71 | 0.4781 | 0.950 | -33.70 |
| heavy-exhaustion-fade @ 12 | 95 | 72% | -71.92 | -73.53 | -1.16 | 0.2447 | 0.773 | -77.33 |
| heavy-exhaustion-fade @ 24 | 65 | 72% | -230.34 | -235.18 | -2.36 | 0.0183 | 0.493 | -238.98 |
| climax-small-body @ 1 | 55 | 71% | 52.40 | 52.26 | 1.57 | 0.1165 | 0.623 | 48.46 |
| climax-small-body @ 3 | 55 | 71% | 13.75 | 13.35 | 0.32 | 0.7485 | 0.979 | 9.55 |
| climax-small-body @ 6 | 54 | 70% | 9.30 | 8.57 | 0.16 | 0.8722 | 0.979 | 4.77 |
| climax-small-body @ 12 | 49 | 67% | 5.35 | 4.05 | 0.05 | 0.9611 | 0.985 | 0.25 |
| climax-small-body @ 24 | 34 | 71% | -77.09 | -81.55 | -0.99 | 0.3243 | 0.866 | -85.35 |
| heavy-close-location @ 1 | 515 | 45% | -5.53 | -5.50 | -0.89 | 0.3751 | 0.866 | -9.30 |
| heavy-close-location @ 3 | 506 | 45% | -8.37 | -8.27 | -0.66 | 0.5067 | 0.950 | -12.07 |
| heavy-close-location @ 6 | 485 | 45% | 3.72 | 3.90 | 0.24 | 0.8138 | 0.979 | 0.10 |
| heavy-close-location @ 12 | 427 | 45% | 31.47 | 31.86 | 1.20 | 0.2306 | 0.773 | 28.06 |
| heavy-close-location @ 24 | 320 | 46% | 71.61 | 72.55 | 1.50 | 0.1325 | 0.623 | 68.75 |
| dryup-break @ 1 | 415 | 60% | -0.63 | -0.70 | -0.23 | 0.8160 | 0.979 | -4.50 |
| dryup-break @ 3 | 389 | 61% | -2.45 | -2.66 | -0.41 | 0.6829 | 0.979 | -6.46 |
| dryup-break @ 6 | 376 | 61% | -6.96 | -7.37 | -0.76 | 0.4454 | 0.950 | -11.17 |
| dryup-break @ 12 | 348 | 61% | -5.22 | -6.08 | -0.43 | 0.6658 | 0.979 | -9.88 |
| dryup-break @ 24 | 240 | 63% | -13.55 | -16.44 | -0.58 | 0.5624 | 0.979 | -20.24 |
| pressure-momentum @ 1 | 3877 | 66% | -0.22 | -0.33 | -0.21 | 0.8372 | 0.979 | -4.13 |
| pressure-momentum @ 3 | 3775 | 66% | 1.09 | 0.78 | 0.19 | 0.8488 | 0.979 | -3.02 |
| pressure-momentum @ 6 | 3640 | 67% | 2.07 | 1.47 | 0.23 | 0.8180 | 0.979 | -2.33 |
| pressure-momentum @ 12 | 3366 | 67% | -0.02 | -1.32 | -0.13 | 0.8979 | 0.980 | -5.12 |
| pressure-momentum @ 24 | 2687 | 67% | 2.97 | -0.79 | -0.05 | 0.9621 | 0.985 | -4.59 |
| pressure-divergence @ 1 | 435 | 61% | -1.90 | -1.97 | -0.50 | 0.6185 | 0.979 | -5.77 |
| pressure-divergence @ 3 | 414 | 60% | 9.87 | 9.68 | 1.34 | 0.1812 | 0.773 | 5.88 |
| pressure-divergence @ 6 | 390 | 60% | -6.63 | -6.98 | -0.51 | 0.6127 | 0.979 | -10.78 |
| pressure-divergence @ 12 | 355 | 62% | 2.63 | 1.75 | 0.08 | 0.9370 | 0.985 | -2.05 |
| pressure-divergence @ 24 | 278 | 63% | -35.73 | -38.54 | -0.73 | 0.4680 | 0.950 | -42.34 |
| session-delta-divergence @ 1 | 589 | 90% | -5.26 | -5.53 | -1.19 | 0.2328 | 0.773 | -9.33 |
| session-delta-divergence @ 3 | 578 | 90% | -16.46 | -17.22 | -1.65 | 0.0992 | 0.623 | -21.02 |
| session-delta-divergence @ 6 | 562 | 90% | -29.31 | -30.74 | -1.58 | 0.1133 | 0.623 | -34.54 |
| session-delta-divergence @ 12 | 527 | 89% | -13.76 | -16.72 | -0.69 | 0.4932 | 0.950 | -20.52 |
| session-delta-divergence @ 24 | 467 | 88% | -24.18 | -32.42 | -0.97 | 0.3331 | 0.866 | -36.22 |
| busy-session-trend @ 1 | 2317 | 30% | 4.73 | 4.86 | 1.61 | 0.1068 | 0.623 | 1.06 |
| busy-session-trend @ 3 | 2253 | 30% | 9.99 | 10.37 | 1.29 | 0.1983 | 0.773 | 6.57 |
| busy-session-trend @ 6 | 2161 | 30% | 15.61 | 16.33 | 1.13 | 0.2577 | 0.773 | 12.53 |
| busy-session-trend @ 12 | 1987 | 29% | 38.21 | 39.76 | 1.58 | 0.1134 | 0.623 | 35.96 |
| busy-session-trend @ 24 | 1632 | 29% | 54.19 | 58.68 | 1.49 | 0.1350 | 0.623 | 54.88 |
| quiet-session-fade @ 1 | 1858 | 44% | -0.97 | -0.93 | -0.52 | 0.6023 | 0.979 | -4.73 |
| quiet-session-fade @ 3 | 1796 | 44% | -2.36 | -2.24 | -0.55 | 0.5834 | 0.979 | -6.04 |
| quiet-session-fade @ 6 | 1711 | 43% | 3.10 | 3.35 | 0.50 | 0.6202 | 0.979 | -0.45 |
| quiet-session-fade @ 12 | 1525 | 43% | -2.14 | -1.60 | -0.15 | 0.8814 | 0.979 | -5.40 |
| quiet-session-fade @ 24 | 1153 | 44% | -0.53 | 0.78 | 0.04 | 0.9719 | 0.985 | -3.02 |

The five strongest research cells, re-measured on the holdout with session clustering and a side split. None of them was licensed to be here — nothing survived stage 3 — so this is diagnosis, not validation:

| cell | holdout n | holdout drift-adj | holdout HAC t | sessions | clustered t | long ticks | short ticks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| trailing-surge-continuation @ 24 | 546 | 64.43 | 2.57 | 200 | 1.33 | 32.1 (n=231) | 88.1 (n=315) |
| light-continuation @ 3 | 537 | 1.47 | 0.32 | 127 | 0.24 | -0.3 (n=285) | 3.4 (n=252) |
| quiet-session-fade @ 12 | 1525 | -1.60 | -0.15 | 68 | 0.32 | 5.2 (n=653) | -6.7 (n=872) |
| trailing-surge-continuation @ 12 | 622 | 40.42 | 2.25 | 202 | 1.32 | 60.6 (n=262) | 25.8 (n=360) |
| busy-session-trend @ 12 | 1987 | 39.76 | 1.58 | 75 | 0.66 | 21.3 (n=583) | 47.4 (n=1404) |

### Does the research half carry any information about the holdout half?

Sign agreement across all 60 cells: **31/60 = 52%** (a coin flip is 50%).
Correlation of the drift-adjusted edge between halves: **0.244**.

The six cells that came closest to surviving, and what they did next:

| cell | research drift-adj | research t | research q | holdout drift-adj | holdout t |
| --- | --- | --- | --- | --- | --- |
| heavy-continuation @ 24 | 32.74 | 2.30 | 0.162 | 56.57 | 1.68 |
| light-continuation @ 3 | 5.99 | 2.59 | 0.162 | 1.47 | 0.32 |
| trailing-surge-continuation @ 12 | 24.33 | 2.44 | 0.162 | 40.42 | 2.25 |
| trailing-surge-continuation @ 24 | 33.75 | 2.59 | 0.162 | 64.43 | 2.57 |
| heavy-close-location @ 1 | 6.91 | 2.31 | 0.162 | -5.50 | -0.89 |
| heavy-close-location @ 24 | 30.54 | 2.38 | 0.162 | 72.55 | 1.50 |

### The one candidate that behaved the same way twice

`trailing-surge-continuation` did not survive stage 3 and is therefore NOT a finding. It is singled out because on the 5-minute pass it is the one condition whose drift-adjusted edge kept its sign, roughly its size, and a t above 2 in BOTH halves — so the useful question is what happens when the robustness probes are pointed at it. Every number below is diagnostic; none of it reverses the failed gate.

| horizon | year | events | sessions | drift-adj ticks | per-event std | clustered t |
| --- | --- | --- | --- | --- | --- | --- |
| 12 | 2022 | 7 | 3 | -114.7 | 267 | -0.04 |
| 12 | 2023 | 709 | 232 | 8.3 | 294 | 1.57 |
| 12 | 2024 | 727 | 237 | 41.0 | 353 | 2.46 |
| 12 | 2025 | 665 | 215 | 39.8 | 440 | 1.14 |
| 24 | 2022 | 7 | 3 | -198.2 | 378 | -0.33 |
| 24 | 2023 | 609 | 227 | 12.4 | 357 | 1.66 |
| 24 | 2024 | 627 | 231 | 51.8 | 402 | 2.87 |
| 24 | 2025 | 588 | 213 | 67.8 | 580 | 1.42 |

Across the whole sample the 120-minute cell means 42.9 ticks with a per-event standard deviation of 455 ticks — an information ratio of 0.094 per event. The edge is 11.3x the round turn and 11x smaller than the noise it sits in, which is why 1,831 events still cannot settle the question.

## 7. The arithmetic

| quantity | value |
| --- | --- |
| cells tested (research) | 60 |
| cells surviving BH at q <= 0.1 | 0 |
| largest drift-adjusted edge, research (n >= 100) | 44.40 ticks (busy-session-trend @ 24) |
| round-turn cost | 3.80 ticks |
| largest edge / cost | 11.68 |
| ...its HAC t and BH q | t = 1.67, q = 0.269 |
| ...same cell on the holdout | 58.68 ticks, t = 1.49 |

The "largest edge / cost" ratio above is the trap this protocol exists to catch: 44.40 ticks looks like 11.7x the cost of trading, and it is not distinguishable from noise once the 60 cells that produced it are accounted for. A large edge measured over a 2-hour horizon sits on top of a very large variance; ticks alone never settle anything.

