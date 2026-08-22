# Systematic scalping study — NQ (realistic fills)

> Generated 2026-08-22T06:37:02.644Z · seed `20250822` · every number below is reproducible from this repo.
> Research output, not trading advice. A passed protocol is a licence to paper-trade, not to size up.

## 1. Data

| field | value |
| --- | --- |
| file | `data/NQ_5m.csv` |
| raw bars | 210,516 |
| timeframe | 5 min |
| range | 2022-12-26T23:00:00.000Z → 2025-12-12T01:50:00.000Z |
| session studied | 09:30–16:00 America/New_York |
| fill model | `realistic` |
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
| ou-reversion | 2471 | 7.27 | 0% | 0.75 | 1.07 | 0.287 |
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
| orb | 400 | 0.36 | 737 | 4.64 | 0.49 | 50% | ridge |
| vol-breakout | 400 | 1.10 | 718 | 15.15 | 0.70 | 100% | plateau |
| vwap-fade | 400 | 0.52 | 512 | 4.99 | n/a | n/a | spike |
| ou-reversion | 400 | 1.12 | 956 | 12.36 | 0.69 | 100% | plateau |
| sweep-reversal | 400 | 0.82 | 462 | 5.59 | 0.38 | 83% | ridge |
| trend-pullback | 400 | 0.24 | 528 | 1.74 | 0.51 | 100% | ridge |
| tod-control | 20 | 0.57 | 805 | 4.57 | -0.47 | 33% | spike |

Best parameters found in sample:

| strategy | parameters |
| --- | --- |
| orb | `orMinutes=30 maxWidthAtr=2.5 stopAtr=1.5 rr=1 maxBars=48 buffTicks=2` |
| vol-breakout | `lookback=10 volLookback=100 minVolPct=0.8 stopAtr=1.5 rr=1.5 maxBars=40` |
| vwap-fade | `stretchAtr=2.5 maxVolPct=0.5 volLookback=50 stopAtr=1.5 rr=1.5 maxBars=16 rsiLen=5 rsiEdge=15` |
| ou-reversion | `lookback=20 entryZ=2.5 stopAtr=2 targetFrac=1 maxBars=20 minVolPct=0 volLookback=100` |
| sweep-reversal | `lookback=20 minPierceAtr=0.5 stopAtr=1 rr=1 maxBars=8 maxVolPct=1 volLookback=100` |
| trend-pullback | `fast=5 slow=30 rsiLen=5 resetLevel=30 stopAtr=0.75 rr=2 maxBars=10` |
| tod-control | `hourLocal=10 side=1 stopAtr=1 rr=1.5 maxBars=20` |

Total configurations evaluated in stage 4: **2420**. This number is carried into the Deflated Sharpe in stage 8.

## 5. Reality check across the candidate set

White's Reality Check and Hansen's SPA, applied to the daily P&L of each strategy's in-sample winner, stationary block bootstrap (2,000 resamples) over the cross-section so correlation between candidates is preserved. The null is "no candidate has an edge"; a high p-value means the best result is what picking the max of 7 noisy candidates looks like.

| statistic | value |
| --- | --- |
| best candidate | `ou-reversion` |
| mean daily P&L of best | $110 |
| candidates | 7 |
| observations (sessions) | 537 |
| White Reality Check p | 0.103 |
| Hansen SPA p | 0.201 |

## 6. Probability of backtest overfitting (CSCV)

For each strategy, the daily P&L of up to 120 sampled configurations is split into 10 contiguous blocks; every balanced train/test partition (252 of them) picks the in-sample winner and asks where that winner lands out of sample. PBO is the share of partitions where it falls below the median. **PBO > 0.5 means the selection procedure itself is selecting noise.**

| strategy | configs | PBO | IS→OOS slope | OOS loss rate | reading |
| --- | --- | --- | --- | --- | --- |
| orb | 120 | 0.464 | -0.848 | 82% | weak |
| vol-breakout | 120 | 0.433 | -0.802 | 36% | weak |
| vwap-fade | 120 | 0.147 | -0.527 | 64% | selection informative |
| ou-reversion | 120 | 0.131 | -0.932 | 43% | selection informative |
| sweep-reversal | 120 | 0.234 | -1.068 | 62% | selection informative |
| trend-pullback | 120 | 0.401 | -0.588 | 91% | weak |
| tod-control | 16 | 0.440 | -0.182 | 79% | weak |

