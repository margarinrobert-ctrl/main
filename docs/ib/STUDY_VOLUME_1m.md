# Volume alpha on NQ — does the volume column predict anything?

Data `data/NQ_1m.csv`, 292,908 RTH bars at 1m, 2022-12-26 to 2025-12-12.
Split chronologically 70/30: research = bars 0..205035, holdout = 205035..292908.
Round-turn cost **3.80 ticks**. Horizons 5/15/30/60/120 minutes = 5/15/30/60/120 bars.

## 1. Why intraday volume has to be normalised by time of day

| hour (ET) | bars | mean volume | share flagged by trailing-mean rvol >= 2 |
| --- | --- | --- | --- |
| 09:00 | 22919 | 2,333 | 9.6% |
| 10:00 | 45825 | 1,585 | 2.6% |
| 11:00 | 45835 | 1,099 | 3.2% |
| 12:00 | 45837 | 849 | 4.0% |
| 13:00 | 44288 | 825 | 4.9% |
| 14:00 | 44104 | 860 | 5.1% |
| 15:00 | 44100 | 1,062 | 7.8% |

Overall share of bars flagged "high volume": trailing-20-mean 5.0%, time-of-day-median 9.2%.

## 2. Does volume predict RANGE? (non-directional family, BH-controlled)

Forward 30-minute high-low range in ticks, by time-of-day relative volume of the current bar.
Unconditional mean 227.1 ticks in research, 327.8 in holdout.
This family is NOT directional and cannot be traded on its own — it is reported because it is the one place volume carries information, and because it is the control that proves the volume column is not noise.

| rvol bucket | research n | fwd range | lift vs rest | t | q (BH) | holdout n | holdout fwd range | holdout lift | holdout t |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rvol < 0.7 (dry) | 41045 | 185.9 | -52.9 | -79.94 | 0.0000 | 18982 | 237.6 | -117.9 | -70.04 |
| 0.7 - 1.0 | 51750 | 222.0 | -7.1 | -10.71 | 0.0000 | 21590 | 300.9 | -36.7 | -18.40 |
| 1.0 - 1.5 | 54367 | 238.8 | 16.5 | 24.07 | 0.0000 | 22824 | 347.3 | 27.2 | 12.87 |
| 1.5 - 2.5 | 29596 | 251.9 | 29.5 | 34.05 | 0.0000 | 13603 | 413.3 | 102.8 | 31.66 |
| rvol >= 2.5 (heavy) | 8536 | 296.3 | 72.5 | 35.41 | 0.0000 | 4004 | 499.0 | 180.1 | 25.17 |

## 3. Does volume predict DIRECTION? Twelve conditions x five horizons, research half

60 cells, Benjamini-Hochberg applied across all of them at q <= 0.1.

