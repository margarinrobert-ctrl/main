# Systematic scalping study — NQ

> Generated 2026-08-22T03:19:49.869Z · seed `20250822` · every number below is reproducible from this repo.
> Research output, not trading advice. A passed protocol is a licence to paper-trade, not to size up.

## 1. Data

| field | value |
| --- | --- |
| file | `data/NQ_1m.csv` |
| raw bars | 1,048,575 |
| timeframe | 1 min |
| range | 2022-12-26T23:01:00.000Z → 2025-12-12T01:52:00.000Z |
| session studied | 09:30–16:00 America/New_York |
| bars in session | 292,908 |
| sessions | 924 |
| duplicate stamps | 0 |
| out of order | 0 |
| invalid OHLC | 0 |
| missing-data gaps | 12 |
| structural (session-break) gaps | 763 |
| fat-tail bars (>10 robust σ) | 4769 |
| suspect prints (>10σ and >3%) | 0 |

Audit notes:
- 12 non-recurring gaps > 3 bars — genuinely missing data
- 763 gaps at recurring local times — exchange session breaks, expected

**Cost model.** 1 tick spread + 1 tick slippage per side + $4.00 commission = **3.80 ticks ($19.00) per round turn**. Every strategy below must clear that before it has an edge at all.

**Sample split.** Research set: 205,035 bars (2022-12-27 → 2025-01-24, 537 sessions). Locked holdout: 87,873 bars (2025-01-24 → 2025-12-11, 229 sessions), evaluated once in stage 11 and never used for any choice.

## 2. Engine validity — null calibration

Before trusting any result, the machinery is run over simulated martingale bars with costs switched OFF. There is no edge in that series by construction, so a profitable, significant result here would be a bug, not an alpha. The gross-edge column also prices the engine's one deliberate pessimism: when a bar contains both the stop and the target the trade is booked as a loss, because the intrabar path is unknown. The "ambiguous bars" column is how often that rule fired, and the negative gross edge next to it is what that costs. Real results are conservative by roughly that much.

| strategy | trades | gross edge (ticks) | ambiguous bars | Sharpe | t (HAC) | p |
| --- | --- | --- | --- | --- | --- | --- |
| orb | 0 | 0.00 | 0% | 0.00 | 0.00 | 1.000 |
| vol-breakout | 1691 | 5.99 | 1% | 0.77 | 1.10 | 0.273 |
| vwap-fade | 1975 | -3.72 | 1% | -0.86 | -1.17 | 0.240 |
| sweep-reversal | 1433 | 4.74 | 0% | 0.64 | 0.81 | 0.416 |
| trend-pullback | 1613 | 3.18 | 0% | 0.46 | 0.63 | 0.530 |
| tod-control | 652 | -10.72 | 0% | -0.78 | -1.04 | 0.300 |

**Passed.** No strategy is significantly profitable on data with no edge in it.

Power check — inject known momentum into the simulator and confirm the pipeline detects it (costs zeroed to isolate detection):

| injected effect | trades | net edge (ticks) | Sharpe | t (HAC) |
| --- | --- | --- | --- | --- |
| momentum AR(1)=0 | 3035 | 2.63 | 0.69 | 0.83 |
| momentum AR(1)=0.15 | 3317 | 22.40 | 5.55 | 6.97 |
| momentum AR(1)=0.3 | 3665 | 49.88 | 11.46 | 13.83 |

## 3. Alpha discovery — is there anything to trade?

A strategy backtest confounds two questions: does this market contain exploitable structure, and does this particular rule capture it? This stage answers the first one on its own, on the research set only, with no stops, targets or position management that could manufacture or mask an effect. Everything is measured in TICKS, against the 3.80-tick round turn, because that comparison decides the whole question.

**Return autocorrelation** (within-session 1-minute bar returns). Positive = momentum, negative = reversal.

| lag | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rho | 0.0044 | -0.0052 | 0.0010 | 0.0120 | -0.0048 | -0.0056 | -0.0004 | -0.0021 |
| t | 1.98 | -2.33 | 0.46 | 5.41 | -2.19 | -2.53 | -0.16 | -0.93 |
| p | 0.048 | 0.020 | 0.648 | 0.000 | 0.029 | 0.011 | 0.869 | 0.354 |

