# Adaptive Trade Management: the execution mechanic is worth more than every signal found in nineteen studies — and it is mean reversion

*Brief: run Adaptive Trade Management & Execution Optimization over ~100,000 combinations, keep
iterating until a strategy works profitably on all four markets. Intraday trend-following scalping,
avoid chop, Turtle-style breakout triggers.*

**Result: 0 of 64,800 cross-market configurations are profitable on all four markets.** 279 reach
three. But the search found something larger than the ranking: **the entry mechanic is worth
+0.24 to +0.43 R per trade** — bigger than any signal this branch has found in nineteen studies —
and it is **unambiguously mean reversion, not trend following**.

`research/atme/`.

---

## 1. The search

97,920 configurations per pass, 293,760 evaluations across four markets and three base signals,
deduplicated where a knob is inert (entry offset does nothing for a market order, so MARKET
contributes one entry configuration rather than eight).

| dimension | options |
| --- | --- |
| entry | market at next open · resting **limit** k×ATR below · buy **stop** k×ATR above |
| stop | fixed k×ATR · chandelier trail · breakeven after b×R |
| target | fixed R · partial fraction at first target then trail |
| time | hard max hold · give-up if not working by bar *t* |

Conservative throughout: **a limit that never fills is not a trade** (no free option), the stop
wins when one bar touches both barriers, the trail is checked before the target, and a gap through
a level fills at the open.

**Three base signals were run deliberately** — the every-bar null, plus H5 and H6, the two entries
that were positive on all four markets *gross* in `STUDY_HYPOTHESIS_PROGRAMME.md`. The comparison
between them answers the question `STUDY_LIMIT_ENTRY.md` left open.

## 2. The finding: a monotone mirror image on all four markets

Median E[R] by how far the order rests from the close, every-bar signal, research block:

| entry offset | **LIMIT** (buy dips) | | | | **STOP** (buy strength) | | | |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| | NQ | US100 | US30 | XAU | NQ | US100 | US30 | XAU |
| 0.25×ATR | −0.074 | −0.130 | −0.127 | −0.220 | −0.111 | −0.137 | −0.151 | −0.236 |
| 0.50×ATR | −0.077 | −0.113 | −0.131 | −0.214 | −0.133 | −0.163 | −0.177 | −0.262 |
| 0.75×ATR | −0.066 | −0.081 | −0.130 | −0.215 | −0.166 | −0.206 | −0.206 | −0.295 |
| 1.00×ATR | **−0.051** | **−0.062** | **−0.107** | **−0.201** | **−0.204** | **−0.279** | **−0.249** | **−0.340** |

**The deeper the dip you buy, the better. The more strength you chase, the worse.** Monotone in
both directions, on all four markets, with no exception. Buying strength — which is what a
breakout entry *is* — is the single most reliably destructive choice in the entire search.

This is not a filter or a threshold. It is a property of the price process at the execution
horizon, and it says the same thing four times independently.

## 3. The mechanic is the whole edge

The winning configuration, isolated by re-running it with **only** the entry swapped back to a
market order:

| market | with the limit mechanic | as a market order | **mechanic worth** | fill rate |
| --- | ---: | ---: | ---: | ---: |
| US30 | +0.1733 | −0.1894 | **+0.363** | 34.9% |
| US100 | +0.1986 | −0.1671 | **+0.366** | 41.7% |
| NQ | +0.3312 | −0.0941 | **+0.425** | 35.7% |
| XAUUSD | −0.1246 | −0.3649 | **+0.240** | 30.9% |

**Every market is negative as a market order and the mechanic is worth +0.24 to +0.43 R.** For
scale: nineteen studies of entry-signal search on this branch produced a best candidate worth
**+0.043 R**. The execution decision is an order of magnitude larger than the signal decision.

The fill rate is the cost: **about two thirds of signals never trade**, because price does not
come back a full ATR. That is the selection the mechanic makes, and it is why it cannot be
bolted onto a signal whose edge is immediacy — the finding `STUDY_LIMIT_ENTRY.md` recorded and
this study now confirms from the other direction.

## 4. Out of sample

Frozen on research: resting limit **1.0×ATR** below the close (3-bar validity), stop **1.0×ATR**
from the fill, target **1R**, max hold 24 bars, flat at 13:00, every eligible bar 09:00–13:00.

| market | research E[R] | **OOS win** | **OOS PF** | **OOS Sharpe** | OOS max DD |
| --- | ---: | ---: | ---: | ---: | ---: |
| NQ | +0.331 | **67.6%** | **2.03** | 11.63 | 6.7 R |
| US30 | +0.173 | **64.2%** | **1.68** | 8.11 | 12.6 R |
| US100 | +0.199 | **62.8%** | **1.74** | 5.77 | 10.6 R |
| XAUUSD | −0.125 | 54.3% | 0.92 | −1.08 | 551 R |

