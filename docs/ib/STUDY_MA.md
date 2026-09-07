# Moving-average system (EMA/SMA, cross / filter / pullback) — deep study (NQ)

> Generated 2026-08-22T07:32:10.442Z · seed `20250822` · fill model `realistic` · reproducible from this repo.
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
| trades | 1194 |
| fill rate | 222% of sessions |
| unfilled limit orders | 0 |
| win rate | 36.9% |
| gross edge | -5.22 ticks |
| net edge | -8.65 ticks |
| expectancy | -0.032 R |
| profit factor | 0.911 |
| total P&L (1 contract) | -$51,616 |
| Sharpe | -0.90 |
| HAC t-stat | -1.33 (p=0.182) |
| max drawdown | 69.2% |

Exit mix: session 188 ($50,278) · stop 688 (-$562,072) · target 296 ($445,891) · time 22 ($14,287)

## 2. Anomaly search — which sessions are worth trading?

The geometry is held fixed and the question becomes: does some observable feature of the first hour predict whether the trade works? Every feature is computable the moment the IB window closes, before the break, the entry or the outcome. The statistic is the **lift** — this bucket's mean R minus every other trade's mean R — because a bucket can look good purely because the strategy is profitable overall. "Tuesdays make money" is not a finding when every day makes money.

| feature | bucket | trades | mean R | win | lift (R) | t | p | BH q |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| range vs prior IB | expanding | 387 | 0.095 | 40% | 0.189 | 2.29 | 0.022 | 0.227 |
| took prior session extreme | both | 37 | 0.139 | 41% | 0.177 | 0.76 | 0.448 | 0.723 |
| weekday | Tue | 246 | 0.104 | 42% | 0.171 | 1.79 | 0.073 | 0.227 |
| first-hour close position | closed low third | 416 | 0.061 | 40% | 0.142 | 1.78 | 0.074 | 0.227 |
| IB range percentile | wide | 398 | 0.061 | 39% | 0.139 | 1.71 | 0.086 | 0.227 |
| weekday | Fri | 234 | 0.058 | 39% | 0.112 | 1.17 | 0.244 | 0.465 |
| overnight gap | gap up | 452 | 0.026 | 40% | 0.094 | 1.20 | 0.229 | 0.465 |
| overnight gap | flat open | 331 | 0.000 | 38% | 0.044 | 0.52 | 0.603 | 0.844 |
| took prior session extreme | took prior high | 457 | -0.014 | 37% | 0.029 | 0.37 | 0.711 | 0.872 |
| first-hour close position | closed high third | 421 | -0.024 | 37% | 0.012 | 0.15 | 0.881 | 0.925 |
| IB range percentile | narrow | 349 | -0.027 | 37% | 0.008 | 0.09 | 0.925 | 0.925 |
| range vs prior IB | similar | 399 | -0.047 | 37% | -0.022 | -0.28 | 0.783 | 0.872 |
| took prior session extreme | inside prior range | 351 | -0.048 | 37% | -0.022 | -0.27 | 0.789 | 0.872 |
| took prior session extreme | took prior low | 349 | -0.058 | 36% | -0.037 | -0.45 | 0.656 | 0.861 |
| weekday | Mon | 238 | -0.082 | 36% | -0.063 | -0.67 | 0.501 | 0.751 |
| weekday | Thu | 214 | -0.112 | 34% | -0.098 | -1.01 | 0.311 | 0.545 |
| weekday | Wed | 262 | -0.129 | 34% | -0.125 | -1.38 | 0.166 | 0.388 |
| overnight gap | gap down | 411 | -0.122 | 33% | -0.137 | -1.76 | 0.079 | 0.227 |
| IB range percentile | medium | 447 | -0.119 | 34% | -0.139 | -1.80 | 0.072 | 0.227 |
| range vs prior IB | contracting | 408 | -0.139 | 34% | -0.162 | -2.08 | 0.038 | 0.227 |
| first-hour close position | closed middle | 357 | -0.149 | 33% | -0.167 | -2.08 | 0.038 | 0.227 |

