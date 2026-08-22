# Value-area rotation (auction-market theory) — deep study (NQ)

> Generated 2026-08-22T07:52:18.360Z · seed `20250822` · fill model `realistic` · reproducible from this repo.
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
| trades | 290 |
| fill rate | 54% of sessions |
| unfilled limit orders | 0 |
| win rate | 51.7% |
| gross edge | 22.20 ticks |
| net edge | 19.02 ticks |
| expectancy | 0.065 R |
| profit factor | 1.123 |
| total P&L (1 contract) | $27,585 |
| Sharpe | 0.56 |
| HAC t-stat | 0.94 (p=0.350) |
| max drawdown | 15.6% |

Exit mix: stop 90 (-$149,585) · target 120 ($222,540) · session 80 (-$45,370)

## 2. Anomaly search — which sessions are worth trading?

The geometry is held fixed and the question becomes: does some observable feature of the first hour predict whether the trade works? Every feature is computable the moment the IB window closes, before the break, the entry or the outcome. The statistic is the **lift** — this bucket's mean R minus every other trade's mean R — because a bucket can look good purely because the strategy is profitable overall. "Tuesdays make money" is not a finding when every day makes money.

| feature | bucket | trades | mean R | win | lift (R) | t | p | BH q |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| first-hour close position | closed middle | 76 | 0.351 | 67% | 0.387 | 3.41 | 0.001 | 0.013 |
| took prior session extreme | inside prior range | 29 | 0.388 | 72% | 0.358 | 2.09 | 0.037 | 0.183 |
| IB range percentile | narrow | 87 | 0.244 | 62% | 0.256 | 2.29 | 0.022 | 0.146 |
| range vs prior IB | contracting | 89 | 0.204 | 61% | 0.200 | 1.83 | 0.068 | 0.271 |
| weekday | Thu | 66 | 0.210 | 58% | 0.187 | 1.58 | 0.115 | 0.308 |
| weekday | Mon | 48 | 0.135 | 58% | 0.083 | 0.61 | 0.545 | 0.726 |
| overnight gap | gap up | 136 | 0.102 | 53% | 0.069 | 0.67 | 0.504 | 0.726 |
| took prior session extreme | took prior high | 152 | 0.085 | 52% | 0.042 | 0.40 | 0.689 | 0.861 |
| weekday | Tue | 49 | 0.077 | 55% | 0.014 | 0.10 | 0.923 | 0.923 |
| overnight gap | gap down | 110 | 0.059 | 53% | -0.010 | -0.10 | 0.922 | 0.923 |
| range vs prior IB | similar | 88 | 0.054 | 55% | -0.016 | -0.14 | 0.890 | 0.923 |
| first-hour close position | closed low third | 108 | 0.053 | 51% | -0.020 | -0.18 | 0.854 | 0.923 |
| IB range percentile | wide | 94 | 0.019 | 47% | -0.070 | -0.63 | 0.529 | 0.726 |
| overnight gap | flat open | 43 | -0.034 | 47% | -0.117 | -0.73 | 0.464 | 0.726 |
| weekday | Fri | 59 | -0.028 | 46% | -0.118 | -0.93 | 0.355 | 0.645 |
| took prior session extreme | took prior low | 103 | -0.021 | 48% | -0.135 | -1.26 | 0.208 | 0.446 |
| weekday | Wed | 67 | -0.053 | 45% | -0.154 | -1.22 | 0.223 | 0.446 |
| IB range percentile | medium | 108 | -0.038 | 48% | -0.165 | -1.54 | 0.123 | 0.308 |
| range vs prior IB | expanding | 112 | -0.036 | 43% | -0.166 | -1.57 | 0.117 | 0.308 |
| first-hour close position | closed high third | 105 | -0.128 | 42% | -0.304 | -2.90 | 0.004 | 0.038 |

**Survives FDR control (q ≤ 0.10): first-hour close position = closed middle (lift 0.387R); first-hour close position = closed high third (lift -0.304R).**

## 3. Parameter search over the full geometry

