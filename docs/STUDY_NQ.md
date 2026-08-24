# Systematic scalping study — NQ

> Generated 2026-08-22T03:13:19.045Z · seed `20250822` · every number below is reproducible from this repo.
> Research output, not trading advice. A passed protocol is a licence to paper-trade, not to size up.

## 1. Data

| field | value |
| --- | --- |
| file | `data/NQ_5m.csv` |
| raw bars | 210,516 |
| timeframe | 5 min |
| range | 2022-12-26T23:00:00.000Z → 2025-12-12T01:50:00.000Z |
| session studied | 09:30–16:00 America/New_York |
| bars in session | 58,609 |
| sessions | 924 |
| duplicate stamps | 0 |
| out of order | 0 |
| invalid OHLC | 0 |
| missing-data gaps | 3 |
| structural (session-break) gaps | 765 |
| fat-tail bars (>10 robust σ) | 1028 |
| suspect prints (>10σ and >3%) | 2 |

Audit notes:
- 2 returns beyond 10 robust sigma AND > 3% — likely bad prints, inspect before trusting
- 3 non-recurring gaps > 3 bars — genuinely missing data
- 765 gaps at recurring local times — exchange session breaks, expected

**Cost model.** 1 tick spread + 1 tick slippage per side + $4.00 commission = **3.80 ticks ($19.00) per round turn**. Every strategy below must clear that before it has an edge at all.

**Sample split.** Research set: 41,026 bars (2022-12-27 → 2025-01-24, 537 sessions). Locked holdout: 17,583 bars (2025-01-24 → 2025-12-11, 229 sessions), evaluated once in stage 11 and never used for any choice.

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

**Return autocorrelation** (within-session 5-minute bar returns). Positive = momentum, negative = reversal.

| lag | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rho | 0.0107 | -0.0047 | 0.0096 | -0.0066 | 0.0014 | -0.0089 | -0.0069 | 0.0065 |
| t | 2.14 | -0.95 | 1.93 | -1.33 | 0.28 | -1.80 | -1.38 | 1.31 |
| p | 0.032 | 0.342 | 0.053 | 0.182 | 0.781 | 0.073 | 0.166 | 0.190 |

Significant at |t| > 2: lag 1 (rho 0.0107, momentum). Note the magnitude: a rho of 0.0107 on a bar whose typical move is a few ticks is a fraction of a tick of forecast.

**Variance ratio** (Lo-MacKinlay, heteroskedasticity-robust). VR > 1 trends, VR < 1 reverts, VR = 1 is a random walk.

| q (bars) | VR | z | p | reading |
| --- | --- | --- | --- | --- |
| 2 | 0.996 | -0.49 | 0.623 | random walk |
| 3 | 0.984 | -1.32 | 0.188 | random walk |
| 5 | 0.972 | -1.66 | 0.097 | random walk |
| 10 | 0.928 | -2.81 | 0.005 | mean reversion |
| 20 | 0.918 | -2.29 | 0.022 | mean reversion |

**Time-of-day profile.** Mean signed move is where a seasonality edge would live; mean absolute move is where scalping opportunity lives.

| local time | bars | mean move (ticks) | t | mean |move| (ticks) | mean volume |
| --- | --- | --- | --- | --- | --- |
| 09:30 | 2679 | -0.544 | -0.31 | 70.25 | 11,248 |
| 10:00 | 3209 | -0.572 | -0.37 | 66.09 | 9,146 |
| 10:30 | 3210 | -1.646 | -1.20 | 55.69 | 7,345 |
| 11:00 | 3210 | 2.734 | 2.32 | 47.27 | 5,954 |
| 11:30 | 3209 | 1.814 | 1.84 | 42.29 | 5,214 |
| 12:00 | 3210 | 0.074 | 0.07 | 38.21 | 4,461 |
| 12:30 | 3210 | 0.962 | 1.00 | 37.07 | 4,074 |
| 13:00 | 3125 | 1.164 | 1.18 | 38.25 | 4,287 |
| 13:30 | 3090 | 0.450 | 0.48 | 36.43 | 4,048 |
| 14:00 | 3085 | -0.259 | -0.25 | 38.84 | 4,469 |
| 14:30 | 3084 | 0.767 | 0.77 | 37.84 | 4,466 |
| 15:00 | 3084 | -1.249 | -1.32 | 38.00 | 4,645 |
| 15:30 | 3084 | -0.664 | -0.53 | 45.40 | 6,337 |

