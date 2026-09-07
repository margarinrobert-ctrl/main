# Systematic scalping study — NQ (open hour, passive fills)

> Generated 2026-08-22T06:42:38.157Z · seed `20250822` · every number below is reproducible from this repo.
> Research output, not trading advice. A passed protocol is a licence to paper-trade, not to size up.

## 1. Data

| field | value |
| --- | --- |
| file | `data/NQ_5m.csv` |
| raw bars | 210,516 |
| timeframe | 5 min |
| range | 2022-12-26T23:00:00.000Z → 2025-12-12T01:50:00.000Z |
| session studied | 09:30–10:30 America/New_York |
| fill model | `passive` |
| bars in session | 9,168 |
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

**Sample split.** Research set: 6,417 bars (2022-12-27 → 2025-01-23, 536 sessions). Locked holdout: 2,751 bars (2025-01-23 → 2025-12-11, 230 sessions), evaluated once in stage 11 and never used for any choice.

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
| rho | -0.0114 | 0.0107 | -0.0077 | -0.0067 | 0.0130 | -0.0384 | 0.0015 | 0.0002 |
| t | -0.88 | 0.82 | -0.59 | -0.52 | 0.99 | -2.94 | 0.11 | 0.02 |
| p | 0.380 | 0.410 | 0.553 | 0.606 | 0.320 | 0.003 | 0.911 | 0.988 |

Significant at |t| > 2: lag 6 (rho -0.0384, reversal). Note the magnitude: a rho of 0.0384 on a bar whose typical move is a few ticks is a fraction of a tick of forecast.

**Variance ratio** (Lo-MacKinlay, heteroskedasticity-robust). VR > 1 trends, VR < 1 reverts, VR = 1 is a random walk.

| q (bars) | VR | z | p | reading |
| --- | --- | --- | --- | --- |
| 2 | 0.979 | -1.30 | 0.195 | random walk |
| 3 | 0.983 | -0.72 | 0.473 | random walk |
| 5 | 0.983 | -0.47 | 0.636 | random walk |
| 10 | 0.897 | -2.01 | 0.045 | mean reversion |
| 20 | 1.000 | 0.00 | 1.000 | random walk |

**Time-of-day profile.** Mean signed move is where a seasonality edge would live; mean absolute move is where scalping opportunity lives.

| local time | bars | mean move (ticks) | t | mean |move| (ticks) | mean volume |
| --- | --- | --- | --- | --- | --- |
| 09:30 | 2675 | -0.601 | -0.34 | 70.23 | 11,250 |
| 10:00 | 3206 | -0.563 | -0.37 | 66.09 | 9,150 |

**No time-of-day bucket survives Benjamini-Hochberg correction across the 2 buckets tested.** Any single bucket with |t| > 2 in the table above is what testing 2 buckets on noise produces.

Widest tape: **09:30** at 70.2 ticks per bar; quietest: **10:00** at 66.1. A 3.80-tick round turn is 6% of a typical bar in the quiet window and 5% in the busy one — which is why session selection matters more than entry logic.

**Event studies.** For each classic microstructure hypothesis, the average forward move in the predicted direction, in ticks.

