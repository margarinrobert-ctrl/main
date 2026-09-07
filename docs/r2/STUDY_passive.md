# Systematic scalping study — NQ (passive fills)

> Generated 2026-08-22T06:39:33.696Z · seed `20250822` · every number below is reproducible from this repo.
> Research output, not trading advice. A passed protocol is a licence to paper-trade, not to size up.

## 1. Data

| field | value |
| --- | --- |
| file | `data/NQ_5m.csv` |
| raw bars | 210,516 |
| timeframe | 5 min |
| range | 2022-12-26T23:00:00.000Z → 2025-12-12T01:50:00.000Z |
| session studied | 09:30–16:00 America/New_York |
| fill model | `passive` |
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
| vol-breakout | 1549 | -23.61 | 1% | -3.05 | -4.36 | 0.000 |
| vwap-fade | 1698 | -23.24 | 1% | -4.57 | -6.19 | 0.000 |
| ou-reversion | 2138 | -23.01 | 0% | -2.34 | -3.28 | 0.001 |
| sweep-reversal | 1185 | -14.98 | 0% | -1.88 | -2.36 | 0.018 |
| trend-pullback | 1363 | -17.58 | 0% | -2.35 | -3.28 | 0.001 |
| tod-control | 625 | -35.51 | 0% | -2.57 | -3.49 | 0.000 |

**Passed.** No strategy is significantly profitable on data with no edge in it.

Power check — inject known momentum into the simulator and confirm the pipeline detects it (costs zeroed to isolate detection):

| injected effect | trades | net edge (ticks) | Sharpe | t (HAC) |
| --- | --- | --- | --- | --- |
| momentum AR(1)=0 | 2778 | -19.55 | -5.10 | -6.34 |
| momentum AR(1)=0.15 | 2950 | -3.57 | -0.85 | -1.16 |
| momentum AR(1)=0.3 | 3124 | 15.25 | 3.57 | 4.43 |

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
| orb | 400 | 0.52 | 1964 | 3.50 | -0.22 | 33% | spike |
| vol-breakout | 400 | 1.43 | 4071 | 4.48 | 0.41 | 100% | ridge |
| vwap-fade | 400 | 0.46 | 498 | 4.38 | n/a | n/a | spike |
| ou-reversion | 400 | 1.30 | 760 | 18.15 | 0.86 | 75% | ridge |
| sweep-reversal | 400 | 0.88 | 450 | 6.12 | 0.50 | 83% | ridge |
| trend-pullback | 400 | 0.49 | 556 | 2.93 | 0.91 | 100% | plateau |
| tod-control | 20 | 0.75 | 720 | 5.32 | 0.09 | 50% | spike |

Best parameters found in sample:

| strategy | parameters |
| --- | --- |
| orb | `orMinutes=45 maxWidthAtr=99 stopAtr=1.5 rr=2 maxBars=24 buffTicks=4` |
| vol-breakout | `lookback=10 volLookback=50 minVolPct=0 stopAtr=1 rr=1.5 maxBars=40` |
| vwap-fade | `stretchAtr=2.5 maxVolPct=0.5 volLookback=50 stopAtr=1.5 rr=1.5 maxBars=16 rsiLen=5 rsiEdge=15` |
| ou-reversion | `lookback=20 entryZ=2.5 stopAtr=2 targetFrac=1 maxBars=30 minVolPct=0.3 volLookback=100` |
| sweep-reversal | `lookback=20 minPierceAtr=0.5 stopAtr=1 rr=1 maxBars=8 maxVolPct=1 volLookback=100` |
| trend-pullback | `fast=15 slow=30 rsiLen=5 resetLevel=30 stopAtr=0.75 rr=1.5 maxBars=10` |
| tod-control | `hourLocal=11 side=1 stopAtr=1 rr=1 maxBars=20` |

Total configurations evaluated in stage 4: **2420**. This number is carried into the Deflated Sharpe in stage 8.

## 5. Reality check across the candidate set

