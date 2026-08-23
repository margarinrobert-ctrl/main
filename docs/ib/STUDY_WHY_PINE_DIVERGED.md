# Why two strategies failed on TradingView and the third did not

Reported: the Initial Balance script reproduces on TradingView; the IVB and supply/demand scripts
do not. Three strategies from the same repository, written by the same process, on the same
instrument — two fail and one works. That is a controlled experiment, so it was treated as one
rather than guessed at.

## The answer

**Line 280 of `NQ_InitialBalance.pine`:**

```pine
nyMin = hour(time, TZ) * 60 + minute(time, TZ)
```

**`NQ_IVB.pine` and `NQ_SupplyDemand.pine` used the bare built-ins instead:**

```pine
barMin = hour * 60 + minute
```

Pine's bare `hour` and `minute` are in the **exchange** timezone. CME's is **America/Chicago**.
Every figure these scripts were validated against comes from research in **New York** time. The
one script that reproduces is the one that named its timezone; the two that failed both ran an
hour late.

### What that was worth, measured

| | correct | buggy | cost |
| --- | --- | --- | --- |
| **IVB** — opening window shifted +60 min | $13,244 | **$2,080** | **−84%** |
| **Supply/demand preset A** — 4H bars anchored to Chicago midnight | $32,413 | **$13,298** | **−59%** |
| *Initial Balance, if it had had the bug* | $2,495 | **−$171** | **−107%** |

The supply/demand figure is the more striking one. Anchoring the 4-hour aggregation to Chicago
midnight instead of New York midnight produces a bar set that shares **0 of 4,744 timestamps**
with the correct one. The buggy version was not a slightly different strategy; it was building
zones from an entirely different set of bars.

And the last row closes the loop: the Initial Balance strategy is *not* intrinsically more robust.
Give it the same bug and it goes from $2,495 to **−$171**. It reproduced because it did not have
the bug.

## Two hypotheses that were tested first and falsified

Recording these because they were the obvious ones and both are wrong.

**1. "Close-threshold rules are more data-sensitive than limit orders."** The Initial Balance
strategy arms a limit order at a computed level; IVB and supply/demand fire when a bar's close
crosses a threshold. It seemed likely that a tick of disagreement between data vendors would flip
close-threshold signals and leave limit fills alone.

Every bar's OHLC was moved by a Gaussian with a 0.5-tick standard deviation — smaller than the
real disagreement between two futures vendors — over 40 draws:

| | baseline | mean | sd | worst | coefficient of variation |
| --- | --- | --- | --- | --- | --- |
| IVB (close crosses a level) | 13,244 | 13,179 | 271 | 12,547 | **0.02** |
| Initial Balance (limit order) | 2,495 | 2,522 | 41 | 2,437 | **0.02** |
| Supply/demand (zones + close) | 32,413 | 32,376 | 297 | 31,764 | **0.01** |

All three are equally immune, and all three stayed profitable in 100% of draws. **Price-level
disagreement is not the problem.**

**2. "The hand-built 4H aggregation drifts."** Shifting when a zone becomes visible by up to three
hours costs supply/demand 1%, 3% and 7%. Also not the problem — it is the bar *boundaries* that
matter, not the visibility offset, which is why the proper test above shows 59%.

## The property that made this possible

The perturbation table and the shift table together say something worth keeping:

**These strategies are robust to what the price is and fragile to when it is.**

Half a tick on every bar costs 2%. Fifteen minutes on the session boundary costs **81%** of IVB
and **53%** of Initial Balance:

| opening window shift | IVB | Initial Balance |
| --- | --- | --- |
| +15 min | −81% | −53% |
| +30 min | −62% | −85% |
| +60 min | −84% | −107% |

Time is exactly the dimension in which two implementations differ — timezones, session
definitions, bar anchoring, what counts as the first bar of a day. **A strategy family this
sensitive to the clock will fail to port unless the clock is specified explicitly**, and none of
these should be trusted on a chart whose session handling has not been checked against the
research.

## The deeper failure, which was mine

The Pine scripts were "verified" by building a Python mirror of the intended Pine and checking it
against the research engine. Both are mine. **That verification can only catch errors in my
transcription of the strategy — it cannot catch errors in my model of what Pine does**, because
the mirror encodes exactly the same beliefs.

The timezone bug is invisible to it by construction: the mirror computes minute-of-day from a
New-York-localised index because that is what I assumed Pine did. So does the engine. They agreed
perfectly, and both were wrong about TradingView.

The Initial Balance numbers did not come from that process. `ib_sim.py` is an **independent
reimplementation** of a TypeScript engine — not a port — and the two agree exactly across 1,413
trades on every entry index, exit index, side, price and P&L. Two implementations built from a
spec, agreeing, is evidence. One implementation checked against a model of itself is not.

Two real defects have now been found only when a script met the actual compiler and a real chart:
the entry-gate bug in the BOS script (worth 35 trades and −$8,318) and this one. Both were
invisible to every test in this repository.

**What follows from that:** a mirror check is necessary and not sufficient. The remaining
verification gap can only be closed against TradingView itself, which is what the diagnostic
tables in these scripts are now for.

## What is fixed, and what to do

All three scripts now take an explicit timezone input defaulting to `America/New_York`, with an
`"exchange"` option kept so the difference can be seen on a chart. Both failing strategies should
be re-tested with it.

Two things remain unexplained by the timezone bug and should be held in mind when re-testing:

1. **The test periods are outside the research sample.** The reported runs covered 2026 and, in
   one case, back to 2020. The research is 2022-12 to 2025-12. Fixing the clock does not make
   those in-sample.
2. **The IVB run had Script execution set to 4 of 4.** Every rule in these scripts reads a bar's
   close; the intrabar options replace `close` with the running price. That is worth more than the
   timezone bug on its own, and the IVB statistics table now shows runs-per-bar in red when it
   detects it.

## Reproduce

```
python3 research/robustness.py     # the perturbation test and the specification-shift test
```