**No time-of-day bucket survives Benjamini-Hochberg correction across the 13 buckets tested.** Any single bucket with |t| > 2 in the table above is what testing 13 buckets on noise produces.

Widest tape: **09:30** at 70.2 ticks per bar; quietest: **13:30** at 36.4. A 3.80-tick round turn is 10% of a typical bar in the quiet window and 5% in the busy one — which is why session selection matters more than entry logic.

**Event studies.** For each classic microstructure hypothesis, the average forward move in the predicted direction, in ticks.

| condition | horizon | events | long % | raw (ticks) | drift-adj (ticks) | t (HAC) | BH q | hit rate | net of cost |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| momentum after a >0.5 ATR bar | 1 | 14,343 | 52% | 1.03 | 1.02 | 1.73 | 0.323 | 49.8% | -2.78 |
| momentum after a >0.5 ATR bar | 3 | 13,837 | 51% | 1.99 | 1.97 | 1.94 | 0.259 | 50.6% | -1.83 |
| momentum after a >0.5 ATR bar | 6 | 13,197 | 52% | 0.75 | 0.70 | 0.46 | 0.797 | 50.5% | -3.10 |
| momentum after a >0.5 ATR bar | 12 | 12,035 | 52% | 5.15 | 5.00 | 2.18 | 0.247 | 50.7% | 1.20 |
| reversal after a >1 ATR bar | 1 | 3,371 | 55% | -1.15 | -1.18 | -0.83 | 0.733 | 49.8% | -4.98 |
| reversal after a >1 ATR bar | 3 | 3,202 | 55% | -2.32 | -2.40 | -0.92 | 0.733 | 49.8% | -6.20 |
| reversal after a >1 ATR bar | 6 | 3,047 | 56% | -1.48 | -1.66 | -0.42 | 0.797 | 49.7% | -5.46 |
| reversal after a >1 ATR bar | 12 | 2,774 | 56% | -14.79 | -15.25 | -2.32 | 0.247 | 49.5% | -19.05 |
| volume-surge continuation | 1 | 1,380 | 42% | 0.28 | 0.32 | 0.13 | 0.899 | 49.6% | -3.48 |
| volume-surge continuation | 3 | 1,269 | 42% | -0.96 | -0.83 | -0.18 | 0.899 | 49.8% | -4.63 |
| volume-surge continuation | 6 | 1,221 | 42% | -1.79 | -1.53 | -0.21 | 0.899 | 49.7% | -5.33 |
| volume-surge continuation | 12 | 1,154 | 42% | 10.90 | 11.50 | 1.07 | 0.717 | 49.8% | 7.70 |
| three-bar run continuation | 1 | 9,429 | 56% | 1.06 | 1.03 | 1.66 | 0.323 | 49.3% | -2.77 |
| three-bar run continuation | 3 | 9,182 | 56% | 2.24 | 2.15 | 1.52 | 0.368 | 51.0% | -1.65 |
| three-bar run continuation | 6 | 8,833 | 56% | 1.75 | 1.56 | 0.71 | 0.733 | 51.6% | -2.24 |
| three-bar run continuation | 12 | 8,087 | 56% | 7.70 | 7.21 | 2.09 | 0.247 | 51.6% | 3.41 |
| compression break | 1 | 1,168 | 54% | -1.24 | -1.26 | -0.72 | 0.733 | 48.5% | -5.06 |
| compression break | 3 | 1,133 | 55% | -1.37 | -1.44 | -0.50 | 0.797 | 49.6% | -5.24 |
| compression break | 6 | 1,092 | 55% | -2.61 | -2.77 | -0.65 | 0.733 | 51.0% | -6.57 |
| compression break | 12 | 1,008 | 55% | 5.63 | 5.20 | 0.83 | 0.733 | 50.9% | 1.40 |