| condition | horizon | events | long % | raw (ticks) | drift-adj (ticks) | t (HAC) | BH q | hit rate | net of cost |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| momentum after a >0.5 ATR bar | 1 | 1,536 | 50% | -2.04 | -2.04 | -0.78 | 1.000 | 48.7% | -5.84 |
| momentum after a >0.5 ATR bar | 3 | 1,241 | 50% | -0.98 | -0.99 | -0.23 | 1.000 | 51.2% | -4.79 |
| momentum after a >0.5 ATR bar | 6 | 770 | 50% | -3.81 | -3.81 | -0.48 | 1.000 | 52.1% | -7.61 |
| momentum after a >0.5 ATR bar | 12 | 0 | 0% | 0.00 | 0.00 | 0.00 | 1.000 | 0.0% | -3.80 |
| reversal after a >1 ATR bar | 1 | 277 | 62% | -0.03 | 0.12 | 0.02 | 1.000 | 49.8% | -3.68 |
| reversal after a >1 ATR bar | 3 | 238 | 61% | 4.61 | 4.78 | 0.42 | 1.000 | 46.6% | 0.98 |
| reversal after a >1 ATR bar | 6 | 138 | 59% | 5.92 | 6.21 | 0.26 | 1.000 | 48.6% | 2.41 |
| reversal after a >1 ATR bar | 12 | 0 | 0% | 0.00 | 0.00 | 0.00 | 1.000 | 0.0% | -3.80 |
| volume-surge continuation | 1 | 77 | 22% | -0.38 | -0.70 | -0.07 | 1.000 | 46.8% | -4.50 |
| volume-surge continuation | 3 | 75 | 23% | 0.85 | 0.43 | 0.03 | 1.000 | 49.3% | -3.37 |
| volume-surge continuation | 6 | 53 | 23% | 31.57 | 30.74 | 1.03 | 1.000 | 64.2% | 26.94 |
| volume-surge continuation | 12 | 0 | 0% | 0.00 | 0.00 | 0.00 | 1.000 | 0.0% | -3.80 |
| three-bar run continuation | 1 | 1,019 | 53% | -2.28 | -2.25 | -0.93 | 1.000 | 47.3% | -6.05 |
| three-bar run continuation | 3 | 766 | 53% | -3.98 | -3.93 | -0.66 | 1.000 | 49.6% | -7.73 |
| three-bar run continuation | 6 | 368 | 52% | -5.88 | -5.81 | -0.42 | 1.000 | 51.1% | -9.61 |
| three-bar run continuation | 12 | 0 | 0% | 0.00 | 0.00 | 0.00 | 1.000 | 0.0% | -3.80 |
| compression break | 1 | 126 | 51% | -7.61 | -7.60 | -1.23 | 1.000 | 50.8% | -11.40 |
| compression break | 3 | 74 | 39% | -15.18 | -15.34 | -1.01 | 1.000 | 45.9% | -19.14 |
| compression break | 6 | 0 | 0% | 0.00 | 0.00 | 0.00 | 1.000 | 0.0% | -3.80 |
| compression break | 12 | 0 | 0% | 0.00 | 0.00 | 0.00 | 1.000 | 0.0% | -3.80 |

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
| orb | 400 | 1.72 | 64 | 26.55 | 1.00 | 100% | plateau |
| vol-breakout | 400 | 1.30 | 207 | 32.37 | 0.77 | 100% | plateau |
| vwap-fade | 400 | 1.05 | 209 | 13.66 | 0.41 | 100% | ridge |
| ou-reversion | 400 | -0.06 | 218 | -1.49 | 5.57 | 0% | spike |
| sweep-reversal | 400 | 0.44 | 96 | 11.67 | 0.45 | 57% | ridge |
| trend-pullback | 400 | 1.16 | 52 | 44.49 | 0.56 | 67% | ridge |
| tod-control | 20 | 0.08 | 648 | 0.73 | -2.58 | 0% | spike |

Best parameters found in sample:

| strategy | parameters |
| --- | --- |
| orb | `orMinutes=45 maxWidthAtr=2.5 stopAtr=0.75 rr=1 maxBars=12 buffTicks=4` |
| vol-breakout | `lookback=20 volLookback=50 minVolPct=0.8 stopAtr=1 rr=1.5 maxBars=40` |
| vwap-fade | `stretchAtr=1 maxVolPct=0.5 volLookback=100 stopAtr=1 rr=1.5 maxBars=8 rsiLen=5 rsiEdge=35` |
| ou-reversion | `lookback=10 entryZ=2.5 stopAtr=1.5 targetFrac=0.5 maxBars=30 minVolPct=0 volLookback=100` |
| sweep-reversal | `lookback=20 minPierceAtr=0.25 stopAtr=1.5 rr=1 maxBars=16 maxVolPct=0.7 volLookback=100` |
| trend-pullback | `fast=9 slow=30 rsiLen=9 resetLevel=40 stopAtr=1 rr=1 maxBars=10` |
| tod-control | `hourLocal=10 side=-1 stopAtr=1 rr=1.5 maxBars=20` |

