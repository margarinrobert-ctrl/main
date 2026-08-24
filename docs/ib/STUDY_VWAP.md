# VWAP band mean reversion (sigma / ATR bands) — deep study (NQ)

> Generated 2026-08-22T07:40:58.420Z · seed `20250822` · fill model `realistic` · reproducible from this repo.
> Research output, not financial advice.

| field | value |
| --- | --- |
| data | `data/NQ_5m.csv` · 210,516 bars @ 5m |
| range | 2022-12-26 → 2025-12-12 |
| session | 09:30–16:00 America/New_York |
| opening window studied | 09:30–10:30 (60 min) |
| research bars / sessions | 41,026 / 537 |
| holdout bars / sessions | 17,583 / 229 |
| round-turn cost | 3.80 ticks ($19.00) |

## 1. Baseline — the published geometry, untouched

The strategy's published / default geometry, both sides, every session. No filtering, no tuning. This is the number every improvement below has to beat.

| metric | value |
| --- | --- |
| trades | 2516 |
| fill rate | 469% of sessions |
| unfilled limit orders | 0 |
| win rate | 30.6% |
| gross edge | -0.92 ticks |
| net edge | -4.13 ticks |
| expectancy | -0.084 R |
| profit factor | 0.901 |
| total P&L (1 contract) | -$52,007 |
| Sharpe | -1.28 |
| HAC t-stat | -2.12 (p=0.034) |
| max drawdown | 56.9% |

Exit mix: target 975 ($408,638) · stop 1417 (-$516,243) · time 44 ($34,879) · session 80 ($20,720)

## 2. Anomaly search — which sessions are worth trading?

The geometry is held fixed and the question becomes: does some observable feature of the first hour predict whether the trade works? Every feature is computable the moment the IB window closes, before the break, the entry or the outcome. The statistic is the **lift** — this bucket's mean R minus every other trade's mean R — because a bucket can look good purely because the strategy is profitable overall. "Tuesdays make money" is not a finding when every day makes money.

| feature | bucket | trades | mean R | win | lift (R) | t | p | BH q |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| took prior session extreme | both | 36 | 0.240 | 33% | 0.329 | 1.00 | 0.319 | 0.558 |
| took prior session extreme | took prior low | 663 | 0.025 | 33% | 0.149 | 2.12 | 0.034 | 0.240 |
| first-hour close position | closed middle | 791 | 0.012 | 33% | 0.141 | 2.14 | 0.032 | 0.240 |
| IB range percentile | narrow | 991 | -0.014 | 34% | 0.117 | 1.91 | 0.056 | 0.284 |
| range vs prior IB | contracting | 1025 | -0.021 | 34% | 0.108 | 1.76 | 0.079 | 0.284 |
| overnight gap | gap down | 824 | -0.019 | 33% | 0.097 | 1.49 | 0.137 | 0.360 |
| weekday | Wed | 523 | -0.020 | 31% | 0.082 | 1.06 | 0.291 | 0.555 |
| weekday | Tue | 488 | -0.061 | 32% | 0.029 | 0.38 | 0.702 | 0.738 |
| took prior session extreme | inside prior range | 800 | -0.068 | 31% | 0.025 | 0.38 | 0.703 | 0.738 |
| overnight gap | flat open | 613 | -0.067 | 29% | 0.023 | 0.31 | 0.754 | 0.754 |
| weekday | Mon | 483 | -0.108 | 31% | -0.028 | -0.39 | 0.699 | 0.738 |
| weekday | Fri | 477 | -0.116 | 27% | -0.038 | -0.48 | 0.630 | 0.738 |
| range vs prior IB | similar | 843 | -0.111 | 28% | -0.040 | -0.63 | 0.530 | 0.702 |
| first-hour close position | closed low third | 812 | -0.112 | 31% | -0.041 | -0.64 | 0.521 | 0.702 |
| IB range percentile | wide | 615 | -0.119 | 27% | -0.046 | -0.62 | 0.535 | 0.702 |
| weekday | Thu | 544 | -0.121 | 31% | -0.046 | -0.65 | 0.513 | 0.702 |
| IB range percentile | medium | 909 | -0.139 | 29% | -0.085 | -1.37 | 0.169 | 0.395 |
| range vs prior IB | expanding | 647 | -0.151 | 28% | -0.089 | -1.30 | 0.194 | 0.408 |
| first-hour close position | closed high third | 912 | -0.144 | 28% | -0.093 | -1.49 | 0.137 | 0.360 |
| overnight gap | gap up | 1078 | -0.144 | 29% | -0.105 | -1.74 | 0.081 | 0.284 |
| took prior session extreme | took prior high | 1016 | -0.181 | 28% | -0.161 | -2.67 | 0.008 | 0.160 |

