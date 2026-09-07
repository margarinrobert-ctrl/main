# Overnight gap fade (size-filtered) — deep study (NQ)

> Generated 2026-08-22T14:15:39.550Z · seed `20250822` · fill model `realistic` · reproducible from this repo.
> Research output, not financial advice.

| field | value |
| --- | --- |
| data | `data/NQ_1m.csv` · 1,048,575 bars @ 1m |
| range | 2022-12-26 → 2025-12-12 |
| session | 09:30–16:00 America/New_York (entries); full 23h series retained for signal formation |
| opening window studied | 09:30–10:30 (60 min) |
| research bars / sessions | 734,002 / 648 |
| holdout bars / sessions | 314,573 / 276 |
| round-turn cost | 3.80 ticks ($19.00) |

## 1. Baseline — the published geometry, untouched

The strategy's published / default geometry, both sides, every session. No filtering, no tuning. This is the number every improvement below has to beat.

| metric | value |
| --- | --- |
| trades | 126 |
| fill rate | 19% of sessions |
| unfilled limit orders | 0 |
| win rate | 40.5% |
| gross edge | 11.22 ticks |
| net edge | 7.82 ticks |
| expectancy | 0.059 R |
| profit factor | 1.045 |
| total P&L (1 contract) | $4,924 |
| Sharpe | 0.13 |
| HAC t-stat | 0.19 (p=0.848) |
| max drawdown | 21.4% |

Exit mix: stop 66 (-$103,709) · target 33 ($73,891) · session 27 ($34,742)

## 2. Anomaly search — which sessions are worth trading?

The geometry is held fixed and the question becomes: does some observable feature of the first hour predict whether the trade works? Every feature is computable the moment the IB window closes, before the break, the entry or the outcome. The statistic is the **lift** — this bucket's mean R minus every other trade's mean R — because a bucket can look good purely because the strategy is profitable overall. "Tuesdays make money" is not a finding when every day makes money.

| feature | bucket | trades | mean R | win | lift (R) | t | p | BH q |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| weekday | Thu | 31 | 0.439 | 52% | 0.504 | 1.84 | 0.066 | 0.751 |
| IB range percentile | narrow | 28 | 0.188 | 46% | 0.166 | 0.57 | 0.568 | 0.994 |
| took prior session extreme | took prior high | 60 | 0.124 | 38% | 0.124 | 0.54 | 0.591 | 0.994 |
| range vs prior IB | expanding | 58 | 0.106 | 40% | 0.087 | 0.37 | 0.709 | 0.994 |
| weekday | Tue | 26 | 0.127 | 42% | 0.085 | 0.28 | 0.778 | 0.994 |
| first-hour close position | closed middle | 26 | 0.086 | 42% | 0.034 | 0.12 | 0.907 | 0.994 |
| first-hour close position | closed low third | 51 | 0.060 | 37% | 0.002 | 0.01 | 0.994 | 0.994 |
| range vs prior IB | similar | 45 | 0.051 | 42% | -0.012 | -0.05 | 0.960 | 0.994 |
| first-hour close position | closed high third | 49 | 0.044 | 43% | -0.025 | -0.11 | 0.914 | 0.994 |
| IB range percentile | wide | 55 | 0.036 | 38% | -0.041 | -0.18 | 0.861 | 0.994 |
| IB range percentile | medium | 43 | 0.004 | 40% | -0.083 | -0.35 | 0.726 | 0.994 |
| range vs prior IB | contracting | 23 | -0.045 | 39% | -0.127 | -0.43 | 0.664 | 0.994 |
| weekday | Fri | 20 | -0.051 | 30% | -0.131 | -0.43 | 0.667 | 0.994 |
| took prior session extreme | took prior low | 50 | -0.121 | 38% | -0.298 | -1.32 | 0.187 | 0.936 |
| weekday | Wed | 35 | -0.235 | 31% | -0.407 | -1.64 | 0.100 | 0.751 |