The **drift-adjusted** column is the one to read. NQ roughly doubled over this sample, so any condition that fires long more often than short earns a large raw mean from exposure alone — the "long %" column shows how much of that is in play. Drift adjustment subtracts `mean(side) x mean(unconditional forward move)`, leaving only what the signal itself predicts. BH q-values control the false discovery rate across all 20 cells tested here.

| quantity | value |
| --- | --- |
| largest credible conditional edge (drift-adjusted, q <= 0.10) | 0.00 ticks |
| from | none |
| round-turn cost | 3.80 ticks |
| edge / cost | 0.00 |

**no tested condition shows a drift-adjusted edge that survives false-discovery control (q <= 0.1) — on this sample and session none of these hypotheses is distinguishable from noise, which does not prove the market is unpredictable, only that these signals do not predict it.**

## 4. In-sample parameter search

Grid search on the research set only, objective = annualised Sharpe of daily P&L, minimum 50 trades. The winner's score is NOT evidence of anything — it is the maximum of 400 draws. What matters is the shape of the surface around it, reported as the plateau verdict.

| strategy | trials | best Sharpe (IS) | trades | net (ticks) | neighbour stability | neighbour hit | surface |
| --- | --- | --- | --- | --- | --- | --- | --- |
| orb | 400 | 0.31 | 737 | 3.92 | 0.47 | 50% | ridge |
| vol-breakout | 400 | 1.07 | 718 | 14.57 | 0.68 | 100% | plateau |
| vwap-fade | 400 | 0.48 | 512 | 4.58 | n/a | n/a | spike |
| sweep-reversal | 400 | 0.71 | 462 | 4.83 | 0.29 | 67% | spike |
| trend-pullback | 400 | 0.18 | 528 | 1.27 | 0.17 | 100% | spike |
| tod-control | 20 | 0.49 | 805 | 3.96 | -0.81 | 33% | spike |

Best parameters found in sample:

| strategy | parameters |
| --- | --- |
| orb | `orMinutes=30 maxWidthAtr=2.5 stopAtr=1.5 rr=1 maxBars=48 buffTicks=2` |
| vol-breakout | `lookback=10 volLookback=100 minVolPct=0.8 stopAtr=1.5 rr=1.5 maxBars=40` |
| vwap-fade | `stretchAtr=2.5 maxVolPct=0.5 volLookback=50 stopAtr=1.5 rr=1.5 maxBars=16 rsiLen=5 rsiEdge=15` |
| sweep-reversal | `lookback=20 minPierceAtr=0.5 stopAtr=1 rr=1 maxBars=8 maxVolPct=1 volLookback=100` |
| trend-pullback | `fast=5 slow=30 rsiLen=5 resetLevel=30 stopAtr=0.75 rr=2 maxBars=10` |
| tod-control | `hourLocal=10 side=1 stopAtr=1 rr=1.5 maxBars=20` |

Total configurations evaluated in stage 4: **2020**. This number is carried into the Deflated Sharpe in stage 8.

## 5. Reality check across the candidate set

White's Reality Check and Hansen's SPA, applied to the daily P&L of each strategy's in-sample winner, stationary block bootstrap (2,000 resamples) over the cross-section so correlation between candidates is preserved. The null is "no candidate has an edge"; a high p-value means the best result is what picking the max of 6 noisy candidates looks like.