**No feature survives FDR control across the 21 buckets tested.** The largest raw lift is 0.329R (took prior session extreme = both, q=0.558), which is what testing 21 slices of a profitable strategy produces by chance.

## 3. Parameter search over the full geometry

| field | value |
| --- | --- |
| configurations evaluated | 800 |
| best parameters | `bandType=0 bandK=3 confirm=0 stopMode=1 stopK=1.5 targetMode=0 targetFrac=75 maxVolPct=100 maxBars=24 sideMode=0 minMinutes=60 anchorBars=20` |
| in-sample Sharpe | 1.73 |
| in-sample trades | 124 |
| in-sample net edge | 35.66 ticks |
| neighbour stability | n/a |
| neighbours still profitable | n/a |
| surface | spike |

Top 12 configurations in sample — note how little separates them, which is what a flat surface looks like:

| # | parameters | trades | net (ticks) | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 1 | `bandType=0 bandK=3 confirm=0 stopMode=1 stopK=1.5 targetMode=0 targetFrac=75 maxVolPct=100 maxBars=24 sideMode=0 minMinutes=60 anchorBars=20` | 124 | 35.66 | 1.676 | 1.73 |
| 2 | `bandType=0 bandK=3 confirm=0 stopMode=1 stopK=0.75 targetMode=0 targetFrac=50 maxVolPct=100 maxBars=12 sideMode=-1 minMinutes=60 anchorBars=20` | 61 | 39.60 | 2.150 | 1.60 |
| 3 | `bandType=1 bandK=2 confirm=1 stopMode=1 stopK=2 targetMode=0 targetFrac=50 maxVolPct=60 maxBars=48 sideMode=1 minMinutes=0 anchorBars=12` | 186 | 27.99 | 1.501 | 1.60 |
| 4 | `bandType=1 bandK=1.5 confirm=1 stopMode=1 stopK=1.5 targetMode=1 targetFrac=50 maxVolPct=80 maxBars=24 sideMode=-1 minMinutes=30 anchorBars=40` | 850 | 5.55 | 1.197 | 1.39 |
| 5 | `bandType=0 bandK=1.5 confirm=1 stopMode=0 stopK=2 targetMode=1 targetFrac=50 maxVolPct=80 maxBars=48 sideMode=1 minMinutes=60 anchorBars=20` | 1044 | 5.75 | 1.173 | 1.34 |
| 6 | `bandType=1 bandK=3 confirm=0 stopMode=1 stopK=1 targetMode=0 targetFrac=100 maxVolPct=60 maxBars=48 sideMode=1 minMinutes=0 anchorBars=20` | 136 | 30.18 | 1.468 | 1.30 |
| 7 | `bandType=1 bandK=2.5 confirm=0 stopMode=1 stopK=1.5 targetMode=0 targetFrac=50 maxVolPct=60 maxBars=24 sideMode=1 minMinutes=60 anchorBars=40` | 412 | 17.24 | 1.226 | 1.27 |
| 8 | `bandType=2 bandK=1.5 confirm=1 stopMode=0 stopK=0.75 targetMode=0 targetFrac=75 maxVolPct=80 maxBars=12 sideMode=1 minMinutes=30 anchorBars=0` | 637 | 7.34 | 1.190 | 1.23 |
| 9 | `bandType=1 bandK=3 confirm=0 stopMode=1 stopK=1 targetMode=0 targetFrac=100 maxVolPct=60 maxBars=24 sideMode=1 minMinutes=60 anchorBars=0` | 432 | 14.33 | 1.231 | 1.23 |
| 10 | `bandType=1 bandK=2 confirm=1 stopMode=0 stopK=2 targetMode=1 targetFrac=75 maxVolPct=60 maxBars=48 sideMode=1 minMinutes=0 anchorBars=40` | 339 | 14.83 | 1.258 | 1.19 |
| 11 | `bandType=1 bandK=2.5 confirm=0 stopMode=0 stopK=0.75 targetMode=0 targetFrac=75 maxVolPct=60 maxBars=12 sideMode=1 minMinutes=30 anchorBars=40` | 840 | 5.97 | 1.150 | 1.16 |
| 12 | `bandType=0 bandK=3 confirm=1 stopMode=1 stopK=1 targetMode=0 targetFrac=50 maxVolPct=100 maxBars=48 sideMode=0 minMinutes=30 anchorBars=20` | 132 | 18.80 | 1.401 | 1.12 |