| field | value |
| --- | --- |
| configurations evaluated | 800 |
| best parameters | `mode=2 minTargetPts=40 rrStop=0.5 entryDelayBars=6 maxBars=999 holdBars=4 sideMode=1 minGapPts=0 binTicks=4` |
| in-sample Sharpe | 1.66 |
| in-sample trades | 114 |
| in-sample net edge | 63.43 ticks |
| neighbour stability | 0.71 |
| neighbours still profitable | 100% |
| surface | plateau |

Top 12 configurations in sample — note how little separates them, which is what a flat surface looks like:

| # | parameters | trades | net (ticks) | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 1 | `mode=2 minTargetPts=40 rrStop=0.5 entryDelayBars=6 maxBars=999 holdBars=4 sideMode=1 minGapPts=0 binTicks=4` | 114 | 63.43 | 1.827 | 1.66 |
| 2 | `mode=2 minTargetPts=40 rrStop=0.75 entryDelayBars=1 maxBars=999 holdBars=4 sideMode=1 minGapPts=40 binTicks=4` | 63 | 92.20 | 2.145 | 1.59 |
| 3 | `mode=2 minTargetPts=40 rrStop=0.75 entryDelayBars=1 maxBars=999 holdBars=1 sideMode=1 minGapPts=40 binTicks=4` | 63 | 92.20 | 2.145 | 1.59 |
| 4 | `mode=2 minTargetPts=40 rrStop=0.5 entryDelayBars=1 maxBars=999 holdBars=4 sideMode=1 minGapPts=40 binTicks=4` | 63 | 85.13 | 2.259 | 1.56 |
| 5 | `mode=2 minTargetPts=40 rrStop=1 entryDelayBars=1 maxBars=999 holdBars=2 sideMode=1 minGapPts=40 binTicks=4` | 63 | 90.27 | 1.972 | 1.48 |
| 6 | `mode=2 minTargetPts=40 rrStop=1 entryDelayBars=1 maxBars=999 holdBars=1 sideMode=1 minGapPts=40 binTicks=4` | 63 | 90.27 | 1.972 | 1.48 |
| 7 | `mode=2 minTargetPts=40 rrStop=0.5 entryDelayBars=6 maxBars=999 holdBars=2 sideMode=0 minGapPts=0 binTicks=4` | 191 | 41.17 | 1.479 | 1.44 |
| 8 | `mode=2 minTargetPts=40 rrStop=0.5 entryDelayBars=6 maxBars=999 holdBars=1 sideMode=0 minGapPts=0 binTicks=4` | 191 | 41.17 | 1.479 | 1.44 |
| 9 | `mode=2 minTargetPts=40 rrStop=0.5 entryDelayBars=6 maxBars=999 holdBars=4 sideMode=0 minGapPts=0 binTicks=4` | 191 | 41.17 | 1.479 | 1.44 |
| 10 | `mode=2 minTargetPts=40 rrStop=1 entryDelayBars=3 maxBars=999 holdBars=1 sideMode=1 minGapPts=40 binTicks=4` | 61 | 92.13 | 1.994 | 1.39 |
| 11 | `mode=2 minTargetPts=40 rrStop=1 entryDelayBars=3 maxBars=999 holdBars=4 sideMode=1 minGapPts=40 binTicks=4` | 61 | 92.13 | 1.994 | 1.39 |
| 12 | `mode=2 minTargetPts=40 rrStop=1 entryDelayBars=3 maxBars=999 holdBars=2 sideMode=1 minGapPts=40 binTicks=4` | 61 | 92.13 | 1.994 | 1.39 |

Published geometry ranks **#708** of 800.

## 4. Walk-forward — paying for the parameter choice

| metric | walk-forward OOS |
| --- | --- |
| folds | 7 |
| trades | 92 |
| net edge | 29.02 ticks |
| profit factor | 1.275 |
| Sharpe | 0.76 |
| HAC t-stat | 0.95 (p=0.345) |
| efficiency | 0.41 |
| folds profitable | 71% |
| total P&L | $13,350 |

OOS equity: `▁▁▁▁▁▁▁▁▁▁▁▁▂▂▂▂▂▂▂▁▁▁▁▁▁▁▁▁▁▂▁▁▁▂▂▂▂▂▃▄▄▄▄▄▄▇▇▇█▆▆▆▆▆▆▆▆▆▆▅`