Total configurations evaluated in stage 4: **2420**. This number is carried into the Deflated Sharpe in stage 8.

## 5. Reality check across the candidate set

White's Reality Check and Hansen's SPA, applied to the daily P&L of each strategy's in-sample winner, stationary block bootstrap (2,000 resamples) over the cross-section so correlation between candidates is preserved. The null is "no candidate has an edge"; a high p-value means the best result is what picking the max of 7 noisy candidates looks like.

| statistic | value |
| --- | --- |
| best candidate | `vol-breakout` |
| mean daily P&L of best | $63 |
| candidates | 7 |
| observations (sessions) | 536 |
| White Reality Check p | 0.105 |
| Hansen SPA p | 0.043 |

## 6. Probability of backtest overfitting (CSCV)

For each strategy, the daily P&L of up to 120 sampled configurations is split into 10 contiguous blocks; every balanced train/test partition (252 of them) picks the in-sample winner and asks where that winner lands out of sample. PBO is the share of partitions where it falls below the median. **PBO > 0.5 means the selection procedure itself is selecting noise.**

| strategy | configs | PBO | IS→OOS slope | OOS loss rate | reading |
| --- | --- | --- | --- | --- | --- |
| orb | 120 | 0.000 | -0.900 | 0% | selection informative |
| vol-breakout | 120 | 0.591 | -0.932 | 30% | selecting noise |
| vwap-fade | 120 | 0.365 | -0.709 | 51% | weak |
| ou-reversion | 120 | 0.611 | -1.039 | 100% | selecting noise |
| sweep-reversal | 120 | 0.397 | -1.167 | 73% | weak |
| trend-pullback | 120 | 0.627 | -0.430 | 59% | selecting noise |
| tod-control | 4 | n/a | n/a | n/a | too few valid configurations |

## 7. Walk-forward out-of-sample

Rolling walk-forward on the research set: re-optimise on 1,440 bars (120 sessions at 12 bars/session), trade the next 480 bars (40 sessions) with those parameters, step forward, never look back. The stitched test windows are the first genuinely out-of-sample record in this study.

| strategy | folds | OOS trades | net (ticks) | PF | Sharpe | t (HAC) | WF efficiency | folds up | OOS P&L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| orb | 10 | 105 | 18.50 | 1.64 | 1.51 | 1.94 | 0.75 | 100% | $9,710 |
| vol-breakout | 10 | 150 | 3.15 | 1.04 | 0.15 | 0.19 | 0.05 | 70% | $2,360 |
| vwap-fade | 10 | 98 | -15.63 | 0.75 | -1.02 | -1.40 | -0.41 | 40% | -$7,660 |
| ou-reversion | 10 | 189 | 0.66 | 1.01 | 0.03 | 0.04 | -0.10 | 40% | $627 |
| sweep-reversal | 10 | 136 | -8.18 | 0.87 | -0.52 | -0.78 | -0.08 | 30% | -$5,564 |
| trend-pullback | 10 | 171 | 5.49 | 1.09 | 0.38 | 0.49 | -0.06 | 40% | $4,694 |
| tod-control | 10 | 492 | -1.74 | 0.97 | -0.19 | -0.22 | 0.01 | 50% | -$4,281 |