White's Reality Check and Hansen's SPA, applied to the daily P&L of each strategy's in-sample winner, stationary block bootstrap (2,000 resamples) over the cross-section so correlation between candidates is preserved. The null is "no candidate has an edge"; a high p-value means the best result is what picking the max of 7 noisy candidates looks like.

| statistic | value |
| --- | --- |
| best candidate | `vol-breakout` |
| mean daily P&L of best | $170 |
| candidates | 7 |
| observations (sessions) | 537 |
| White Reality Check p | 0.019 |
| Hansen SPA p | 0.082 |

## 6. Probability of backtest overfitting (CSCV)

For each strategy, the daily P&L of up to 120 sampled configurations is split into 10 contiguous blocks; every balanced train/test partition (252 of them) picks the in-sample winner and asks where that winner lands out of sample. PBO is the share of partitions where it falls below the median. **PBO > 0.5 means the selection procedure itself is selecting noise.**

| strategy | configs | PBO | IS→OOS slope | OOS loss rate | reading |
| --- | --- | --- | --- | --- | --- |
| orb | 120 | 0.440 | -0.801 | 68% | weak |
| vol-breakout | 120 | 0.230 | -0.556 | 13% | selection informative |
| vwap-fade | 120 | 0.194 | -0.507 | 64% | selection informative |
| ou-reversion | 120 | 0.115 | -0.920 | 35% | selection informative |
| sweep-reversal | 120 | 0.325 | -0.996 | 63% | weak |
| trend-pullback | 120 | 0.456 | -0.502 | 85% | weak |
| tod-control | 16 | 0.349 | -0.167 | 66% | weak |

## 7. Walk-forward out-of-sample

Rolling walk-forward on the research set: re-optimise on 9,120 bars (120 sessions at 76 bars/session), trade the next 3,040 bars (40 sessions) with those parameters, step forward, never look back. The stitched test windows are the first genuinely out-of-sample record in this study.

| strategy | folds | OOS trades | net (ticks) | PF | Sharpe | t (HAC) | WF efficiency | folds up | OOS P&L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| orb | 10 | 760 | -2.76 | 0.96 | -0.34 | -0.46 | -0.22 | 40% | -$10,505 |
| vol-breakout | 10 | 1494 | 3.89 | 1.06 | 0.83 | 1.16 | 0.37 | 80% | $29,039 |
| vwap-fade | 10 | 575 | -8.64 | 0.85 | -1.24 | -1.68 | -1.12 | 30% | -$24,830 |
| ou-reversion | 10 | 566 | 6.86 | 1.07 | 0.55 | 0.71 | 0.92 | 50% | $19,406 |
| sweep-reversal | 10 | 863 | -6.94 | 0.89 | -1.28 | -1.55 | 0.04 | 50% | -$29,942 |
| trend-pullback | 10 | 805 | -3.22 | 0.94 | -0.57 | -0.89 | -0.01 | 40% | -$12,953 |
| tod-control | 10 | 572 | -3.33 | 0.95 | -0.46 | -0.62 | -0.05 | 40% | -$9,526 |