Parameter stability across folds: mode 71%, minTargetPts 100%, rrStop 57%, entryDelayBars 57%, maxBars 100%, holdBars 57%, sideMode 43%, minGapPts 86%, binTicks 100%

## 5. Selection bias — PBO, Deflated Sharpe, bootstrap

| statistic | value |
| --- | --- |
| configurations evaluated in total | 3600 |
| PBO | 0.524 over 252 balanced splits of 120 configurations |
| walk-forward OOS Sharpe | 0.75 |
| bootstrap 95% CI on that Sharpe | [-0.92, 2.15] |
| expected max Sharpe under the null | 2.23 |
| Deflated Sharpe | 0.031 |
| minimum track record | never at this Sharpe |

## 6. Monte Carlo on the out-of-sample trade sequence

The backtest shows one ordering of the trades that happened to occur. Reshuffling that order 20,000 times answers the question that decides whether it is tradeable with real money: how deep does the drawdown get in the unlucky-but-normal case?

| measure | reshuffled order | resampled with replacement |
| --- | --- | --- |
| median max drawdown | 16.9% | 17.2% |
| 95th percentile drawdown | 26.9% | 38.2% |
| 99th percentile drawdown | 32.6% | 51.1% |
| P(ending below start) | 0.0% | 18.6% |
| P(25% drawdown on $50k) | 8.3% | 22.2% |
| median final P&L | $13,350 | $13,095 |
| 5th percentile final P&L | $13,350 | -$10,908 |
| median worst losing streak | 6 | 6 |

Reshuffling keeps the observed trades and asks about luck of ordering; resampling with replacement also asks what a different draw of trades from the same distribution would have looked like. The second is the harsher and more honest test.

## 7. Robustness of the tuned configuration

Walk-forward modal parameters: `mode=2 minTargetPts=40 rrStop=0.75 entryDelayBars=6 maxBars=999 holdBars=1 sideMode=0 minGapPts=0 binTicks=4`

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 227.20 | 219.41 | 211.62 | 203.82 | 196.03 | 180.45 |
| Sharpe | 1.41 | 1.36 | 1.31 | 1.26 | 1.22 | 1.12 |

Cost tolerance: **survives every cost level tested — still profitable at 3x (11.40 ticks)**.

| probe | result |
| --- | --- |
| profitable OOS sub-periods | 67% |
| worst sub-period | -$9,323 |
| best year's share of P&L | 84% |
| profitable years | 100% |
| long vs short | 53 long ($8,756) · 39 short ($4,594) |

**Gates passed 5/10.**

- PASS — positive net edge after costs (29.02 ticks)
- PASS — survives >=1.5x modelled costs — survives every cost level tested — still profitable at 3x (11.40 ticks)
- PASS — parameter surface is not a mined spike (plateau)
- PASS — profitable in >=60% of sub-periods (67%)
- PASS — walk-forward efficiency >=0.4 (0.41)
- FAIL — >=100 out-of-sample trades (92)
- FAIL — HAC t-stat > 2 (0.95)
- FAIL — deflated Sharpe > 0.95 (0.031)
- FAIL — PBO < 0.30 (0.52)
- FAIL — no single year carries >60% of P&L (84%)

## 8. Locked holdout — evaluated once

| configuration | trades | win | net (ticks) | R | PF | Sharpe | t | P&L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| published geometry | 133 | 54% | 51.87 | 0.088 | 1.232 | 0.96 | 1.03 | $34,496 |
| in-sample optimum | 50 | 34% | -12.73 | -0.110 | 0.901 | -0.30 | -0.28 | -$3,183 |
| walk-forward modal | 78 | 41% | -51.92 | -0.108 | 0.700 | -1.33 | -1.22 | -$20,247 |

Applying the anomaly filters that survived FDR control to the holdout:

| set | trades | mean R | win | t | P&L |
| --- | --- | --- | --- | --- | --- |
| all holdout trades | 133 | 0.088 | 54% | 1.30 | $34,496 |
| filtered | 0 | 0.000 | 0% | 0.00 | $0 |

---

Runtime 38.6s · 3600 configurations evaluated · seed 20250822.