**No feature survives FDR control across the 21 buckets tested.** The largest raw lift is 0.189R (range vs prior IB = expanding, q=0.227), which is what testing 21 slices of a profitable strategy produces by chance.

## 3. Parameter search over the full geometry

| field | value |
| --- | --- |
| configurations evaluated | 800 |
| best parameters | `maType=0 fast=20 slow=200 mode=1 exitMode=0 stopAtr=1 rr=1 maxBars=120 sideMode=0` |
| in-sample Sharpe | 1.70 |
| in-sample trades | 802 |
| in-sample net edge | 10.54 ticks |
| neighbour stability | n/a |
| neighbours still profitable | n/a |
| surface | spike |

Top 12 configurations in sample — note how little separates them, which is what a flat surface looks like:

| # | parameters | trades | net (ticks) | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 1 | `maType=0 fast=20 slow=200 mode=1 exitMode=0 stopAtr=1 rr=1 maxBars=120 sideMode=0` | 802 | 10.54 | 1.222 | 1.70 |
| 2 | `maType=1 fast=50 slow=200 mode=1 exitMode=0 stopAtr=1.5 rr=1 maxBars=60 sideMode=0` | 646 | 17.02 | 1.234 | 1.70 |
| 3 | `maType=0 fast=20 slow=200 mode=1 exitMode=1 stopAtr=1.5 rr=1 maxBars=60 sideMode=0` | 902 | 19.19 | 1.266 | 1.46 |
| 4 | `maType=0 fast=50 slow=200 mode=1 exitMode=1 stopAtr=2.5 rr=2 maxBars=30 sideMode=0` | 882 | 16.22 | 1.234 | 1.45 |
| 5 | `maType=1 fast=9 slow=200 mode=1 exitMode=1 stopAtr=2.5 rr=1 maxBars=120 sideMode=0` | 948 | 18.37 | 1.244 | 1.45 |
| 6 | `maType=1 fast=5 slow=200 mode=1 exitMode=1 stopAtr=2.5 rr=3 maxBars=120 sideMode=0` | 948 | 18.37 | 1.244 | 1.45 |
| 7 | `maType=1 fast=20 slow=50 mode=0 exitMode=0 stopAtr=1 rr=1 maxBars=30 sideMode=0` | 735 | 8.18 | 1.169 | 1.43 |
| 8 | `maType=1 fast=20 slow=50 mode=0 exitMode=0 stopAtr=1 rr=1 maxBars=120 sideMode=0` | 735 | 8.18 | 1.169 | 1.43 |
| 9 | `maType=1 fast=20 slow=200 mode=0 exitMode=1 stopAtr=1.5 rr=2 maxBars=120 sideMode=0` | 348 | 35.04 | 1.353 | 1.41 |
| 10 | `maType=0 fast=5 slow=200 mode=0 exitMode=1 stopAtr=1 rr=2 maxBars=60 sideMode=0` | 580 | 25.45 | 1.327 | 1.41 |
| 11 | `maType=0 fast=50 slow=200 mode=1 exitMode=1 stopAtr=2.5 rr=1 maxBars=60 sideMode=-1` | 547 | 25.96 | 1.370 | 1.39 |
| 12 | `maType=0 fast=50 slow=100 mode=2 exitMode=0 stopAtr=1.5 rr=1 maxBars=30 sideMode=-1` | 358 | 16.61 | 1.252 | 1.37 |

Published geometry ranks **#801** of 800.

## 4. Walk-forward — paying for the parameter choice

| metric | walk-forward OOS |
| --- | --- |
| folds | 7 |
| trades | 480 |
| net edge | -5.72 ticks |
| profit factor | 0.917 |
| Sharpe | -0.65 |
| HAC t-stat | -0.68 (p=0.498) |
| efficiency | -0.49 |
| folds profitable | 43% |
| total P&L | -$13,740 |

