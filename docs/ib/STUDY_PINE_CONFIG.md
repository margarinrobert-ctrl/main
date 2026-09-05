# Why two of three strategies lost money in the Strategy Tester

Three Deep Backtests were run on MNQ 30-minute charts. One made money, two lost heavily.
Neither loss was the strategy.

## What was reported

TradingView gives profit factor, win rate and net. Those three pin the per-trade table exactly.

| | trades | win% | net | exp/trade | avg win | avg loss | W/L | PF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| V3 2022-12→2024-12 | 126 | 26.19 | −$9,437 | **−$74.90** | $94.8 | $135.1 | **0.70** | 0.249 |
| V2L 2024-12→2025-12 | 75 | 25.33 | −$8,284 | **−$110.50** | $222.6 | $223.5 | **1.00** | 0.338 |
| M4 2022-12→2025-12 | 75 | 64.00 | +$5,151 | +$68.70 | $203.6 | $171.3 | 1.19 | 2.114 |

All three are symmetric 1R designs, so W/L ≈ 1.00 is the signature of clean barrier exits. V3's
0.70 says its exits are not resolving at the barriers at all.

## The same rules in the harness, on the same windows

| | trades | win% | net | exp/trade | PF |
| --- | ---: | ---: | ---: | ---: | ---: |
| V3 @ **15m** (design tf) | 112 | 66.07 | **+$4,461** | +$39.8 | 1.62 |
| V3 @ **30m** (as run) | 84 | 58.33 | **+$3,647** | +$43.4 | 1.61 |
| V2L @ 30m (design tf) | 52 | 71.15 | **+$4,689** | +$90.2 | 2.08 |

Both failures show ~45–50% more trades than the rule generates, and a roughly inverted win rate.

## What the data settles

**Not costs.** Modelled friction is ~$3.00/round turn — **4.0%** of V3's loss and **2.7%** of
V2L's. Zero costs leaves both heavily negative.

**Not the extra trades alone.** If V2L's 52 real trades won at 71% and *every* one of the 23
extra trades lost, the result would be 49%, not 25.3%.

**Not variance.** Scored against each geometry's own population base rate:

| | observed | base | expected wins | z | p |
| --- | ---: | ---: | ---: | ---: | ---: |
| V3 | 33/126 | 48.2% | 60.7 | **−4.94** | 6.3e-07 |
| V2L | 19/75 | 48.9% | 36.7 | **−4.08** | 4.0e-05 |
| M4 | 48/75 | 49.5% | 37.1 | +2.51 | 0.015 |

Joint probability both are variance: ~1e-10. **A dead signal reverts to its base rate; it does
not go to 25%.** Being significantly *worse* than random on a symmetric barrier is mechanical,
not statistical.

**The stop was not the documented one.** The average loss reads the stop distance out directly:

| stop method | implied avg loss | ratio to V2L's $223.5 |
| --- | ---: | ---: |
| **Percent of price, 0.50% (input default)** | **$222.7** | **1.00** |
| ATR multiple 2.5× — *documented* | $415.9 | 1.86 |
| Fixed points, 50 | $100.0 | 0.45 |
| Fixed dollars, $500 | $500.0 | 2.24 |

Ratio 1.00 against a candidate with no free parameter. Re-simulating that stop costs
71.2% → 60.4% and PF 2.08 → 1.33 — real damage, about a third of the gap.

**25% is outside the reachable space.** Across both timeframes, both windows, four stop methods
and flatten on/off, the lowest win rate reproducible in the harness was **48.3%**. No
signal-or-geometry explanation reaches 26%.

**One variable co-varies perfectly** with the outcome across the three panels: the Strategy
Tester's "Script execution" count — 1 on the profitable run, 4 on both failures.

## Ranked

1. **Strategy Tester execution settings re-resolving entries and exits.** The only candidate left
   after signal space is exhausted, and the only one that produces trade inflation *and* win
   collapse together. `CLAUDE.md` records tick evaluation firing 5.1× as many signals with 80% on
   bars that never satisfied the rule. The scripts declare `calc_on_every_tick = false`, but the
   tester's checkboxes override the declaration.
2. **Stop method changed off ATR.** Demonstrated for V2L. Insufficient alone.
3. **V3 timeframe mismatch.** Certain, and insufficient — still +$3,647 at 30m.
4. **Variance or a dead edge.** Rejected at ~1e-10.

## What changed as a result

`pine/more1R/V3_strategy.pine`, `pine/more1R/V2L_strategy.pine`, `pine/mega2_1R/M4_strategy.pine`
gained a **Configuration** preset, defaulting to `Best measured (locked)`:

* every input is overridden by the measured constant — timezone, session, flatten, stop method,
  ATR multiple, target ratio, exit style, floor/cap, direction;
* each raw input is now referenced in exactly two places, its own definition and its `…Eff`
  assignment, so nothing downstream can read an unlocked value;
* the script refuses to trade off its design timeframe rather than producing numbers that
  mean nothing;
* a banner reports `AS MEASURED`, `CUSTOM`, or `WRONG TIMEFRAME` with the effective stop, target,
  session and flatten time.

## Rule verification

Each script's expressions were transcribed literally into numpy and diffed against the
authoritative research masks over the full sample:

| strategy | tf | pine triggers | research triggers | shared | pine only | research only |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| V3 | 15 | 171 | 171 | 171 | 0 | 0 |
| V2L | 30 | 172 | 172 | 172 | 0 | 0 |
| M4 | 30 | 94 | 94 | 94 | 0 | 0 |

`ta.ema(ta.tr(true), 14)` against the research ATR: max absolute difference 0.0.

## Still true afterwards

The lock restores the measured configuration; it does not upgrade the evidence. V3 and V2L both
carry the **grew on locked** flag in their own headers — they earn more out of sample than in,
which this branch treats as a defect. M4's TradingView expectancy (+$68.70) is already below its
harness figure (~$100). Reconciled, these are modest and provisional, not validated.