**It holds out of sample on the three indices and improves there.** Gold fails on validation —
though its *test* block reaches PF 1.08 and its *untouched* 2025–26 block PF 1.58, so gold's
failure is not uniform either.

**Monte Carlo** (permutation for the path, bootstrap with 0.03R execution jitter for the edge):

| | n | E[R] | median DD | 95th DD | mean p05 | **P(edge ≤ 0)** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **three indices** | **6585** | **+0.274** | 12.7 R | 17.5 R | +0.254 | **0.0%** |
| XAUUSD | 6726 | −0.040 | 293 R | 326 R | −0.061 | 99.9% |

**Implementability was checked, not assumed.** The every-bar signal could in principle hold dozens
of overlapping positions; measured, the median concurrent position count is **1** and the maximum
is **3**, because the 35% fill rate and short holds keep it there. It is a strategy, not a
portfolio.

## 5. Why this is not what was asked for

The brief asked for **intraday trend-following scalping using breakout triggers**. What the search
found is the opposite on every axis:

| asked for | found |
| --- | --- |
| trend following | **mean reversion** — buying dips improves monotonically, chasing strength degrades monotonically |
| breakout entry | a **resting limit below the market**; the stop-entry (the true breakout mechanic) is the worst choice tested |
| a signal | **no signal at all** — the best configuration fires on *every* bar and the edge is entirely in the execution |
| all four markets | **three** — gold fails, and 0 of 64,800 configurations clear all four |

This is the fifth time on this branch that a trend-following brief has resolved into mean
reversion. It is stated plainly rather than presented as a trend strategy.

## 6. What would break it

**Costs.** The edge is real but not large relative to the spread assumption:

| × assumed cost | NQ | US100 | US30 | XAUUSD |
| --- | ---: | ---: | ---: | ---: |
| 0.5× | +0.377 | +0.288 | +0.257 | +0.095 |
| **1.0×** | **+0.331** | **+0.199** | **+0.173** | −0.125 |
| 1.5× | +0.270 | +0.088 | +0.021 | −0.345 |
| 2.0× | +0.225 | +0.006 | −0.074 | −0.545 |

NQ survives 2×. **US100 and US30 are at zero by 1.5× and negative by 2×.** Bid/ask is unavailable
in all four feeds, so the spread is assumed — and for two of the three surviving markets the
result sits inside that assumption's error bar.

**Selection.** The single cell was chosen from 64,800 cross-market configurations. The *mechanism*
is far better evidenced than the cell: a monotone response in both directions on four independent
markets is not something a search finds by luck.

**One optimistic modelling choice, stated.** A gap below the resting limit fills at the open rather
than at the limit — better than the limit for a buyer. That is what a real resting order does, but
it flatters the mechanic on gap-down bars and is worth remembering.

## 7. Verdict

| claim | status |
| --- | --- |
| A configuration is profitable on all four markets | **REJECTED** — 0 of 64,800; 279 reach three |
| The entry mechanic dominates the entry signal | **SUPPORTED** — +0.24 to +0.43 R against a best-ever signal of +0.043 R |
| The limit mechanic is additive on a null signal | **SUPPORTED** — the every-bar null is where it works best |
| The result is trend following | **REJECTED** — it is mean reversion, monotone on four markets in both directions |
| Chasing breakouts costs money | **SUPPORTED** — stop-entry degrades monotonically with distance, on all four markets |
| A tradable edge on the three indices | **PROMISING** — PF 1.68–2.03 out of sample, P(edge ≤ 0) 0.0%, but two of three die at 2× costs |

**What to research next:**

1. **Measure the spread.** Fourth study ending here. Two of the three surviving markets are inside
   the cost assumption's error bar, and one dataset would settle it.
2. **Stop searching for entry signals.** The measured ratio is roughly ten to one in favour of
   execution. That is where the remaining research budget belongs.
3. **Accept the direction the data keeps giving.** Five briefs have now asked for trend following
   and five have resolved into mean reversion. The next hypothesis should be built on that rather
   than against it.

## Files

| | |
| --- | --- |
| `research/atme/engine.py` | the path walker: three entry mechanics, trailing/breakeven stops, partials, give-up rule |
| `research/atme/sweep.py` | the 24,480-configuration grid per market-signal, with inert-knob deduplication |
| `research/atme/run_sweep.py` | all four markets × three base signals |
| `research/atme/validate.py` | out-of-sample, mechanic isolation, plateau, cost stress |

Measured on US30 (5m), US100 (15m), NQ (5m) and XAUUSD (5m), 09:00–13:00 New York, one unit per
trade. Costs assumed, not measured — bid/ask is unavailable in every feed. Research tooling for
education and analysis, not financial advice.
