# Fixing the false positive: which selection procedure actually transfers

The 1R strategy shipped earlier — `ATR falling AND close<5-bar low AND Tue` — was a false
positive. Deleting its weekday condition earned **more** money on 4.5× the trades. This is the
repair, and the repair itself had to be tested because the obvious fix made things worse.

## The head-to-head

`research/oner_procedures.py`. Five procedures, 14 de-duplicated legs each, same universe, same
trade-count floors. **Every one selects on the research block alone; the locked block is read
once at the end.**

| procedure | research $ | **locked $** | legs +ve on locked | mean research win | mean locked win |
| --- | --- | --- | --- | --- | --- |
| A ungated, by win rate | 96,385 | **704** | 7/14 | 74.9% | 54.4% |
| B + ban calendar conditions | 73,961 | **9,475** | 10/14 | 74.1% | 57.4% |
| **C + subset coherence** | 74,142 | **15,505** | **12/14** | 71.9% | 57.3% |
| D + geometry neighbours | 74,142 | 15,505 | 12/14 | — | — |
| **E ranked by worst-of-neighbourhood** | 19,202 | **−3,465** | **6/14** | 59.6% | 51.0% |

Three findings, and the third is the one worth keeping.

**Banning calendar conditions is worth $8,771 on the holdout.** Weekday and month conditions
partition the sample five or twelve ways and hand the search a free lottery; 12.5% of the rule
space contains one. Locked P&L goes from $704 to $9,475 and profitable legs from 7 to 10.

**Subset coherence is worth another $6,030.** Requiring that every subset of a rule also beats
its own base rate removes three-way interactions that exist only because 253,575 rules were
tried. 12 of 14 legs then hold up out of sample.

**The obvious over-correction is worse than doing nothing.** "The winner was an extreme tail
value, so rank by the worst score across its neighbourhood instead" sounds like exactly the right
lesson from the Tuesday failure. It takes the locked block from **+$15,505 to −$3,465** and
profitable legs from 12 to 6. Ranking by a minimum selects mid-distribution rules with no edge in
any direction. **The extreme tail was never the problem — the calendar condition inside it was.**

Procedure D changed nothing at all: subset coherence already implies geometry-neighbour
robustness, so the gate is dropped rather than kept for decoration.

## The book that comes out

Procedure C, then greedy decorrelation below |ρ| 0.25.

| | old (false positive) | new |
| --- | --- | --- |
| trades | 1,432 | 1,474 |
| win rate at 1R | 66.1% | 65.5% |
| net | $41,734 | **$73,501** |
| **locked** | $18,584 | $8,456 |
| book Sharpe | 4.30 | 3.48 |
| max drawdown | $1,118 | $3,741 |
| **legs profitable on locked** | not measured | **9 of 14** |
| calendar conditions | 1 of 14 legs | **none** |
| largest pairwise ρ | +0.42 | **+0.23** |

The new book earns more in total and less on the holdout. That is the honest trade: the old book's
locked figure came from legs sitting at the extreme of a win-rate distribution, and the one that
was handed over as a single strategy turned out to be a fitted weekday. The new one has no
calendar conditions, every rule's subsets are coherent, no pair correlates above 0.23, and 9 of
its 14 legs held up on data they were not chosen on.

Note the drawdown honestly: **$3,741 for the book against $3,128 for its worst single leg.**
Fourteen legs at one contract each is fourteen times the risk. Diversification flattens the
*ratio* — net/drawdown is 19.6 for the book against 14.1 for the best leg — not the drawdown.

## Style tags

Each leg is tagged from what it does, not what it is called: median holding time, whether it
crosses a session boundary, trade frequency, win rate, and whether its conditions are reversion
or breakout shaped.

```
swing 7 · long 12 · high win rate 14 · selective 14 · mean reversion 7
breakout 7 · scalping 4 · session timed 7 · intraday 3 · short 2 · flat by close 1
```

The page filters on these, combining with AND — `scalping + short` leaves 2 of 14.

Worth noticing what the tags reveal: **12 of 14 legs are long** and all 14 are "selective" (under
40 trades a year each). The long tilt is not automatically the §4c problem, because every excess
here is measured against the *long* base rate of 52–54% rather than against 50% — but a book that
is 12/14 long on a market that rose 89% is a fact to carry forward, not to file away.
