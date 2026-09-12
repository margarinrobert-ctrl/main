# US30: the 09:00 pre-open range, broken after the open, confirmed by an EMA cross — nothing survives

*The rule as asked for: ATR(14) and EMA(200) for trend, an EMA(13)/EMA(48) cross for momentum, the
high and low marked at 09:00 New York, a break of that high or low at or after the 09:30 open,
entries until 10:30 in the highest-volume hour, 100-point stop, 100-point target. Then every
parameter swept on its own neighbourhood, gated by a matched control, walked forward, and read
once on the locked block.*

*Result:* **The rule loses on both blocks and does worse than a random entry with the same side,
minute and geometry. Across 13,425 research cells of its own neighbourhood not one beats that
control at z > 2 (0.0% against 2.3% expected by chance). The best research cell is a spike; the
best plateau cell is negative on the holdout. Walk-forward loses in 7 of 9 folds. It is not the
costs: at zero cost the rule as specified still loses 7 points a trade on research and 20 on
locked.** Do not trade it, and do not re-run this structure on this file.

> Research output, not financial advice. Reproducible from this repo:
> `python3 research/us30_ingest.py --in <us30_2_year_data.rtf> --out data/US30_15m.csv` then
> `python3 research/us30_orb.py`.

| field | value |
| --- | --- |
| data | `data/US30_15m.csv` · 48,937 bars @ 15m · 2024-08-19 → 2026-08-26 · stamped New York time with UTC offset |
| instrument | a Dow index contract (CFD or YM/MYM; the export does not say). Prices 36,693 → 54,726; the index rose 32% over the sample |
| sessions | 24 h weekdays, 18:00 → 17:00 New York; 511 sessions carry every bar of the 08:30–09:30 pre-open window |
| split | research = first 65% of sessions, 332 (to 2025-12-15) · locked = last 35%, 179 |
| costs | **assumed**: 3 points round turn (spread + slippage + commission) + 1 point on stop fills; swept 0 / 3 / 6 / 10. Dollars at $5 per point (one YM contract); ×0.5 for MYM, ×~1 for a CFD |
| execution | decision on a confirmed bar, fill at the next bar's open; stop and target both inside one bar books the **stop** (1% of trades); TradingView's intrabar path also reported |
| ambiguity | 1 of 232 research trades; the 15-minute bars after 09:45 rarely span 200 points |

---

## 1. The rule, made precise

Every clock condition is New York time. Every decision is taken on a confirmed bar and filled at the
next bar's open, which is exactly what the Pine does.

| piece | definition | parameter, swept over |
| --- | --- | --- |
| range | high and low of the bars stamped 09:00 and 09:15, the 09:00–09:30 pre-open | `range_start` 08:30 / **09:00** / 09:15; the range always ends at the 09:30 open |
| break | a **close** beyond the range high (long) or low (short) at or after 09:30; sticky within the day | — |
| momentum | EMA(13) above EMA(48) for a long, below for a short | fast 8 / **13** / 21 × slow 34 / **48** / 89; `cross_k` **state** / cross within 1 / 2 / 4 bars |
| trend | close above EMA(200) for a long, below for a short | **200** / off |
| window | signal bars 09:30 … 10:15, so fills run 09:45 … 10:30 | last fill 10:00 / **10:30** / 11:00 |
| exit | stop 100 points, target 100 points from the fill; flat at 16:00 | 50–200 points × R 1 / 1.5 / 2; 1–3 × ATR(14) × R 1 / 2; flat 12:00 / **16:00** / 16:45 |
| frequency | one trade per session, first signal wins | — |

Bold is the rule as asked for. 648 rules × 25 geometries = 16,200 cells; 13,425 have at least 50
research trades. ATR(14) is `ema(tr, 14)`; the rule as asked for does not size anything in it, so
its role is the ATR-sized geometry family in the sweep.

## 2. The rule as specified

Research block, 232 trades:

| | trades | win | net | per trade | PF | Sharpe | max DD | exits tp / sl / flat |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| both sides | 232 | 47.4% | −2,352 pt (−$11,762) | **−10.1 pt** | 0.81 | −1.62 | 2,726 pt | 105 / 122 / 5 |
| long | 120 | 49.2% | −802 pt | −6.7 pt | 0.87 | −1.06 | 1,465 pt | 56 / 61 / 3 |
| short | 112 | 45.5% | −1,550 pt | −13.8 pt | 0.76 | −2.21 | 1,922 pt | 49 / 61 / 2 |
| under TradingView's intrabar path | 232 | 47.8% | −2,152 pt | −9.3 pt | 0.83 | −1.48 | 2,526 pt | 106 / 121 / 5 |

