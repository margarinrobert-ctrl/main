# Systematic scalping study — NQ (open hour, realistic fills)

> Generated 2026-08-22T06:42:03.581Z · seed `20250822` · every number below is reproducible from this repo.
> Research output, not trading advice. A passed protocol is a licence to paper-trade, not to size up.

## 1. Data

| field | value |
| --- | --- |
| file | `data/NQ_5m.csv` |
| raw bars | 210,516 |
| timeframe | 5 min |
| range | 2022-12-26T23:00:00.000Z → 2025-12-12T01:50:00.000Z |
| session studied | 09:30–10:30 America/New_York |
| fill model | `realistic` |
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
| orb | 400 | 1.80 | 70 | 26.24 | n/a | n/a | spike |
| vol-breakout | 400 | 1.17 | 209 | 28.81 | 0.76 | 100% | plateau |
| vwap-fade | 400 | 0.88 | 103 | 10.10 | 0.83 | 100% | plateau |
| ou-reversion | 400 | -0.09 | 219 | -2.35 | 4.27 | 0% | spike |
| sweep-reversal | 400 | 0.36 | 96 | 9.55 | 0.17 | 57% | spike |
| trend-pullback | 400 | 1.18 | 53 | 44.27 | 0.57 | 67% | ridge |
| tod-control | 20 | 0.03 | 648 | 0.31 | -8.39 | 0% | spike |

Best parameters found in sample:

| strategy | parameters |
| --- | --- |
| orb | `orMinutes=45 maxWidthAtr=2.5 stopAtr=0.75 rr=1 maxBars=48 buffTicks=2` |
| vol-breakout | `lookback=20 volLookback=50 minVolPct=0.8 stopAtr=1 rr=1.5 maxBars=40` |
| vwap-fade | `stretchAtr=1.5 maxVolPct=0.5 volLookback=100 stopAtr=0.75 rr=0.75 maxBars=16 rsiLen=5 rsiEdge=35` |
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
| mean daily P&L of best | $56 |
| candidates | 7 |
| observations (sessions) | 536 |
| White Reality Check p | 0.147 |
| Hansen SPA p | 0.031 |

## 6. Probability of backtest overfitting (CSCV)

For each strategy, the daily P&L of up to 120 sampled configurations is split into 10 contiguous blocks; every balanced train/test partition (252 of them) picks the in-sample winner and asks where that winner lands out of sample. PBO is the share of partitions where it falls below the median. **PBO > 0.5 means the selection procedure itself is selecting noise.**

| strategy | configs | PBO | IS→OOS slope | OOS loss rate | reading |
| --- | --- | --- | --- | --- | --- |
| orb | 120 | 0.000 | -0.894 | 0% | selection informative |
| vol-breakout | 120 | 0.643 | -0.992 | 47% | selecting noise |
| vwap-fade | 120 | 0.425 | -0.536 | 66% | weak |
| ou-reversion | 120 | 0.690 | -1.072 | 99% | selecting noise |
| sweep-reversal | 120 | 0.389 | -1.150 | 80% | weak |
| trend-pullback | 120 | 0.488 | -0.483 | 59% | weak |
| tod-control | 4 | n/a | n/a | n/a | too few valid configurations |

## 7. Walk-forward out-of-sample

Rolling walk-forward on the research set: re-optimise on 1,440 bars (120 sessions at 12 bars/session), trade the next 480 bars (40 sessions) with those parameters, step forward, never look back. The stitched test windows are the first genuinely out-of-sample record in this study.

| strategy | folds | OOS trades | net (ticks) | PF | Sharpe | t (HAC) | WF efficiency | folds up | OOS P&L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| orb | 10 | 106 | 19.00 | 1.68 | 1.59 | 1.92 | 0.64 | 100% | $10,069 |
| vol-breakout | 10 | 157 | 0.42 | 1.00 | 0.02 | 0.03 | 0.69 | 50% | $332 |
| vwap-fade | 10 | 97 | -14.78 | 0.76 | -0.99 | -1.41 | -0.60 | 40% | -$7,168 |
| ou-reversion | 10 | 191 | 0.51 | 1.00 | 0.02 | 0.03 | -0.11 | 40% | $484 |
| sweep-reversal | 10 | 133 | -5.32 | 0.92 | -0.33 | -0.48 | -0.44 | 40% | -$3,540 |
| trend-pullback | 10 | 158 | 1.79 | 1.03 | 0.11 | 0.14 | -0.14 | 40% | $1,413 |
| tod-control | 10 | 507 | -6.91 | 0.90 | -0.80 | -0.91 | -0.11 | 30% | -$17,516 |