Significant at |t| > 2: lag 2 (rho -0.0052, reversal), lag 4 (rho 0.0120, momentum), lag 5 (rho -0.0048, reversal), lag 6 (rho -0.0056, reversal). Note the magnitude: a rho of 0.0052 on a bar whose typical move is a few ticks is a fraction of a tick of forecast.

**Variance ratio** (Lo-MacKinlay, heteroskedasticity-robust). VR > 1 trends, VR < 1 reverts, VR = 1 is a random walk.

| q (bars) | VR | z | p | reading |
| --- | --- | --- | --- | --- |
| 2 | 1.000 | 0.02 | 0.984 | random walk |
| 3 | 0.994 | -1.02 | 0.309 | random walk |
| 5 | 0.992 | -1.03 | 0.302 | random walk |
| 10 | 0.973 | -2.26 | 0.024 | mean reversion |
| 20 | 0.949 | -2.98 | 0.003 | mean reversion |

**Time-of-day profile.** Mean signed move is where a seasonality edge would live; mean absolute move is where scalping opportunity lives.

| local time | bars | mean move (ticks) | t | mean |move| (ticks) | mean volume |
| --- | --- | --- | --- | --- | --- |
| 09:30 | 15542 | -0.021 | -0.06 | 33.69 | 2,480 |
| 10:00 | 16045 | -0.115 | -0.37 | 29.02 | 1,829 |
| 10:30 | 16043 | -0.329 | -1.20 | 24.76 | 1,470 |
| 11:00 | 16050 | 0.547 | 2.38 | 21.24 | 1,191 |
| 11:30 | 16045 | 0.363 | 1.79 | 19.02 | 1,043 |
| 12:00 | 16047 | 0.015 | 0.08 | 17.61 | 892 |
| 12:30 | 16050 | 0.192 | 1.03 | 16.59 | 815 |
| 13:00 | 15545 | 0.234 | 1.23 | 17.42 | 862 |
| 13:30 | 15447 | 0.090 | 0.50 | 16.58 | 810 |
| 14:00 | 15424 | -0.052 | -0.26 | 18.11 | 894 |
| 14:30 | 15420 | 0.153 | 0.75 | 17.64 | 893 |
| 15:00 | 15420 | -0.250 | -1.29 | 17.87 | 929 |
| 15:30 | 15420 | -0.133 | -0.56 | 19.84 | 1,267 |

**No time-of-day bucket survives Benjamini-Hochberg correction across the 13 buckets tested.** Any single bucket with |t| > 2 in the table above is what testing 13 buckets on noise produces.

Widest tape: **09:30** at 33.7 ticks per bar; quietest: **13:30** at 16.6. A 3.80-tick round turn is 23% of a typical bar in the quiet window and 11% in the busy one — which is why session selection matters more than entry logic.

**Event studies.** For each classic microstructure hypothesis, the average forward move in the predicted direction, in ticks.