OOS equity: `▆▆▆▆▆▆▆▆▅▄▅▄▄▄▅▅▅▅▅▅▅▅▅▄▄▄▄▂▃▂▂▂▂▂▁▁▁▁▁▂▃▄▅▅▆▇▆▇▇▇█▇▆▅▅▅▅▄▃▃`

Parameter stability across folds: maType 86%, fast 43%, slow 71%, mode 57%, exitMode 57%, stopAtr 86%, rr 71%, maxBars 57%, sideMode 57%

## 5. Selection bias — PBO, Deflated Sharpe, bootstrap

| statistic | value |
| --- | --- |
| configurations evaluated in total | 3600 |
| PBO | 0.413 over 252 balanced splits of 120 configurations |
| walk-forward OOS Sharpe | -0.65 |
| bootstrap 95% CI on that Sharpe | [-2.77, 1.32] |
| expected max Sharpe under the null | 2.53 |
| Deflated Sharpe | 0.000 |
| minimum track record | never at this Sharpe |

## 6. Monte Carlo on the out-of-sample trade sequence

The backtest shows one ordering of the trades that happened to occur. Reshuffling that order 20,000 times answers the question that decides whether it is tradeable with real money: how deep does the drawdown get in the unlucky-but-normal case?

| measure | reshuffled order | resampled with replacement |
| --- | --- | --- |
| median max drawdown | 45.4% | 47.5% |
| 95th percentile drawdown | 61.8% | 93.0% |
| 99th percentile drawdown | 70.8% | 112.8% |
| P(ending below start) | 100.0% | 78.5% |
| P(25% drawdown on $50k) | 100.0% | 89.7% |
| median final P&L | -$13,740 | -$14,160 |
| 5th percentile final P&L | -$13,740 | -$42,855 |
| median worst losing streak | 10 | 10 |

Reshuffling keeps the observed trades and asks about luck of ordering; resampling with replacement also asks what a different draw of trades from the same distribution would have looked like. The second is the harsher and more honest test.

## 7. Robustness of the tuned configuration

Walk-forward modal parameters: `maType=1 fast=5 slow=100 mode=0 exitMode=0 stopAtr=1 rr=1 maxBars=120 sideMode=0`

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 51.64 | 44.09 | 36.54 | 29.00 | 21.45 | 6.36 |
| Sharpe | 1.86 | 1.58 | 1.30 | 1.03 | 0.76 | 0.22 |

Cost tolerance: **survives every cost level tested — still profitable at 3x (11.40 ticks)**.

| probe | result |
| --- | --- |
| profitable OOS sub-periods | 33% |
| worst sub-period | -$14,563 |
| best year's share of P&L | 0% |
| profitable years | 0% |
| long vs short | 322 long (-$1,418) · 158 short (-$12,322) |

**Gates passed 3/10.**

- PASS — >=100 out-of-sample trades (480)
- PASS — survives >=1.5x modelled costs — survives every cost level tested — still profitable at 3x (11.40 ticks)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-5.72 ticks)
- FAIL — HAC t-stat > 2 (-0.68)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — PBO < 0.30 (0.41)
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (33%)
- FAIL — walk-forward efficiency >=0.4 (-0.49)

## 8. Locked holdout — evaluated once

| configuration | trades | win | net (ticks) | R | PF | Sharpe | t | P&L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| published geometry | 530 | 39% | 4.15 | 0.063 | 1.030 | 0.23 | 0.21 | $10,985 |
| in-sample optimum | 366 | 46% | -12.53 | -0.100 | 0.847 | -1.40 | -1.23 | -$22,922 |
| walk-forward modal | 379 | 51% | -0.31 | -0.013 | 0.996 | -0.04 | -0.05 | -$581 |

---

Runtime 26.0s · 3600 configurations evaluated · seed 20250822.