`orb            ` OOS equity: `▇▇▇▇█▆▅▅▅▅▅▄▄▄▄▄▄▄▄▄▄▄▄▃▄▂▂▂▁▂▂▂▃▂▂▂▂▂▂▃▂▃▃▅▄▅▆▄▄▄▂▁▂▃▃▄▄▄▄▄`
`vol-breakout   ` OOS equity: `▂▂▂▂▂▁▁▁▂▁▁▁▂▂▂▃▂▂▂▂▁▂▁▂▂▂▂▂▂▃▃▃▄▄▅▅▅▅▇█▆▆▅▆▆▆▆▅▆▆▅▅▅▅▅▅▅▆▆▆`
`vwap-fade      ` OOS equity: `▇█▇▇▇▇▇▇▇▇▇▇▇▆▆▆▆▆▆▆▆▆▆▆▅▅▅▆▆▆▅▅▄▄▄▅▅▅▅▅▅▅▅▄▃▃▁▁▁▁▂▂▂▂▂▂▃▃▂▃`
`ou-reversion   ` OOS equity: `▅▄▄▄▄▄▄▄▄▄▄▃▃▃▃▂▃▃▃▃▂▂▂▂▂▂▁▁▂▁▁▁▁▁▂▁▂▂▂▂▂▂▂▁▂▃▄▅▅▄▅▅▆▆▆▆▇▇▇█`
`sweep-reversal ` OOS equity: `▅▅▅▅▅▅▅▆▆▇▆▆▆▆▆▆▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇█▇▆▆▆▇▇▆▆▆▆▆▆▅▅▅▅▆▆▅▄▂▁▁`
`trend-pullback ` OOS equity: `▆▇▇▇▇▇▇▇▇▇▆▇▆▆▆▅▆▆▅▅▅▅▅▅▆█▇▇▆▅▆▅▅▃▄▆▃▄▃▄▅▅▄▄▅▃▄▅▇▅▅▄▃▃▃▃▃▂▁▁`
`tod-control    ` OOS equity: `▇▇█▇▇▆▅▃▃▃▄▄▅▇▇▅▃▄▅▄▂▁▁▁▂▂▂▄▃▄▅▆▇▅▅▄▄▅▅▆▅▇▇▆▅▇▇▄▃▄▃▆▃▂▂▁▂▂▂▁`

Parameter stability across folds (share of folds choosing the modal value):

| strategy | stability by parameter |
| --- | --- |
| orb | orMinutes 30%, maxWidthAtr 70%, stopAtr 50%, rr 40%, maxBars 50%, buffTicks 60% |
| vol-breakout | lookback 40%, volLookback 60%, minVolPct 40%, stopAtr 60%, rr 60%, maxBars 50% |
| vwap-fade | stretchAtr 50%, maxVolPct 60%, volLookback 50%, stopAtr 60%, rr 90%, maxBars 50%, rsiLen 40%, rsiEdge 70% |
| ou-reversion | lookback 40%, entryZ 50%, stopAtr 60%, targetFrac 90%, maxBars 60%, minVolPct 50%, volLookback 100% |
| sweep-reversal | lookback 50%, minPierceAtr 50%, stopAtr 70%, rr 50%, maxBars 50%, maxVolPct 80%, volLookback 100% |
| trend-pullback | fast 60%, slow 60%, rsiLen 50%, resetLevel 40%, stopAtr 50%, rr 50%, maxBars 50% |
| tod-control | hourLocal 50%, side 80%, stopAtr 100%, rr 50%, maxBars 100% |

## 8. Deflated Sharpe and family-wide error control

A backtest Sharpe is the maximum of however many were looked at. The Deflated Sharpe Ratio prices that in using the actual number of configurations evaluated (**14620**) and the cross-sectional dispersion of trial Sharpes, together with the skew and fat tails of the realised daily stream. DSR is the probability the true Sharpe exceeds what the best of 14620 trials would produce by luck.

| strategy | OOS Sharpe | bootstrap 95% CI | expected max under null | DSR | min track record |
| --- | --- | --- | --- | --- | --- |
| orb | -0.33 | [-1.82, 1.26] | 1.83 | 0.003 | never |
| vol-breakout | 0.82 | [-0.47, 2.16] | 2.17 | 0.040 | never |
| vwap-fade | -1.22 | [-2.39, 0.26] | 2.94 | 0.000 | never |
| ou-reversion | 0.54 | [-0.94, 2.00] | 2.88 | 0.001 | never |
| sweep-reversal | -1.26 | [-2.77, 0.34] | 2.33 | 0.000 | never |
| trend-pullback | -0.57 | [-1.74, 0.60] | 2.19 | 0.000 | never |
| tod-control | -0.45 | [-1.89, 0.97] | 2.45 | 0.000 | never |