| statistic | value |
| --- | --- |
| best candidate | `vol-breakout` |
| mean daily P&L of best | $97 |
| candidates | 6 |
| observations (sessions) | 537 |
| White Reality Check p | 0.088 |
| Hansen SPA p | 0.195 |

## 6. Probability of backtest overfitting (CSCV)

For each strategy, the daily P&L of up to 120 sampled configurations is split into 10 contiguous blocks; every balanced train/test partition (252 of them) picks the in-sample winner and asks where that winner lands out of sample. PBO is the share of partitions where it falls below the median. **PBO > 0.5 means the selection procedure itself is selecting noise.**

| strategy | configs | PBO | IS→OOS slope | OOS loss rate | reading |
| --- | --- | --- | --- | --- | --- |
| orb | 120 | 0.440 | -0.829 | 81% | weak |
| vol-breakout | 120 | 0.329 | -0.899 | 35% | weak |
| vwap-fade | 120 | 0.095 | -0.558 | 64% | selection informative |
| sweep-reversal | 120 | 0.218 | -0.961 | 67% | selection informative |
| trend-pullback | 120 | 0.325 | -0.591 | 92% | weak |
| tod-control | 16 | 0.409 | -0.148 | 83% | weak |

## 7. Walk-forward out-of-sample

Rolling walk-forward on the research set: re-optimise on 9,360 bars (~120 sessions), trade the next 3,120 bars (~40 sessions) with those parameters, step forward, never look back. The stitched test windows are the first genuinely out-of-sample record in this study.

| strategy | folds | OOS trades | net (ticks) | PF | Sharpe | t (HAC) | WF efficiency | folds up | OOS P&L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| orb | 10 | 364 | -29.84 | 0.65 | -2.29 | -2.85 | -0.45 | 30% | -$54,316 |
| vol-breakout | 10 | 1203 | 3.33 | 1.05 | 0.51 | 0.70 | 0.52 | 60% | $20,043 |
| vwap-fade | 10 | 174 | -16.18 | 0.78 | -0.98 | -1.41 | -1.06 | 40% | -$14,076 |
| sweep-reversal | 10 | 559 | -3.16 | 0.96 | -0.35 | -0.40 | 0.11 | 50% | -$8,831 |
| trend-pullback | 10 | 885 | -4.20 | 0.93 | -0.68 | -0.92 | 0.08 | 50% | -$18,595 |
| tod-control | 10 | 569 | -9.51 | 0.86 | -1.29 | -1.74 | -0.57 | 30% | -$27,051 |

`orb            ` OOS equity: `▇▇█████████▇▇▇▇▇▇▇▇▆▆▇▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▄▄▃▂▂▂▁▁▁▁▁▁▁▁`
`vol-breakout   ` OOS equity: `▃▃▃▂▂▂▂▂▂▁▁▁▄▄▄▄▃▄▃▂▂▂▁▁▁▁▂▁▂▂▂▃▅▅▆▅▅▇▇▅▆▄▆▇▆▅▅▆▄▅▆▅▅▆▆▅▆▇▇█`
`vwap-fade      ` OOS equity: `▇▇▇▇████▇▇▆▇▇▇▇▇▇▇▇▇▆▆▆▅▅▆▆▆▆▆▆▄▄▄▅▅▅▅▄▄▄▄▂▂▃▂▂▁▁▂▂▂▂▃▂▂▂▂▁▁`
`sweep-reversal ` OOS equity: `▆▆▆▆▆▆▆▇█▇▆▇▇▇▇▇▇▇▇▇▆▆▆▆▆▆▆▆▆▆▆▆▆▆▇▇▇▇▇▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▅▅▄▂▁▃`
`trend-pullback ` OOS equity: `▆▆▆▆▆▆▆▇▆▆▆▆▆▆▅▆▆▆▆▆▆▆▆▆▆▅▆▅▃▄▄▄▃▄▄▅▄▅▆▆▆▅█▄▁▁▂▄▄▃▂▂▁▂▂▁▂▂▁▁`
`tod-control    ` OOS equity: `▇▇▇█▇▇▇▇▆▇▇▆▆▆▅▄▄▅▄▄▄▄▃▄▄▄▃▃▃▂▂▃▂▂▂▂▃▂▃▃▃▃▂▂▃▃▂▃▃▄▃▃▂▁▁▁▁▁▁▁`