`orb            ` OOS equity: `▁▁▂▁▂▁▁▁▂▂▂▁▁▂▂▁▁▂▂▃▃▃▂▂▂▃▃▃▃▃▃▃▃▄▄▅▅▆▆▆▆▆▆▆▆▆▆▆▆▇▆▆▇▆▆▆▇▇▇█`
`vol-breakout   ` OOS equity: `▃▃▄▄▅▆▆█▅▄▄▄▄▄▃▄▄▅▅▅▄▅▄▄▃▃▃▃▅▄▅▅▅▇▆▅▅▅▅▄▄▁▁▁▁▁▁▁▄▄▄▂▂▂▁▁▁▁▁▂`
`vwap-fade      ` OOS equity: `▆▆▅▆▆▆▆▆▅▆▆▇▇▇▇████▆▆▇▇▇▇▇▇▆▆▅▅▅▄▃▄▄▄▃▃▃▃▃▂▃▃▃▃▄▄▄▃▂▁▁▁▁▁▁▁▁`
`ou-reversion   ` OOS equity: `▆▇▆▅▄▅▄▃▅▅▇▆▆▅▅▅▅▅▆▅▄▄▄▅▅▆▆▃▃▁▂▂▂▁▂▂▁▁▁▁▁▁▁▁▄▃▄▄▃▂▃▃▂▁▁▁▅▅▅█`
`sweep-reversal ` OOS equity: `▄▄▄▅▅▆▆▆▆▆▆▆▆▆▇▅▇▇▇▇▆▆▆█▇▆▆▆▆▄▅▄▄▄▅▄▄▂▄▅▄▄▃▃▄▃▂▁▁▁▂▂▂▂▂▂▂▁▁▂`
`trend-pullback ` OOS equity: `▁▁▁▁▂▃▆▆▆▃▃▃▃▂▃▃▄▅▄▄▄▄▄▆▆▅▅▆▆▅▅▅▄▅▅▅▅▄▅▅█▇▆▄▆▆▆▅▅▄▂▂▂▃▄▂▁▂▂▂`
`tod-control    ` OOS equity: `▇▇▇▇▇▇▇▇▆▇▇▆▅▄▃▃▃▃▃▄▄▄▄▅▆▆▇▆▆▇▇▇▆▆▇▆▆▇█▇▇▇▆▇▅▅▄▃▂▂▂▃▂▂▁▁▁▁▁▂`

Parameter stability across folds (share of folds choosing the modal value):

| strategy | stability by parameter |
| --- | --- |
| orb | orMinutes 100%, maxWidthAtr 90%, stopAtr 80%, rr 80%, maxBars 80%, buffTicks 80% |
| vol-breakout | lookback 40%, volLookback 40%, minVolPct 60%, stopAtr 40%, rr 60%, maxBars 50% |
| vwap-fade | stretchAtr 50%, maxVolPct 50%, volLookback 50%, stopAtr 60%, rr 40%, maxBars 50%, rsiLen 50%, rsiEdge 50% |
| ou-reversion | lookback 50%, entryZ 40%, stopAtr 40%, targetFrac 50%, maxBars 40%, minVolPct 80%, volLookback 100% |
| sweep-reversal | lookback 40%, minPierceAtr 80%, stopAtr 60%, rr 50%, maxBars 70%, maxVolPct 60%, volLookback 100% |
| trend-pullback | fast 50%, slow 50%, rsiLen 60%, resetLevel 60%, stopAtr 50%, rr 80%, maxBars 50% |
| tod-control | hourLocal 100%, side 70%, stopAtr 100%, rr 50%, maxBars 100% |

## 8. Deflated Sharpe and family-wide error control

A backtest Sharpe is the maximum of however many were looked at. The Deflated Sharpe Ratio prices that in using the actual number of configurations evaluated (**14620**) and the cross-sectional dispersion of trial Sharpes, together with the skew and fat tails of the realised daily stream. DSR is the probability the true Sharpe exceeds what the best of 14620 trials would produce by luck.