`orb            ` OOS equity: `▁▁▁▁▁▁▁▁▂▂▁▁▁▂▂▁▁▂▂▃▂▂▂▂▂▃▃▃▃▃▃▃▃▄▄▅▅▆▆▆▆▆▆▆▅▆▆▆▆▇▅▆▇▆▆▆▇▇▆█`
`vol-breakout   ` OOS equity: `▃▃▄▄▅▆▆▆▃▃▃▃▂▂▂▂▃▄▄▄▃▄▃▄▃▃▃▃▅▄▅▅▅█▆▅▅▅▅▄▄▁▁▁▁▁▁▁▄▄▄▄▄▄▄▄▄▄▄▃`
`vwap-fade      ` OOS equity: `▆▆▆▆▆▆▆▆▅▆▆▇▇▇▇████▇▇▇▇▇▇▇▇▆▆▆▆▆▅▄▅▅▅▄▄▄▄▄▄▄▅▅▅▅▅▅▄▄▃▃▃▃▂▁▁▁`
`ou-reversion   ` OOS equity: `▅▆▅▅▄▅▄▃▅▅▆▆▆▅▅▅▅▄▆▅▄▄▄▅▅▅▆▃▃▁▁▁▂▁▂▂▁▁▁▁▁▁▁▁▄▃▄▄▃▂▃▃▃▂▁▁▅▅▅█`
`sweep-reversal ` OOS equity: `▆▆▆▇▇▇▆▆▆▆▆▆▆▆█▆▇▇▆▇▆▆▆▇▇▇▇▆▆▅▄▄▄▄▄▃▃▂▄▅▄▄▃▃▄▃▂▁▁▁▂▂▂▂▂▂▂▂▁▂`
`trend-pullback ` OOS equity: `▁▁▁▁▂▄▅▅▅▃▃▃▃▃▃▃▄▄▄▄▄▄▄▅▅▅▄▅▅▅▅▅▄▅▅▅▅▅▆▆██▇▆▇▇▇▇▇▆▅▄▄▄▅▄▃▃▃▃`
`tod-control    ` OOS equity: `▄▄▄▄▄▄▃▃▄▄▄▄▅▄▃▂▂▃▃▃▄▄▄▅▅▆▆▆▆▇▇▇▆▆▆▆▆▇█▇▇▇▆▆▄▅▃▂▂▁▂▃▃▂▁▁▁▁▁▂`

Parameter stability across folds (share of folds choosing the modal value):

| strategy | stability by parameter |
| --- | --- |
| orb | orMinutes 100%, maxWidthAtr 100%, stopAtr 60%, rr 90%, maxBars 90%, buffTicks 70% |
| vol-breakout | lookback 50%, volLookback 50%, minVolPct 50%, stopAtr 50%, rr 60%, maxBars 50% |
| vwap-fade | stretchAtr 60%, maxVolPct 60%, volLookback 50%, stopAtr 70%, rr 40%, maxBars 40%, rsiLen 50%, rsiEdge 50% |
| ou-reversion | lookback 50%, entryZ 40%, stopAtr 40%, targetFrac 50%, maxBars 40%, minVolPct 80%, volLookback 100% |
| sweep-reversal | lookback 40%, minPierceAtr 70%, stopAtr 50%, rr 50%, maxBars 70%, maxVolPct 60%, volLookback 100% |
| trend-pullback | fast 40%, slow 60%, rsiLen 50%, resetLevel 40%, stopAtr 50%, rr 90%, maxBars 50% |
| tod-control | hourLocal 100%, side 60%, stopAtr 100%, rr 70%, maxBars 100% |

## 8. Deflated Sharpe and family-wide error control

A backtest Sharpe is the maximum of however many were looked at. The Deflated Sharpe Ratio prices that in using the actual number of configurations evaluated (**14620**) and the cross-sectional dispersion of trial Sharpes, together with the skew and fat tails of the realised daily stream. DSR is the probability the true Sharpe exceeds what the best of 14620 trials would produce by luck.

| strategy | OOS Sharpe | bootstrap 95% CI | expected max under null | DSR | min track record |
| --- | --- | --- | --- | --- | --- |
| orb | 1.51 | [0.23, 2.78] | 2.87 | 0.035 | never |
| vol-breakout | 0.15 | [-1.52, 1.45] | 1.58 | 0.034 | never |
| vwap-fade | -1.02 | [-2.45, 0.41] | 2.39 | 0.000 | never |
| ou-reversion | 0.03 | [-1.23, 1.11] | 1.82 | 0.012 | never |
| sweep-reversal | -0.52 | [-1.77, 0.65] | 2.70 | 0.000 | never |
| trend-pullback | 0.38 | [-1.09, 2.00] | 1.79 | 0.039 | never |
| tod-control | -0.19 | [-1.80, 1.52] | 0.54 | 0.177 | never |

