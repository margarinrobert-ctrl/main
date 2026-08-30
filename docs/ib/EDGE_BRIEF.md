# The brief to give me when you want an edge found

Paste the block below. Everything in it is calibrated to what this branch has already measured —
the targets are the three things that have shown a real effect, the exclusions are families that
have each burned a full study, and the protocol is the set of gates that have caught every false
positive here so far.

Two things to know before you use it. **It is written to fail loudly**: most runs under this brief
will end in "no edge found", and that is the intended behaviour, because the alternative is the
110,250-configuration sweep that bought +0.098 R against the un-swept starting point's +0.097.
And **it will not produce a big profit factor**. A high PF on this data has always meant a small
trade count or an unrun control.

---

## THE BRIEF

```
Find an edge. Follow this protocol exactly; it is designed so that a negative result is a
successful run.

PRE-REGISTER BEFORE YOU LOOK AT ANYTHING
Write these five things down first, in your reply, before running any code:
  1. The hypothesis, as one falsifiable sentence naming a MECHANISM, not a pattern.
  2. The exact control it must beat.
  3. The success threshold, as a number, decided now.
  4. The block you will read once, and when.
  5. What result would make you abandon the hypothesis.
Anything you compute before those five exist is exploratory and cannot be used as evidence.

WHERE TO LOOK — these three have measurable effects on this branch, unlike anything else
  A. THE ENTRY MECHANIC. A resting limit 1.0xATR below is worth +0.24 to +0.43 R/trade across four
     markets, against a best-ever SIGNAL of +0.043 R. It is the largest effect ever measured here,
     it is monotone, and it mirrors exactly for stop entries. The open question is not whether it
     works but WHERE it stops working: it is additive on a null signal and substitutive on a good
     one, and the fill rate is ~35%. Find the boundary.
  B. MEAN REVERSION. Nine independent routes have now landed here, most recently momentum entering
     a ridge model at -0.19 and tsmom120 monotone-negative on both blocks. Build the hypothesis ON
     that, not against it.
  C. THE EXIT GEOMETRY. Every control that has eaten a result was beaten by the exits, not the
     signal. That means the exits are where the edge already is. Attack them directly rather than
     searching for another trigger to bolt on.

WHERE NOT TO LOOK — each cost a full study; do not re-run without new data
  momentum/RSI/MACD confirming a breakout (a breakout IS a momentum event; MACD>0 already passes
  95-98% of entries) · volume profile / auction (0 of 172 survived) · Initial Balance · the
  trend-pullback family (5.7M combinations, 0 survivors) · calendar conditions as SEARCH axes ·
  MA type or length as a degree of freedom · position sizing · partial exits · take-profit
  optimisation (no-target has won ten times) · intraday scalping constraints (failed seven times) ·
  PEAD or the variance risk premium (not computable from OHLCV — say so instead of proxying).

THE GATES, in this order. Stop at the first one that fails and report the failure.
  1. LEAKAGE. Truncation-audit every feature: recompute on history ending at bar i, require the
     value to match. Read features at the SIGNAL bar, never at ent_bar.
  2. THE MATCHED CONTROL, RUN AS A GATE AND NOT A FINAL CHECK. Random entry, same side, same
     geometry, same exits, same costs, same minute-of-day distribution, matched on TRADE COUNT with
     the rate computed against ELIGIBLE bars. If the rule does not beat it on the research block,
     stop. Do not proceed to a holdout.
  3. POPULATION BEFORE RANKING. Report the share of the grid that is profitable before you report
     any top row, and read every axis by its MARGINAL average. If an axis runs to the edge of the
     grid, say so and do not extend the grid afterwards.
  4. COST STRESS. Re-run at 1.5x and 2x the assumed spread. Every candidate on this branch has died
     at 1.5x. If yours does too, that is the result.
  5. ONE HOLDOUT READ, after the rule is frozen. Passing on locked while FAILING on research is a
     DEFECT, not a result — say so if it happens.
  6. CROSS-MARKET, with the trigger overlap measured first. 68% of NQ's signals fire on the same
     15-minute bar as US100's; a second feed over the same calendar is not a second test.

SUCCESS IS THIS, AND NOTHING ELSE
  Beats its matched control on the research block AND on a held-back market, at p <= 0.05 on both,
  survives 1.5x spread, and has a coherent neighbourhood (a plateau, not a spike). Report the
  effect in R and in points. Profit factor alone is not evidence and neither is a bootstrap against
  zero — clearing a control and clearing zero are different questions and I want both reported.

HOW TO REPORT
  Lead with whether the hypothesis survived. If it died, say what killed it and at which gate.
  Do not soften a negative, do not present a research-block number as a finding, and do not
  recommend a configuration you did not put through every gate. If a result is one market, one
  block, or under 100 trades, say that in the same sentence as the number.
```

---

## Two variants worth having

**When you want breadth rather than a single hypothesis**, replace the WHERE TO LOOK block with:

```
Run a NULL AUDIT instead of a search. Take a family this branch has not falsified, generate its
full declared grid, and report only: the share profitable, the marginal average per axis, the
correlation between research and locked cell scores, and how many cells beat their control against
how many are expected by chance. Recommend nothing. The deliverable is the shape of the
population, not a configuration.
```

**When you have new data** (bid/ask, a release calendar, a new instrument), prepend:

```
This data has never been used on this branch. Before any strategy work, do the inventory: format,
delimiter, exact row count and span, derived clock WITH its evidence, measured defects, and a
sha256 — then add it to research/datasets.py. Then re-run the ONE question that data unlocks,
stated before you look at it.
```

---

## What this brief cannot fix

The binding constraint is not the prompt. **Spread is assumed in all six feeds**, and every
candidate measured here dies at 1.5× the assumption, so no result on this data is distinguishable
from zero on execution grounds. A brief cannot manufacture quotes. If you want the odds of finding
something real to rise materially, supply bid/ask, a longer sample, or a second asset class — in
that order.