| cell | n | long% | raw ticks | drift-adj ticks | HAC t | p | q (BH) | net of cost |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| heavy-continuation @ 5 | 11909 | 46% | 0.42 | 0.45 | 0.54 | 0.5895 | 0.820 | -3.35 |
| heavy-continuation @ 15 | 11702 | 46% | 1.42 | 1.49 | 1.05 | 0.2915 | 0.648 | -2.31 |
| heavy-continuation @ 30 | 11198 | 46% | -0.53 | -0.39 | -0.19 | 0.8509 | 0.928 | -4.19 |
| heavy-continuation @ 60 | 10190 | 46% | 6.61 | 6.91 | 2.18 | 0.0296 | 0.299 | 3.11 |
| heavy-continuation @ 120 | 7771 | 46% | 6.35 | 7.27 | 1.62 | 0.1057 | 0.423 | 3.47 |
| light-continuation @ 5 | 10292 | 53% | 0.04 | 0.02 | 0.05 | 0.9610 | 0.961 | -3.78 |
| light-continuation @ 15 | 9959 | 53% | 1.18 | 1.13 | 1.36 | 0.1749 | 0.527 | -2.67 |
| light-continuation @ 30 | 9481 | 53% | 0.74 | 0.65 | 0.57 | 0.5707 | 0.820 | -3.15 |
| light-continuation @ 60 | 8424 | 52% | 3.31 | 3.12 | 1.77 | 0.0766 | 0.423 | -0.68 |
| light-continuation @ 120 | 6291 | 52% | 4.13 | 3.63 | 1.33 | 0.1846 | 0.527 | -0.17 |
| trailing-surge-continuation @ 5 | 7520 | 45% | 0.68 | 0.71 | 0.71 | 0.4790 | 0.800 | -3.09 |
| trailing-surge-continuation @ 15 | 7047 | 44% | 0.37 | 0.47 | 0.29 | 0.7751 | 0.925 | -3.33 |
| trailing-surge-continuation @ 30 | 6748 | 44% | 0.26 | 0.47 | 0.20 | 0.8417 | 0.928 | -3.33 |
| trailing-surge-continuation @ 60 | 6134 | 44% | 6.71 | 7.16 | 2.00 | 0.0453 | 0.340 | 3.36 |
| trailing-surge-continuation @ 120 | 4783 | 44% | 10.01 | 11.37 | 2.00 | 0.0453 | 0.340 | 7.57 |
| heavy-exhaustion-fade @ 5 | 2099 | 61% | -1.25 | -1.32 | -0.60 | 0.5503 | 0.820 | -5.12 |
| heavy-exhaustion-fade @ 15 | 2083 | 61% | -4.14 | -4.35 | -1.06 | 0.2876 | 0.648 | -8.15 |
| heavy-exhaustion-fade @ 30 | 2002 | 62% | -1.06 | -1.48 | -0.25 | 0.8027 | 0.925 | -5.28 |
| heavy-exhaustion-fade @ 60 | 1825 | 62% | -17.72 | -18.64 | -2.17 | 0.0299 | 0.299 | -22.44 |
| heavy-exhaustion-fade @ 120 | 1302 | 63% | -14.59 | -17.46 | -1.73 | 0.0833 | 0.423 | -21.26 |
| climax-small-body @ 5 | 735 | 64% | -4.87 | -4.97 | -1.23 | 0.2197 | 0.573 | -8.77 |
| climax-small-body @ 15 | 723 | 64% | -0.98 | -1.23 | -0.14 | 0.8911 | 0.939 | -5.03 |
| climax-small-body @ 30 | 695 | 64% | -10.30 | -10.81 | -0.72 | 0.4739 | 0.800 | -14.61 |
| climax-small-body @ 60 | 610 | 64% | -10.52 | -11.60 | -1.09 | 0.2768 | 0.648 | -15.40 |
| climax-small-body @ 120 | 375 | 65% | -13.77 | -17.07 | -0.89 | 0.3726 | 0.745 | -20.87 |
| heavy-close-location @ 5 | 8639 | 49% | -0.24 | -0.23 | -0.23 | 0.8175 | 0.925 | -4.03 |
| heavy-close-location @ 15 | 8497 | 49% | -1.06 | -1.04 | -0.60 | 0.5452 | 0.820 | -4.84 |
| heavy-close-location @ 30 | 8127 | 49% | -0.24 | -0.19 | -0.07 | 0.9403 | 0.956 | -3.99 |
| heavy-close-location @ 60 | 7346 | 49% | 5.12 | 5.22 | 1.45 | 0.1483 | 0.527 | 1.42 |
| heavy-close-location @ 120 | 5649 | 48% | 9.33 | 9.77 | 1.86 | 0.0626 | 0.417 | 5.97 |
| dryup-break @ 5 | 5595 | 56% | -0.33 | -0.36 | -0.45 | 0.6537 | 0.834 | -4.16 |
| dryup-break @ 15 | 5407 | 56% | 0.85 | 0.74 | 0.50 | 0.6153 | 0.820 | -3.06 |
| dryup-break @ 30 | 5150 | 56% | 3.35 | 3.14 | 1.40 | 0.1627 | 0.527 | -0.66 |
| dryup-break @ 60 | 4592 | 56% | 4.76 | 4.32 | 1.26 | 0.2081 | 0.568 | 0.52 |
| dryup-break @ 120 | 3408 | 56% | 6.56 | 5.25 | 0.80 | 0.4221 | 0.800 | 1.45 |
| pressure-momentum @ 5 | 48890 | 59% | 0.38 | 0.32 | 0.61 | 0.5418 | 0.820 | -3.48 |
| pressure-momentum @ 15 | 47533 | 59% | 0.44 | 0.27 | 0.26 | 0.7913 | 0.925 | -3.53 |
| pressure-momentum @ 30 | 45618 | 59% | -0.15 | -0.49 | -0.31 | 0.7539 | 0.925 | -4.29 |
| pressure-momentum @ 60 | 41901 | 59% | 4.77 | 4.05 | 1.67 | 0.0957 | 0.423 | 0.25 |
| pressure-momentum @ 120 | 34567 | 59% | 6.27 | 4.25 | 1.02 | 0.3070 | 0.658 | 0.45 |
| pressure-divergence @ 5 | 6025 | 55% | 0.49 | 0.46 | 0.54 | 0.5907 | 0.820 | -3.34 |
| pressure-divergence @ 15 | 5835 | 54% | -0.93 | -1.01 | -0.58 | 0.5636 | 0.820 | -4.81 |
| pressure-divergence @ 30 | 5588 | 54% | -2.41 | -2.54 | -1.05 | 0.2917 | 0.648 | -6.34 |
| pressure-divergence @ 60 | 5081 | 53% | -2.28 | -2.52 | -0.71 | 0.4800 | 0.800 | -6.32 |
| pressure-divergence @ 120 | 4114 | 53% | 0.11 | -0.57 | -0.12 | 0.9077 | 0.939 | -4.37 |
| session-delta-divergence @ 5 | 1748 | 60% | -3.30 | -3.37 | -0.96 | 0.3360 | 0.695 | -7.17 |
| session-delta-divergence @ 15 | 1748 | 60% | -1.75 | -1.93 | -0.25 | 0.8041 | 0.925 | -5.73 |
| session-delta-divergence @ 30 | 1747 | 60% | 8.15 | 7.79 | 0.52 | 0.6060 | 0.820 | 3.99 |
| session-delta-divergence @ 60 | 1729 | 59% | -9.84 | -10.58 | -0.47 | 0.6391 | 0.834 | -14.38 |
| session-delta-divergence @ 120 | 1658 | 58% | 5.63 | 3.96 | 0.13 | 0.8967 | 0.939 | 0.16 |
| busy-session-trend @ 5 | 15306 | 25% | 3.01 | 3.18 | 2.36 | 0.0183 | 0.299 | -0.62 |
| busy-session-trend @ 15 | 14963 | 25% | 8.60 | 9.06 | 2.62 | 0.0089 | 0.299 | 5.26 |
| busy-session-trend @ 30 | 14435 | 25% | 14.51 | 15.43 | 2.29 | 0.0219 | 0.299 | 11.63 |
| busy-session-trend @ 60 | 13293 | 25% | 30.57 | 32.55 | 2.45 | 0.0145 | 0.299 | 28.75 |
| busy-session-trend @ 120 | 10789 | 25% | 36.75 | 42.23 | 1.69 | 0.0917 | 0.423 | 38.43 |
| quiet-session-fade @ 5 | 18276 | 46% | -0.55 | -0.52 | -0.77 | 0.4425 | 0.800 | -4.32 |
| quiet-session-fade @ 15 | 17712 | 46% | -1.13 | -1.06 | -0.74 | 0.4569 | 0.800 | -4.86 |
| quiet-session-fade @ 30 | 16892 | 46% | -3.26 | -3.11 | -1.33 | 0.1835 | 0.527 | -6.91 |
| quiet-session-fade @ 60 | 15249 | 46% | -6.76 | -6.43 | -1.62 | 0.1050 | 0.423 | -10.23 |
| quiet-session-fade @ 120 | 12048 | 46% | -8.30 | -7.32 | -1.34 | 0.1814 | 0.527 | -11.12 |