Multiple-testing correction over the 7 strategies carried to walk-forward:

| rank | strategy | raw p | BH q | Holm p | survives BH | survives Holm |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | orb | 0.0523 | 0.3661 | 0.3661 | no | no |
| 2 | vwap-fade | 0.1607 | 0.5624 | 0.9641 | no | no |
| 3 | sweep-reversal | 0.4341 | 0.9682 | 1.0000 | no | no |
| 4 | trend-pullback | 0.6274 | 0.9682 | 1.0000 | no | no |
| 5 | tod-control | 0.8256 | 0.9682 | 1.0000 | no | no |
| 6 | vol-breakout | 0.8461 | 0.9682 | 1.0000 | no | no |
| 7 | ou-reversion | 0.9682 | 0.9682 | 1.0000 | no | no |

## 9. Robustness of the out-of-sample record

### orb — Opening-range breakout

*Narrow opening ranges mark unresolved auctions; the first break runs the stops resting on the other side.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 85.81 | 80.19 | 74.57 | 68.96 | 63.34 | 52.10 |
| Sharpe | 1.54 | 1.44 | 1.34 | 1.24 | 1.14 | 0.94 |

Cost tolerance: **survives every cost level tested — still profitable at 3x (11.40 ticks)** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 83% |
| worst sub-period | -$87 |
| best year's share of P&L | 68% |
| profitable years | 100% |
| profitable hours of day | 100% |
| Monte Carlo median maxDD | 2.6% |
| Monte Carlo 95th pct maxDD | 4.2% |
| P(losing overall) across orderings | 0% |
| P(25% drawdown) | 0% |
| median worst losing streak | 5 |

By exit reason: session 89 ($15,982) · stop 13 (-$8,740) · target 3 ($2,468)

By volatility tercile: 1-low $3,077 · 2-mid $2,535 · 3-high $4,099

**Gates passed 7/10.**

- PASS — >=100 out-of-sample trades (105)
- PASS — positive net edge after costs (18.50 ticks)
- PASS — PBO < 0.30 (0.00)
- PASS — survives >=1.5x modelled costs — survives every cost level tested — still profitable at 3x (11.40 ticks)
- PASS — parameter surface is not a mined spike (plateau)
- PASS — profitable in >=60% of sub-periods (83%)
- PASS — walk-forward efficiency >=0.4 (0.75)
- FAIL — HAC t-stat > 2 (1.94)
- FAIL — deflated Sharpe > 0.95 (0.035)
- FAIL — no single year carries >60% of P&L (68%)

### vol-breakout — Vol-expansion Donchian break

*Intraday momentum is conditional on volatility expansion; in compression the same break mean-reverts.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 66.02 | 62.15 | 58.29 | 54.42 | 50.56 | 42.83 |
| Sharpe | 0.67 | 0.63 | 0.59 | 0.55 | 0.51 | 0.43 |

Cost tolerance: **survives every cost level tested — still profitable at 3x (11.40 ticks)** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 67% |
| worst sub-period | -$7,960 |
| best year's share of P&L | 56% |
| profitable years | 100% |
| profitable hours of day | 67% |
| Monte Carlo median maxDD | 11.0% |
| Monte Carlo 95th pct maxDD | 16.5% |
| P(losing overall) across orderings | 0% |
| P(25% drawdown) | 0% |
| median worst losing streak | 7 |

By exit reason: session 31 ($8,054) · stop 65 (-$59,498) · target 48 ($49,733) · time 6 ($4,071)

By volatility tercile: 1-low $40 · 2-mid -$2,748 · 3-high $5,068

**Gates passed 6/10.**

- PASS — >=100 out-of-sample trades (150)
- PASS — positive net edge after costs (3.15 ticks)
- PASS — survives >=1.5x modelled costs — survives every cost level tested — still profitable at 3x (11.40 ticks)
- PASS — parameter surface is not a mined spike (plateau)
- PASS — profitable in >=60% of sub-periods (67%)
- PASS — no single year carries >60% of P&L (56%)
- FAIL — HAC t-stat > 2 (0.19)
- FAIL — deflated Sharpe > 0.95 (0.034)
- FAIL — PBO < 0.30 (0.59)
- FAIL — walk-forward efficiency >=0.4 (0.05)

