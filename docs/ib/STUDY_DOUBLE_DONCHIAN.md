# STUDY_DOUBLE_DONCHIAN — the "Double Donchian Channel Breakout" Pine on US30, US100 and NQ

**Brief.** A published Pine v5 strategy (omererkan: slow Donchian 50, fast Donchian 30, both
lagged a bar; long on a close crossing the slow upper band when the slow channel's width exceeds
3% of its lower band, short mirrored; close everything on a close crossing the fast band the
other way; a limit take-profit at ±2% for half the position; 100% of equity per entry, 0.05%
commission per side, no stop) was uploaded with a header naming BTC/USDT, January 2024, 1-hour
bars, and the instruction to run it on US30, US100 and NQ instead. Its parameters were chosen
for BTC, so every block below is out of sample for them.

**Verdict.** As configured it makes **+22% on US30 over 8.7 years, loses 44% on US100 over 8.9
years, and breaks even on NQ over 3 years**, against buy-and-hold of +143%, +423% and +88%, while
in the market 18–34% of the time. Against a random entry bar with the identical exits, take-profit,
sizing and costs, matched on trades taken, it clears the control on US30 (p 0.037 inside the width
regime, 0.010 anywhere), fails on US100 (p 0.84 / 0.92 — the control loses less) and fails on NQ
(p 0.37 / 0.22). The US30 result sits on a spike in the width filter (2% → −22%, 3% → +22%, 4% →
+17%, 5% → −14%) and inverts across timeframes (15m −4%, 1h +22%, 4h −19%), so it is one cell of
a noisy surface rather than an edge. US100 is negative at zero commission (−23%), so cost is not
the obstacle there. **And the script's partial take-profit does not do what it says**: it is
re-issued every bar, so after the first fill it halves the position at every subsequent open while
price stays past the level — which happens to be worth +12 points of net return on US30 against the
author's evident intent, because scaling out into strength is a better exit than the one the
script meant to have.

`research/ddc/ddc_core.py`, `research/ddc/run_ddc.py`; full output in `results/ddc/run.txt`.

## 1. The order model