## 7. Walk-forward out-of-sample

Rolling walk-forward on the research set: re-optimise on 9,120 bars (120 sessions at 76 bars/session), trade the next 3,040 bars (40 sessions) with those parameters, step forward, never look back. The stitched test windows are the first genuinely out-of-sample record in this study.

| strategy | folds | OOS trades | net (ticks) | PF | Sharpe | t (HAC) | WF efficiency | folds up | OOS P&L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| orb | 10 | 779 | -13.71 | 0.82 | -1.71 | -2.26 | -0.58 | 30% | -$53,406 |
| vol-breakout | 10 | 1194 | 1.03 | 1.01 | 0.17 | 0.25 | 0.08 | 70% | $6,174 |
| vwap-fade | 10 | 391 | -14.18 | 0.80 | -1.47 | -1.93 | -1.17 | 20% | -$27,714 |
| ou-reversion | 10 | 581 | 6.60 | 1.07 | 0.54 | 0.69 | 0.84 | 50% | $19,169 |
| sweep-reversal | 10 | 807 | -9.21 | 0.86 | -1.56 | -1.99 | -0.28 | 40% | -$37,163 |
| trend-pullback | 10 | 830 | -2.31 | 0.96 | -0.42 | -0.61 | 0.02 | 50% | -$9,580 |
| tod-control | 10 | 570 | -5.73 | 0.92 | -0.75 | -1.01 | -0.23 | 20% | -$16,335 |

`orb            ` OOS equity: `█▇▇▇▇▇▆▆▆▆▆▆▆▆▆▅▅▅▅▅▅▅▅▅▅▄▅▄▄▅▄▅▅▅▅▅▅▅▅▅▅▅▅▅▅▅▅▄▄▄▂▁▁▁▁▁▁▁▁▁`
`vol-breakout   ` OOS equity: `▅▅▅▄▄▄▅▄▅▄▂▃▃▄▃▃▃▃▄▄▂▂▂▁▁▁▁▁▁▃▃▁▃▂▆▇▅▆█▇▇▇▆▇▇▇▇▅▆▆▄▃▂▂▂▃▃▃▄▆`
`vwap-fade      ` OOS equity: `▇█▇▇▇▇▇▇▇▇▇▇▇▆▆▆▆▆▆▆▆▅▅▅▅▅▅▅▅▅▅▅▄▄▄▅▅▅▅▅▄▄▄▄▃▃▁▁▁▁▂▂▂▂▂▂▃▂▂▃`
`ou-reversion   ` OOS equity: `▅▅▄▅▄▄▅▅▄▄▄▄▃▃▃▃▃▃▃▃▂▂▂▂▂▂▁▁▂▁▁▁▁▁▂▁▂▂▂▂▂▂▂▁▁▃▄▅▄▄▄▅▆▅▆▆▆▇▇█`
`sweep-reversal ` OOS equity: `▆▆▆▆▆▆▆▇▇▇▆▆▆▇▇▇▇▇█▇▇▇▇▇▇▇▇▇▇▆▆▆▆▆▆▆▆▇▇▇▆▆▆▆▅▆▅▅▅▅▄▅▅▅▅▅▃▂▁▁`
`trend-pullback ` OOS equity: `▇█▇▇▇▇▇▇▇▇▆▆▆▆▅▅▆▅▅▅▄▅▅▄▅▇▆▇▆▃▄▄▄▁▄▆▃▄▃▄▅▅▄▃▄▁▃▃▆▄▃▂▁▁▁▁▂▁▂▃`
`tod-control    ` OOS equity: `▇▇▇▇▇▆▆▅▅▅▅▅▆█▇▆▅▅▆▇▇▆▆▅▆▆▅▅▅▅▅▆▆▅▅▅▅▅▆▆▅▆▆▆▆▇▇▅▄▅▄▆▄▃▃▁▁▁▁▁`

Parameter stability across folds (share of folds choosing the modal value):