Multiple-testing correction over the 7 strategies carried to walk-forward:

| rank | strategy | raw p | BH q | Holm p | survives BH | survives Holm |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | vwap-fade | 0.0928 | 0.4274 | 0.6496 | no | no |
| 2 | sweep-reversal | 0.1221 | 0.4274 | 0.7326 | no | no |
| 3 | vol-breakout | 0.2471 | 0.5765 | 1.0000 | no | no |
| 4 | trend-pullback | 0.3750 | 0.6280 | 1.0000 | no | no |
| 5 | ou-reversion | 0.4793 | 0.6280 | 1.0000 | no | no |
| 6 | tod-control | 0.5383 | 0.6280 | 1.0000 | no | no |
| 7 | orb | 0.6491 | 0.6491 | 1.0000 | no | no |

## 9. Robustness of the out-of-sample record

### orb — Opening-range breakout

*Narrow opening ranges mark unresolved auctions; the first break runs the stops resting on the other side.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 1.58 | -3.27 | -8.13 | -12.98 | -17.83 | -27.54 |
| Sharpe | 0.06 | -0.12 | -0.31 | -0.49 | -0.67 | -1.03 |

Cost tolerance: **dies at 0.16x modelled costs (0.62 ticks)** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 33% |
| worst sub-period | -$13,336 |
| best year's share of P&L | 0% |
| profitable years | 50% |
| profitable hours of day | 50% |
| Monte Carlo median maxDD | 24.7% |
| Monte Carlo 95th pct maxDD | 34.3% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 47% |
| median worst losing streak | 10 |

By exit reason: session 41 ($3,879) · stop 406 (-$255,599) · target 298 ($237,598) · time 15 ($3,618)

By volatility tercile: 1-low -$550 · 2-mid -$7,724 · 3-high -$2,232

**Gates passed 2/10.**

- PASS — >=100 out-of-sample trades (760)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-2.76 ticks)
- FAIL — HAC t-stat > 2 (-0.46)
- FAIL — deflated Sharpe > 0.95 (0.003)
- FAIL — PBO < 0.30 (0.44)
- FAIL — survives >=1.5x modelled costs — dies at 0.16x modelled costs (0.62 ticks)
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (33%)
- FAIL — walk-forward efficiency >=0.4 (-0.22)

### vol-breakout — Vol-expansion Donchian break

*Intraday momentum is conditional on volatility expansion; in compression the same break mean-reverts.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 28.06 | 23.78 | 19.51 | 15.24 | 10.96 | 2.42 |
| Sharpe | 0.88 | 0.74 | 0.61 | 0.48 | 0.34 | 0.08 |

Cost tolerance: **survives every cost level tested — still profitable at 3x (11.40 ticks)** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 83% |
| worst sub-period | -$8,074 |
| best year's share of P&L | 103% |
| profitable years | 50% |
| profitable hours of day | 50% |
| Monte Carlo median maxDD | 17.5% |
| Monte Carlo 95th pct maxDD | 27.6% |
| P(losing overall) across orderings | 0% |
| P(25% drawdown) | 9% |
| median worst losing streak | 13 |

By exit reason: session 40 ($7,575) · stop 859 (-$443,244) · target 530 ($453,395) · time 65 ($11,313)

By volatility tercile: 1-low $4,981 · 2-mid -$9,589 · 3-high $33,647

**Gates passed 6/10.**

- PASS — >=100 out-of-sample trades (1494)
- PASS — positive net edge after costs (3.89 ticks)
- PASS — PBO < 0.30 (0.23)
- PASS — survives >=1.5x modelled costs — survives every cost level tested — still profitable at 3x (11.40 ticks)
- PASS — parameter surface is not a mined spike (ridge)
- PASS — profitable in >=60% of sub-periods (83%)
- FAIL — HAC t-stat > 2 (1.16)
- FAIL — deflated Sharpe > 0.95 (0.040)
- FAIL — no single year carries >60% of P&L (103%)
- FAIL — walk-forward efficiency >=0.4 (0.37)

