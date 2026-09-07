# Supply/demand zones and Wyckoff, tested

Two documents were supplied: a 5-page supply-and-demand piece in the Sam Seiden lineage, and a
14-page Wyckoff summary. The request was to find sources supporting supply/demand as a proven
profitable strategy. What follows is what the literature actually says, and what the rules actually
do on three years of NQ.

## What the documents contain

The **supply/demand document has no testable rule in it** — no zone-construction algorithm, no
entry, no stop, no target, no sample, no cost model. It asserts *"The answer is yes, supply and
demand trading strategies work. It is profitable"* and then, two sentences later, *"You cannot
predict future supply and demand based on current observable supply and demand."* Those cannot both
be true. It does make one falsifiable claim — that a zone **weakens with each test** — which is
tested below.

The **Wyckoff document is better**: the accumulation schematic (PS, SC, AR, ST, Spring, LPS, SOS
across phases A-E) contains at least one mechanical, falsifiable pattern in the **spring**. It
contains no statistics.

## What the literature actually supports

The academic evidence for level-based trading is real and it is worth knowing precisely what it
covers, because it is **not** what these documents teach.

- **Kavajecz & Odders-White (2004), RFS.** Support and resistance levels coincide with **peaks in
  depth on the limit order book**. The framing matters: technical levels do not cause reversals,
  they *locate liquidity already resting there*. This is the strongest support for the premise, and
  it is a statement about an order book, not about rectangles drawn on a chart.
- **Osler (2003), Journal of Finance.** Using actual currency stop-loss and take-profit order data:
  take-profit orders cluster at **round numbers**, stop-loss orders cluster **just beyond** them.
  This explains both why trends stall at levels and why they accelerate through them. Again: round
  numbers — observable, unambiguous, not hand-drawn.
- **Park & Irwin (2007), Journal of Economic Surveys.** Of 92 modern studies, 58 positive, 24
  negative, 10 mixed — with the caveat that most positive results are compromised by data snooping,
  ex-post rule selection and inadequate cost treatment. **Sullivan, Timmermann & White (1999)**
  is the demonstration: DJIA technical rules lost significance once search size was accounted for.

So the supporting evidence is for **liquidity clustering at objectively-defined levels**. Extending
it to discretionary zones is an extrapolation the papers do not make.

## Test 1 — supply/demand zone retest, 53,924 configurations

Mechanised: a BASE of k consecutive bars each with range ≤ base_max × ATR, then a DEPARTURE bar of
range ≥ dep_min × ATR closing away from it; the base's high..low becomes the zone; entry when price
returns into it. Swept over base length, base tightness, departure size, zone age, test count,
stop, target, side, freshness and three timeframes. Same costs, session gate, 2×ATR stop and 2R
target as the BOS/CHoCH book, so the numbers are directly comparable.

| | |
| --- | --- |
| best on RESEARCH | $17,806 → **LOCKED −$3,808** |
| best on LOCKED (hindsight, unattainable) | $16,663 |
| **median locked** | **−$779** |
| positive on research / locked / **both** | 34.7% / 36.4% / **15.3%** |
| BOS/CHoCH 2R book, same locked block | **$8,932** |

The configuration that looks best in research **loses money out of sample**. The median
configuration loses money. Fewer than one in six is positive on both blocks — worse than a coin
flip on two independent draws.

## Test 2 — "a zone weakens with each test"

The one falsifiable claim the document makes, measured directly by tagging every entry with which
test of that zone it was:

| test number | $/trade | win % |
| --- | --- | --- |
| 1st test | −$12 | 33.1% |
| 2nd test | −$0 | 35.5% |
| 3rd test | +$7 | 35.3% |
| 4th and later | −$12 | 35.0% |

**No decay.** The win rate *rises* from the first test to the second and then sits flat. If
anything the third test is the best of them. The claim is not supported in either direction — the
test number carries no information.

## Test 3 — the Wyckoff spring, 279 configurations

A trading range of tr_n bars spanning ≤ tr_max × ATR, then a bar whose low pierces the range low
and whose close returns inside it (upthrust mirrored for shorts).

| | |
| --- | --- |
| best on RESEARCH | $4,406 → **LOCKED $989** |
| best on LOCKED (hindsight) | $8,595 |
| **median locked** | **−$4** |
| positive on both blocks | 13.6% |

Essentially zero. Not harmful, not an edge. The best honestly-selected configuration returns about
a ninth of what the existing book does on the same block.

## Test 4 — round numbers, and a confound I walked into

Round numbers are the version of "levels" that Osler's order-flow data actually supports, so they
deserved a direct test.

**No clustering of extremes.** Within 2 points of a round hundred: 3.99% of highs, 3.39% of lows,
against 4.00% expected under uniformity. Lows are *below* chance. No barrier effect on NQ.

**Volatility after a crossing looked strong** — forward 3-hour |move| of 83.2 points after an
up-cross and 90.6 after a down-cross, against 61.0 with no crossing, at t = +6.94 and +9.50. That
appeared to reproduce Osler's second prediction directly, and it was reported that way for about a
minute.

**It does not survive its control.** Crossing a round number means the bar *just moved*, and
volatility clusters. Crossers had moved 0.982 ATR on the signal bar against non-crossers' 0.425 —
the two groups were never comparable. Matched on the bar's own move:

| bar move (ATR) | n cross | n no-cross | fwd move, cross | fwd move, no cross | t |
| --- | --- | --- | --- | --- | --- |
| 0.00-0.25 | 174 | 2,403 | 1.290 | 1.279 | +0.12 |
| 0.25-0.50 | 451 | 1,731 | 1.253 | 1.209 | +0.66 |
| 0.50-0.75 | 579 | 1,086 | 1.271 | 1.212 | +0.88 |
| 0.75-1.00 | 488 | 590 | 1.170 | 1.333 | −2.17 |
| 1.00-1.50 | 617 | 336 | 1.388 | 1.449 | −0.69 |
| 1.50-2.00 | 264 | 80 | 1.658 | 1.656 | +0.01 |

Noise. The entire raw effect was volatility clustering wearing a round number's clothes. **A t of
+9.50 became +0.01 under a single obvious control** — which is the most useful thing in this
document, and a reminder that a large t-statistic on an unconditioned comparison is not evidence of
anything.

## Verdict

Nothing in either document produces an edge on this data. The supply/demand zone rule fails at
53,924 configurations; its one falsifiable claim about zone decay is not supported; the Wyckoff
spring is indistinguishable from zero; and the round-number effect the literature would predict
does not survive a volatility control.

The honest reconciliation with the academic evidence: **Kavajecz & Odders-White and Osler are about
limit-order-book depth and FX round numbers.** Neither is what these documents teach, and neither
can be tested from 30-minute OHLC bars on a single index future. The mechanism they document may
well be real; the retail method built on top of it, as specified here, is not tradeable on NQ.

Reproduce with `python research/supply_demand.py`.