| strategy | stability by parameter |
| --- | --- |
| orb | orMinutes 30%, maxWidthAtr 50%, stopAtr 50%, rr 60%, maxBars 50%, buffTicks 60% |
| vol-breakout | lookback 50%, volLookback 40%, minVolPct 40%, stopAtr 70%, rr 80%, maxBars 50% |
| vwap-fade | stretchAtr 60%, maxVolPct 50%, volLookback 60%, stopAtr 70%, rr 90%, maxBars 60%, rsiLen 40%, rsiEdge 90% |
| ou-reversion | lookback 40%, entryZ 50%, stopAtr 60%, targetFrac 90%, maxBars 60%, minVolPct 50%, volLookback 100% |
| sweep-reversal | lookback 60%, minPierceAtr 60%, stopAtr 60%, rr 60%, maxBars 60%, maxVolPct 70%, volLookback 100% |
| trend-pullback | fast 60%, slow 60%, rsiLen 40%, resetLevel 40%, stopAtr 50%, rr 50%, maxBars 50% |
| tod-control | hourLocal 50%, side 70%, stopAtr 100%, rr 80%, maxBars 100% |

## 8. Deflated Sharpe and family-wide error control

A backtest Sharpe is the maximum of however many were looked at. The Deflated Sharpe Ratio prices that in using the actual number of configurations evaluated (**14620**) and the cross-sectional dispersion of trial Sharpes, together with the skew and fat tails of the realised daily stream. DSR is the probability the true Sharpe exceeds what the best of 14620 trials would produce by luck.

| strategy | OOS Sharpe | bootstrap 95% CI | expected max under null | DSR | min track record |
| --- | --- | --- | --- | --- | --- |
| orb | -1.69 | [-3.10, -0.28] | 2.13 | 0.000 | never |
| vol-breakout | 0.16 | [-1.09, 1.34] | 2.42 | 0.002 | never |
| vwap-fade | -1.46 | [-2.63, 0.13] | 3.55 | 0.000 | never |
| ou-reversion | 0.53 | [-1.02, 1.99] | 3.10 | 0.000 | never |
| sweep-reversal | -1.55 | [-2.97, -0.10] | 2.44 | 0.000 | never |
| trend-pullback | -0.41 | [-1.60, 0.85] | 2.35 | 0.000 | never |
| tod-control | -0.74 | [-2.16, 0.68] | 2.38 | 0.000 | never |

Multiple-testing correction over the 7 strategies carried to walk-forward:

| rank | strategy | raw p | BH q | Holm p | survives BH | survives Holm |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | orb | 0.0241 | 0.1250 | 0.1684 | no | no |
| 2 | sweep-reversal | 0.0469 | 0.1250 | 0.2814 | no | no |
| 3 | vwap-fade | 0.0536 | 0.1250 | 0.2814 | no | no |
| 4 | tod-control | 0.3145 | 0.5504 | 1.0000 | no | no |
| 5 | ou-reversion | 0.4920 | 0.6312 | 1.0000 | no | no |
| 6 | trend-pullback | 0.5410 | 0.6312 | 1.0000 | no | no |
| 7 | vol-breakout | 0.8028 | 0.8028 | 1.0000 | no | no |

## 9. Robustness of the out-of-sample record

### orb — Opening-range breakout

*Narrow opening ranges mark unresolved auctions; the first break runs the stops resting on the other side.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 23.95 | 15.57 | 7.18 | -1.21 | -9.60 | -26.37 |
| Sharpe | 0.24 | 0.16 | 0.07 | -0.01 | -0.10 | -0.27 |

Cost tolerance: **dies at 1.43x modelled costs (5.43 ticks)** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 17% |
| worst sub-period | -$17,818 |
| best year's share of P&L | 0% |
| profitable years | 0% |
| profitable hours of day | 38% |
| Monte Carlo median maxDD | 57.7% |
| Monte Carlo 95th pct maxDD | 65.6% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 100% |
| median worst losing streak | 12 |

By exit reason: session 54 ($4,559) · stop 443 (-$281,187) · target 242 ($210,457) · time 40 ($12,765)

By volatility tercile: 1-low -$1,842 · 2-mid -$12,177 · 3-high -$39,387

**Gates passed 3/10.**

- PASS — >=100 out-of-sample trades (779)
- PASS — parameter surface is not a mined spike (ridge)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-13.71 ticks)
- FAIL — HAC t-stat > 2 (-2.26)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — PBO < 0.30 (0.46)
- FAIL — survives >=1.5x modelled costs — dies at 1.43x modelled costs (5.43 ticks)
- FAIL — profitable in >=60% of sub-periods (17%)
- FAIL — walk-forward efficiency >=0.4 (-0.58)

### vol-breakout — Vol-expansion Donchian break