**No feature survives FDR control across the 15 buckets tested.** The largest raw lift is 0.504R (weekday = Thu, q=0.751), which is what testing 15 slices of a profitable strategy produces by chance.

## 3. Parameter search over the full geometry

| field | value |
| --- | --- |
| configurations evaluated | 324 |
| best parameters | `minGapRatio=0.4 maxGapRatio=99 rrStop=0.5 entryDelayBars=6 minGapPts=5 sideMode=1 maxBars=999` |
| in-sample Sharpe | 0.44 |
| in-sample trades | 92 |
| in-sample net edge | 27.31 ticks |
| neighbour stability | 0.65 |
| neighbours still profitable | 83% |
| surface | plateau |

Top 12 configurations in sample — note how little separates them, which is what a flat surface looks like:

| # | parameters | trades | net (ticks) | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 1 | `minGapRatio=0.4 maxGapRatio=99 rrStop=0.5 entryDelayBars=6 minGapPts=5 sideMode=1 maxBars=999` | 92 | 27.31 | 1.200 | 0.44 |
| 2 | `minGapRatio=0.4 maxGapRatio=99 rrStop=0.5 entryDelayBars=6 minGapPts=20 sideMode=1 maxBars=999` | 92 | 27.31 | 1.200 | 0.44 |
| 3 | `minGapRatio=0.4 maxGapRatio=99 rrStop=0.5 entryDelayBars=6 minGapPts=40 sideMode=1 maxBars=999` | 89 | 27.91 | 1.198 | 0.44 |
| 4 | `minGapRatio=0.25 maxGapRatio=99 rrStop=0.5 entryDelayBars=6 minGapPts=5 sideMode=1 maxBars=999` | 130 | 16.65 | 1.136 | 0.36 |
| 5 | `minGapRatio=0.25 maxGapRatio=99 rrStop=0.5 entryDelayBars=6 minGapPts=20 sideMode=1 maxBars=999` | 130 | 16.65 | 1.136 | 0.36 |
| 6 | `minGapRatio=0.25 maxGapRatio=99 rrStop=0.5 entryDelayBars=6 minGapPts=40 sideMode=1 maxBars=999` | 123 | 16.95 | 1.133 | 0.35 |
| 7 | `minGapRatio=0.4 maxGapRatio=99 rrStop=0.5 entryDelayBars=1 minGapPts=5 sideMode=1 maxBars=999` | 92 | 20.87 | 1.136 | 0.30 |
| 8 | `minGapRatio=0.4 maxGapRatio=99 rrStop=0.5 entryDelayBars=1 minGapPts=20 sideMode=1 maxBars=999` | 92 | 20.87 | 1.136 | 0.30 |
| 9 | `minGapRatio=0.4 maxGapRatio=99 rrStop=0.5 entryDelayBars=3 minGapPts=5 sideMode=1 maxBars=999` | 92 | 18.78 | 1.129 | 0.29 |
| 10 | `minGapRatio=0.4 maxGapRatio=99 rrStop=0.5 entryDelayBars=3 minGapPts=20 sideMode=1 maxBars=999` | 92 | 18.78 | 1.129 | 0.29 |
| 11 | `minGapRatio=0.4 maxGapRatio=99 rrStop=0.5 entryDelayBars=1 minGapPts=40 sideMode=1 maxBars=999` | 89 | 20.24 | 1.128 | 0.29 |
| 12 | `minGapRatio=0.4 maxGapRatio=99 rrStop=0.5 entryDelayBars=3 minGapPts=40 sideMode=1 maxBars=999` | 89 | 18.90 | 1.127 | 0.28 |

Published geometry ranks **#47** of 324.

## 4. Walk-forward — paying for the parameter choice

| metric | walk-forward OOS |
| --- | --- |
| folds | 9 |
| trades | 116 |
| net edge | 18.41 ticks |
| profit factor | 1.106 |
| Sharpe | 0.35 |
| HAC t-stat | 0.53 (p=0.598) |
| efficiency | -0.16 |
| folds profitable | 44% |
| total P&L | $10,676 |