The exit split says what kind of loss this is: 105 targets at +97 and 122 stops at −104. At a 1R
barrier the driftless base rate is 50%, costs push it to about 49%, and the rule wins 47.4%. It is
a barrier bet that picks the wrong side slightly more often than a coin.

**Matched control** (2,000 draws; random fills with the same side, same fill minute, same block):

| block | n | rule net | control net | z | p | rule win | control win | p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| research | 232 | −2,352 | −1,091 ± 1,510 | **−0.84** | 0.799 | 47.4% | 49.2% | 0.750 |

The rule is 0.84 standard deviations *worse* than picking the same minutes at random. The window
itself has nothing in it either: every 09:45 fill on the research block, long, same geometry,
nets −6.1 points a trade (48.8% win); short, −2.7 (50.0%). With a 3-point round turn that is a
gross edge of about zero on both sides. The 32% rise in the index over the sample does not reach a
100-point barrier placed 15 minutes after the open.

## 3. Drop-one: what each piece is worth

Research block, each piece changed on its own, control z:

| variant | n | net | control | z | win |
| --- | --- | --- | --- | --- | --- |
| as specified | 232 | −2,352 | −1,141 ± 1,517 | −0.80 | 47.4% |
| no trend gate | 261 | −2,114 | −1,201 ± 1,623 | −0.56 | 48.3% |
| EMA state → cross within 2 bars | 74 | −890 | −349 ± 823 | −0.66 | 47.3% |
| range 08:30–09:30 | 228 | −2,950 | −1,105 ± 1,565 | −1.18 | 46.1% |
| range 09:15–09:30 (one bar) | 236 | −2,608 | −1,148 ± 1,501 | −0.97 | 46.6% |
| fills to 10:00 | 185 | −1,428 | −909 ± 1,383 | −0.38 | 48.6% |
| fills to 11:00 | 259 | −2,146 | −1,325 ± 1,596 | −0.51 | 48.3% |
| long only | 123 | −712 | −628 ± 1,132 | −0.07 | 49.6% |
| short only | 115 | −1,460 | −503 ± 1,070 | −0.89 | 46.1% |

No piece is carrying anything. Removing the trend gate helps slightly, requiring a fresh cross
cuts the sample by two thirds without changing the sign, and neither range window is better than
the other. The long side is exactly a coin flip against its control; the short side is worse than
one.

## 4. The neighbourhood sweep, research only

16,200 cells, ranked on the matched-control z-score (400 draws each), 13,425 with ≥ 50 trades:

| statistic | value |
| --- | --- |
| median z over all cells | **−0.54** |
| 90th percentile z | 0.43 |
| share of cells with z > 2 | **0.0%** (2.3% expected from noise alone) |
| cells that are long-only in effect | 0.0% (every cell trades both sides, so this is not a drift bet) |
| the rule as specified | rank **9,116 of 13,425**, z −0.87 |

Median z by axis value, which is how a mechanism would show itself if there were one:

| axis | values → median z |
| --- | --- |
| fast EMA | 8: −0.40 · 13: −0.49 · 21: −0.78 |
| slow EMA | 34: −0.39 · 48: −0.57 · 89: −0.73 |
| trend gate | off: −0.35 · 200: −0.70 |
| range start | 08:30: −0.64 · 09:00: −0.51 · 09:15: −0.47 |
| last fill | 10:00: −0.79 · 10:30: −0.62 · 11:00: −0.27 |
| cross | state: −0.87 · within 1: −0.19 · within 2: −0.37 · within 4: −0.48 |
| geometry | best 75/75 pt: +0.10 · 50/75 pt: +0.05 · 100/100 flat 12:00: −0.21 · everything ATR-sized or ≥ 150 pt: −0.5 to −1.1 |

Every axis's median is below zero. Faster EMAs, no trend gate, a fresh cross and a small barrier
are all *less bad*, which is the shape of a family with no edge whose small-barrier cells are
closest to the coin.