Published geometry ranks **#682** of 800.

## 4. Walk-forward — paying for the parameter choice

| metric | walk-forward OOS |
| --- | --- |
| folds | 7 |
| trades | 176 |
| net edge | -16.48 ticks |
| profit factor | 0.782 |
| Sharpe | -1.04 |
| HAC t-stat | -1.12 (p=0.261) |
| efficiency | -0.56 |
| folds profitable | 29% |
| total P&L | -$14,502 |

OOS equity: `▅▅▆▆▆▅▅▆▆▆▆▆▇▇▇▇▇▇▇▇▆▆▆▆▆▆▆▆▆█▇▇▇▄▄▃▃▃▃▂▂▂▂▂▂▁▂▁▁▁▁▁▁▁▁▁▁▁▁▁`

Parameter stability across folds: bandType 57%, bandK 43%, confirm 71%, stopMode 86%, stopK 43%, targetMode 57%, targetFrac 57%, maxVolPct 57%, maxBars 57%, sideMode 43%, minMinutes 71%, anchorBars 57%

## 5. Selection bias — PBO, Deflated Sharpe, bootstrap

| statistic | value |
| --- | --- |
| configurations evaluated in total | 3600 |
| PBO | 0.234 over 252 balanced splits of 120 configurations |
| walk-forward OOS Sharpe | -1.03 |
| bootstrap 95% CI on that Sharpe | [-2.57, 0.81] |
| expected max Sharpe under the null | 3.67 |
| Deflated Sharpe | 0.000 |
| minimum track record | never at this Sharpe |

## 6. Monte Carlo on the out-of-sample trade sequence

The backtest shows one ordering of the trades that happened to occur. Reshuffling that order 20,000 times answers the question that decides whether it is tradeable with real money: how deep does the drawdown get in the unlucky-but-normal case?

| measure | reshuffled order | resampled with replacement |
| --- | --- | --- |
| median max drawdown | 36.8% | 37.9% |
| 95th percentile drawdown | 46.3% | 68.5% |
| 99th percentile drawdown | 51.3% | 81.6% |
| P(ending below start) | 100.0% | 91.0% |
| P(25% drawdown on $50k) | 100.0% | 80.3% |
| median final P&L | -$14,502 | -$14,567 |
| 5th percentile final P&L | -$14,502 | -$32,214 |
| median worst losing streak | 8 | 8 |

Reshuffling keeps the observed trades and asks about luck of ordering; resampling with replacement also asks what a different draw of trades from the same distribution would have looked like. The second is the harsher and more honest test.

## 7. Robustness of the tuned configuration

Walk-forward modal parameters: `bandType=2 bandK=3 confirm=1 stopMode=1 stopK=1 targetMode=0 targetFrac=50 maxVolPct=100 maxBars=48 sideMode=0 minMinutes=30 anchorBars=20`

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 305.56 | 296.89 | 288.22 | 279.56 | 270.89 | 253.56 |
| Sharpe | 0.65 | 0.63 | 0.61 | 0.60 | 0.58 | 0.54 |

Cost tolerance: **survives every cost level tested — still profitable at 3x (11.40 ticks)**.

| probe | result |
| --- | --- |
| profitable OOS sub-periods | 33% |
| worst sub-period | -$15,008 |
| best year's share of P&L | 0% |
| profitable years | 50% |
| long vs short | 146 long (-$15,512) · 30 short ($1,010) |

**Gates passed 4/10.**

- PASS — >=100 out-of-sample trades (176)
- PASS — PBO < 0.30 (0.23)
- PASS — survives >=1.5x modelled costs — survives every cost level tested — still profitable at 3x (11.40 ticks)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-16.48 ticks)
- FAIL — HAC t-stat > 2 (-1.12)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (33%)
- FAIL — walk-forward efficiency >=0.4 (-0.56)

## 8. Locked holdout — evaluated once

| configuration | trades | win | net (ticks) | R | PF | Sharpe | t | P&L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| published geometry | 1038 | 28% | -9.19 | -0.068 | 0.865 | -1.52 | -1.61 | -$47,677 |
| in-sample optimum | 48 | 58% | 21.88 | 0.172 | 1.252 | 0.62 | 0.58 | $5,251 |
| walk-forward modal | 5 | 40% | -110.20 | 0.371 | 0.477 | -0.66 | -0.63 | -$2,755 |

---

Runtime 49.4s · 3600 configurations evaluated · seed 20250822.