OOS equity: `▄▄▄▃▂▃▂▃▃▃▃▂▂▂▂▂▁▁▂▂▂▂▂▂▂▃▃▂▁▁▁▂▂▄▄▆▆▅▆▇▇▇█▇▇▇▆▇▆▅▆▆▇▇▇▇▇▇▆▆`

Parameter stability across folds: minGapRatio 78%, maxGapRatio 100%, rrStop 78%, entryDelayBars 56%, minGapPts 67%, sideMode 78%, maxBars 100%

## 5. Selection bias — PBO, Deflated Sharpe, bootstrap

| statistic | value |
| --- | --- |
| configurations evaluated in total | 3240 |
| PBO | 0.968 over 252 balanced splits of 120 configurations |
| walk-forward OOS Sharpe | 0.35 |
| bootstrap 95% CI on that Sharpe | [-0.98, 1.81] |
| expected max Sharpe under the null | 0.71 |
| Deflated Sharpe | 0.315 |
| minimum track record | never at this Sharpe |

## 6. Monte Carlo on the out-of-sample trade sequence

The backtest shows one ordering of the trades that happened to occur. Reshuffling that order 20,000 times answers the question that decides whether it is tradeable with real money: how deep does the drawdown get in the unlucky-but-normal case?

| measure | reshuffled order | resampled with replacement |
| --- | --- | --- |
| median max drawdown | 30.0% | 31.1% |
| 95th percentile drawdown | 48.2% | 72.2% |
| 99th percentile drawdown | 58.3% | 95.0% |
| P(ending below start) | 0.0% | 31.8% |
| P(25% drawdown on $50k) | 76.4% | 66.6% |
| median final P&L | $10,676 | $10,916 |
| 5th percentile final P&L | $10,676 | -$26,407 |
| median worst losing streak | 6 | 6 |

Reshuffling keeps the observed trades and asks about luck of ordering; resampling with replacement also asks what a different draw of trades from the same distribution would have looked like. The second is the harsher and more honest test.

## 7. Robustness of the tuned configuration

Walk-forward modal parameters: `minGapRatio=0.25 maxGapRatio=99 rrStop=1 entryDelayBars=3 minGapPts=5 sideMode=-1 maxBars=999`

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 9.50 | 1.50 | -6.50 | -14.50 | -22.50 | -38.50 |
| Sharpe | 0.04 | 0.01 | -0.03 | -0.06 | -0.09 | -0.16 |

Cost tolerance: **dies at 0.59x modelled costs (2.26 ticks)**.

| probe | result |
| --- | --- |
| profitable OOS sub-periods | 50% |
| worst sub-period | -$8,128 |
| best year's share of P&L | 157% |
| profitable years | 50% |
| long vs short | 18 long (-$7,600) · 98 short ($18,276) |

**Gates passed 3/10.**

- PASS — >=100 out-of-sample trades (116)
- PASS — positive net edge after costs (18.41 ticks)
- PASS — parameter surface is not a mined spike (plateau)
- FAIL — HAC t-stat > 2 (0.53)
- FAIL — deflated Sharpe > 0.95 (0.315)
- FAIL — PBO < 0.30 (0.97)
- FAIL — survives >=1.5x modelled costs — dies at 0.59x modelled costs (2.26 ticks)
- FAIL — profitable in >=60% of sub-periods (50%)
- FAIL — no single year carries >60% of P&L (157%)
- FAIL — walk-forward efficiency >=0.4 (-0.16)

## 8. Locked holdout — evaluated once

| configuration | trades | win | net (ticks) | R | PF | Sharpe | t | P&L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| published geometry | 60 | 55% | 239.05 | 0.483 | 2.119 | 2.19 | 2.71 | $71,715 |
| in-sample optimum | 44 | 48% | 153.87 | 0.154 | 1.672 | 1.20 | 1.45 | $33,852 |
| walk-forward modal | 75 | 52% | 94.20 | 0.063 | 1.493 | 1.26 | 1.51 | $35,325 |

---

Runtime 52.5s · 3240 configurations evaluated · seed 20250822.
