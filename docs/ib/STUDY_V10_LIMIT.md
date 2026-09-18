# Optimising V9 for scalping: the mechanic is the lever, not the signal


> **CORRECTION (V15).** Every limit-entry figure in this study was produced by `eem.run`, whose
> fill model scans forward from each signal in turn and fills at *that* signal's level — so a limit
> priced eight bars ago outranks a nearer one priced since. That needs eight simultaneous resting
> orders and for the far one to fill first; a script has one live order. Re-measured with the
> implementable model the legs keep **24–47%** of their R, with every shared trade identical (exit
> bar 100%, correlation 1.0000). Read the numbers below as an upper bound, not as a result. See
> `docs/ib/STUDY_V15_BOOK.md` §2 and `research/v15/v15_parity.py`. Market-order results are
> unaffected.

NQ 15-minute, 70,685 bars, 2022-12-26 → 2025-12-12. Research = first 65% of sessions, LOCKED read
once after parameters were fixed. All headline figures are **true 1-minute path execution**
(`research/limit_entry.run_1m`), fills require price to trade **through** the limit by 4 ticks, and
costs are scaled to the real MNQ stack of $1.44 a round turn.

## Three bar-level artifacts, found before any result

A 15-minute bar loop cannot know intrabar order, and the limit-entry question is *entirely* about
intrabar order. Three separate artifacts appeared, each inflating the result:

1. **Fill the limit at a bar's low, pay the target at the same bar's high.** Assumes the low came
   first.
2. **The Donchian channel exit sitting ABOVE a limit fill.** A limit that fills on a dip below the
   recent range makes `max(ATR stop, channel low)` a level *above* the entry — so the "stop"
   triggered instantly at a profit. **3,170 trades averaging +1.14 with a median hold of one bar.**
3. **A sell stop resting above the market.** Not a stop at all; it is a limit booking free profit.

Together, on a rule-free every-bar test, those three showed **Sharpe 11**. Removing them took it to
Sharpe 6; moving to the 1-minute path took it to ~2. *The lesson generalises: any limit-entry
backtest run on the same bars that decide the exits is measuring intrabar ordering.*

A fourth check mattered less than expected — `through_ticks = 4` (requiring price to trade beyond
the limit, because an order resting at the exact low of a swing is the least likely to fill) costs
only ~0.02 of profit factor.

## The result

| variant | research PF / Sharpe | LOCKED PF / Sharpe | locked $/trade |
| --- | ---: | ---: | ---: |
| V9-PROP, market entry at next open | 1.08 / 0.66 | 1.17 / 1.23 | +12.34 |
| **V9 + resting limit (don55, 0.75×ATR5, 16 bars)** | **1.63 / 3.81** | **1.22 / 1.57** | **+24.44** |

Same Donchian breakout, same ADX gate, same ATR stop. **Only the fill changes.** Sharpe roughly
doubles on locked and the per-trade result doubles. The shape is correct — it decays research →
locked rather than improving.

Robust to cost: at a 2× stress the no-signal variant still runs 1.24 / 1.98.

## Parameters were taken from a plateau

25 cells swept on research only. `lim 0.75` sits in a flat region — 0.50 / 0.75 / 1.00 score within
0.05 PF at every Donchian length — and Donchian 55 beat 10 / 20 / 30 consistently across every
limit distance. Expiry 16 was taken instead of the better-scoring 24 because 24 sat at the edge of
the tested range.

Other plateau picks, on LOCKED, none of which was the pre-registered choice:

| config | locked PF | locked Sharpe | locked ret/DD |
| --- | ---: | ---: | ---: |
| don55 lim0.75 exp16 *(pre-registered)* | 1.22 | 1.57 | 1.46 |
| don30 lim0.75 exp16 | 1.28 | 1.85 | 2.39 |
| don55 lim1.50 exp16 | 1.29 | 1.57 | 2.88 |

They are within noise. **Selecting one of them now would be selecting on the locked block**, so the
shipped default stays the pre-registered pick and the table is published rather than pruned.

## The Donchian is retained by instruction, and it is not what earns the money

| trigger, all with the limit entry | research PF / Sharpe | LOCKED PF / Sharpe |
| --- | ---: | ---: |
| Donchian + ADX (V9's signal) | 1.34 / 2.26 | 1.19 / 1.30 |
| ADX ≥ 15 only | 1.38 / 2.95 | 1.24 / 1.97 |
| **no indicator at all** | 1.36 / 2.84 | **1.26 / 2.10** |

*(expiry 8, 1.0×ATR5, real costs — the like-for-like comparison run before the plateau sweep.)*

Removing every entry condition scored best on both blocks, and on a matched control the Donchian
trigger does not beat entering at a random bar with the same geometry (p 0.12–0.43). This
replicates the branch's standing result that **the mechanic substitutes for a signal rather than
complementing one**.

The user's instruction is to keep it, and that is a defensible trade: the Donchian roughly halves
the trade count, spaces entries out, and keeps the system recognisably a Turtle. The cost of
keeping it is about 0.04–0.07 profit factor and 0.3–0.5 Sharpe on the locked block. Recorded here
so the decision can be revisited on evidence rather than re-argued.

## What this is

Short-horizon mean reversion at the execution layer, exactly as `STUDY_LIMIT_ENTRY` described it:
worth little as a signal and a lot as a better fill on a trade you were making anyway. Two caveats
that do not go away:

- **Long only, on an instrument that rose 89% over the sample.** The earlier work found the
  mechanic pays on both sides, which argues against pure drift, but this configuration has not been
  tested short.
- **The fill rate is ~35%.** Two orders in three expire unfilled. The backtest assumes you keep
  placing them.

Shipped as `pine/turtle/V10_LIMIT_scalp_strategy.pine`.