### vwap-fade — Session-VWAP band fade

*VWAP is the institutional execution benchmark; stretches away from it are corrected by the same flow.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | -24.28 | -28.93 | -33.59 | -38.25 | -42.91 | -52.23 |
| Sharpe | -0.92 | -1.09 | -1.26 | -1.42 | -1.58 | -1.89 |

Cost tolerance: **unprofitable even with costs switched off — the rule loses on its own, not because of the cost model** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 17% |
| worst sub-period | -$14,129 |
| best year's share of P&L | 0% |
| profitable years | 0% |
| profitable hours of day | 38% |
| Monte Carlo median maxDD | 29.9% |
| Monte Carlo 95th pct maxDD | 36.2% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 99% |
| median worst losing streak | 11 |

By exit reason: session 28 ($1,418) · stop 299 (-$160,014) · target 181 ($130,836) · time 67 ($2,930)

By volatility tercile: 1-low -$5,957 · 2-mid $6,966 · 3-high -$25,839

**Gates passed 3/10.**

- PASS — >=100 out-of-sample trades (575)
- PASS — PBO < 0.30 (0.19)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-8.64 ticks)
- FAIL — HAC t-stat > 2 (-1.68)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — survives >=1.5x modelled costs — unprofitable even with costs switched off — the rule loses on its own, not because of the cost model
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (17%)
- FAIL — walk-forward efficiency >=0.4 (-1.12)

### ou-reversion — Rolling-mean reversion (VR-matched horizon)

*Variance ratios below 1 at the 10-20 bar horizon say displacement from the local mean is partly transitory; this trades that displacement back to the mean.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 75.11 | 70.40 | 65.69 | 60.99 | 56.28 | 46.86 |
| Sharpe | 1.25 | 1.17 | 1.09 | 1.01 | 0.93 | 0.77 |

Cost tolerance: **survives every cost level tested — still profitable at 3x (11.40 ticks)** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 50% |
| worst sub-period | -$14,548 |
| best year's share of P&L | 216% |
| profitable years | 50% |
| profitable hours of day | 63% |
| Monte Carlo median maxDD | 19.8% |
| Monte Carlo 95th pct maxDD | 31.1% |
| P(losing overall) across orderings | 0% |
| P(25% drawdown) | 19% |
| median worst losing streak | 11 |

By exit reason: session 39 ($1,712) · stop 293 (-$253,545) · target 150 ($206,185) · time 84 ($65,054)

By volatility tercile: 1-low -$2,742 · 2-mid $6,525 · 3-high $15,623

**Gates passed 6/10.**

- PASS — >=100 out-of-sample trades (566)
- PASS — positive net edge after costs (6.86 ticks)
- PASS — PBO < 0.30 (0.12)
- PASS — survives >=1.5x modelled costs — survives every cost level tested — still profitable at 3x (11.40 ticks)
- PASS — parameter surface is not a mined spike (ridge)
- PASS — walk-forward efficiency >=0.4 (0.92)
- FAIL — HAC t-stat > 2 (0.71)
- FAIL — deflated Sharpe > 0.95 (0.001)
- FAIL — profitable in >=60% of sub-periods (50%)
- FAIL — no single year carries >60% of P&L (216%)

### sweep-reversal — Liquidity-sweep reversal

*A pierce of a swing extreme that closes back inside is stop-run absorption, not repricing.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 13.32 | 9.34 | 5.37 | 1.39 | -2.58 | -10.53 |
| Sharpe | 0.43 | 0.30 | 0.17 | 0.04 | -0.08 | -0.33 |

Cost tolerance: **dies at 1.68x modelled costs (6.37 ticks)** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 33% |
| worst sub-period | -$25,565 |
| best year's share of P&L | 0% |
| profitable years | 50% |
| profitable hours of day | 25% |
| Monte Carlo median maxDD | 37.0% |
| Monte Carlo 95th pct maxDD | 45.4% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 100% |
| median worst losing streak | 10 |