| condition | horizon | events | long % | raw (ticks) | drift-adj (ticks) | t (HAC) | BH q | hit rate | net of cost |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| momentum after a >0.5 ATR bar | 1 | 80,833 | 51% | -0.04 | -0.05 | -0.43 | 0.933 | 47.8% | -3.85 |
| momentum after a >0.5 ATR bar | 3 | 80,452 | 51% | -0.10 | -0.10 | -0.54 | 0.933 | 48.6% | -3.90 |
| momentum after a >0.5 ATR bar | 6 | 79,606 | 51% | -0.05 | -0.05 | -0.20 | 0.933 | 48.9% | -3.85 |
| momentum after a >0.5 ATR bar | 12 | 78,072 | 51% | 0.48 | 0.46 | 1.22 | 0.933 | 49.6% | -3.34 |
| reversal after a >1 ATR bar | 1 | 19,439 | 53% | -0.18 | -0.19 | -0.78 | 0.933 | 50.8% | -3.99 |
| reversal after a >1 ATR bar | 3 | 19,361 | 53% | -0.26 | -0.27 | -0.65 | 0.933 | 50.5% | -4.07 |
| reversal after a >1 ATR bar | 6 | 19,018 | 53% | -0.29 | -0.31 | -0.51 | 0.933 | 51.0% | -4.11 |
| reversal after a >1 ATR bar | 12 | 18,508 | 53% | -0.35 | -0.39 | -0.45 | 0.933 | 50.7% | -4.19 |
| volume-surge continuation | 1 | 7,928 | 45% | 0.05 | 0.06 | 0.14 | 0.933 | 48.3% | -3.74 |
| volume-surge continuation | 3 | 7,875 | 45% | 0.52 | 0.54 | 0.73 | 0.933 | 48.4% | -3.26 |
| volume-surge continuation | 6 | 7,491 | 45% | 0.52 | 0.55 | 0.51 | 0.933 | 48.5% | -3.25 |
| volume-surge continuation | 12 | 7,103 | 44% | 0.28 | 0.35 | 0.23 | 0.933 | 48.8% | -3.45 |
| three-bar run continuation | 1 | 45,950 | 53% | -0.31 | -0.32 | -2.24 | 0.496 | 47.4% | -4.12 |
| three-bar run continuation | 3 | 45,682 | 53% | 0.14 | 0.13 | 0.41 | 0.933 | 48.9% | -3.67 |
| three-bar run continuation | 6 | 45,273 | 53% | -0.02 | -0.04 | -0.08 | 0.933 | 49.0% | -3.84 |
| three-bar run continuation | 12 | 44,605 | 53% | 0.53 | 0.49 | 0.67 | 0.933 | 49.7% | -3.31 |
| compression break | 1 | 4,344 | 52% | -0.42 | -0.42 | -0.92 | 0.933 | 47.0% | -4.22 |
| compression break | 3 | 4,342 | 52% | -0.46 | -0.46 | -0.61 | 0.933 | 48.6% | -4.26 |
| compression break | 6 | 4,332 | 52% | -0.33 | -0.34 | -0.32 | 0.933 | 48.9% | -4.14 |
| compression break | 12 | 4,292 | 52% | 0.33 | 0.31 | 0.19 | 0.933 | 49.2% | -3.49 |

The **drift-adjusted** column is the one to read. NQ roughly doubled over this sample, so any condition that fires long more often than short earns a large raw mean from exposure alone — the "long %" column shows how much of that is in play. Drift adjustment subtracts `mean(side) x mean(unconditional forward move)`, leaving only what the signal itself predicts. BH q-values control the false discovery rate across all 20 cells tested here.

| quantity | value |
| --- | --- |
| largest credible conditional edge (drift-adjusted, q <= 0.10) | 0.00 ticks |
| from | none |
| round-turn cost | 3.80 ticks |
| edge / cost | 0.00 |

**no tested condition shows a drift-adjusted edge that survives false-discovery control (q <= 0.1) — on this sample and session none of these hypotheses is distinguishable from noise, which does not prove the market is unpredictable, only that these signals do not predict it.**

## 4. In-sample parameter search

Grid search on the research set only, objective = annualised Sharpe of daily P&L, minimum 50 trades. The winner's score is NOT evidence of anything — it is the maximum of 200 draws. What matters is the shape of the surface around it, reported as the plateau verdict.

| strategy | trials | best Sharpe (IS) | trades | net (ticks) | neighbour stability | neighbour hit | surface |
| --- | --- | --- | --- | --- | --- | --- | --- |
| orb | 200 | -0.04 | 55 | -1.42 | n/a | n/a | spike |
| vol-breakout | 200 | -0.36 | 2076 | -1.50 | 4.41 | 0% | spike |
| vwap-fade | 200 | -0.05 | 58 | -0.40 | n/a | n/a | spike |
| sweep-reversal | 200 | -1.57 | 1024 | -5.43 | 1.61 | 0% | spike |
| trend-pullback | 200 | 0.71 | 270 | 4.67 | n/a | n/a | spike |
| tod-control | 20 | -0.19 | 1993 | -0.41 | 9.68 | 0% | spike |

Best parameters found in sample:

| strategy | parameters |
| --- | --- |
| orb | `orMinutes=30 maxWidthAtr=1.8 stopAtr=1 rr=1 maxBars=48 buffTicks=2` |
| vol-breakout | `lookback=40 volLookback=200 minVolPct=0.8 stopAtr=1.5 rr=2 maxBars=20` |
| vwap-fade | `stretchAtr=1 maxVolPct=0.7 volLookback=50 stopAtr=0.75 rr=1.5 maxBars=16 rsiLen=14 rsiEdge=15` |
| sweep-reversal | `lookback=40 minPierceAtr=0.5 stopAtr=1.5 rr=2 maxBars=32 maxVolPct=0.7 volLookback=100` |
| trend-pullback | `fast=15 slow=50 rsiLen=9 resetLevel=30 stopAtr=1 rr=2 maxBars=10` |
| tod-control | `hourLocal=11 side=1 stopAtr=1 rr=1.5 maxBars=20` |

Total configurations evaluated in stage 4: **1020**. This number is carried into the Deflated Sharpe in stage 8.

## 5. Reality check across the candidate set

White's Reality Check and Hansen's SPA, applied to the daily P&L of each strategy's in-sample winner, stationary block bootstrap (2,000 resamples) over the cross-section so correlation between candidates is preserved. The null is "no candidate has an edge"; a high p-value means the best result is what picking the max of 6 noisy candidates looks like.

| statistic | value |
| --- | --- |
| best candidate | `trend-pullback` |
| mean daily P&L of best | $12 |
| candidates | 6 |
| observations (sessions) | 537 |
| White Reality Check p | 0.795 |
| Hansen SPA p | 0.573 |

## 6. Probability of backtest overfitting (CSCV)

For each strategy, the daily P&L of up to 120 sampled configurations is split into 10 contiguous blocks; every balanced train/test partition (252 of them) picks the in-sample winner and asks where that winner lands out of sample. PBO is the share of partitions where it falls below the median. **PBO > 0.5 means the selection procedure itself is selecting noise.**

| strategy | configs | PBO | IS→OOS slope | OOS loss rate | reading |
| --- | --- | --- | --- | --- | --- |
| orb | 98 | 0.028 | -0.580 | 74% | selection informative |
| vol-breakout | 120 | 0.000 | -0.787 | 82% | selection informative |
| vwap-fade | 120 | 0.000 | -0.618 | 100% | selection informative |
| sweep-reversal | 120 | 0.000 | -0.713 | 100% | selection informative |
| trend-pullback | 120 | 0.000 | -0.404 | 33% | selection informative |
| tod-control | 16 | 0.036 | -0.789 | 80% | selection informative |

## 7. Walk-forward out-of-sample

Rolling walk-forward on the research set: re-optimise on 45,840 bars (120 sessions at 382 bars/session), trade the next 15,280 bars (40 sessions) with those parameters, step forward, never look back. The stitched test windows are the first genuinely out-of-sample record in this study.

| strategy | folds | OOS trades | net (ticks) | PF | Sharpe | t (HAC) | WF efficiency | folds up | OOS P&L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| orb | 10 | 623 | -4.55 | 0.91 | -0.72 | -0.94 | -1.53 | 0% | -$14,162 |
| vol-breakout | 10 | 2857 | -2.42 | 0.95 | -0.96 | -1.37 | -2.50 | 40% | -$34,608 |
| vwap-fade | 10 | 243 | -9.48 | 0.71 | -2.05 | -2.86 | n/a | 30% | -$11,517 |
| sweep-reversal | 10 | 1245 | -5.95 | 0.81 | -2.55 | -3.03 | n/a | 20% | -$37,010 |
| trend-pullback | 10 | 354 | 1.04 | 1.03 | 0.19 | 0.23 | 0.44 | 50% | $1,834 |
| tod-control | 10 | 1648 | -3.58 | 0.87 | -1.80 | -2.32 | -2.61 | 20% | -$29,532 |