Parameter stability across folds (share of folds choosing the modal value):

| strategy | stability by parameter |
| --- | --- |
| orb | orMinutes 30%, maxWidthAtr 40%, stopAtr 60%, rr 60%, maxBars 50%, buffTicks 60% |
| vol-breakout | lookback 60%, volLookback 40%, minVolPct 40%, stopAtr 60%, rr 50%, maxBars 50% |
| vwap-fade | stretchAtr 70%, maxVolPct 50%, volLookback 60%, stopAtr 70%, rr 90%, maxBars 60%, rsiLen 70%, rsiEdge 80% |
| sweep-reversal | lookback 50%, minPierceAtr 80%, stopAtr 50%, rr 50%, maxBars 50%, maxVolPct 50%, volLookback 100% |
| trend-pullback | fast 50%, slow 40%, rsiLen 50%, resetLevel 40%, stopAtr 50%, rr 40%, maxBars 50% |
| tod-control | hourLocal 40%, side 60%, stopAtr 100%, rr 70%, maxBars 100% |

## 8. Deflated Sharpe and family-wide error control

A backtest Sharpe is the maximum of however many were looked at. The Deflated Sharpe Ratio prices that in using the actual number of configurations evaluated (**12220**) and the cross-sectional dispersion of trial Sharpes, together with the skew and fat tails of the realised daily stream. DSR is the probability the true Sharpe exceeds what the best of 12220 trials would produce by luck.

| strategy | OOS Sharpe | bootstrap 95% CI | expected max under null | DSR | min track record |
| --- | --- | --- | --- | --- | --- |
| orb | -2.27 | [-3.44, -0.85] | 2.45 | 0.000 | never |
| vol-breakout | 0.51 | [-0.82, 1.81] | 2.70 | 0.002 | never |
| vwap-fade | -0.97 | [-2.08, 0.42] | 3.97 | 0.000 | never |
| sweep-reversal | -0.34 | [-1.97, 1.25] | 2.59 | 0.000 | never |
| trend-pullback | -0.68 | [-1.93, 0.82] | 2.49 | 0.000 | never |
| tod-control | -1.27 | [-2.72, 0.10] | 2.45 | 0.000 | never |

Multiple-testing correction over the 6 strategies carried to walk-forward:

| rank | strategy | raw p | BH q | Holm p | survives BH | survives Holm |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | orb | 0.0043 | 0.0260 | 0.0260 | yes | yes |
| 2 | tod-control | 0.0815 | 0.2445 | 0.4076 | no | no |
| 3 | vwap-fade | 0.1574 | 0.3148 | 0.6296 | no | no |
| 4 | trend-pullback | 0.3586 | 0.5379 | 1.0000 | no | no |
| 5 | vol-breakout | 0.4834 | 0.5800 | 1.0000 | no | no |
| 6 | sweep-reversal | 0.6858 | 0.6858 | 1.0000 | no | no |

## 9. Robustness of the out-of-sample record

### orb — Opening-range breakout

*Narrow opening ranges mark unresolved auctions; the first break runs the stops resting on the other side.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 0.72 | -8.78 | -18.28 | -27.78 | -37.28 | -56.28 |
| Sharpe | 0.02 | -0.29 | -0.61 | -0.93 | -1.25 | -1.87 |