Top 15 cells:

| fast | slow | trend | range | last fill | cross | geometry | n | win | net | per trade | L / S | z | p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 13 | 34 | off | 08:30 | 11:00 | 1 | 1×ATR / 2×ATR | 91 | 41.8% | 1,442 | 15.9 | 44 / 47 | 1.86 | 0.03 |
| 8 | 34 | off | 09:00 | 11:00 | 1 | 100 / 100 flat 12:00 | 105 | 57.1% | 1,204 | 11.5 | 49 / 56 | 1.81 | 0.03 |
| 8 | 89 | 200 | 09:00 | 11:00 | 1 | 75 / 75 | 81 | 58.0% | 674 | 8.3 | 32 / 49 | 1.75 | 0.03 |
| 8 | 89 | 200 | 09:15 | 11:00 | 1 | 75 / 75 | 81 | 58.0% | 674 | 8.3 | 33 / 48 | 1.74 | 0.05 |
| 21 | 34 | off | 09:15 | 11:00 | 1 | 100 / 150 | 89 | 51.7% | 1,691 | 19.0 | 42 / 47 | 1.73 | 0.03 |
| 21 | 34 | off | 09:00 | 11:00 | 1 | 100 / 150 | 89 | 51.7% | 1,691 | 19.0 | 42 / 47 | 1.73 | 0.03 |
| 8 | 89 | 200 | 08:30 | 11:00 | 1 | 75 / 75 | 78 | 59.0% | 784 | 10.1 | 29 / 49 | 1.73 | 0.05 |
| 13 | 34 | off | 09:15 | 11:00 | 1 | 1×ATR / 2×ATR | 93 | 40.9% | 1,332 | 14.3 | 45 / 48 | 1.67 | 0.06 |
| 8 | 34 | off | 09:00 | 10:00 | 2 | 100 / 100 flat 12:00 | 70 | 57.1% | 972 | 13.9 | 35 / 35 | 1.63 | 0.04 |
| 8 | 34 | off | 09:00 | 11:00 | 4 | 100 / 100 flat 12:00 | 129 | 55.0% | 1,118 | 8.7 | 59 / 70 | 1.62 | 0.05 |
| 21 | 34 | off | 08:30 | 11:00 | 1 | 100 / 150 | 87 | 50.6% | 1,397 | 16.1 | 41 / 46 | 1.61 | 0.05 |
| 8 | 34 | off | 09:00 | 10:00 | 1 | 100 / 100 flat 12:00 | 59 | 57.6% | 953 | 16.2 | 30 / 29 | 1.61 | 0.04 |
| 13 | 34 | off | 09:00 | 11:00 | 1 | 1×ATR / 2×ATR | 92 | 41.3% | 1,375 | 15.0 | 44 / 48 | 1.60 | 0.06 |
| 8 | 34 | off | 09:00 | 11:00 | 2 | 100 / 100 flat 12:00 | 115 | 55.7% | 1,020 | 8.9 | 54 / 61 | 1.59 | 0.05 |
| 8 | 89 | off | 08:30 | 11:00 | 1 | 75 / 75 | 98 | 57.1% | 714 | 7.3 | 35 / 63 | 1.57 | 0.07 |

The p-values in the last column are the maximum of 13,425 draws and mean nothing on their own. The
**winner** (EMA 13/34, no trend gate, 08:30 range, fills to 11:00, cross within one bar, 1×ATR
stop, 2×ATR target) has a neighbour stability of **0.31**: the median of its one-step neighbours
keeps less than a third of its z. That is a **spike**.

The **plateau pick** — the cell in the top 5% whose neighbours hold up best — is EMA 8/34, no
trend gate, range 09:15–09:30, fills to 10:00, cross within one bar, 100/100 points, flat at
12:00, with z 1.35 and stability 0.98. That is the "best parameters" this data can offer for the
structure, and it is carried forward as the selected rule so the locked block can judge it.

## 5. The selected rule, research only

| | trades | win | net | per trade | PF | Sharpe | max DD | tp / sl / flat |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| both | 59 | 55.9% | 752 pt ($3,762) | 12.8 pt | 1.32 | 2.14 | 745 pt | 30 / 21 / 8 |
| long | 29 | 58.6% | 569 pt | 19.6 pt | 1.53 | 3.27 | 446 pt | 17 / 9 / 3 |
| short | 30 | 53.3% | 184 pt | 6.1 pt | 1.15 | 1.02 | 486 pt | 13 / 12 / 5 |