`orb            ` OOS equity: `▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇█▇▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▅▅▅▅▅▃▂▁▁▃`
`vol-breakout   ` OOS equity: `█▇▇▆▅▆▆▆▅▅▄▃▄▃▃▃▃▃▃▃▃▃▄▄▄▄▄▅▄▄▅▅▅▄▄▄▄▄▅▄▃▃▂▁▂▁▂▃▃▃▂▁▁▁▁▁▂▁▁▂`
`vwap-fade      ` OOS equity: `▇▇▇▇▇█▇▇▇▇▇▇▇▆▇▇▆▅▅▅▅▅▄▄▄▅▄▄▄▄▄▄▃▃▃▃▃▃▃▂▃▂▂▂▂▁▂▂▂▃▃▃▃▃▃▂▂▂▁▁`
`sweep-reversal ` OOS equity: `█▇▇▇▇▆▆▆▆▆▆▆▆▆▅▅▅▅▅▆▅▅▅▅▅▅▄▄▄▄▄▄▄▄▄▄▄▄▃▃▃▃▃▂▂▂▂▂▃▃▂▂▂▂▂▁▁▁▁▁`
`trend-pullback ` OOS equity: `▇▆▆▅▅▆▆▅▅▅▅▅▄▃▅▆▅▆▅▄▅▄▃▄▄▃▃▃▃▃▄▃▂▁▁▁▁▁▁▁▁▁▁▂▂▃▃▃▄▄▄▅▆▆▆▆▆▇▆█`
`tod-control    ` OOS equity: `▇▇▇▇▇▇▇▆▆▆▇▇▇▇█▇▇▇▇▆▆▆▅▅▅▅▄▄▄▄▄▄▄▃▃▃▃▃▃▃▃▃▃▃▂▃▃▃▂▃▂▂▂▁▁▁▁▁▁▁`

Parameter stability across folds (share of folds choosing the modal value):

| strategy | stability by parameter |
| --- | --- |
| orb | orMinutes 70%, maxWidthAtr 50%, stopAtr 50%, rr 60%, maxBars 40%, buffTicks 50% |
| vol-breakout | lookback 60%, volLookback 40%, minVolPct 50%, stopAtr 90%, rr 60%, maxBars 60% |
| vwap-fade | stretchAtr 40%, maxVolPct 80%, volLookback 60%, stopAtr 40%, rr 60%, maxBars 40%, rsiLen 90%, rsiEdge 100% |
| sweep-reversal | lookback 50%, minPierceAtr 100%, stopAtr 80%, rr 40%, maxBars 40%, maxVolPct 70%, volLookback 100% |
| trend-pullback | fast 60%, slow 50%, rsiLen 90%, resetLevel 60%, stopAtr 60%, rr 80%, maxBars 80% |
| tod-control | hourLocal 40%, side 60%, stopAtr 100%, rr 80%, maxBars 100% |

## 8. Deflated Sharpe and family-wide error control

A backtest Sharpe is the maximum of however many were looked at. The Deflated Sharpe Ratio prices that in using the actual number of configurations evaluated (**11220**) and the cross-sectional dispersion of trial Sharpes, together with the skew and fat tails of the realised daily stream. DSR is the probability the true Sharpe exceeds what the best of 11220 trials would produce by luck.

| strategy | OOS Sharpe | bootstrap 95% CI | expected max under null | DSR | min track record |
| --- | --- | --- | --- | --- | --- |
| orb | -0.71 | [-3.06, 0.67] | 16.56 | 0.000 | never |
| vol-breakout | -0.95 | [-2.45, 0.29] | 10.01 | 0.000 | never |
| vwap-fade | -2.04 | [-3.32, -0.67] | 12.51 | 0.000 | never |
| sweep-reversal | -2.52 | [-4.14, -0.98] | 8.22 | 0.000 | never |
| trend-pullback | 0.19 | [-1.37, 1.70] | 8.46 | 0.000 | never |
| tod-control | -1.78 | [-3.47, -0.24] | 6.79 | 0.000 | never |

Multiple-testing correction over the 6 strategies carried to walk-forward:

| rank | strategy | raw p | BH q | Holm p | survives BH | survives Holm |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | sweep-reversal | 0.0025 | 0.0126 | 0.0148 | yes | yes |
| 2 | vwap-fade | 0.0042 | 0.0126 | 0.0210 | yes | yes |
| 3 | tod-control | 0.0201 | 0.0402 | 0.0803 | yes | no |
| 4 | vol-breakout | 0.1700 | 0.2550 | 0.5101 | no | no |
| 5 | orb | 0.3496 | 0.4196 | 0.6993 | no | no |
| 6 | trend-pullback | 0.8161 | 0.8161 | 0.8161 | no | no |

## 9. Robustness of the out-of-sample record

### orb — Opening-range breakout

*Narrow opening ranges mark unresolved auctions; the first break runs the stops resting on the other side.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | -37.63 | -47.13 | -56.63 | -66.13 | -75.63 | -94.63 |
| Sharpe | -0.71 | -0.88 | -1.05 | -1.20 | -1.35 | -1.63 |

Break-even cost multiple: **0.00x** (0.00 ticks vs 3.80 modelled).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 17% |
| worst sub-period | -$9,221 |
| best year's share of P&L | 0% |
| profitable years | 0% |
| profitable hours of day | 13% |
| Monte Carlo median maxDD | 21.3% |
| Monte Carlo 95th pct maxDD | 28.2% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 18% |
| median worst losing streak | 14 |

By exit reason: session 26 ($4,776) · stop 405 (-$148,430) · target 177 ($125,792) · time 15 ($3,700)

By volatility tercile: 1-low -$5,093 · 2-mid -$11,080 · 3-high $2,011

**Gates passed 3/10.**

- PASS — >=100 out-of-sample trades (623)
- PASS — PBO < 0.30 (0.03)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-4.55 ticks)
- FAIL — HAC t-stat > 2 (-0.94)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — survives >=1.5x modelled costs (0.00x)
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (17%)
- FAIL — walk-forward efficiency >=0.4 (-1.53)

### vol-breakout — Vol-expansion Donchian break

*Intraday momentum is conditional on volatility expansion; in compression the same break mean-reverts.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | -9.69 | -19.19 | -28.69 | -38.19 | -47.69 | -66.69 |
| Sharpe | -0.54 | -1.07 | -1.60 | -2.14 | -2.68 | -3.76 |

Break-even cost multiple: **0.00x** (0.00 ticks vs 3.80 modelled).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 17% |
| worst sub-period | -$14,698 |
| best year's share of P&L | 0% |
| profitable years | 0% |
| profitable hours of day | 25% |
| Monte Carlo median maxDD | 45.8% |
| Monte Carlo 95th pct maxDD | 58.4% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 100% |
| median worst losing streak | 14 |

By exit reason: session 120 ($7,570) · stop 1596 (-$636,339) · target 910 ($551,625) · time 231 ($42,536)

By volatility tercile: 1-low -$2,610 · 2-mid -$31,104 · 3-high -$894

**Gates passed 3/10.**

- PASS — >=100 out-of-sample trades (2857)
- PASS — PBO < 0.30 (0.00)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-2.42 ticks)
- FAIL — HAC t-stat > 2 (-1.37)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — survives >=1.5x modelled costs (0.00x)
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (17%)
- FAIL — walk-forward efficiency >=0.4 (-2.50)

### vwap-fade — Session-VWAP band fade

*VWAP is the institutional execution benchmark; stretches away from it are corrected by the same flow.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | -4.32 | -13.82 | -23.32 | -32.82 | -42.32 | -61.32 |
| Sharpe | -0.11 | -0.35 | -0.59 | -0.82 | -1.04 | -1.46 |

Break-even cost multiple: **0.00x** (0.00 ticks vs 3.80 modelled).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 0% |
| worst sub-period | -$2,719 |
| best year's share of P&L | 0% |
| profitable years | 0% |
| profitable hours of day | 25% |
| Monte Carlo median maxDD | 12.8% |
| Monte Carlo 95th pct maxDD | 14.9% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 0% |
| median worst losing streak | 9 |

By exit reason: session 1 ($41) · stop 131 (-$37,474) · target 95 ($26,975) · time 16 (-$1,059)

By volatility tercile: 1-low -$3,442 · 2-mid -$3,717 · 3-high -$4,358