### vwap-fade — Session-VWAP band fade

*VWAP is the institutional execution benchmark; stretches away from it are corrected by the same flow.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 33.31 | 28.53 | 23.75 | 18.96 | 14.18 | 4.62 |
| Sharpe | 0.61 | 0.52 | 0.43 | 0.34 | 0.26 | 0.08 |

Cost tolerance: **survives every cost level tested — still profitable at 3x (11.40 ticks)** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 17% |
| worst sub-period | -$3,558 |
| best year's share of P&L | 0% |
| profitable years | 50% |
| profitable hours of day | 33% |
| Monte Carlo median maxDD | 10.5% |
| Monte Carlo 95th pct maxDD | 13.7% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 0% |
| median worst losing streak | 7 |

By exit reason: session 47 (-$2,651) · stop 30 (-$22,570) · target 21 ($17,561)

By volatility tercile: 1-low -$929 · 2-mid -$10,559 · 3-high $3,828

**Gates passed 3/10.**

- PASS — survives >=1.5x modelled costs — survives every cost level tested — still profitable at 3x (11.40 ticks)
- PASS — parameter surface is not a mined spike (ridge)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — >=100 out-of-sample trades (98)
- FAIL — positive net edge after costs (-15.63 ticks)
- FAIL — HAC t-stat > 2 (-1.40)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — PBO < 0.30 (0.37)
- FAIL — profitable in >=60% of sub-periods (17%)
- FAIL — walk-forward efficiency >=0.4 (-0.41)

### ou-reversion — Rolling-mean reversion (VR-matched horizon)

*Variance ratios below 1 at the 10-20 bar horizon say displacement from the local mean is partly transitory; this trades that displacement back to the mean.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | -35.85 | -40.16 | -44.48 | -48.79 | -53.10 | -61.73 |
| Sharpe | -0.43 | -0.48 | -0.53 | -0.58 | -0.64 | -0.74 |

Cost tolerance: **unprofitable even with costs switched off — the rule loses on its own, not because of the cost model** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 50% |
| worst sub-period | -$4,271 |
| best year's share of P&L | 66% |
| profitable years | 100% |
| profitable hours of day | 33% |
| Monte Carlo median maxDD | 17.2% |
| Monte Carlo 95th pct maxDD | 25.2% |
| P(losing overall) across orderings | 0% |
| P(25% drawdown) | 5% |
| median worst losing streak | 7 |

By exit reason: session 62 ($10,567) · stop 54 (-$71,001) · target 38 ($54,738) · time 35 ($6,323)

By volatility tercile: 1-low -$1,644 · 2-mid -$3,133 · 3-high $5,403

**Gates passed 2/10.**

- PASS — >=100 out-of-sample trades (189)
- PASS — positive net edge after costs (0.66 ticks)
- FAIL — HAC t-stat > 2 (0.04)
- FAIL — deflated Sharpe > 0.95 (0.012)
- FAIL — PBO < 0.30 (0.61)
- FAIL — survives >=1.5x modelled costs — unprofitable even with costs switched off — the rule loses on its own, not because of the cost model
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (50%)
- FAIL — no single year carries >60% of P&L (66%)
- FAIL — walk-forward efficiency >=0.4 (-0.10)

### sweep-reversal — Liquidity-sweep reversal

*A pierce of a swing extreme that closes back inside is stop-run absorption, not repricing.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 18.47 | 14.39 | 10.31 | 6.22 | 2.14 | -6.02 |
| Sharpe | 0.28 | 0.22 | 0.16 | 0.09 | 0.03 | -0.09 |

Cost tolerance: **dies at 2.26x modelled costs (8.60 ticks)** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 67% |
| worst sub-period | -$5,642 |
| best year's share of P&L | 0% |
| profitable years | 50% |
| profitable hours of day | 0% |
| Monte Carlo median maxDD | 10.9% |
| Monte Carlo 95th pct maxDD | 15.4% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 0% |
| median worst losing streak | 7 |