Break-even cost multiple: **0.04x** (0.14 ticks vs 3.80 modelled).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 17% |
| worst sub-period | -$21,694 |
| best year's share of P&L | 0% |
| profitable years | 0% |
| profitable hours of day | 25% |
| Monte Carlo median maxDD | 56.3% |
| Monte Carlo 95th pct maxDD | 60.5% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 100% |
| median worst losing streak | 12 |

By exit reason: session 29 ($5,034) · stop 212 (-$151,253) · target 79 ($80,734) · time 44 ($11,169)

By volatility tercile: 1-low -$9 · 2-mid -$16,951 · 3-high -$37,356

**Gates passed 3/10.**

- PASS — >=100 out-of-sample trades (364)
- PASS — parameter surface is not a mined spike (ridge)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-29.84 ticks)
- FAIL — HAC t-stat > 2 (-2.85)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — PBO < 0.30 (0.44)
- FAIL — survives >=1.5x modelled costs (0.04x)
- FAIL — profitable in >=60% of sub-periods (17%)
- FAIL — walk-forward efficiency >=0.4 (-0.45)

### vol-breakout — Vol-expansion Donchian break

*Intraday momentum is conditional on volatility expansion; in compression the same break mean-reverts.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 31.36 | 21.86 | 12.36 | 2.86 | -6.64 | -25.64 |
| Sharpe | 1.14 | 0.79 | 0.45 | 0.10 | -0.24 | -0.94 |

Break-even cost multiple: **1.65x** (6.27 ticks vs 3.80 modelled).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 50% |
| worst sub-period | -$11,404 |
| best year's share of P&L | 135% |
| profitable years | 33% |
| profitable hours of day | 75% |
| Monte Carlo median maxDD | 21.3% |
| Monte Carlo 95th pct maxDD | 33.4% |
| P(losing overall) across orderings | 0% |
| P(25% drawdown) | 27% |
| median worst losing streak | 12 |

By exit reason: session 38 ($7,303) · stop 678 (-$424,407) · target 391 ($414,971) · time 96 ($22,176)

By volatility tercile: 1-low -$478 · 2-mid -$7,046 · 3-high $27,567

**Gates passed 5/10.**

- PASS — >=100 out-of-sample trades (1203)
- PASS — positive net edge after costs (3.33 ticks)
- PASS — survives >=1.5x modelled costs (1.65x)
- PASS — parameter surface is not a mined spike (plateau)
- PASS — walk-forward efficiency >=0.4 (0.52)
- FAIL — HAC t-stat > 2 (0.70)
- FAIL — deflated Sharpe > 0.95 (0.002)
- FAIL — PBO < 0.30 (0.33)
- FAIL — profitable in >=60% of sub-periods (50%)
- FAIL — no single year carries >60% of P&L (135%)

### vwap-fade — Session-VWAP band fade

*VWAP is the institutional execution benchmark; stretches away from it are corrected by the same flow.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | -101.20 | -110.70 | -120.20 | -129.70 | -139.20 | -158.20 |
| Sharpe | -0.84 | -0.91 | -0.98 | -1.04 | -1.11 | -1.23 |

Break-even cost multiple: **0.00x** (0.00 ticks vs 3.80 modelled).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 17% |
| worst sub-period | -$4,801 |
| best year's share of P&L | 0% |
| profitable years | 33% |
| profitable hours of day | 13% |
| Monte Carlo median maxDD | 18.1% |
| Monte Carlo 95th pct maxDD | 22.9% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 1% |
| median worst losing streak | 9 |

By exit reason: session 7 ($762) · stop 97 (-$61,463) · target 56 ($48,011) · time 14 (-$1,386)

By volatility tercile: 1-low -$7,038 · 2-mid $3,684 · 3-high -$10,722

**Gates passed 3/10.**

- PASS — >=100 out-of-sample trades (174)
- PASS — PBO < 0.30 (0.10)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-16.18 ticks)
- FAIL — HAC t-stat > 2 (-1.41)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — survives >=1.5x modelled costs (0.00x)
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (17%)
- FAIL — walk-forward efficiency >=0.4 (-1.06)

