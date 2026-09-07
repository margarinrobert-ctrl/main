# Initial Balance — deep study (NQ)

> Generated 2026-08-22T06:59:55.407Z · seed `20250822` · fill model `realistic` · reproducible from this repo.
> Research output, not financial advice.

| field | value |
| --- | --- |
| data | `data/NQ_5m.csv` · 210,516 bars @ 5m |
| range | 2022-12-26 → 2025-12-12 |
| session | 09:30–16:00 America/New_York |
| research bars / sessions | 41,026 / 537 |
| holdout bars / sessions | 17,583 / 229 |
| round-turn cost | 3.80 ticks ($19.00) |

## 1. Baseline — the published geometry, untouched

25% retracement entry, 60% stop, 50% target, all as fractions of the first hour's range, both sides, every session. No filtering, no tuning. This is the number every improvement below has to beat.

| metric | value |
| --- | --- |
| trades | 366 |
| fill rate | 68% of sessions |
| unfilled limit orders | 150 |
| win rate | 36.3% |
| gross edge | -0.89 ticks |
| net edge | -4.32 ticks |
| expectancy | 0.005 R |
| profit factor | 0.956 |
| total P&L (1 contract) | -$7,907 |
| Sharpe | -0.25 |
| HAC t-stat | -0.37 (p=0.709) |
| max drawdown | 19.8% |

Exit mix: stop 209 (-$168,941) · session 68 ($23,693) · target 89 ($137,342)

## 2. Anomaly search — which sessions are worth trading?

The geometry is held fixed and the question becomes: does some observable feature of the first hour predict whether the trade works? Every feature is computable the moment the IB window closes, before the break, the entry or the outcome. The statistic is the **lift** — this bucket's mean R minus every other trade's mean R — because a bucket can look good purely because the strategy is profitable overall. "Tuesdays make money" is not a finding when every day makes money.

| feature | bucket | trades | mean R | win | lift (R) | t | p | BH q |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| weekday | Fri | 67 | 0.234 | 43% | 0.280 | 1.46 | 0.144 | 0.665 |
| weekday | Tue | 69 | 0.215 | 42% | 0.258 | 1.35 | 0.177 | 0.665 |
| first-hour close position | closed middle | 108 | 0.130 | 39% | 0.178 | 1.06 | 0.290 | 0.717 |
| IB range percentile | medium | 136 | 0.098 | 41% | 0.147 | 0.97 | 0.332 | 0.717 |
| overnight gap | gap down | 123 | 0.099 | 41% | 0.142 | 0.92 | 0.359 | 0.717 |
| IB range percentile | narrow | 138 | 0.079 | 37% | 0.118 | 0.76 | 0.450 | 0.818 |
| took prior session extreme | took prior low | 103 | 0.043 | 38% | 0.053 | 0.33 | 0.744 | 0.889 |
| range vs prior IB | expanding | 99 | 0.038 | 37% | 0.044 | 0.27 | 0.788 | 0.889 |
| overnight gap | gap up | 148 | 0.030 | 36% | 0.042 | 0.28 | 0.782 | 0.889 |
| range vs prior IB | contracting | 143 | 0.028 | 38% | 0.038 | 0.25 | 0.804 | 0.889 |
| first-hour close position | closed low third | 128 | 0.024 | 36% | 0.030 | 0.19 | 0.847 | 0.889 |
| took prior session extreme | took prior high | 149 | 0.018 | 36% | 0.021 | 0.14 | 0.889 | 0.889 |
| weekday | Thu | 77 | -0.018 | 35% | -0.029 | -0.16 | 0.870 | 0.889 |
| took prior session extreme | inside prior range | 107 | -0.018 | 36% | -0.033 | -0.20 | 0.840 | 0.889 |
| range vs prior IB | similar | 124 | -0.047 | 34% | -0.079 | -0.52 | 0.605 | 0.889 |
| first-hour close position | closed high third | 130 | -0.118 | 35% | -0.191 | -1.28 | 0.200 | 0.665 |
| weekday | Mon | 73 | -0.152 | 30% | -0.197 | -1.07 | 0.283 | 0.717 |
| overnight gap | flat open | 95 | -0.155 | 32% | -0.217 | -1.32 | 0.185 | 0.665 |
| weekday | Wed | 80 | -0.201 | 33% | -0.264 | -1.54 | 0.124 | 0.665 |
| IB range percentile | wide | 92 | -0.242 | 28% | -0.330 | -2.18 | 0.029 | 0.588 |