**No cell survives FDR control in the research half.**

**Predictability budget (volume family, research half):** best surviving drift-adjusted edge 0.00 ticks (`none`) against 3.80 ticks of cost — ratio 0.00.

> no tested condition shows a drift-adjusted edge that survives false-discovery control (q <= 0.1) — on this sample and session none of these hypotheses is distinguishable from noise, which does not prove the market is unpredictable, only that these signals do not predict it

## 4. Heavy versus light: the interaction test, stated in advance

The hypothesis this study was built to test: *the same-sized move continues differently on heavy volume than on light volume.*
Both conditions require an identical body (>= 0.5 ATR); the only difference is the volume filter.

| horizon (bars) | heavy n | heavy drift-adj | light n | light drift-adj | difference | t | p |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | 11909 | 0.45 | 10292 | 0.02 | 0.42 | 0.47 | 0.639 |
| 15 | 11702 | 1.49 | 9959 | 1.13 | 0.35 | 0.23 | 0.818 |
| 30 | 11198 | -0.39 | 9481 | 0.65 | -1.04 | -0.48 | 0.635 |
| 60 | 10190 | 6.91 | 8424 | 3.12 | 3.78 | 1.17 | 0.243 |
| 120 | 7771 | 7.27 | 6291 | 3.63 | 3.64 | 0.69 | 0.488 |

