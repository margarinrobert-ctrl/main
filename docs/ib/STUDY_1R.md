# The 1R hunt: 8.5 million strategies, and what a 60% win rate is actually worth

`research/oner_hunt.py` → `oner_select.py` → `oner_book.py` → `oner_export.py`.

## The bound is not 50%

At a 1R target a driftless path wins 1/(1+R) = **50%**. That is the textbook number and it is the
wrong one to measure against. Three things move the real base rate:

* **Costs.** A round turn is about $5 on MNQ. Against a 1.0×ATR barrier that is a large fraction
  of the move, so it flips marginal wins into losses. The mean 1R win rate across three million
  live strategies is **47.3%**, not 50%.
* **Barrier width.** The same $5 is a smaller fraction of a 2.5×ATR move, so the base rate climbs
  with the stop. This is why every naive "60%+" list is dominated by 2.5×ATR stops — mechanics,
  not edge.
* **Drift.** NQ rose 89% over the sample, so a long barrier pair clears more often than a short.

Measured, on 60-minute bars:

| geometry | base win % | 95th percentile |
| --- | --- | --- |
| 2.5×ATR, hold, **long** | **54.16** | 59.90 |
| 2.0×ATR, hold, long | 53.43 | 59.56 |
| 1.0×ATR, hold, long | 50.04 | 55.70 |
| 2.5×ATR, hold, **short** | **45.54** | 51.66 |
| 2.5×ATR, flat 16:00, short | 42.79 | 49.00 |

**A long 2.5×ATR 1R strategy at 60% is roughly a one-in-twenty accident, and 156,219 of that exact
geometry were searched.** A short at 60% sits against a 45.5% base and is a completely different
claim. Ranking by raw win rate ranks by geometry.

## Does a 1R win rate persist out of sample?

The question the whole hunt turns on, measured inside each geometry so stop width and side are
held fixed:

```
Pooled: of 58,154 strategies clearing 60% on research,
        8,226 (14.1%) clear it on the locked block.

Base rate of clearing 60% on locked, unconditionally:  ~1.4%
Lift, by geometry bucket:                              3.5x to 46x
```

**This is the strongest persistence result on this branch** — the cross-timeframe filter managed
×1.57. A high 1R win rate is not a coin that came up heads; it carries forward.

It carries forward as a *win rate*, which at 1R is close to carrying forward as profit, but the
dollar amounts are small: individual survivors earn $500–$5,800 over three years on 85–140 trades.
Each one is a component, not a strategy.

## The book

Fourteen legs, selected on the **research block alone** — win rate ≥ 60%, positive excess over
their own geometry's base, profitable. The locked column was read once, afterwards.

| | |
| --- | --- |
| combined trades | 1,432 |
| **win rate at 1R** | **66.1%** (base ~47%) |
| net, one contract each | $41,734 |
| **locked block** | **$18,584** |
| book Sharpe | **4.30** |
| best single leg Sharpe | 2.16 |
| **book max drawdown** | **$1,118** |
| worst single leg drawdown | $1,143 |

Mean pairwise correlation **+0.01**, largest +0.42, 3 of 91 pairs above 0.3. The book's drawdown
is *smaller than its worst single leg's* — fourteen small edges that do not fail together, which
is the only reason the aggregate is interesting when no member of it is.

Eleven of the fourteen are **short**. That is the opposite of every prior finding here, and it
follows directly from scoring against geometry: shorts start from a 43–47% base, so clearing 60%
is a much larger excess than the same number from a long.

## What was wrong first, and got fixed

The first version of `oner_select.py` required `ls > 0 and exc_l > 0` — profitability and excess
on the **locked** block — as selection criteria. That puts the holdout inside the selection and
makes every locked figure downstream a restatement of the fit. It is the same error caught earlier
in this repository's direction-neutral filter, and it produced a book that looked slightly better
than the honest one ($17,248 locked against the corrected $18,584 — the corrected version is
*better*, which is luck, not vindication).

Selection is now research-only. The comment in the file says so, because the next person to add a
criterion will be tempted the same way.

## What this is not

The matched-null test saturates here — all ten of the first finalists returned p = 0.0025, which
is 1/401, which is "no random draw beat it". That is not evidence. These were **selected** from
8.5 million on exactly the statistic the null measures, and a null that does not know about the
selection cannot speak to it. The persistence table above is the honest test, and it is the one
to quote.

Trade counts are low (85–140 per leg), the sample is one instrument over one regime, and nothing
here has been traded.