**No feature survives FDR control across the 20 buckets tested.** The largest raw lift is 0.280R (weekday = Fri, q=0.665), which is what testing 20 slices of a profitable strategy produces by chance.

## 3. Parameter search over the full geometry

| field | value |
| --- | --- |
| configurations evaluated | 1200 |
| best parameters | `ibMinutes=60 retrPct=10 stopPct=100 targetPct=150 minRangePct=0 maxRangePct=60 sideMode=1 breakBuffer=2` |
| in-sample Sharpe | 1.95 |
| in-sample trades | 146 |
| in-sample net edge | 71.85 ticks |
| neighbour stability | 0.90 |
| neighbours still profitable | 100% |
| surface | plateau |

Top 12 configurations in sample — note how little separates them, which is what a flat surface looks like:

| # | parameters | trades | net (ticks) | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 1 | `ibMinutes=60 retrPct=10 stopPct=100 targetPct=150 minRangePct=0 maxRangePct=60 sideMode=1 breakBuffer=2` | 146 | 71.85 | 1.775 | 1.95 |
| 2 | `ibMinutes=60 retrPct=25 stopPct=80 targetPct=75 minRangePct=0 maxRangePct=60 sideMode=1 breakBuffer=4` | 122 | 64.75 | 1.823 | 1.93 |
| 3 | `ibMinutes=60 retrPct=25 stopPct=100 targetPct=150 minRangePct=0 maxRangePct=60 sideMode=1 breakBuffer=0` | 123 | 76.87 | 1.873 | 1.93 |
| 4 | `ibMinutes=60 retrPct=10 stopPct=80 targetPct=100 minRangePct=0 maxRangePct=60 sideMode=1 breakBuffer=0` | 146 | 58.07 | 1.671 | 1.83 |
| 5 | `ibMinutes=60 retrPct=10 stopPct=80 targetPct=100 minRangePct=0 maxRangePct=60 sideMode=1 breakBuffer=2` | 146 | 58.07 | 1.671 | 1.83 |
| 6 | `ibMinutes=60 retrPct=10 stopPct=100 targetPct=150 minRangePct=0 maxRangePct=80 sideMode=1 breakBuffer=2` | 188 | 56.70 | 1.575 | 1.75 |
| 7 | `ibMinutes=60 retrPct=10 stopPct=80 targetPct=75 minRangePct=0 maxRangePct=60 sideMode=1 breakBuffer=2` | 146 | 52.39 | 1.623 | 1.75 |
| 8 | `ibMinutes=30 retrPct=50 stopPct=60 targetPct=150 minRangePct=0 maxRangePct=80 sideMode=1 breakBuffer=2` | 150 | 43.31 | 2.017 | 1.61 |
| 9 | `ibMinutes=30 retrPct=50 stopPct=60 targetPct=150 minRangePct=0 maxRangePct=80 sideMode=1 breakBuffer=0` | 152 | 42.44 | 2.003 | 1.60 |
| 10 | `ibMinutes=60 retrPct=50 stopPct=80 targetPct=75 minRangePct=0 maxRangePct=100 sideMode=1 breakBuffer=4` | 121 | 54.25 | 1.737 | 1.59 |
| 11 | `ibMinutes=60 retrPct=10 stopPct=80 targetPct=75 minRangePct=0 maxRangePct=80 sideMode=1 breakBuffer=2` | 188 | 43.57 | 1.471 | 1.55 |
| 12 | `ibMinutes=90 retrPct=25 stopPct=80 targetPct=150 minRangePct=0 maxRangePct=60 sideMode=1 breakBuffer=4` | 121 | 55.91 | 1.652 | 1.54 |

Published geometry ranks **#923** of 1200.

## 4. Walk-forward — paying for the parameter choice