Bar-level, exactly as the Strategy Tester runs a script with `calc_on_every_tick` off: a signal
at bar t's close fills at t+1's open; `close_all` likewise; an opposite-side `strategy.entry`
reverses at the open; `strategy.exit(limit=)` is placed at the close of the first bar the
position exists on, so it is live from the second bar after the fill and fills at the limit
intrabar or at the open if the bar opens through it. Sizing is 100% of equity at the signal
close; commission 0.05% of order value per fill; no slippage (the script sets none — "fills
that are free", `STUDY_TICK_RECALC`).

**The take-profit as written vs as meant.** `strategy.exit("TP1", "Long", qty_percent = 50,
limit = ...)` runs on every bar `strategy.position_size > 0`. Once the order has filled it no
longer exists, so the next bar's call creates a new one for 50% of what remains at a limit the
market is already beyond, which the emulator fills at that bar's open. The position is therefore
halved on every bar the price stays past +2% until the channel exit closes the remainder.
`mode="literal"` reproduces that; `mode="intended"` fires the partial once per position.

Hourly bars are resampled on a New York clock from the 15-minute CFD feeds (US30, US100) and the
1-minute NQ file, labelled at the top of the hour.

## 2. The backtest as configured, 1-hour bars, whole file

| market | bars | buy & hold | literal net | PF | win | max DD | trades | median hold | intended net | in market (L / S) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| US30 2016-10 → 2025-07 | 49,325 | +143% | **+22.2%** | 1.20 | 48.7% | 15.1% | 152 | 51 h | +9.9% | 11.6% / 6.9% |
| US100 2016-11 → 2025-10 | 51,889 | +423% | **−43.6%** | 0.79 | 49.2% | 57.2% | 313 | 47 h | −54.5% | 19.6% / 13.9% |
| NQ 2022-12 → 2025-12 | 18,243 | +88% | **+0.1%** | 1.00 | 44.4% | 12.7% | 63 | 54 h | −9.0% | 13.7% / 7.5% |

The width filter passes on 18% of US30 bars, 35% of US100, 20% of NQ, and cuts the raw
breakouts from 1,513 / 941 (US30 up / down) to 245 / 201; the position lock then takes 152 of
those. The header's own window, January 2024, contains 0 trades on US30, 3 on US100 and 1 on NQ
— a one-month backtest of this rule is a coin.

**By side and by cost (literal):**

| market | long only | short only | zero commission | 0.10% / side |
| --- | ---: | ---: | ---: | ---: |
| US30 | +24.6% (PF 1.51, DD 6.6%) | −2.0% (PF 0.97, DD 19.9%) | +42.2% | +4.9% |
| US100 | −22.3% (PF 0.83) | −27.4% (PF 0.79) | **−22.8%** | −58.6% |
| NQ | +3.4% (PF 1.13) | −3.1% (PF 0.85) | +6.6% | −6.0% |

The short side loses on all three indices, as every short on this branch has. US100 loses
gross, so it is not a cost problem; US30 and NQ are cost-sensitive, and the script's 0.05% is
already generous for a futures contract and thin for a CFD spread on a 1-hour breakout.

**By year, literal, equity return:** US30 2018 +1.7%, 2019 −3.1%, 2020 +7.8%, 2021 −2.6%, 2022
+11.8%, 2023 +1.2%, 2024 +5.6%, 2025 +2.8% — two years (2020, 2022) are 88% of the total. US100
2020 −33.6% and 2021 −14.6% are the damage; 2022 +7.1%, 2024 +2.2%, 2025 +8.8%. NQ +1.3%, +1.6%,
−2.6%.

## 3. The control

Random entry bars with the identical exits, take-profit, sizing and costs, **matched on the
number of trades taken per side** (a random signal is taken more often than a clustered breakout,
so matching signal counts hands the control more trades and more commission — the first draft
here did that and printed p 0.000 on US30). Two pools: bars inside the width regime, which keeps
the filter and removes only the breakout timing; and any bar.

| market | strategy net | control inside regime, median (p) | control anywhere, median (p) |
| --- | ---: | ---: | ---: |
| US30 | +22.2% | −13.2% (**0.037**) | −11.8% (**0.010**) |
| US100 | −43.6% | −25.3% (0.840) | −21.2% (0.920) |
| NQ | +0.1% | −3.9% (0.367) | −6.2% (0.217) |

Note the controls are all NEGATIVE: this exit structure — a 30-bar channel cross with no stop,
both sides, 100% of equity, paying 0.05% twice — loses money on a random entry in a rising
market. On US30 the breakout timing recovers that and more; on US100 it makes it worse.

## 4. The two BTC-fitted knobs, and the timeframe

Net over the whole file, literal model, trades in brackets:

| width filter | 0% | 1% | 2% | **3%** | 4% | 5% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| US30 | −45% (652) | −40% (560) | −22% (298) | **+22% (152)** | +17% (71) | −14% (46) |
| US100 | −51% (713) | −45% (671) | −59% (492) | **−44% (313)** | −55% (190) | −61% (114) |
| NQ | −34% (251) | −27% (236) | −23% (147) | **+0% (63)** | −1% (25) | −6% (12) |

| take-profit | 1% | **2%** | 3% | 5% |
| --- | ---: | ---: | ---: | ---: |
| US30 | −4% | **+22%** | +22% | +8% |
| US100 | −42% | **−44%** | −35% | −38% |
| NQ | +13% | **+0%** | −10% | −12% |

| timeframe | US30 | US100 | NQ |
| --- | ---: | ---: | ---: |
| 15 min | −3.9% (91, PF 0.94) | −18.2% (220, 0.86) | +7.5% (28, 1.54) |
| **60 min** | **+22.2%** (152, 1.20) | **−43.6%** (313, 0.79) | **+0.1%** (63, 1.00) |
| 240 min | −18.6% (139, 0.87) | +21.3% (178, 1.09) | +13.4% (58, 1.20) |

The width filter is what makes the unfiltered breakout (−45% / −51% / −34%) survivable at
all, and on US30 it works in a two-rung window. The 1-hour result on US30 and the 4-hour result
on US100 are each the only positive cell in their column. A real edge is a ridge; these are
points.

## 5. What to take from it

* Run on TradingView, the script will show the LITERAL numbers, and the partial take-profit it
  shows you is not the one described in its inputs. Anyone porting it should decide which
  behaviour they want and write it explicitly.
* The unfiltered double-channel breakout loses on all three indices; the 3% width filter is the
  whole strategy and it was fitted to BTC. On US30 it lands on a two-cell island; on NQ it takes
  the rule to zero; on US100 nothing on the ladder is positive.
* This is the seventh Donchian-family breakout on this branch to fail its random-entry control on
  at least two of three markets (`STUDY_TURTLE`, `STUDY_TURTLE_YOUTUBE`, `STUDY_V12`,
  `STUDY_DONCHIAN_ADX_CHOP`, `STUDY_SWEEP_110K`, `STUDY_V60_AROON`). The one that passed,
  `STUDY_V11_MARKET`, had an ADX ≥ 25 floor, one unit, and no take-profit.