| strategy | OOS Sharpe | bootstrap 95% CI | expected max under null | DSR | min track record |
| --- | --- | --- | --- | --- | --- |
| orb | 1.59 | [0.25, 2.98] | 2.95 | 0.035 | never |
| vol-breakout | 0.02 | [-1.60, 1.32] | 1.49 | 0.032 | never |
| vwap-fade | -0.99 | [-2.36, 0.34] | 2.45 | 0.000 | never |
| ou-reversion | 0.02 | [-1.25, 1.08] | 1.78 | 0.013 | never |
| sweep-reversal | -0.33 | [-1.59, 0.88] | 2.86 | 0.000 | never |
| trend-pullback | 0.11 | [-1.41, 1.68] | 2.00 | 0.009 | never |
| tod-control | -0.79 | [-2.49, 1.02] | 0.65 | 0.033 | never |

Multiple-testing correction over the 7 strategies carried to walk-forward:

| rank | strategy | raw p | BH q | Holm p | survives BH | survives Holm |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | orb | 0.0542 | 0.3796 | 0.3796 | no | no |
| 2 | vwap-fade | 0.1584 | 0.5544 | 0.9504 | no | no |
| 3 | tod-control | 0.3625 | 0.8459 | 1.0000 | no | no |
| 4 | sweep-reversal | 0.6301 | 0.9797 | 1.0000 | no | no |
| 5 | trend-pullback | 0.8861 | 0.9797 | 1.0000 | no | no |
| 6 | ou-reversion | 0.9755 | 0.9797 | 1.0000 | no | no |
| 7 | vol-breakout | 0.9797 | 0.9797 | 1.0000 | no | no |

## 9. Robustness of the out-of-sample record

### orb — Opening-range breakout

*Narrow opening ranges mark unresolved auctions; the first break runs the stops resting on the other side.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 92.60 | 83.26 | 73.91 | 64.57 | 55.22 | 36.53 |
| Sharpe | 1.69 | 1.52 | 1.35 | 1.18 | 1.01 | 0.67 |

Cost tolerance: **survives every cost level tested — still profitable at 3x (11.40 ticks)** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 100% |
| worst sub-period | $439 |
| best year's share of P&L | 67% |
| profitable years | 100% |
| profitable hours of day | 100% |
| Monte Carlo median maxDD | 2.4% |
| Monte Carlo 95th pct maxDD | 3.9% |
| P(losing overall) across orderings | 0% |
| P(25% drawdown) | 0% |
| median worst losing streak | 5 |

By exit reason: session 87 ($11,847) · stop 12 (-$7,783) · target 7 ($6,005)

By volatility tercile: 1-low $2,651 · 2-mid $3,729 · 3-high $3,689

**Gates passed 6/10.**

- PASS — >=100 out-of-sample trades (106)
- PASS — positive net edge after costs (19.00 ticks)
- PASS — PBO < 0.30 (0.00)
- PASS — survives >=1.5x modelled costs — survives every cost level tested — still profitable at 3x (11.40 ticks)
- PASS — profitable in >=60% of sub-periods (100%)
- PASS — walk-forward efficiency >=0.4 (0.64)
- FAIL — HAC t-stat > 2 (1.92)
- FAIL — deflated Sharpe > 0.95 (0.035)
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — no single year carries >60% of P&L (67%)

### vol-breakout — Vol-expansion Donchian break

*Intraday momentum is conditional on volatility expansion; in compression the same break mean-reverts.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 138.13 | 129.09 | 120.05 | 111.01 | 101.97 | 83.88 |
| Sharpe | 0.74 | 0.69 | 0.65 | 0.60 | 0.55 | 0.45 |

Cost tolerance: **survives every cost level tested — still profitable at 3x (11.40 ticks)** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 50% |
| worst sub-period | -$4,058 |
| best year's share of P&L | 651% |
| profitable years | 50% |
| profitable hours of day | 67% |
| Monte Carlo median maxDD | 12.8% |
| Monte Carlo 95th pct maxDD | 19.1% |
| P(losing overall) across orderings | 0% |
| P(25% drawdown) | 0% |
| median worst losing streak | 7 |

By exit reason: session 41 ($15,376) · stop 67 (-$67,358) · target 44 ($50,439) · time 5 ($1,875)

By volatility tercile: 1-low -$635 · 2-mid -$3,549 · 3-high $4,515

**Gates passed 5/10.**