## 4b. Is a "volume surge" a volume filter, or a clock?

A volume filter whose flagged bars cluster at particular hours is partly a clock, and the clock is the first thing to rule out. The controls below use the IDENTICAL body filter with NO volume condition whatsoever; they are not candidates and are not in the FDR family — they can only take a result away, never create one.

| condition | 09:00 | 10:00 | 11:00 | 12:00 | 13:00 | 14:00 | 15:00 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| trailing-surge-continuation | 13% | 9% | 10% | 13% | 16% | 16% | 22% |
| heavy-continuation (time-of-day rvol) | 3% | 13% | 14% | 17% | 18% | 20% | 15% |

| condition | horizon | research n | research drift-adj | research t | holdout n | holdout drift-adj | holdout t |
| --- | --- | --- | --- | --- | --- | --- | --- |
| body-only (any time) | 60 | 67670 | 1.88 | 2.10 | 28838 | 0.46 | 0.22 |
| body-only (any time) | 120 | 54848 | 1.94 | 1.48 | 23356 | 3.67 | 1.09 |
| body-only (first 60 min) | 60 | 12482 | 3.28 | 1.21 | 5274 | 3.44 | 0.71 |
| body-only (first 60 min) | 120 | 12482 | 5.49 | 1.60 | 5274 | 4.74 | 0.85 |
| trailing-surge-continuation | 60 | 6134 | 7.16 | 2.00 | 2242 | 6.99 | 0.80 |
| trailing-surge-continuation | 120 | 4783 | 11.37 | 2.00 | 1771 | 26.06 | 2.04 |
| heavy-continuation | 60 | 10190 | 6.91 | 2.18 | 4543 | 2.53 | 0.33 |
| heavy-continuation | 120 | 7771 | 7.27 | 1.62 | 3567 | 14.10 | 1.19 |

## 5. Long/short decomposition

Prior studies in this repo found "edges" that were entirely one-sided, i.e. the NQ uptrend. Any condition whose drift-adjusted edge lives on one side only is suspect by default.

