# The three mechanised supply/demand strategies from the third document

233,280 configurations, 7,712 seconds, 125,796 of them with at least 30 trades. Two entry
models (a reversal at the zone, and a break-and-retest), crossed with zone construction,
rejection-candle confirmation, buffers, targets, ages and direction. Research block = first 65% of
sessions, locked block read once. MNQ costs throughout.

## The verdict

| | |
| --- | --- |
| best on RESEARCH | $21,501 → **locked −$256** |
| best on LOCKED (hindsight) | $21,980 |
| **median locked** | **−$375** |
| positive on research | 50.0% |
| positive on locked | 43.8% |
| **positive on BOTH** | **26.2%** |
| BOS/CHoCH book, same locked block | **$8,932** |

The configuration chosen the only legitimate way — best on research, read once on locked — earns
**−$256**. A quarter of a million configurations produced nothing worth trading.

Walk-forward on that winner returns **1 negative fold of 6** and a stitched OOS of **$21,394**,
and a 5,000-path block bootstrap gives **P(net < 0) = 3.2%**. Both tests pass a configuration that
loses on the holdout. This is the same failure documented in `RESEARCH_PROTOCOL.md` §4c, now seen
on a third strategy family.

## The marginals, which are the useful part

Marginals average over every setting of everything else, so they are not selections on a single
cell.

| entry model | n | median locked | positive on both |
| --- | --- | --- | --- |
| reversal at the zone | 56,422 | −$716 | 20.8% |
| **break and retest** | 69,374 | **−$104** | **30.5%** |

| rejection confirmation | n | median locked | positive on both |
| --- | --- | --- | --- |
| none | 46,643 | −$457 | 23.3% |
| pin bar | 29,756 | −$657 | 23.0% |
| **engulfing** | 15,973 | **+$154** | **36.3%** |
| either | 33,424 | −$286 | 28.1% |

| zone origin | median locked | | base length | median locked |
| --- | --- | --- | --- | --- |
| any | −$374 | | 1 bar | −$411 |
| reversal (DBR/RBD) | −$595 | | 2 bars | −$305 |
| **continuation** | **−$129** | | 3 bars | −$411 |

Three things reproduce findings from elsewhere on the branch: **break-and-retest beats a
reversal entry**, **continuation-origin zones beat reversal-origin zones**, and **base length does
not matter**. The pin bar — the single most-cited confirmation candle in the retail literature —
is the *worst* of the four options.

## The one positive cell, and what happened when it was tested

The **engulfing** confirmation is the only cell in the entire marginal table with a positive
median locked P&L, at a lift of 1.39 over the sweep's own base rate. That is a concrete,
falsifiable claim, so it was applied to the two configurations that actually ship:

| | trades | net $ | PF | win % | research | LOCKED | maxDD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| preset A as shipped | 479 | **32,413** | 1.43 | 45.9 | **17,775** | **14,638** | 4,970 |
| preset A + engulfing | 427 | 21,459 | 1.34 | 44.0 | 8,108 | 13,350 | 4,585 |
| preset B as shipped | 294 | **14,284** | 1.33 | 55.8 | **5,825** | **8,459** | 4,930 |
| preset B + engulfing | 157 | 8,333 | 1.34 | 57.3 | 3,995 | 4,339 | **2,115** |

**It makes both presets worse on both blocks.** Preset B's drawdown halves and its profit factor
holds, so the filter is not destroying information — it is removing trades, and the ones it
removes were paying. **Not adopted.**

That is the whole value of the marginal: it generated one testable claim out of 233,280
configurations, and the test rejected it in four lines.

## Reproduce

```
python3 research/sd_battery.py     # 233,280 configurations, ~2 hours
```