- PASS — >=100 out-of-sample trades (157)
- PASS — positive net edge after costs (0.42 ticks)
- PASS — survives >=1.5x modelled costs — survives every cost level tested — still profitable at 3x (11.40 ticks)
- PASS — parameter surface is not a mined spike (plateau)
- PASS — walk-forward efficiency >=0.4 (0.69)
- FAIL — HAC t-stat > 2 (0.03)
- FAIL — deflated Sharpe > 0.95 (0.032)
- FAIL — PBO < 0.30 (0.64)
- FAIL — profitable in >=60% of sub-periods (50%)
- FAIL — no single year carries >60% of P&L (651%)

### vwap-fade — Session-VWAP band fade

*VWAP is the institutional execution benchmark; stretches away from it are corrected by the same flow.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 34.04 | 25.96 | 17.88 | 9.81 | 1.73 | -14.42 |
| Sharpe | 0.63 | 0.48 | 0.33 | 0.18 | 0.03 | -0.26 |

Cost tolerance: **dies at 2.11x modelled costs (8.01 ticks)** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 17% |
| worst sub-period | -$3,741 |
| best year's share of P&L | 0% |
| profitable years | 50% |
| profitable hours of day | 33% |
| Monte Carlo median maxDD | 10.1% |
| Monte Carlo 95th pct maxDD | 13.3% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 0% |
| median worst losing streak | 7 |

By exit reason: session 41 (-$3,284) · stop 30 (-$22,310) · target 26 ($18,426)

By volatility tercile: 1-low $977 · 2-mid -$8,839 · 3-high $694

**Gates passed 3/10.**

- PASS — survives >=1.5x modelled costs — dies at 2.11x modelled costs (8.01 ticks)
- PASS — parameter surface is not a mined spike (plateau)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — >=100 out-of-sample trades (97)
- FAIL — positive net edge after costs (-14.78 ticks)
- FAIL — HAC t-stat > 2 (-1.41)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — PBO < 0.30 (0.42)
- FAIL — profitable in >=60% of sub-periods (17%)
- FAIL — walk-forward efficiency >=0.4 (-0.60)

### ou-reversion — Rolling-mean reversion (VR-matched horizon)

*Variance ratios below 1 at the 10-20 bar horizon say displacement from the local mean is partly transitory; this trades that displacement back to the mean.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | -32.35 | -40.40 | -48.44 | -56.49 | -64.54 | -80.63 |
| Sharpe | -0.39 | -0.49 | -0.58 | -0.68 | -0.77 | -0.96 |

Cost tolerance: **unprofitable even with costs switched off — the rule loses on its own, not because of the cost model** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 33% |
| worst sub-period | -$3,576 |
| best year's share of P&L | 170% |
| profitable years | 50% |
| profitable hours of day | 67% |
| Monte Carlo median maxDD | 17.2% |
| Monte Carlo 95th pct maxDD | 25.6% |
| P(losing overall) across orderings | 0% |
| P(25% drawdown) | 6% |
| median worst losing streak | 7 |

By exit reason: session 61 ($10,666) · stop 55 (-$71,835) · target 39 ($55,607) · time 36 ($6,046)

By volatility tercile: 1-low -$2,218 · 2-mid -$3,683 · 3-high $6,384

**Gates passed 2/10.**

- PASS — >=100 out-of-sample trades (191)
- PASS — positive net edge after costs (0.51 ticks)
- FAIL — HAC t-stat > 2 (0.03)
- FAIL — deflated Sharpe > 0.95 (0.013)
- FAIL — PBO < 0.30 (0.69)
- FAIL — survives >=1.5x modelled costs — unprofitable even with costs switched off — the rule loses on its own, not because of the cost model
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (33%)
- FAIL — no single year carries >60% of P&L (170%)
- FAIL — walk-forward efficiency >=0.4 (-0.11)

### sweep-reversal — Liquidity-sweep reversal

*A pierce of a swing extreme that closes back inside is stop-run absorption, not repricing.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 23.32 | 15.51 | 7.69 | -0.12 | -7.93 | -23.55 |
| Sharpe | 0.36 | 0.24 | 0.12 | -0.00 | -0.12 | -0.35 |

Cost tolerance: **dies at 1.49x modelled costs (5.67 ticks)** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 33% |
| worst sub-period | -$3,117 |
| best year's share of P&L | 0% |
| profitable years | 50% |
| profitable hours of day | 33% |
| Monte Carlo median maxDD | 9.8% |
| Monte Carlo 95th pct maxDD | 14.1% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 0% |
| median worst losing streak | 7 |