*Intraday momentum is conditional on volatility expansion; in compression the same break mean-reverts.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 32.09 | 23.77 | 15.45 | 7.13 | -1.18 | -17.82 |
| Sharpe | 1.24 | 0.92 | 0.60 | 0.28 | -0.05 | -0.69 |

Cost tolerance: **dies at 1.93x modelled costs (7.33 ticks)** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 33% |
| worst sub-period | -$6,789 |
| best year's share of P&L | 237% |
| profitable years | 50% |
| profitable hours of day | 50% |
| Monte Carlo median maxDD | 24.3% |
| Monte Carlo 95th pct maxDD | 36.0% |
| P(losing overall) across orderings | 0% |
| P(25% drawdown) | 45% |
| median worst losing streak | 13 |

By exit reason: session 36 ($7,421) · stop 697 (-$410,628) · target 348 ($376,738) · time 113 ($32,643)

By volatility tercile: 1-low $2,469 · 2-mid -$9,623 · 3-high $13,329

**Gates passed 4/10.**

- PASS — >=100 out-of-sample trades (1194)
- PASS — positive net edge after costs (1.03 ticks)
- PASS — survives >=1.5x modelled costs — dies at 1.93x modelled costs (7.33 ticks)
- PASS — parameter surface is not a mined spike (plateau)
- FAIL — HAC t-stat > 2 (0.25)
- FAIL — deflated Sharpe > 0.95 (0.002)
- FAIL — PBO < 0.30 (0.43)
- FAIL — profitable in >=60% of sub-periods (33%)
- FAIL — no single year carries >60% of P&L (237%)
- FAIL — walk-forward efficiency >=0.4 (0.08)

### vwap-fade — Session-VWAP band fade

*VWAP is the institutional execution benchmark; stretches away from it are corrected by the same flow.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | -95.00 | -103.48 | -111.95 | -120.43 | -128.91 | -145.86 |
| Sharpe | -0.39 | -0.41 | -0.44 | -0.47 | -0.49 | -0.53 |

Cost tolerance: **unprofitable even with costs switched off — the rule loses on its own, not because of the cost model** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 17% |
| worst sub-period | -$15,462 |
| best year's share of P&L | 0% |
| profitable years | 0% |
| profitable hours of day | 38% |
| Monte Carlo median maxDD | 31.5% |
| Monte Carlo 95th pct maxDD | 37.4% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 100% |
| median worst losing streak | 11 |

By exit reason: session 18 ($123) · stop 208 (-$127,417) · target 118 ($98,783) · time 47 ($797)

By volatility tercile: 1-low -$10,930 · 2-mid $5,871 · 3-high -$22,655

**Gates passed 3/10.**

- PASS — >=100 out-of-sample trades (391)
- PASS — PBO < 0.30 (0.15)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-14.18 ticks)
- FAIL — HAC t-stat > 2 (-1.93)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — survives >=1.5x modelled costs — unprofitable even with costs switched off — the rule loses on its own, not because of the cost model
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (17%)
- FAIL — walk-forward efficiency >=0.4 (-1.17)

### ou-reversion — Rolling-mean reversion (VR-matched horizon)

*Variance ratios below 1 at the 10-20 bar horizon say displacement from the local mean is partly transitory; this trades that displacement back to the mean.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 77.47 | 69.02 | 60.57 | 52.11 | 43.66 | 26.76 |
| Sharpe | 1.30 | 1.16 | 1.01 | 0.87 | 0.73 | 0.44 |

Cost tolerance: **survives every cost level tested — still profitable at 3x (11.40 ticks)** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 33% |
| worst sub-period | -$14,393 |
| best year's share of P&L | 221% |
| profitable years | 50% |
| profitable hours of day | 63% |
| Monte Carlo median maxDD | 20.1% |
| Monte Carlo 95th pct maxDD | 31.3% |
| P(losing overall) across orderings | 0% |
| P(25% drawdown) | 20% |
| median worst losing streak | 10 |

By exit reason: session 41 ($1,076) · stop 296 (-$258,189) · target 157 ($212,245) · time 87 ($64,037)

By volatility tercile: 1-low -$3,431 · 2-mid $8,874 · 3-high $13,726

**Gates passed 6/10.**