**Gates passed 3/10.**

- PASS — >=100 out-of-sample trades (243)
- PASS — PBO < 0.30 (0.00)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-9.48 ticks)
- FAIL — HAC t-stat > 2 (-2.86)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — survives >=1.5x modelled costs (0.00x)
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (0%)
- FAIL — walk-forward efficiency >=0.4 (NaN)

### sweep-reversal — Liquidity-sweep reversal

*A pierce of a swing extreme that closes back inside is stop-run absorption, not repricing.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | -8.17 | -17.67 | -27.17 | -36.67 | -46.17 | -65.17 |
| Sharpe | -0.47 | -1.02 | -1.57 | -2.11 | -2.64 | -3.69 |

Break-even cost multiple: **0.00x** (0.00 ticks vs 3.80 modelled).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 0% |
| worst sub-period | -$12,497 |
| best year's share of P&L | 0% |
| profitable years | 0% |
| profitable hours of day | 13% |
| Monte Carlo median maxDD | 39.1% |
| Monte Carlo 95th pct maxDD | 42.5% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 100% |
| median worst losing streak | 12 |

By exit reason: session 18 (-$442) · stop 669 (-$187,436) · target 395 ($140,400) · time 163 ($10,468)

By volatility tercile: 1-low -$10,091 · 2-mid -$21,074 · 3-high -$5,845

**Gates passed 3/10.**

- PASS — >=100 out-of-sample trades (1245)
- PASS — PBO < 0.30 (0.00)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-5.95 ticks)
- FAIL — HAC t-stat > 2 (-3.03)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — survives >=1.5x modelled costs (0.00x)
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (0%)
- FAIL — walk-forward efficiency >=0.4 (NaN)

### trend-pullback — EMA-stack pullback continuation

*Pullbacks inside an intraday trend are inventory rebalancing, not a change in the auction's direction.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | -7.12 | -16.62 | -26.12 | -35.62 | -45.12 | -64.12 |
| Sharpe | -0.04 | -0.10 | -0.15 | -0.21 | -0.26 | -0.37 |

Break-even cost multiple: **0.00x** (0.00 ticks vs 3.80 modelled).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 33% |
| worst sub-period | -$2,966 |
| best year's share of P&L | 363% |
| profitable years | 50% |
| profitable hours of day | 38% |
| Monte Carlo median maxDD | 6.9% |
| Monte Carlo 95th pct maxDD | 10.3% |
| P(losing overall) across orderings | 0% |
| P(25% drawdown) | 0% |
| median worst losing streak | 10 |

By exit reason: session 4 ($339) · stop 214 (-$59,336) · target 129 ($58,714) · time 7 ($2,117)

By volatility tercile: 1-low -$2,470 · 2-mid -$972 · 3-high $5,276

**Gates passed 4/10.**

- PASS — >=100 out-of-sample trades (354)
- PASS — positive net edge after costs (1.04 ticks)
- PASS — PBO < 0.30 (0.00)
- PASS — walk-forward efficiency >=0.4 (0.44)
- FAIL — HAC t-stat > 2 (0.23)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — survives >=1.5x modelled costs (0.00x)
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (33%)
- FAIL — no single year carries >60% of P&L (363%)

### tod-control — Time-of-day control (null benchmark)

*Deliberate null: fixed-hour entry with no predictive content, used to calibrate the rest of the pipeline.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 16.94 | 7.44 | -2.06 | -11.56 | -21.06 | -40.06 |
| Sharpe | 1.57 | 0.69 | -0.19 | -1.06 | -1.91 | -3.60 |

Break-even cost multiple: **0.89x** (3.39 ticks vs 3.80 modelled).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 0% |
| worst sub-period | -$10,375 |
| best year's share of P&L | 0% |
| profitable years | 0% |
| profitable hours of day | 33% |
| Monte Carlo median maxDD | 32.5% |
| Monte Carlo 95th pct maxDD | 37.0% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 100% |
| median worst losing streak | 12 |

By exit reason: stop 930 (-$233,360) · target 706 ($203,521) · time 12 ($307)

