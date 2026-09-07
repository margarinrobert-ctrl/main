# A second engine: vectorbt, and what a 100× speedup is actually worth

`research/` adds a Python research layer built on numba and vectorbt. It was added to find more
edge. What it found first was a flaw in how edge was being measured.

## 1. The cross-check: two engines, one answer

`research/ib_sim.py` is an independent reimplementation — written from the stated rules and from
reading the TypeScript engine's semantics, in a different language with a different array layout,
not ported. The point of a second implementation is that disagreement is evidence of a bug.

They agree **exactly**:

| configuration | trades | expectancy | total P&L | mismatched fields |
| --- | --- | --- | --- | --- |
| retr 50 / stop 80 / 1:2 | 167 | 0.3248R | $29,657 | 0 |
| retr 25 / stop 80 / 1:1 | 349 | 0.0963R | $37,409 | 0 |
| retr 50 / stop 70 / 1:1.5 | 167 | 0.3364R | $20,134 | 0 |
| retr 10 / stop 60 / 1:3 | 508 | 0.0112R | $7,053 | 0 |
| retr 40 / stop 100 / 1:1 | 222 | 0.0637R | $4,212 | 0 |

1,413 trades, matching on every entry index, exit index, side, entry price, exit price and P&L. The
largest disagreement anywhere is 5e-7 in R, which is the six-decimal rounding of the CSV used to
compare them.

That validates far more than the strategy. It validates the **hand-rolled DST rule** in `clock.ts`
against the IANA database, the **resting-limit trade-through** semantics, the **pessimistic intrabar
rule**, the **cost model** and the **tick-snapping arithmetic** — all at once, and independently.

Speed: **0.89 ms per full backtest over 113,816 bars**, roughly 1,100 a second against a TypeScript
engine that took minutes for a few thousand.

## 2. What the speed is not for

vectorbt's headline feature is sweeping millions of parameter combinations. This project has already
measured that as harmful — `STUDY_SEARCH_CURVE.md` found a pre-specified configuration earning
0.312R against a searched one's 0.278–0.343, and re-optimising the IB geometry turned $27,253 into
$14,580.

**A faster search does not fix an overfitting problem. It makes it cheaper to have.** So the speed
went into validation that was previously unaffordable: CSCV at 16 blocks (12,870 splits), a
stationary block bootstrap at 10,000 resamples, and the search-width curve at enough resolution to
see its shape rather than its first two points.

## 3. The finding: the objective was hiding the overfitting

Draw W configurations, pick the best on the first 70% of bars, record where it ranks on the last
30%. 700 draws per width, 1,308 configurations.

**Selecting on mean R:**

| width | holdout percentile | median holdout R | % of picks with R:R ≥ 3 |
| --- | --- | --- | --- |
| 1 | 49.3 | 0.032 | 25% |
| 16 | 78.1 | 0.102 | 33% |
| 64 | 93.6 | 0.167 | 42% |
| 128 | 98.5 | 0.263 | 53% |
| 512 | 98.5 | 0.263 | **96%** |

Read alone, that says search harder — the winner lands in the 98th percentile and stays there.

**Selecting on dollars, same configurations, same draws:**

| width | holdout percentile | median holdout $ | % of picks with R:R ≥ 3 |
| --- | --- | --- | --- |
| 1 | 50.4 | $942 | 23% |
| 16 | 67.1 | $3,697 | 29% |
| 64 | 78.8 | $5,923 | 34% |
| 256 | 88.5 | $8,177 | 45% |
| **512** | **45.0** | **−$90** | 64% |

**The curve is non-monotonic, and only the dollar version shows it.** Selection is genuinely
informative up to a point — the holdout percentile climbs from 50 to 88 — and then collapses the
moment the search is wide enough to converge on the global in-sample optimum. At that point the
winner is a *below-median* configuration out of sample that loses money.

The mechanism is in the last column. R divides by the stop distance, so a configuration with a tiny
stop books large multiples on very few trades. A search maximising mean R converges on exactly those
— 96% of its picks are the widest reward-to-risk setting — and mean R never registers the failure
because the failure is in trade count and dollars, not in the ratio.

This is the same trap found in `STUDY_ASIA.md`, where the best Asia candidate showed **E = +0.351R
with total P&L of −$707**. It has now appeared twice from different directions. **R-multiples
flatter; dollars tell the truth.**

Confirming the mechanism: restricting the grid to both-sides configurations (480 instead of 1,308)
moves the collapse *earlier*, to width 256 — because 256 of 480 is a larger share of the grid, so
the search converges on the global optimum sooner.

| width | holdout percentile | median holdout $ |
| --- | --- | --- |
| 64 | 86.7 | $8,177 |
| 128 | 79.6 | $5,923 |
| **256** | **44.2** | **−$90** |

The turning point is not a property of the number 256 or 512. It is a property of **what fraction of
the grid the search has seen.**

## 4. PBO, and what it cannot see

| objective | S = 10 | S = 12 | S = 16 |
| --- | --- | --- | --- |
| mean R | 0.171 | 0.181 | 0.331 |
| dollars | 0.222 | 0.242 | 0.172 |

All well below the 0.5 that marks a procedure selecting pure noise, and far below the 0.968 the gap
fade produced. That is a real difference between strategies, not a contradiction — but two cautions
belong next to it:

- **The objective changes the answer here too** (0.331 against 0.172 at S = 16), for the same reason
  as section 3. A PBO quoted without its objective is under-specified.
- **PBO measures rank consistency across blocks, so it is blind to any bias present in every
  block.** NQ rose through all sixteen. A direction filter that is pure drift-fitting looks perfectly
  stable to CSCV, which is precisely why the longs-only filter was rejected in
  `STUDY_IB_SCREENSHOT.md` on a research/holdout split rather than on PBO.

## 5. The validated configuration, re-tested

Stationary block bootstrap, 10,000 resamples, mean block length 5 — resampling blocks rather than
individual trades so serial dependence survives:

> ib 60 / retr 50 / stop 80 / fixed 1:2 / both sides — n = 167, mean **+0.3248R**,
> 95% CI **[+0.1614, +0.4895]**, P(mean ≤ 0) = **0.0000**

Holding up under a dependence-preserving bootstrap is a real result, and it is the same number the
TypeScript engine reports, from different code.

## 6. What this changes

- **Every future search in this repo should select on dollars, not on mean R.** The R objective is
  measurably biased toward small-denominator, low-frequency configurations, and it hid a collapse
  that the dollar objective made obvious.
- **Search width has a turning point, and it is measurable.** Below it selection adds information;
  above it selection destroys value. It arrives at a fraction of the grid, not a fixed count.
- **The two engines are now a standing check.** `research/crosscheck.py` compares them trade-for-
  trade, so a future change to either that alters behaviour will show up as a mismatch rather than
  as a slightly different number nobody notices.

## Caveats

- One instrument, three years, one regime.
- The grid is 1,536 configurations of one strategy family. The turning point's *location* is
  specific to this grid; its *existence* is the transferable part.
- vectorbt is used for the analytics layer (returns accessor, drawdown decomposition, risk ratios),
  not for the simulation. The simulation is ours precisely so it can be checked against the
  TypeScript engine.