- PASS — >=100 out-of-sample trades (581)
- PASS — positive net edge after costs (6.60 ticks)
- PASS — PBO < 0.30 (0.13)
- PASS — survives >=1.5x modelled costs — survives every cost level tested — still profitable at 3x (11.40 ticks)
- PASS — parameter surface is not a mined spike (plateau)
- PASS — walk-forward efficiency >=0.4 (0.84)
- FAIL — HAC t-stat > 2 (0.69)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — profitable in >=60% of sub-periods (33%)
- FAIL — no single year carries >60% of P&L (221%)

### sweep-reversal — Liquidity-sweep reversal

*A pierce of a swing extreme that closes back inside is stop-run absorption, not repricing.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 16.22 | 8.51 | 0.80 | -6.91 | -14.61 | -30.03 |
| Sharpe | 0.53 | 0.28 | 0.03 | -0.22 | -0.47 | -0.96 |

Cost tolerance: **dies at 1.05x modelled costs (4.00 ticks)** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 33% |
| worst sub-period | -$20,021 |
| best year's share of P&L | 0% |
| profitable years | 50% |
| profitable hours of day | 38% |
| Monte Carlo median maxDD | 42.9% |
| Monte Carlo 95th pct maxDD | 50.6% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 100% |
| median worst losing streak | 10 |

By exit reason: session 45 ($3,710) · stop 397 (-$256,653) · target 298 ($214,143) · time 67 ($1,637)

By volatility tercile: 1-low $2,012 · 2-mid -$26,330 · 3-high -$12,846

**Gates passed 4/10.**

- PASS — >=100 out-of-sample trades (807)
- PASS — PBO < 0.30 (0.23)
- PASS — parameter surface is not a mined spike (ridge)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-9.21 ticks)
- FAIL — HAC t-stat > 2 (-1.99)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — survives >=1.5x modelled costs — dies at 1.05x modelled costs (4.00 ticks)
- FAIL — profitable in >=60% of sub-periods (33%)
- FAIL — walk-forward efficiency >=0.4 (-0.28)

### trend-pullback — EMA-stack pullback continuation

*Pullbacks inside an intraday trend are inventory rebalancing, not a change in the auction's direction.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 205.24 | 197.88 | 190.52 | 183.17 | 175.81 | 161.10 |
| Sharpe | 1.02 | 0.99 | 0.95 | 0.92 | 0.88 | 0.81 |

Cost tolerance: **survives every cost level tested — still profitable at 3x (11.40 ticks)** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 17% |
| worst sub-period | -$6,459 |
| best year's share of P&L | 0% |
| profitable years | 0% |
| profitable hours of day | 50% |
| Monte Carlo median maxDD | 22.3% |
| Monte Carlo 95th pct maxDD | 30.6% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 28% |
| median worst losing streak | 11 |

By exit reason: session 38 ($7,088) · stop 455 (-$233,600) · target 298 ($204,873) · time 39 ($12,059)

By volatility tercile: 1-low -$12,623 · 2-mid $79 · 3-high $2,964

**Gates passed 4/10.**

- PASS — >=100 out-of-sample trades (830)
- PASS — survives >=1.5x modelled costs — survives every cost level tested — still profitable at 3x (11.40 ticks)
- PASS — parameter surface is not a mined spike (ridge)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-2.31 ticks)
- FAIL — HAC t-stat > 2 (-0.61)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — PBO < 0.30 (0.40)
- FAIL — profitable in >=60% of sub-periods (17%)
- FAIL — walk-forward efficiency >=0.4 (0.02)

### tod-control — Time-of-day control (null benchmark)

*Deliberate null: fixed-hour entry with no predictive content, used to calibrate the rest of the pipeline.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 38.78 | 30.81 | 22.84 | 14.87 | 6.91 | -9.03 |
| Sharpe | 0.97 | 0.77 | 0.57 | 0.37 | 0.17 | -0.22 |

Cost tolerance: **dies at 2.43x modelled costs (9.25 ticks)** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 33% |
| worst sub-period | -$13,190 |
| best year's share of P&L | 0% |
| profitable years | 0% |
| profitable hours of day | 20% |
| Monte Carlo median maxDD | 25.8% |
| Monte Carlo 95th pct maxDD | 33.9% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 56% |
| median worst losing streak | 10 |

By exit reason: session 1 (-$49) · stop 330 (-$196,615) · target 228 ($177,568) · time 11 ($2,761)

By volatility tercile: 1-low -$843 · 2-mid -$12,037 · 3-high -$3,456

**Gates passed 3/10.**