| cell / side | n | raw ticks | drift-adj ticks | HAC t |
| --- | --- | --- | --- | --- |
| busy-session-trend @ 15 long | 3751 | 10.84 | 9.93 | 1.43 |
| busy-session-trend @ 15 short | 11212 | 7.86 | 8.77 | 2.18 |
| busy-session-trend @ 60 long | 3293 | 42.62 | 38.70 | 1.36 |
| busy-session-trend @ 60 short | 10000 | 26.61 | 30.53 | 1.99 |
| busy-session-trend @ 5 long | 3837 | 3.70 | 3.36 | 1.32 |
| busy-session-trend @ 5 short | 11469 | 2.78 | 3.12 | 2.00 |
| busy-session-trend @ 30 long | 3626 | 18.56 | 16.72 | 1.23 |
| busy-session-trend @ 30 short | 10809 | 13.15 | 14.99 | 1.90 |
| heavy-continuation @ 60 long | 4711 | -0.08 | -4.00 | -0.50 |
| heavy-continuation @ 60 short | 5479 | 12.36 | 16.28 | 1.76 |

### The same edges with SESSION-clustered standard errors

Several of these conditions are day-level states, not bar-level events: once a session is "busy" or "quiet" the condition fires on most of its bars. The HAC lag inside the event study prices the overlap of the forward windows, not the fact that thousands of events come from a few hundred days. Collapsing each session to one observation prices that too.

| cell | events | sessions | drift-adj ticks (event mean) | HAC t | per-session mean | clustered t |
| --- | --- | --- | --- | --- | --- | --- |
| busy-session-trend @ 15 | 14963 | 176 | 9.06 | 2.62 | -15.76 | -1.97 |
| busy-session-trend @ 60 | 13293 | 175 | 32.55 | 2.45 | 4.74 | 0.31 |
| busy-session-trend @ 5 | 15306 | 177 | 3.18 | 2.36 | -6.59 | -1.61 |
| busy-session-trend @ 30 | 14435 | 176 | 15.43 | 2.29 | -13.05 | -1.22 |
| heavy-continuation @ 60 | 10190 | 504 | 6.91 | 2.18 | -3.50 | -1.30 |

## 6. Holdout

Nothing survived stage 3, so there is nothing the holdout is being asked to confirm.

For completeness — the whole grid on the holdout. **This table decided nothing**; it is printed so a reader can see whether the research half was unlucky rather than uninformative.

