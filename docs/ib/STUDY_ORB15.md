# Opening-range breakout (parameterised) — deep study (NQ)

> Generated 2026-08-22T07:23:19.582Z · seed `20250822` · fill model `realistic` · reproducible from this repo.
> Research output, not financial advice.

| field | value |
| --- | --- |
| data | `data/NQ_1m.csv` · 1,048,575 bars @ 1m |
| range | 2022-12-26 → 2025-12-12 |
| session | 09:30–16:00 America/New_York |
| opening window studied | 09:30–09:45 (15 min) |
| research bars / sessions | 205,035 / 537 |
| holdout bars / sessions | 87,873 / 229 |
| round-turn cost | 3.80 ticks ($19.00) |

## 1. Baseline — the published geometry, untouched

The strategy's published / default geometry, both sides, every session. No filtering, no tuning. This is the number every improvement below has to beat.

| metric | value |
| --- | --- |
| trades | 536 |
| fill rate | 100% of sessions |
| unfilled limit orders | 0 |
| win rate | 56.2% |
| gross edge | 8.99 ticks |
| net edge | 5.97 ticks |
| expectancy | 0.016 R |
| profit factor | 1.048 |
| total P&L (1 contract) | $16,009 |
| Sharpe | 0.33 |
| HAC t-stat | 0.56 (p=0.575) |
| max drawdown | 21.9% |

Exit mix: session 49 (-$6,551) · stop 208 (-$315,487) · target 279 ($338,047)

## 2. Anomaly search — which sessions are worth trading?

The geometry is held fixed and the question becomes: does some observable feature of the first hour predict whether the trade works? Every feature is computable the moment the IB window closes, before the break, the entry or the outcome. The statistic is the **lift** — this bucket's mean R minus every other trade's mean R — because a bucket can look good purely because the strategy is profitable overall. "Tuesdays make money" is not a finding when every day makes money.

| feature | bucket | trades | mean R | win | lift (R) | t | p | BH q |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| range vs prior IB | expanding | 161 | 0.201 | 65% | 0.265 | 3.37 | 0.001 | 0.015 |
| IB range percentile | medium | 188 | 0.112 | 61% | 0.148 | 1.89 | 0.059 | 0.368 |
| weekday | Thu | 108 | 0.122 | 62% | 0.132 | 1.42 | 0.154 | 0.496 |
| took prior session extreme | took prior high | 190 | 0.085 | 61% | 0.107 | 1.36 | 0.174 | 0.496 |
| weekday | Tue | 109 | 0.082 | 61% | 0.083 | 0.91 | 0.364 | 0.615 |
| took prior session extreme | took prior low | 120 | 0.066 | 57% | 0.065 | 0.72 | 0.469 | 0.642 |
| first-hour close position | closed high third | 207 | 0.051 | 58% | 0.056 | 0.73 | 0.468 | 0.642 |
| overnight gap | gap up | 248 | 0.035 | 58% | 0.035 | 0.46 | 0.645 | 0.753 |
| overnight gap | gap down | 198 | 0.037 | 57% | 0.033 | 0.42 | 0.673 | 0.753 |
| weekday | Fri | 107 | 0.031 | 57% | 0.019 | 0.20 | 0.839 | 0.839 |
| first-hour close position | closed low third | 164 | -0.005 | 55% | -0.030 | -0.36 | 0.715 | 0.753 |
| first-hour close position | closed middle | 165 | -0.007 | 55% | -0.033 | -0.40 | 0.686 | 0.753 |
| weekday | Wed | 107 | -0.038 | 54% | -0.068 | -0.70 | 0.481 | 0.642 |
| IB range percentile | narrow | 174 | -0.033 | 55% | -0.072 | -0.90 | 0.369 | 0.615 |
| IB range percentile | wide | 174 | -0.039 | 52% | -0.081 | -1.01 | 0.312 | 0.615 |
| range vs prior IB | contracting | 173 | -0.048 | 54% | -0.095 | -1.17 | 0.240 | 0.534 |
| overnight gap | flat open | 90 | -0.081 | 50% | -0.117 | -1.17 | 0.240 | 0.534 |
| took prior session extreme | inside prior range | 221 | -0.054 | 53% | -0.120 | -1.57 | 0.117 | 0.468 |
| range vs prior IB | similar | 202 | -0.076 | 51% | -0.148 | -1.90 | 0.057 | 0.368 |
| weekday | Mon | 105 | -0.121 | 46% | -0.171 | -1.79 | 0.074 | 0.368 |