By exit reason: session 42 (-$623) · stop 48 (-$34,757) · target 41 ($31,359) · time 2 ($482)

By volatility tercile: 1-low $1,360 · 2-mid -$1,990 · 3-high -$2,910

**Gates passed 2/10.**

- PASS — >=100 out-of-sample trades (133)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-5.32 ticks)
- FAIL — HAC t-stat > 2 (-0.48)
- FAIL — deflated Sharpe > 0.95 (0.000)
- FAIL — PBO < 0.30 (0.39)
- FAIL — survives >=1.5x modelled costs — dies at 1.49x modelled costs (5.67 ticks)
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (33%)
- FAIL — walk-forward efficiency >=0.4 (-0.44)

### trend-pullback — EMA-stack pullback continuation

*Pullbacks inside an intraday trend are inventory rebalancing, not a change in the auction's direction.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | -35.74 | -44.02 | -52.30 | -60.58 | -68.86 | -85.42 |
| Sharpe | -0.47 | -0.57 | -0.68 | -0.78 | -0.88 | -1.09 |

Cost tolerance: **unprofitable even with costs switched off — the rule loses on its own, not because of the cost model** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 50% |
| worst sub-period | -$2,730 |
| best year's share of P&L | 263% |
| profitable years | 50% |
| profitable hours of day | 67% |
| Monte Carlo median maxDD | 8.8% |
| Monte Carlo 95th pct maxDD | 13.3% |
| P(losing overall) across orderings | 0% |
| P(25% drawdown) | 0% |
| median worst losing streak | 7 |

By exit reason: session 56 ($3,411) · stop 54 (-$43,481) · target 48 ($41,483)

By volatility tercile: 1-low $1,979 · 2-mid $8,081 · 3-high -$8,647

**Gates passed 3/10.**

- PASS — >=100 out-of-sample trades (158)
- PASS — positive net edge after costs (1.79 ticks)
- PASS — parameter surface is not a mined spike (ridge)
- FAIL — HAC t-stat > 2 (0.14)
- FAIL — deflated Sharpe > 0.95 (0.009)
- FAIL — PBO < 0.30 (0.49)
- FAIL — survives >=1.5x modelled costs — unprofitable even with costs switched off — the rule loses on its own, not because of the cost model
- FAIL — profitable in >=60% of sub-periods (50%)
- FAIL — no single year carries >60% of P&L (263%)
- FAIL — walk-forward efficiency >=0.4 (-0.14)

### tod-control — Time-of-day control (null benchmark)

*Deliberate null: fixed-hour entry with no predictive content, used to calibrate the rest of the pipeline.*

| cost multiple | 0x | 0.5x | 1x | 1.5x | 2x | 3x |
| --- | --- | --- | --- | --- | --- | --- |
| cost (ticks) | 0.00 | 1.90 | 3.80 | 5.70 | 7.60 | 11.40 |
| expectancy ($/trade) | 6.05 | -2.94 | -11.94 | -20.93 | -29.92 | -47.90 |
| Sharpe | 0.14 | -0.07 | -0.27 | -0.47 | -0.67 | -1.07 |

Cost tolerance: **dies at 0.34x modelled costs (1.28 ticks)** (modelled cost 3.80 ticks).

| probe | result |
| --- | --- |
| profitable OOS sub-periods (6ths) | 33% |
| worst sub-period | -$14,550 |
| best year's share of P&L | 0% |
| profitable years | 0% |
| profitable hours of day | 50% |
| Monte Carlo median maxDD | 26.4% |
| Monte Carlo 95th pct maxDD | 34.9% |
| P(losing overall) across orderings | 100% |
| P(25% drawdown) | 64% |
| median worst losing streak | 9 |

By exit reason: session 236 ($15,876) · stop 158 (-$142,007) · target 113 ($108,616)

By volatility tercile: 1-low -$6,987 · 2-mid -$7,966 · 3-high -$2,564

**Gates passed 2/10.**

- PASS — >=100 out-of-sample trades (507)
- PASS — no single year carries >60% of P&L (0%)
- FAIL — positive net edge after costs (-6.91 ticks)
- FAIL — HAC t-stat > 2 (-0.91)
- FAIL — deflated Sharpe > 0.95 (0.033)
- FAIL — PBO < 0.30 (NaN)
- FAIL — survives >=1.5x modelled costs — dies at 0.34x modelled costs (1.28 ticks)
- FAIL — parameter surface is not a mined spike (spike)
- FAIL — profitable in >=60% of sub-periods (33%)
- FAIL — walk-forward efficiency >=0.4 (-0.11)