### sweep-reversal — Liquidity-sweep reversal

*A pierce of a swing extreme that closes back inside is stop-run absorption, not repricing.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 11.91 | 2.41 | -7.09 | -16.59 | -26.09 | -45.09 |
| Sharpe | 0.22 | 0.04 | -0.13 | -0.30 | -0.48 | -0.82 |

Break-even cost multiple: **0.63x** (2.38 ticks vs 3.80 modelled).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 33% |
| worst sub-period | -$15,731 |
| best year's share of P&L | 0% |
| profitable years | 67% |
| profitable hours of day | 25% |
| Monte Carlo median maxDD | 22.8% |
| Monte Carlo 95th pct maxDD | 32.2% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 34% |
| median worst losing streak | 9 |

By exit reason: session 42 ($3,397) · stop 262 (-$191,933) · target 201 ($175,996) · time 54 ($3,709)

By volatility tercile: 1-low -$1,486 · 2-mid -$16,515 · 3-high $9,170

**Gates passed 3/10.**

- PASS — >=100 out-of-sample trades (559)
- PASS — PBO < 0.30 (0.22)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-3.16 ticks)
- FAIL — HAC t-stat > 2 (-0.40)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — survives >=1.5x modelled costs (0.63x)
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (33%)
- FAIL — walk-forward efficiency >=0.4 (0.11)

### trend-pullback — EMA-stack pullback continuation

*Pullbacks inside an intraday trend are inventory rebalancing, not a change in the auction's direction.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | -6.75 | -16.25 | -25.75 | -35.25 | -44.75 | -63.75 |
| Sharpe | -0.09 | -0.21 | -0.32 | -0.44 | -0.56 | -0.80 |

Break-even cost multiple: **0.00x** (0.00 ticks vs 3.80 modelled).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 17% |
| worst sub-period | -$6,602 |
| best year's share of P&L | 0% |
| profitable years | 0% |
| profitable hours of day | 25% |
| Monte Carlo median maxDD | 28.7% |
| Monte Carlo 95th pct maxDD | 37.8% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 80% |
| median worst losing streak | 10 |

By exit reason: session 40 ($6,105) · stop 468 (-$259,212) · target 330 ($224,940) · time 47 ($9,572)

By volatility tercile: 1-low -$5,631 · 2-mid $425 · 3-high -$13,389

**Gates passed 2/10.**

- PASS — >=100 out-of-sample trades (885)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-4.20 ticks)
- FAIL — HAC t-stat > 2 (-0.92)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — PBO < 0.30 (0.33)
- FAIL — survives >=1.5x modelled costs (0.00x)
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (17%)
- FAIL — walk-forward efficiency >=0.4 (0.08)

### tod-control — Time-of-day control (null benchmark)

*Deliberate null: fixed-hour entry with no predictive content, used to calibrate the rest of the pipeline.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 20.70 | 11.20 | 1.70 | -7.80 | -17.30 | -36.30 |
| Sharpe | 0.63 | 0.34 | 0.05 | -0.24 | -0.53 | -1.10 |

Break-even cost multiple: **1.09x** (4.14 ticks vs 3.80 modelled).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 17% |
| worst sub-period | -$7,880 |
| best year's share of P&L | 0% |
| profitable years | 33% |
| profitable hours of day | 0% |
| Monte Carlo median maxDD | 32.6% |
| Monte Carlo 95th pct maxDD | 39.6% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 100% |
| median worst losing streak | 11 |

By exit reason: session 1 ($6) · stop 335 (-$188,940) · target 226 ($161,396) · time 7 ($487)

By volatility tercile: 1-low -$1,383 · 2-mid -$16,374 · 3-high -$9,294

**Gates passed 2/10.**