| cell | n | long% | raw ticks | drift-adj ticks | HAC t | p | q (BH) | net of cost |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| heavy-continuation @ 5 | 5280 | 47% | -1.53 | -1.51 | -0.71 | 0.4798 | 0.959 | -5.31 |
| heavy-continuation @ 15 | 5189 | 47% | -3.98 | -3.94 | -1.18 | 0.2387 | 0.895 | -7.74 |
| heavy-continuation @ 30 | 5008 | 48% | -7.03 | -6.94 | -1.28 | 0.2016 | 0.895 | -10.74 |
| heavy-continuation @ 60 | 4543 | 48% | 2.34 | 2.53 | 0.33 | 0.7450 | 0.959 | -1.27 |
| heavy-continuation @ 120 | 3567 | 47% | 13.39 | 14.10 | 1.19 | 0.2338 | 0.895 | 10.30 |
| light-continuation @ 5 | 4740 | 51% | 0.42 | 0.42 | 0.46 | 0.6482 | 0.959 | -3.38 |
| light-continuation @ 15 | 4592 | 51% | -1.86 | -1.88 | -1.20 | 0.2289 | 0.895 | -5.68 |
| light-continuation @ 30 | 4350 | 51% | -1.72 | -1.77 | -0.74 | 0.4579 | 0.959 | -5.57 |
| light-continuation @ 60 | 3917 | 52% | -1.13 | -1.26 | -0.35 | 0.7251 | 0.959 | -5.06 |
| light-continuation @ 120 | 2980 | 52% | -5.44 | -5.81 | -0.87 | 0.3855 | 0.959 | -9.61 |
| trailing-surge-continuation @ 5 | 2818 | 46% | -1.59 | -1.56 | -0.64 | 0.5215 | 0.959 | -5.36 |
| trailing-surge-continuation @ 15 | 2575 | 45% | 3.01 | 3.10 | 0.79 | 0.4302 | 0.959 | -0.70 |
| trailing-surge-continuation @ 30 | 2431 | 45% | 2.12 | 2.29 | 0.36 | 0.7151 | 0.959 | -1.51 |
| trailing-surge-continuation @ 60 | 2242 | 46% | 6.64 | 6.99 | 0.80 | 0.4228 | 0.959 | 3.19 |
| trailing-surge-continuation @ 120 | 1771 | 45% | 24.94 | 26.06 | 2.04 | 0.0418 | 0.895 | 22.26 |
| heavy-exhaustion-fade @ 5 | 908 | 60% | 0.93 | 0.86 | 0.10 | 0.9204 | 0.959 | -2.94 |
| heavy-exhaustion-fade @ 15 | 900 | 60% | 12.48 | 12.30 | 1.71 | 0.0875 | 0.895 | 8.50 |
| heavy-exhaustion-fade @ 30 | 870 | 60% | 14.56 | 14.20 | 1.12 | 0.2630 | 0.928 | 10.40 |
| heavy-exhaustion-fade @ 60 | 806 | 60% | -9.50 | -10.26 | -0.57 | 0.5672 | 0.959 | -14.06 |
| heavy-exhaustion-fade @ 120 | 610 | 60% | -35.09 | -37.17 | -1.44 | 0.1511 | 0.895 | -40.97 |
| climax-small-body @ 5 | 375 | 61% | 3.70 | 3.63 | 0.34 | 0.7315 | 0.959 | -0.17 |
| climax-small-body @ 15 | 373 | 61% | -0.63 | -0.84 | -0.04 | 0.9691 | 0.969 | -4.64 |
| climax-small-body @ 30 | 361 | 60% | 7.39 | 7.01 | 0.32 | 0.7505 | 0.959 | 3.21 |
| climax-small-body @ 60 | 325 | 60% | -27.33 | -28.14 | -1.20 | 0.2306 | 0.895 | -31.94 |
| climax-small-body @ 120 | 228 | 59% | -98.96 | -100.98 | -2.10 | 0.0358 | 0.895 | -104.78 |
| heavy-close-location @ 5 | 4047 | 49% | 0.34 | 0.35 | 0.12 | 0.9019 | 0.959 | -3.45 |
| heavy-close-location @ 15 | 3981 | 49% | -4.36 | -4.34 | -0.94 | 0.3494 | 0.959 | -8.14 |
| heavy-close-location @ 30 | 3822 | 49% | -6.26 | -6.23 | -0.91 | 0.3646 | 0.959 | -10.03 |
| heavy-close-location @ 60 | 3459 | 49% | -1.04 | -0.98 | -0.14 | 0.8867 | 0.959 | -4.78 |
| heavy-close-location @ 120 | 2681 | 48% | 2.77 | 3.12 | 0.30 | 0.7612 | 0.959 | -0.68 |
| dryup-break @ 5 | 2925 | 53% | 0.21 | 0.19 | 0.13 | 0.8935 | 0.959 | -3.61 |
| dryup-break @ 15 | 2836 | 53% | -3.33 | -3.38 | -1.19 | 0.2349 | 0.895 | -7.18 |
| dryup-break @ 30 | 2694 | 53% | -2.73 | -2.84 | -0.67 | 0.5049 | 0.959 | -6.64 |
| dryup-break @ 60 | 2443 | 53% | -0.23 | -0.48 | -0.07 | 0.9428 | 0.959 | -4.28 |
| dryup-break @ 120 | 1874 | 53% | -1.56 | -2.23 | -0.22 | 0.8262 | 0.959 | -6.03 |
| pressure-momentum @ 5 | 20861 | 59% | -0.22 | -0.28 | -0.23 | 0.8161 | 0.959 | -4.08 |
| pressure-momentum @ 15 | 20249 | 59% | -0.56 | -0.72 | -0.30 | 0.7627 | 0.959 | -4.52 |
| pressure-momentum @ 30 | 19469 | 59% | -1.55 | -1.88 | -0.50 | 0.6140 | 0.959 | -5.68 |
| pressure-momentum @ 60 | 17876 | 59% | 2.09 | 1.37 | 0.27 | 0.7871 | 0.959 | -2.43 |
| pressure-momentum @ 120 | 14701 | 59% | 5.37 | 3.31 | 0.34 | 0.7350 | 0.959 | -0.49 |
| pressure-divergence @ 5 | 2703 | 55% | 0.32 | 0.28 | 0.13 | 0.8981 | 0.959 | -3.52 |
| pressure-divergence @ 15 | 2640 | 55% | 1.21 | 1.11 | 0.30 | 0.7665 | 0.959 | -2.69 |
| pressure-divergence @ 30 | 2542 | 55% | -2.52 | -2.71 | -0.46 | 0.6439 | 0.959 | -6.51 |
| pressure-divergence @ 60 | 2312 | 55% | -1.32 | -1.72 | -0.15 | 0.8796 | 0.959 | -5.52 |
| pressure-divergence @ 120 | 1835 | 56% | 2.85 | 1.64 | 0.08 | 0.9333 | 0.959 | -2.16 |
| session-delta-divergence @ 5 | 686 | 58% | -3.36 | -3.41 | -0.49 | 0.6214 | 0.959 | -7.21 |
| session-delta-divergence @ 15 | 686 | 58% | 1.66 | 1.52 | 0.10 | 0.9220 | 0.959 | -2.28 |
| session-delta-divergence @ 30 | 686 | 58% | 17.07 | 16.79 | 0.62 | 0.5343 | 0.959 | 12.99 |
| session-delta-divergence @ 60 | 686 | 58% | -15.04 | -15.64 | -0.42 | 0.6766 | 0.959 | -19.44 |
| session-delta-divergence @ 120 | 674 | 57% | -56.13 | -57.63 | -1.21 | 0.2250 | 0.895 | -61.43 |
| busy-session-trend @ 5 | 11961 | 30% | 5.28 | 5.41 | 1.73 | 0.0831 | 0.895 | 1.61 |
| busy-session-trend @ 15 | 11641 | 30% | 10.51 | 10.87 | 1.37 | 0.1703 | 0.895 | 7.07 |
| busy-session-trend @ 30 | 11173 | 30% | 15.62 | 16.34 | 1.23 | 0.2197 | 0.895 | 12.54 |
| busy-session-trend @ 60 | 10272 | 30% | 38.25 | 39.81 | 1.66 | 0.0974 | 0.895 | 36.01 |
| busy-session-trend @ 120 | 8446 | 30% | 52.01 | 56.37 | 1.47 | 0.1405 | 0.895 | 52.57 |
| quiet-session-fade @ 5 | 10428 | 47% | 0.43 | 0.45 | 0.36 | 0.7165 | 0.959 | -3.35 |
| quiet-session-fade @ 15 | 10099 | 47% | 0.52 | 0.56 | 0.23 | 0.8197 | 0.959 | -3.24 |
| quiet-session-fade @ 30 | 9652 | 47% | -1.15 | -1.05 | -0.28 | 0.7787 | 0.959 | -4.85 |
| quiet-session-fade @ 60 | 8658 | 47% | 0.36 | 0.60 | 0.11 | 0.9155 | 0.959 | -3.20 |
| quiet-session-fade @ 120 | 6761 | 48% | -4.72 | -4.29 | -0.36 | 0.7156 | 0.959 | -8.09 |