## 10. Portfolio combination

Correlation of walk-forward out-of-sample daily P&L:

|  | orb | vol-breakout | vwap-fade | ou-reversion | sweep-reversal | trend-pullback |
| --- | --- | --- | --- | --- | --- | --- |
| orb | 1.00 | 0.03 | -0.22 | -0.03 | 0.00 | -0.02 |
| vol-breakout | 0.03 | 1.00 | -0.06 | -0.42 | -0.12 | 0.13 |
| vwap-fade | -0.22 | -0.06 | 1.00 | 0.12 | 0.12 | -0.00 |
| ou-reversion | -0.03 | -0.42 | 0.12 | 1.00 | 0.20 | -0.06 |
| sweep-reversal | 0.00 | -0.12 | 0.12 | 0.20 | 1.00 | -0.05 |
| trend-pullback | -0.02 | 0.13 | -0.00 | -0.06 | -0.05 | 1.00 |

| scheme | Sharpe | t (HAC) | diversification | avg pairwise r | uplift vs best single | weights |
| --- | --- | --- | --- | --- | --- | --- |
| equal | 0.20 | 0.25 | 2.62 | -0.03 | -1.53 | 17% / 17% / 17% / 17% / 17% / 17% |
| inverse-vol | 0.20 | 0.25 | 2.62 | -0.03 | -1.53 | 17% / 17% / 17% / 17% / 17% / 17% |
| risk-parity | 0.26 | 0.32 | 2.66 | -0.03 | -1.47 | 17% / 19% / 16% / 18% / 15% / 16% |
| min-variance | 0.04 | 0.05 | 1.86 | -0.03 | -1.69 | 0% / 50% / 0% / 50% / 0% / 0% |

Weights are in risk units — each stream is scaled to unit daily volatility first, so a weight is a share of risk, not of dollars.

## 11. Locked holdout — evaluated once

Parameters are frozen to the modal walk-forward choice (the value each parameter took in the most folds) and run over the held-back final 30% of the sample, which no stage above has touched. This is the only number in the study that has never influenced a decision.

| strategy | trades | win | gross (ticks) | cost (ticks) | net (ticks) | PF | Sharpe | t (HAC) | p | P&L | maxDD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| orb | 52 | 65.4% | 28.71 | 3.77 | 24.94 | 1.66 | 1.41 | 1.51 | 0.132 | $6,485 | 2.8% |
| vol-breakout | 57 | 54.4% | 19.53 | 3.54 | 15.99 | 1.09 | 0.28 | 0.30 | 0.768 | $4,557 | 11.9% |
| vwap-fade | 55 | 41.8% | -9.93 | 3.39 | -13.32 | 0.80 | -0.72 | -0.69 | 0.490 | -$3,663 | 6.9% |
| ou-reversion | 193 | 57.5% | 38.43 | 3.18 | 35.25 | 1.27 | 1.36 | 1.51 | 0.131 | $34,018 | 11.0% |
| sweep-reversal | 88 | 46.6% | 13.10 | 3.17 | 9.93 | 1.13 | 0.54 | 0.54 | 0.592 | $4,371 | 7.9% |
| trend-pullback | 99 | 54.5% | 24.04 | 3.22 | 20.82 | 1.22 | 0.82 | 0.79 | 0.430 | $10,304 | 9.3% |
| tod-control | 251 | 56.6% | 27.60 | 3.62 | 23.98 | 1.30 | 1.82 | 1.81 | 0.070 | $30,091 | 14.8% |

## 12. Verdict

| strategy | gates passed | status |
| --- | --- | --- |
| orb | 6/10 | rejected |
| vol-breakout | 5/10 | rejected |
| vwap-fade | 3/10 | rejected |
| ou-reversion | 2/10 | rejected |
| sweep-reversal | 2/10 | rejected |
| trend-pullback | 3/10 | rejected |
| tod-control | 2/10 | rejected |

**No strategy cleared every gate.** On this instrument, session and cost model, the honest conclusion is that none of the tested rules demonstrates an edge that survives costs, search deflation and out-of-sample testing.

---

Runtime 33.7s · configurations evaluated 14620 · seed 20250822.