**Survives FDR control (q ≤ 0.10): range vs prior IB = expanding (lift 0.265R).**

## 3. Parameter search over the full geometry

| field | value |
| --- | --- |
| configurations evaluated | 800 |
| best parameters | `orMinutes=15 entryMode=0 retrPct=40 stopMode=0 stopPct=30 targetPct=0 minRangePct=50 maxRangePct=75 sideMode=1 breakBuffer=0` |
| in-sample Sharpe | 1.32 |
| in-sample trades | 77 |
| in-sample net edge | 102.56 ticks |
| neighbour stability | n/a |
| neighbours still profitable | n/a |
| surface | spike |

Top 12 configurations in sample — note how little separates them, which is what a flat surface looks like:

| # | parameters | trades | net (ticks) | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 1 | `orMinutes=15 entryMode=0 retrPct=40 stopMode=0 stopPct=30 targetPct=0 minRangePct=50 maxRangePct=75 sideMode=1 breakBuffer=0` | 77 | 102.56 | 1.678 | 1.32 |
| 2 | `orMinutes=15 entryMode=0 retrPct=40 stopMode=1 stopPct=100 targetPct=0 minRangePct=25 maxRangePct=75 sideMode=1 breakBuffer=0` | 154 | 61.86 | 1.419 | 1.27 |
| 3 | `orMinutes=15 entryMode=0 retrPct=40 stopMode=0 stopPct=50 targetPct=0 minRangePct=25 maxRangePct=75 sideMode=1 breakBuffer=0` | 154 | 61.86 | 1.419 | 1.27 |
| 4 | `orMinutes=15 entryMode=0 retrPct=25 stopMode=0 stopPct=100 targetPct=0 minRangePct=25 maxRangePct=75 sideMode=1 breakBuffer=0` | 154 | 61.86 | 1.419 | 1.27 |
| 5 | `orMinutes=15 entryMode=0 retrPct=40 stopMode=0 stopPct=100 targetPct=0 minRangePct=25 maxRangePct=75 sideMode=1 breakBuffer=0` | 154 | 61.86 | 1.419 | 1.27 |
| 6 | `orMinutes=15 entryMode=0 retrPct=15 stopMode=1 stopPct=100 targetPct=0 minRangePct=50 maxRangePct=75 sideMode=1 breakBuffer=2` | 79 | 92.58 | 1.600 | 1.22 |
| 7 | `orMinutes=15 entryMode=0 retrPct=15 stopMode=1 stopPct=30 targetPct=200 minRangePct=50 maxRangePct=75 sideMode=0 breakBuffer=0` | 153 | 40.96 | 1.455 | 1.20 |
| 8 | `orMinutes=15 entryMode=1 retrPct=15 stopMode=1 stopPct=100 targetPct=0 minRangePct=25 maxRangePct=75 sideMode=1 breakBuffer=1` | 137 | 57.62 | 1.443 | 1.20 |
| 9 | `orMinutes=15 entryMode=1 retrPct=15 stopMode=0 stopPct=50 targetPct=0 minRangePct=50 maxRangePct=75 sideMode=1 breakBuffer=0` | 66 | 91.23 | 1.663 | 1.17 |
| 10 | `orMinutes=15 entryMode=0 retrPct=15 stopMode=1 stopPct=75 targetPct=0 minRangePct=50 maxRangePct=75 sideMode=1 breakBuffer=2` | 79 | 78.85 | 1.546 | 1.10 |
| 11 | `orMinutes=15 entryMode=0 retrPct=25 stopMode=0 stopPct=100 targetPct=200 minRangePct=50 maxRangePct=75 sideMode=1 breakBuffer=0` | 77 | 69.67 | 1.482 | 1.09 |
| 12 | `orMinutes=15 entryMode=1 retrPct=25 stopMode=1 stopPct=100 targetPct=0 minRangePct=0 maxRangePct=75 sideMode=1 breakBuffer=1` | 179 | 39.79 | 1.347 | 1.04 |

Published geometry ranks **#689** of 800.

## 4. Walk-forward — paying for the parameter choice

| metric | walk-forward OOS |
| --- | --- |
| folds | 7 |
| trades | 116 |
| net edge | -3.64 ticks |
| profit factor | 0.967 |
| Sharpe | -0.12 |
| HAC t-stat | -0.17 (p=0.867) |
| efficiency | 0.15 |
| folds profitable | 57% |
| total P&L | -$2,112 |