| metric | walk-forward OOS |
| --- | --- |
| folds | 7 |
| trades | 131 |
| net edge | -16.94 ticks |
| profit factor | 0.827 |
| Sharpe | -0.71 |
| HAC t-stat | -0.84 (p=0.399) |
| efficiency | -0.52 |
| folds profitable | 29% |
| total P&L | -$11,097 |

OOS equity: `▄▄▃▄▄▃▄▄▅▅▄▅▇▇▇▇▆▇▇▇▆▇█▇▆▆▆▆▅▅▅▅▄▄▄▄▄▄▄▄▄▄▄▃▃▃▂▃▃▃▂▃▃▂▁▁▁▁▁▁`

Parameter stability across folds: ibMinutes 43%, retrPct 43%, stopPct 43%, targetPct 43%, minRangePct 43%, maxRangePct 43%, sideMode 57%, breakBuffer 57%

## 5. Selection bias — PBO, Deflated Sharpe, bootstrap

| statistic | value |
| --- | --- |
| configurations evaluated in total | 4000 |
| PBO | 0.567 over 252 balanced splits of 120 configurations |
| walk-forward OOS Sharpe | -0.70 |
| bootstrap 95% CI on that Sharpe | [-2.37, 0.77] |
| expected max Sharpe under the null | 2.43 |
| Deflated Sharpe | 0.000 |
| minimum track record | never at this Sharpe |

## 6. Monte Carlo on the out-of-sample trade sequence

The backtest shows one ordering of the trades that happened to occur. Reshuffling that order 20,000 times answers the question that decides whether it is tradeable with real money: how deep does the drawdown get in the unlucky-but-normal case?

| measure | reshuffled order | resampled with replacement |
| --- | --- | --- |
| median max drawdown | 35.2% | 36.6% |
| 95th percentile drawdown | 47.5% | 70.6% |
| 99th percentile drawdown | 53.6% | 85.5% |
| P(ending below start) | 100.0% | 80.0% |
| P(25% drawdown on $50k) | 97.8% | 76.9% |
| median final P&L | -$11,097 | -$11,299 |
| 5th percentile final P&L | -$11,097 | -$32,632 |
| median worst losing streak | 10 | 10 |

Reshuffling keeps the observed trades and asks about luck of ordering; resampling with replacement also asks what a different draw of trades from the same distribution would have looked like. The second is the harsher and more honest test.

## 7. Robustness of the tuned configuration

Walk-forward modal parameters: `ibMinutes=60 retrPct=10 stopPct=100 targetPct=100 minRangePct=40 maxRangePct=60 sideMode=1 breakBuffer=2`

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 413.92 | 404.94 | 395.95 | 386.97 | 377.98 | 360.01 |
| Sharpe | 1.27 | 1.24 | 1.22 | 1.19 | 1.16 | 1.11 |

Cost tolerance: **survives every cost level tested — still profitable at 3x (11.40 ticks)**.

| probe | result |
| --- | --- |
| profitable OOS sub-periods | 33% |
| worst sub-period | -$7,377 |
| best year's share of P&L | 0% |
| profitable years | 50% |
| long vs short | 97 long (-$10,618) · 34 short (-$479) |

**Gates passed 4/10.**

- PASS — >=100 out-of-sample trades (131)
- PASS — survives >=1.5x modelled costs — survives every cost level tested — still profitable at 3x (11.40 ticks)
- PASS — parameter surface is not a mined spike (plateau)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-16.94 ticks)
- FAIL — HAC t-stat > 2 (-0.84)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — PBO < 0.30 (0.57)
- FAIL — profitable in >=60% of sub-periods (33%)
- FAIL — walk-forward efficiency >=0.4 (-0.52)

## 8. Locked holdout — evaluated once

| configuration | trades | win | net (ticks) | R | PF | Sharpe | t | P&L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| published geometry | 167 | 43% | 32.06 | 0.165 | 1.253 | 1.21 | 1.06 | $26,772 |
| in-sample optimum | 80 | 55% | 30.42 | 0.068 | 1.190 | 0.65 | 0.59 | $12,170 |
| walk-forward modal | 33 | 55% | 70.05 | 0.134 | 1.401 | 0.85 | 0.83 | $11,558 |

---

Runtime 19.2s · 4000 configurations evaluated · seed 20250822.