By exit reason: session 53 ($1,006) · stop 45 (-$34,013) · target 36 ($26,916) · time 2 ($527)

By volatility tercile: 1-low $1,597 · 2-mid -$3,673 · 3-high -$3,488

**Gates passed 5/10.**

- PASS — >=100 out-of-sample trades (136)
- PASS — survives >=1.5x modelled costs — dies at 2.26x modelled costs (8.60 ticks)
- PASS — parameter surface is not a mined spike (ridge)
- PASS — profitable in >=60% of sub-periods (67%)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-8.18 ticks)
- FAIL — HAC t-stat > 2 (-0.78)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — PBO < 0.30 (0.40)
- FAIL — walk-forward efficiency >=0.4 (-0.08)

### trend-pullback — EMA-stack pullback continuation

*Pullbacks inside an intraday trend are inventory rebalancing, not a change in the auction's direction.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | -22.72 | -27.00 | -31.27 | -35.54 | -39.81 | -48.36 |
| Sharpe | -0.35 | -0.41 | -0.47 | -0.54 | -0.60 | -0.72 |

Cost tolerance: **unprofitable even with costs switched off — the rule loses on its own, not because of the cost model** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 83% |
| worst sub-period | -$4,777 |
| best year's share of P&L | 126% |
| profitable years | 50% |
| profitable hours of day | 33% |
| Monte Carlo median maxDD | 7.6% |
| Monte Carlo 95th pct maxDD | 11.7% |
| P(losing overall) across orderings | 0% |
| P(25% drawdown) | 0% |
| median worst losing streak | 6 |

By exit reason: session 51 ($6,344) · stop 60 (-$45,950) · target 60 ($44,300)

By volatility tercile: 1-low $1,601 · 2-mid $10,128 · 3-high -$7,036

**Gates passed 4/10.**

- PASS — >=100 out-of-sample trades (171)
- PASS — positive net edge after costs (5.49 ticks)
- PASS — parameter surface is not a mined spike (ridge)
- PASS — profitable in >=60% of sub-periods (83%)
- FAIL — HAC t-stat > 2 (0.49)
- FAIL — deflated Sharpe > 0.95 (0.039)
- FAIL — PBO < 0.30 (0.63)
- FAIL — survives >=1.5x modelled costs — unprofitable even with costs switched off — the rule loses on its own, not because of the cost model
- FAIL — no single year carries >60% of P&L (126%)
- FAIL — walk-forward efficiency >=0.4 (-0.06)

### tod-control — Time-of-day control (null benchmark)

*Deliberate null: fixed-hour entry with no predictive content, used to calibrate the rest of the pipeline.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 1.83 | -3.42 | -8.67 | -13.92 | -19.17 | -29.67 |
| Sharpe | 0.04 | -0.08 | -0.19 | -0.31 | -0.43 | -0.66 |

Cost tolerance: **dies at 0.17x modelled costs (0.66 ticks)** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 50% |
| worst sub-period | -$15,461 |
| best year's share of P&L | 0% |
| profitable years | 50% |
| profitable hours of day | 50% |
| Monte Carlo median maxDD | 19.3% |
| Monte Carlo 95th pct maxDD | 27.8% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 12% |
| median worst losing streak | 9 |

By exit reason: session 242 ($28,282) · stop 151 (-$136,652) · target 99 ($104,089)

By volatility tercile: 1-low -$2,323 · 2-mid $2,388 · 3-high -$4,346

**Gates passed 2/10.**

- PASS — >=100 out-of-sample trades (492)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-1.74 ticks)
- FAIL — HAC t-stat > 2 (-0.22)
- FAIL — deflated Sharpe > 0.95 (0.177)
- FAIL — PBO < 0.30 (NaN)
- FAIL — survives >=1.5x modelled costs — dies at 0.17x modelled costs (0.66 ticks)
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (50%)
- FAIL — walk-forward efficiency >=0.4 (0.01)

## 10. Portfolio combination

Correlation of walk-forward out-of-sample daily P&L:

|  | orb | vol-breakout | vwap-fade | ou-reversion | sweep-reversal | trend-pullback |
| --- | --- | --- | --- | --- | --- | --- |
| orb | 1.00 | 0.10 | -0.31 | -0.03 | -0.01 | -0.03 |
| vol-breakout | 0.10 | 1.00 | -0.06 | -0.37 | -0.12 | 0.10 |
| vwap-fade | -0.31 | -0.06 | 1.00 | 0.10 | 0.12 | -0.02 |
| ou-reversion | -0.03 | -0.37 | 0.10 | 1.00 | 0.24 | -0.02 |
| sweep-reversal | -0.01 | -0.12 | 0.12 | 0.24 | 1.00 | -0.09 |
| trend-pullback | -0.03 | 0.10 | -0.02 | -0.02 | -0.09 | 1.00 |

| scheme | Sharpe | t (HAC) | diversification | avg pairwise r | uplift vs best single | weights |
| --- | --- | --- | --- | --- | --- | --- |
| equal | 0.25 | 0.30 | 2.64 | -0.03 | -1.40 | 17% / 17% / 17% / 17% / 17% / 17% |
| inverse-vol | 0.25 | 0.30 | 2.64 | -0.03 | -1.40 | 17% / 17% / 17% / 17% / 17% / 17% |
| risk-parity | 0.31 | 0.36 | 2.66 | -0.03 | -1.35 | 18% / 18% / 17% / 17% / 15% / 16% |
| min-variance | 0.17 | 0.21 | 1.79 | -0.03 | -1.48 | 0% / 50% / 0% / 50% / 0% / 0% |

Weights are in risk units — each stream is scaled to unit daily volatility first, so a weight is a share of risk, not of dollars.

## 11. Locked holdout — evaluated once

Parameters are frozen to the modal walk-forward choice (the value each parameter took in the most folds) and run over the held-back final 30% of the sample, which no stage above has touched. This is the only number in the study that has never influenced a decision.

| strategy | trades | win | gross (ticks) | cost (ticks) | net (ticks) | PF | Sharpe | t (HAC) | p | P&L | maxDD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| orb | 51 | 62.7% | 24.94 | 2.27 | 22.67 | 1.58 | 1.27 | 1.41 | 0.160 | $5,781 | 2.6% |
| vol-breakout | 59 | 45.8% | -45.03 | 1.72 | -46.75 | 0.71 | -1.48 | -1.37 | 0.171 | -$13,791 | 19.1% |
| vwap-fade | 76 | 42.1% | -12.29 | 1.96 | -14.25 | 0.81 | -0.84 | -0.85 | 0.395 | -$5,417 | 7.7% |
| ou-reversion | 191 | 57.6% | 40.51 | 1.68 | 38.83 | 1.30 | 1.49 | 1.64 | 0.100 | $37,081 | 11.2% |
| sweep-reversal | 88 | 46.6% | 13.38 | 1.67 | 11.71 | 1.16 | 0.63 | 0.63 | 0.526 | $5,151 | 7.7% |
| trend-pullback | 103 | 61.2% | 33.04 | 1.50 | 31.54 | 1.39 | 1.55 | 1.63 | 0.103 | $16,243 | 6.6% |
| tod-control | 251 | 56.2% | 27.77 | 2.12 | 25.65 | 1.32 | 1.95 | 1.94 | 0.053 | $32,189 | 14.3% |

## 12. Verdict

| strategy | gates passed | status |
| --- | --- | --- |
| orb | 7/10 | partial — not tradeable |
| vol-breakout | 6/10 | rejected |
| vwap-fade | 3/10 | rejected |
| ou-reversion | 2/10 | rejected |
| sweep-reversal | 5/10 | rejected |
| trend-pullback | 4/10 | rejected |
| tod-control | 2/10 | rejected |

**No strategy cleared every gate.** On this instrument, session and cost model, the honest conclusion is that none of the tested rules demonstrates an edge that survives costs, search deflation and out-of-sample testing.
Partial passes worth another research cycle: orb (7/10).

---

Runtime 34.2s · configurations evaluated 14620 · seed 20250822.