OOS equity: `▁▁▁▁▂▁▁▁▁▁▂▂▁▁▁▁▁▂▂▂▃▃▃▃▃▃▄▄▃▃▃▃▃▃▃▄▄▄▄▄▅▄▄▄▅▅█▅▅▅▄▃▂▁▁▁▁▁▁▁`

Parameter stability across folds: orMinutes 100%, entryMode 57%, retrPct 71%, stopMode 57%, stopPct 43%, targetPct 43%, minRangePct 43%, maxRangePct 43%, sideMode 57%, breakBuffer 57%

## 5. Selection bias — PBO, Deflated Sharpe, bootstrap

| statistic | value |
| --- | --- |
| configurations evaluated in total | 3600 |
| PBO | 0.829 over 252 balanced splits of 120 configurations |
| walk-forward OOS Sharpe | -0.12 |
| bootstrap 95% CI on that Sharpe | [-1.62, 1.09] |
| expected max Sharpe under the null | 1.78 |
| Deflated Sharpe | 0.013 |
| minimum track record | never at this Sharpe |

## 6. Monte Carlo on the out-of-sample trade sequence

The backtest shows one ordering of the trades that happened to occur. Reshuffling that order 20,000 times answers the question that decides whether it is tradeable with real money: how deep does the drawdown get in the unlucky-but-normal case?

| measure | reshuffled order | resampled with replacement |
| --- | --- | --- |
| median max drawdown | 28.2% | 29.4% |
| 95th percentile drawdown | 41.5% | 62.3% |
| 99th percentile drawdown | 48.6% | 79.9% |
| P(ending below start) | 100.0% | 56.5% |
| P(25% drawdown on $50k) | 70.3% | 62.0% |
| median final P&L | -$2,112 | -$2,479 |
| 5th percentile final P&L | -$2,112 | -$27,024 |
| median worst losing streak | 6 | 6 |

Reshuffling keeps the observed trades and asks about luck of ordering; resampling with replacement also asks what a different draw of trades from the same distribution would have looked like. The second is the harsher and more honest test.

## 7. Robustness of the tuned configuration

Walk-forward modal parameters: `orMinutes=15 entryMode=0 retrPct=40 stopMode=1 stopPct=75 targetPct=0 minRangePct=25 maxRangePct=75 sideMode=1 breakBuffer=1`

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 267.66 | 258.16 | 248.66 | 239.16 | 229.66 | 210.66 |
| Sharpe | 1.19 | 1.15 | 1.10 | 1.06 | 1.02 | 0.94 |

Cost tolerance: **survives every cost level tested — still profitable at 3x (11.40 ticks)**.

| probe | result |
| --- | --- |
| profitable OOS sub-periods | 83% |
| worst sub-period | -$11,567 |
| best year's share of P&L | 0% |
| profitable years | 50% |
| long vs short | 63 long (-$497) · 53 short (-$1,615) |

**Gates passed 4/10.**

- PASS — >=100 out-of-sample trades (116)
- PASS — survives >=1.5x modelled costs — survives every cost level tested — still profitable at 3x (11.40 ticks)
- PASS — profitable in >=60% of sub-periods (83%)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-3.64 ticks)
- FAIL — HAC t-stat > 2 (-0.17)
- FAIL — deflated Sharpe > 0.95 (0.013)
- FAIL — PBO < 0.30 (0.83)
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — walk-forward efficiency >=0.4 (0.15)

## 8. Locked holdout — evaluated once

| configuration | trades | win | net (ticks) | R | PF | Sharpe | t | P&L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| published geometry | 227 | 60% | 50.60 | 0.110 | 1.305 | 1.84 | 1.60 | $57,435 |
| in-sample optimum | 39 | 46% | 20.64 | 0.073 | 1.109 | 0.28 | 0.26 | $4,024 |
| walk-forward modal | 56 | 41% | 22.41 | 0.014 | 1.136 | 0.41 | 0.39 | $6,276 |

Applying the anomaly filters that survived FDR control to the holdout:

| set | trades | mean R | win | t | P&L |
| --- | --- | --- | --- | --- | --- |
| all holdout trades | 227 | 0.110 | 60% | 1.90 | $57,435 |
| filtered | 67 | 0.089 | 58% | 0.89 | $16,177 |

---

Runtime 54.9s · 3600 configurations evaluated · seed 20250822.