The five strongest research cells, re-measured on the holdout with session clustering and a side split. None of them was licensed to be here — nothing survived stage 3 — so this is diagnosis, not validation:

| cell | holdout n | holdout drift-adj | holdout HAC t | sessions | clustered t | long ticks | short ticks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| busy-session-trend @ 15 | 11641 | 10.87 | 1.37 | 87 | -0.01 | 13.0 (n=3537) | 9.9 (n=8104) |
| busy-session-trend @ 60 | 10272 | 39.81 | 1.66 | 86 | 0.86 | 32.3 (n=3085) | 43.0 (n=7187) |
| busy-session-trend @ 5 | 11961 | 5.41 | 1.73 | 87 | 0.32 | 7.4 (n=3638) | 4.5 (n=8323) |
| busy-session-trend @ 30 | 11173 | 16.34 | 1.23 | 87 | -0.17 | 12.8 (n=3396) | 17.9 (n=7777) |
| heavy-continuation @ 60 | 4543 | 2.53 | 0.33 | 218 | -1.52 | 5.5 (n=2160) | -0.2 (n=2383) |

### Does the research half carry any information about the holdout half?

Sign agreement across all 60 cells: **32/60 = 53%** (a coin flip is 50%).
Correlation of the drift-adjusted edge between halves: **0.665**.