By volatility tercile: 1-low -$5,441 · 2-mid -$8,153 · 3-high -$15,938

**Gates passed 3/10.**

- PASS — >=100 out-of-sample trades (1648)
- PASS — PBO < 0.30 (0.04)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-3.58 ticks)
- FAIL — HAC t-stat > 2 (-2.32)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — survives >=1.5x modelled costs (0.89x)
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (0%)
- FAIL — walk-forward efficiency >=0.4 (-2.61)

## 10. Portfolio combination

Correlation of walk-forward out-of-sample daily P&L:

|  | orb | vol-breakout | vwap-fade | sweep-reversal | trend-pullback |
| --- | --- | --- | --- | --- | --- |
| orb | 1.00 | 0.19 | -0.13 | 0.10 | 0.01 |
| vol-breakout | 0.19 | 1.00 | -0.17 | 0.02 | 0.20 |
| vwap-fade | -0.13 | -0.17 | 1.00 | 0.03 | -0.02 |
| sweep-reversal | 0.10 | 0.02 | 0.03 | 1.00 | -0.08 |
| trend-pullback | 0.01 | 0.20 | -0.02 | -0.08 | 1.00 |

| scheme | Sharpe | t (HAC) | diversification | avg pairwise r | uplift vs best single | weights |
| --- | --- | --- | --- | --- | --- | --- |
| equal | -2.64 | -3.13 | 2.17 | 0.02 | -2.83 | 20% / 20% / 20% / 20% / 20% |
| inverse-vol | -2.64 | -3.13 | 2.17 | 0.02 | -2.83 | 20% / 20% / 20% / 20% / 20% |
| risk-parity | -2.74 | -3.23 | 2.19 | 0.02 | -2.93 | 19% / 19% / 23% / 20% / 20% |
| min-variance | -2.34 | -3.13 | 1.55 | 0.02 | -2.53 | 0% / 50% / 50% / 0% / 0% |

Weights are in risk units — each stream is scaled to unit daily volatility first, so a weight is a share of risk, not of dollars.

## 11. Locked holdout — evaluated once

Parameters are frozen to the modal walk-forward choice (the value each parameter took in the most folds) and run over the held-back final 30% of the sample, which no stage above has touched. This is the only number in the study that has never influenced a decision.

| strategy | trades | win | gross (ticks) | cost (ticks) | net (ticks) | PF | Sharpe | t (HAC) | p | P&L | maxDD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| orb | 207 | 35.3% | -4.38 | 3.80 | -8.18 | 0.92 | -0.59 | -0.58 | 0.563 | -$8,463 | 21.0% |
| vol-breakout | 999 | 38.2% | 4.48 | 3.80 | 0.68 | 1.01 | 0.12 | 0.12 | 0.903 | $3,404 | 28.7% |
| vwap-fade | 108 | 44.4% | -14.38 | 3.80 | -18.18 | 0.72 | -1.73 | -1.75 | 0.080 | -$9,817 | 11.6% |
| sweep-reversal | 477 | 36.1% | 0.63 | 3.80 | -3.17 | 0.94 | -0.65 | -0.68 | 0.495 | -$7,563 | 17.5% |
| trend-pullback | 15 | 40.0% | -26.87 | 3.80 | -30.67 | 0.60 | -0.91 | -0.93 | 0.354 | -$2,300 | 2.9% |
| tod-control | 826 | 40.4% | -0.10 | 3.80 | -3.90 | 0.91 | -1.10 | -1.33 | 0.183 | -$16,104 | 20.6% |

## 12. Verdict

| strategy | gates passed | status |
| --- | --- | --- |
| orb | 3/10 | rejected |
| vol-breakout | 3/10 | rejected |
| vwap-fade | 3/10 | rejected |
| sweep-reversal | 3/10 | rejected |
| trend-pullback | 4/10 | rejected |
| tod-control | 3/10 | rejected |

**No strategy cleared every gate.** On this instrument, session and cost model, the honest conclusion is that none of the tested rules demonstrates an edge that survives costs, search deflation and out-of-sample testing.

---

Runtime 360.2s · configurations evaluated 11220 · seed 20250822.