Control: 752 vs −270 ± 741, **z 1.38, p 0.086**; win 55.9% vs 49.2%, p 0.187. It did not clear
the gate on research either; it is merely the least-bad plateau.

| probe | as specified | selected |
| --- | --- | --- |
| deflated Sharpe (N 13,425 trials, per-trade SR, T trades) | **0.000** (SR −0.10, T 232) | **0.234** (SR 0.14, hurdle SR0 0.23, T 59) |
| bootstrap 95% CI on annualised Sharpe | [−3.77, 0.40] | [−2.35, 7.39] |
| bootstrap 95% CI on net, points | [−5,380, 581] · P(net ≤ 0) 0.94 | [−839, 2,321] · P(net ≤ 0) 0.16 |
| Monte Carlo max drawdown (observed / median / 95th) | 2,726 / 2,964 / 3,757 | 745 / 515 / 803 |
| cost sweep, per trade, at 0 / 3 / 6 / 10 pt | −7.1 / −10.1 / −13.1 / −17.1 | 15.8 / 12.8 / 9.8 / 5.8 |
| quarters profitable | 1 of 6 | 5 of 6 |

The zero-cost column is the one that closes the door on "it is the spread": the rule as specified
loses seven points a trade before paying anything.

## 6. Walk-forward

Fit on 120 sessions, trade the next 40, step 40; 36 rules (fast 8/13/21 × slow 34/48/89 × trend
on/off × state / cross within 2) × 6 geometries (75/100/150 points × R 1/2); objective in-sample
net.

| fold | fit from | test from | rule chosen | geometry | IS net | OOS n | OOS net |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 2024-09-03 | 2025-02-20 | 8/48, no gate, cross ≤ 2 | 150 / 300 | 1,569 | 11 | −792 |
| 1 | 2024-10-29 | 2025-04-17 | 8/89, no gate, cross ≤ 2 | 150 / 300 | 1,363 | 7 | 96 |
| 2 | 2024-12-24 | 2025-06-13 | 8/89, no gate, cross ≤ 2 | 150 / 300 | 1,202 | 9 | −214 |
| 3 | 2025-02-20 | 2025-08-08 | 8/34, no gate, cross ≤ 2 | 100 / 100 | 969 | 10 | −713 |
| 4 | 2025-04-17 | 2025-10-03 | 8/48, no gate, cross ≤ 2 | 75 / 150 | 568 | 14 | −428 |
| 5 | 2025-06-13 | 2025-11-28 | 21/34, no gate, state | 75 / 150 | 1,021 | 36 | 270 |
| 6 | 2025-08-08 | 2026-01-27 | 8/48, EMA 200, cross ≤ 2 | 100 / 200 | 603 | 11 | −341 |
| 7 | 2025-10-03 | 2026-03-24 | 21/34, no gate, cross ≤ 2 | 150 / 150 | 1,627 | 8 | −386 |
| 8 | 2025-11-28 | 2026-05-20 | 8/48, no gate, cross ≤ 2 | 150 / 300 | 2,085 | 10 | −309 |

Stitched out-of-sample: **116 trades, 31.9% win, −2,816 pt (−$14,080), −24.3 pt a trade, PF 0.67,
Sharpe −2.85.** 2 of 9 folds profitable. The rule changed in 6 of 9 folds and the geometry in 5.
Walk-forward efficiency is negative. Every fold found something with a positive in-sample net of
600–2,100 points, and the thing it found was noise.

## 7. The locked block, read once

Both rules were read on the locked block exactly once, after everything above was fixed.

**As specified** (chosen from 1 cell; research z −0.84):

| | trades | win | net | per trade | PF | Sharpe | max DD | tp / sl / flat | control | z |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| both | 130 | 40.0% | −3,041 pt (−$15,205) | **−23.4 pt** | 0.62 | −3.78 | 3,294 pt | 51 / 77 / 2 | −499 ± 1,156 | **−2.20** |
| long | 76 | 39.5% | −1,790 pt | −23.5 pt | 0.62 | | | 30 / 45 / 1 | | |
| short | 54 | 40.7% | −1,251 pt | −23.2 pt | 0.62 | | | 21 / 32 / 1 | | |