- PASS — >=100 out-of-sample trades (570)
- PASS — survives >=1.5x modelled costs — dies at 2.43x modelled costs (9.25 ticks)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-5.73 ticks)
- FAIL — HAC t-stat > 2 (-1.01)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — PBO < 0.30 (0.44)
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (33%)
- FAIL — walk-forward efficiency >=0.4 (-0.23)

## 10. Portfolio combination

Correlation of walk-forward out-of-sample daily P&L:

|  | orb | vol-breakout | vwap-fade | ou-reversion | sweep-reversal | trend-pullback |
| --- | --- | --- | --- | --- | --- | --- |
| orb | 1.00 | 0.29 | -0.09 | -0.18 | -0.20 | -0.04 |
| vol-breakout | 0.29 | 1.00 | -0.16 | -0.37 | -0.27 | 0.26 |
| vwap-fade | -0.09 | -0.16 | 1.00 | 0.15 | 0.10 | -0.12 |
| ou-reversion | -0.18 | -0.37 | 0.15 | 1.00 | 0.09 | -0.17 |
| sweep-reversal | -0.20 | -0.27 | 0.10 | 0.09 | 1.00 | 0.02 |
| trend-pullback | -0.04 | 0.26 | -0.12 | -0.17 | 0.02 | 1.00 |

| scheme | Sharpe | t (HAC) | diversification | avg pairwise r | uplift vs best single | weights |
| --- | --- | --- | --- | --- | --- | --- |
| equal | -2.09 | -3.00 | 2.79 | -0.05 | -2.62 | 17% / 17% / 17% / 17% / 17% / 17% |
| inverse-vol | -2.09 | -3.00 | 2.79 | -0.05 | -2.62 | 17% / 17% / 17% / 17% / 17% / 17% |
| risk-parity | -2.02 | -2.91 | 2.82 | -0.05 | -2.55 | 17% / 17% / 16% / 19% / 17% / 15% |
| min-variance | -0.16 | -0.21 | 2.19 | -0.05 | -0.70 | 0% / 44% / 0% / 35% / 21% / 0% |

Weights are in risk units — each stream is scaled to unit daily volatility first, so a weight is a share of risk, not of dollars.

## 11. Locked holdout — evaluated once

Parameters are frozen to the modal walk-forward choice (the value each parameter took in the most folds) and run over the held-back final 30% of the sample, which no stage above has touched. This is the only number in the study that has never influenced a decision.

| strategy | trades | win | gross (ticks) | cost (ticks) | net (ticks) | PF | Sharpe | t (HAC) | p | P&L | maxDD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| orb | 113 | 38.9% | 48.23 | 3.28 | 44.95 | 1.32 | 0.94 | 0.99 | 0.322 | $25,396 | 15.1% |
| vol-breakout | 786 | 33.1% | -10.35 | 3.40 | -13.74 | 0.87 | -1.89 | -1.99 | 0.047 | -$54,004 | 57.8% |
| vwap-fade | 1 | 100.0% | 190.00 | 2.30 | 187.70 | inf | 1.05 | 1.01 | 0.312 | $939 | 0.0% |
| ou-reversion | 380 | 39.5% | 7.47 | 3.46 | 4.01 | 1.03 | 0.24 | 0.24 | 0.808 | $7,628 | 30.3% |
| sweep-reversal | 277 | 45.8% | -4.09 | 3.15 | -7.24 | 0.89 | -0.83 | -0.80 | 0.421 | -$10,033 | 18.1% |
| trend-pullback | 6 | 0.0% | -157.17 | 3.80 | -160.97 | 0.00 | -2.51 | -2.46 | 0.014 | -$4,829 | 4.8% |
| tod-control | 304 | 46.4% | 7.18 | 3.18 | 4.00 | 1.04 | 0.32 | 0.26 | 0.792 | $6,084 | 26.5% |

## 12. Verdict

| strategy | gates passed | status |
| --- | --- | --- |
| orb | 3/10 | rejected |
| vol-breakout | 4/10 | rejected |
| vwap-fade | 3/10 | rejected |
| ou-reversion | 6/10 | rejected |
| sweep-reversal | 4/10 | rejected |
| trend-pullback | 4/10 | rejected |
| tod-control | 3/10 | rejected |

**No strategy cleared every gate.** On this instrument, session and cost model, the honest conclusion is that none of the tested rules demonstrates an edge that survives costs, search deflation and out-of-sample testing.

---

Runtime 150.1s · configurations evaluated 14620 · seed 20250822.