- PASS — >=100 out-of-sample trades (569)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-9.51 ticks)
- FAIL — HAC t-stat > 2 (-1.74)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — PBO < 0.30 (0.41)
- FAIL — survives >=1.5x modelled costs (1.09x)
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (17%)
- FAIL — walk-forward efficiency >=0.4 (-0.57)

## 10. Portfolio combination

Correlation of walk-forward out-of-sample daily P&L:

|  | orb | vol-breakout | vwap-fade | sweep-reversal | trend-pullback |
| --- | --- | --- | --- | --- | --- |
| orb | 1.00 | 0.18 | -0.13 | -0.09 | 0.12 |
| vol-breakout | 0.18 | 1.00 | -0.25 | -0.18 | 0.25 |
| vwap-fade | -0.13 | -0.25 | 1.00 | 0.15 | -0.05 |
| sweep-reversal | -0.09 | -0.18 | 0.15 | 1.00 | 0.00 |
| trend-pullback | 0.12 | 0.25 | -0.05 | 0.00 | 1.00 |

| scheme | Sharpe | t (HAC) | diversification | avg pairwise r | uplift vs best single | weights |
| --- | --- | --- | --- | --- | --- | --- |
| equal | -1.71 | -2.24 | 2.24 | -0.00 | -2.23 | 20% / 20% / 20% / 20% / 20% |
| inverse-vol | -1.71 | -2.24 | 2.24 | -0.00 | -2.23 | 20% / 20% / 20% / 20% / 20% |
| risk-parity | -1.71 | -2.22 | 2.27 | -0.00 | -2.23 | 19% / 20% / 22% / 21% / 17% |
| min-variance | -0.36 | -0.45 | 1.78 | -0.00 | -0.88 | 0% / 48% / 42% / 9% / 0% |

Weights are in risk units — each stream is scaled to unit daily volatility first, so a weight is a share of risk, not of dollars.

## 11. Locked holdout — evaluated once

Parameters are frozen to the modal walk-forward choice (the value each parameter took in the most folds) and run over the held-back final 30% of the sample, which no stage above has touched. This is the only number in the study that has never influenced a decision.

| strategy | trades | win | gross (ticks) | cost (ticks) | net (ticks) | PF | Sharpe | t (HAC) | p | P&L | maxDD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| orb | 761 | 36.5% | 17.42 | 3.80 | 13.62 | 1.11 | 1.22 | 1.02 | 0.310 | $51,831 | 17.4% |
| vol-breakout | 710 | 39.9% | -5.13 | 3.80 | -8.93 | 0.92 | -1.09 | -1.06 | 0.287 | -$31,690 | 40.4% |
| vwap-fade | 39 | 35.9% | -57.62 | 3.80 | -61.42 | 0.56 | -1.19 | -1.08 | 0.281 | -$11,976 | 17.9% |
| sweep-reversal | 147 | 46.9% | -9.36 | 3.80 | -13.16 | 0.87 | -0.57 | -0.69 | 0.493 | -$9,673 | 23.3% |
| trend-pullback | 130 | 37.7% | -24.12 | 3.80 | -27.92 | 0.79 | -1.15 | -1.16 | 0.247 | -$18,145 | 26.5% |
| tod-control | 277 | 37.5% | -2.14 | 3.80 | -5.94 | 0.93 | -0.60 | -0.65 | 0.516 | -$8,228 | 19.9% |

## 12. Verdict

| strategy | gates passed | status |
| --- | --- | --- |
| orb | 3/10 | rejected |
| vol-breakout | 5/10 | rejected |
| vwap-fade | 3/10 | rejected |
| sweep-reversal | 3/10 | rejected |
| trend-pullback | 2/10 | rejected |
| tod-control | 2/10 | rejected |

**No strategy cleared every gate.** On this instrument, session and cost model, the honest conclusion is that none of the tested rules demonstrates an edge that survives costs, search deflation and out-of-sample testing.

---

Runtime 82.8s · configurations evaluated 12220 · seed 20250822.