0 of 4 locked quarters profitable. At zero cost, −20.4 a trade. The rule is 2.2 standard
deviations worse than a random entry on the holdout. Over the whole file it is 362 trades, 44.8%
wins, −5,393 points, −$26,967 on one YM contract.

**Selected** (chosen from 13,425 cells; research z 1.38):

| | trades | win | net | per trade | PF | Sharpe | max DD | tp / sl / flat | control | z |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| both | 35 | 48.6% | −284 pt (−$1,420) | **−8.1 pt** | 0.85 | −1.28 | 1,248 pt | 16 / 18 / 1 | −140 ± 596 | −0.24 |
| long | 17 | 52.9% | 41 pt | 2.4 pt | 1.05 | | | 9 / 8 / 0 | | |
| short | 18 | 44.4% | −325 pt | −18.1 pt | 0.69 | | | 7 / 10 / 1 | | |

Research 12.8 pt a trade → locked −8.1: a 164% decay, i.e. the research number was entirely the
selection. 2 of 4 locked quarters profitable; at zero cost still −5.1 a trade.

## 8. What this says, and what it does not

**It says** that on this file, at 15 minutes, a break of the 09:00–09:30 range confirmed by an EMA
cross in the first hour after the open does not pick a side better than a coin, on either side,
at any barrier from 50 to 200 points or 1 to 3 ATR, with or without the 200 EMA, whether the cross
is required to be fresh or not, and in none of nine walk-forward folds. The protocol's gates:

| # | gate | as specified | selected |
| --- | --- | --- | --- |
| 1 | ≥ 100 OOS trades | 130 ✓ | 35 ✗ |
| 2 | positive net edge after costs | ✗ | ✗ |
| 3 | beats the matched control (z > 2) on research | ✗ (−0.84) | ✗ (1.38) |
| 4 | deflated Sharpe > 0.95 | ✗ (0.00) | ✗ (0.23) |
| 6 | survives 1.5× costs | ✗ | research ✓ / locked ✗ |
| 7 | surface not a spike | n/a | plateau ✓ |
| 8 | profitable in ≥ 60% of sub-periods | ✗ (1 of 10) | ✗ (7 of 10) |
| 10 | walk-forward efficiency ≥ 0.4 | ✗ (negative) | ✗ |

**It does not say** the Dow is unpredictable at the open, only that OHLC at 15 minutes plus this
structure is. Three things would change the question rather than the parameters:

1. **One-minute bars.** The user's description — mark the 09:00 high and low, wait for the cross
   after the break — is a one-minute or five-minute idea. On 15-minute bars the "range" is two
   bars, the break and the cross are both read at bar closes 15 minutes apart, and the 09:30 bar
   alone has a median range of 160 points, larger than the whole barrier. NQ here shows the
   opposite trap (`STUDY_NQ_1m.md`: halving the bar halves the move and leaves the cost), so the
   right resolution is an empirical question, not a preference.
2. **The instrument's real cost.** The 3-point round turn is a guess. It does not matter for the
   verdict (the rule loses at zero cost) but it will matter for anything that eventually passes.
3. **Information the bars do not contain.** The 09:30–10:30 hour carries 3–5× the volume of the
   pre-open, and the volume column was not used by the rule as asked for. That is the
   "volume-surge continuation" event study in the protocol's stage 2, and it is the next thing to
   measure before another rule search.

What is **not** a productive response is the top-15 table in §4: fifteen cells with p ≈ 0.03–0.07
out of 13,425 is fewer than chance would produce, and the one that was carried forward lost on
the holdout.

## Files

| file | what |
| --- | --- |
| `research/us30_ingest.py` | RTF export → `data/US30_15m.csv` (UTC, canonical columns), with a data audit |
| `research/us30_orb.py` | the whole study: exit tensor, rule, matched control, sweep, stability, walk-forward, deflated Sharpe, bootstrap, Monte Carlo, cost sweep, locked reveal |
| `pine/us30/US30_OpenRangeEmaCross.pine` | the rule as a Pine v6 strategy, every parameter an input, linted with `research/pine_lint.py`. Its header carries the numbers above; it is shipped so the result can be reproduced on a chart, not because it should be traded |