The six cells that came closest to surviving, and what they did next:

| cell | research drift-adj | research t | research q | holdout drift-adj | holdout t |
| --- | --- | --- | --- | --- | --- |
| heavy-continuation @ 60 | 6.91 | 2.18 | 0.299 | 2.53 | 0.33 |
| heavy-exhaustion-fade @ 60 | -18.64 | -2.17 | 0.299 | -10.26 | -0.57 |
| busy-session-trend @ 5 | 3.18 | 2.36 | 0.299 | 5.41 | 1.73 |
| busy-session-trend @ 15 | 9.06 | 2.62 | 0.299 | 10.87 | 1.37 |
| busy-session-trend @ 30 | 15.43 | 2.29 | 0.299 | 16.34 | 1.23 |
| busy-session-trend @ 60 | 32.55 | 2.45 | 0.299 | 39.81 | 1.66 |

### The one candidate that behaved the same way twice

`trailing-surge-continuation` did not survive stage 3 and is therefore NOT a finding. It is singled out because on the 5-minute pass it is the one condition whose drift-adjusted edge kept its sign, roughly its size, and a t above 2 in BOTH halves — so the useful question is what happens when the robustness probes are pointed at it. Every number below is diagnostic; none of it reverses the failed gate.

| horizon | year | events | sessions | drift-adj ticks | per-event std | clustered t |
| --- | --- | --- | --- | --- | --- | --- |
| 60 | 2022 | 36 | 4 | -17.3 | 160 | -0.92 |
| 60 | 2023 | 3034 | 257 | 5.2 | 220 | 0.58 |
| 60 | 2024 | 2910 | 259 | 10.1 | 266 | 1.68 |
| 60 | 2025 | 2398 | 244 | 6.3 | 382 | 0.85 |
| 120 | 2022 | 33 | 4 | -39.4 | 264 | -0.18 |
| 120 | 2023 | 2360 | 257 | 9.4 | 286 | 1.09 |
| 120 | 2024 | 2262 | 258 | 14.0 | 340 | 1.93 |
| 120 | 2025 | 1901 | 243 | 25.3 | 521 | 1.70 |

Across the whole sample the 120-minute cell means 15.4 ticks with a per-event standard deviation of 385 ticks — an information ratio of 0.040 per event. The edge is 4.0x the round turn and 25x smaller than the noise it sits in, which is why 6,556 events still cannot settle the question.

## 7. The arithmetic

| quantity | value |
| --- | --- |
| cells tested (research) | 60 |
| cells surviving BH at q <= 0.1 | 0 |
| largest drift-adjusted edge, research (n >= 100) | 42.23 ticks (busy-session-trend @ 120) |
| round-turn cost | 3.80 ticks |
| largest edge / cost | 11.11 |
| ...its HAC t and BH q | t = 1.69, q = 0.423 |
| ...same cell on the holdout | 56.37 ticks, t = 1.47 |

The "largest edge / cost" ratio above is the trap this protocol exists to catch: 42.23 ticks looks like 11.1x the cost of trading, and it is not distinguishable from noise once the 60 cells that produced it are accounted for. A large edge measured over a 2-hour horizon sits on top of a very large variance; ticks alone never settle anything.