By exit reason: session 45 ($4,363) · stop 431 (-$261,562) · target 323 ($223,498) · time 64 ($3,759)

By volatility tercile: 1-low -$2,544 · 2-mid -$18,076 · 3-high -$9,323

**Gates passed 4/10.**

- PASS — >=100 out-of-sample trades (863)
- PASS — survives >=1.5x modelled costs — dies at 1.68x modelled costs (6.37 ticks)
- PASS — parameter surface is not a mined spike (ridge)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-6.94 ticks)
- FAIL — HAC t-stat > 2 (-1.55)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — PBO < 0.30 (0.33)
- FAIL — profitable in >=60% of sub-periods (33%)
- FAIL — walk-forward efficiency >=0.4 (0.04)

### trend-pullback — EMA-stack pullback continuation

*Pullbacks inside an intraday trend are inventory rebalancing, not a change in the auction's direction.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | -5.47 | -9.82 | -14.17 | -18.53 | -22.88 | -31.59 |
| Sharpe | -0.07 | -0.13 | -0.19 | -0.25 | -0.31 | -0.42 |

Cost tolerance: **unprofitable even with costs switched off — the rule loses on its own, not because of the cost model** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 33% |
| worst sub-period | -$7,858 |
| best year's share of P&L | 0% |
| profitable years | 0% |
| profitable hours of day | 38% |
| Monte Carlo median maxDD | 24.0% |
| Monte Carlo 95th pct maxDD | 32.9% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 41% |
| median worst losing streak | 11 |

By exit reason: session 34 ($6,839) · stop 448 (-$228,287) · target 286 ($197,306) · time 37 ($11,190)

By volatility tercile: 1-low -$15,295 · 2-mid -$362 · 3-high $2,704

**Gates passed 3/10.**

- PASS — >=100 out-of-sample trades (805)
- PASS — parameter surface is not a mined spike (plateau)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-3.22 ticks)
- FAIL — HAC t-stat > 2 (-0.89)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — PBO < 0.30 (0.46)
- FAIL — survives >=1.5x modelled costs — unprofitable even with costs switched off — the rule loses on its own, not because of the cost model
- FAIL — profitable in >=60% of sub-periods (33%)
- FAIL — walk-forward efficiency >=0.4 (-0.01)

### tod-control — Time-of-day control (null benchmark)

*Deliberate null: fixed-hour entry with no predictive content, used to calibrate the rest of the pipeline.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 35.79 | 31.56 | 27.34 | 23.11 | 18.89 | 10.44 |
| Sharpe | 0.88 | 0.78 | 0.67 | 0.57 | 0.46 | 0.25 |

Cost tolerance: **survives every cost level tested — still profitable at 3x (11.40 ticks)** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 33% |
| worst sub-period | -$7,004 |
| best year's share of P&L | 0% |
| profitable years | 50% |
| profitable hours of day | 40% |
| Monte Carlo median maxDD | 21.4% |
| Monte Carlo 95th pct maxDD | 29.4% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 21% |
| median worst losing streak | 10 |

By exit reason: session 1 (-$42) · stop 318 (-$188,282) · target 247 ($176,982) · time 6 ($1,816)

By volatility tercile: 1-low -$3,435 · 2-mid -$8,720 · 3-high $2,629

**Gates passed 3/10.**

- PASS — >=100 out-of-sample trades (572)
- PASS — survives >=1.5x modelled costs — survives every cost level tested — still profitable at 3x (11.40 ticks)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-3.33 ticks)
- FAIL — HAC t-stat > 2 (-0.62)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — PBO < 0.30 (0.35)
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (33%)
- FAIL — walk-forward efficiency >=0.4 (-0.05)

## 10. Portfolio combination

Correlation of walk-forward out-of-sample daily P&L:

|  | orb | vol-breakout | vwap-fade | ou-reversion | sweep-reversal | trend-pullback |
| --- | --- | --- | --- | --- | --- | --- |
| orb | 1.00 | 0.24 | -0.24 | -0.20 | -0.13 | 0.05 |
| vol-breakout | 0.24 | 1.00 | -0.14 | -0.31 | -0.15 | 0.24 |
| vwap-fade | -0.24 | -0.14 | 1.00 | 0.14 | 0.11 | -0.18 |
| ou-reversion | -0.20 | -0.31 | 0.14 | 1.00 | 0.10 | -0.19 |
| sweep-reversal | -0.13 | -0.15 | 0.11 | 0.10 | 1.00 | 0.03 |
| trend-pullback | 0.05 | 0.24 | -0.18 | -0.19 | 0.03 | 1.00 |

| scheme | Sharpe | t (HAC) | diversification | avg pairwise r | uplift vs best single | weights |
| --- | --- | --- | --- | --- | --- | --- |
| equal | -0.94 | -1.31 | 2.76 | -0.04 | -1.77 | 17% / 17% / 17% / 17% / 17% / 17% |
| inverse-vol | -0.94 | -1.31 | 2.76 | -0.04 | -1.77 | 17% / 17% / 17% / 17% / 17% / 17% |
| risk-parity | -0.90 | -1.25 | 2.78 | -0.04 | -1.73 | 17% / 16% / 17% / 18% / 15% / 16% |
| min-variance | -1.05 | -1.54 | 2.39 | -0.04 | -1.88 | 30% / 0% / 26% / 21% / 0% / 22% |

Weights are in risk units — each stream is scaled to unit daily volatility first, so a weight is a share of risk, not of dollars.

## 11. Locked holdout — evaluated once

Parameters are frozen to the modal walk-forward choice (the value each parameter took in the most folds) and run over the held-back final 30% of the sample, which no stage above has touched. This is the only number in the study that has never influenced a decision.

| strategy | trades | win | gross (ticks) | cost (ticks) | net (ticks) | PF | Sharpe | t (HAC) | p | P&L | maxDD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| orb | 849 | 39.2% | 13.16 | 1.93 | 11.24 | 1.10 | 1.15 | 0.97 | 0.330 | $47,707 | 18.4% |
| vol-breakout | 492 | 36.4% | -21.95 | 1.80 | -23.75 | 0.79 | -2.92 | -3.12 | 0.002 | -$58,416 | 60.6% |
| vwap-fade | 285 | 39.6% | -12.83 | 1.90 | -14.73 | 0.81 | -1.60 | -1.62 | 0.105 | -$20,988 | 23.1% |
| ou-reversion | 371 | 39.6% | 7.58 | 1.96 | 5.63 | 1.04 | 0.33 | 0.35 | 0.730 | $10,436 | 31.4% |
| sweep-reversal | 267 | 44.2% | -6.87 | 1.67 | -8.53 | 0.88 | -0.95 | -0.91 | 0.362 | -$11,393 | 19.9% |
| trend-pullback | 56 | 32.1% | -7.30 | 1.82 | -9.12 | 0.87 | -0.46 | -0.53 | 0.597 | -$2,554 | 4.6% |
| tod-control | 302 | 46.4% | 9.32 | 1.67 | 7.64 | 1.07 | 0.60 | 0.50 | 0.620 | $11,542 | 25.8% |

## 12. Verdict

| strategy | gates passed | status |
| --- | --- | --- |
| orb | 2/10 | rejected |
| vol-breakout | 6/10 | rejected |
| vwap-fade | 3/10 | rejected |
| ou-reversion | 6/10 | rejected |
| sweep-reversal | 4/10 | rejected |
| trend-pullback | 3/10 | rejected |
| tod-control | 3/10 | rejected |

**No strategy cleared every gate.** On this instrument, session and cost model, the honest conclusion is that none of the tested rules demonstrates an edge that survives costs, search deflation and out-of-sample testing.

---

Runtime 149.0s · configurations evaluated 14620 · seed 20250822.
