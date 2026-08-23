# The book under a live-fill execution model, and every test that follows from it

Five legs, each selected and validated separately: **BOS 30m**, **BOS 60m**, **supply/demand
preset A**, **supply/demand preset B**, **IVB**. This study charges them what a live account would
actually pay, then runs out-of-sample, walk-forward, three different Monte Carlos and portfolio
construction through that cost model rather than around it.

## 1. The execution model

The research engines charge a flat cost: 1 tick of spread + 1 tick of slippage **each side**,
1 extra tick when a stop fills, $1.00 commission per round turn. That is fair for MNQ in RTH and
optimistic everywhere else — which matters, because one leg takes **49% of its trades overnight**.

The overlay charges, on top, per side:

| condition | extra |
| --- | --- |
| overnight, 16:00–09:30 | **+1 tick** — MNQ quotes 2 ticks wide off-hours routinely |
| first / last 10 minutes of RTH | **+1 tick** — the fastest tape of the day |
| ATR above its 80th percentile | **+1 tick** — wide markets slip more |

Every charge makes every result worse; none is a free parameter.

| leg | trades | flat $ | realistic $ | cost | 2× overlay + $2 commission | cost | % overnight |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BOS 30m | 141 | 11,679 | 11,651 | −28 | 11,482 | −197 | 0% |
| BOS 60m | 45 | 7,574 | 7,565 | −9 | 7,511 | −63 | 0% |
| S/D A | 479 | 32,413 | 32,082 | **−331** | 31,272 | **−1,141** | **49%** |
| S/D B | 294 | 14,284 | 14,225 | −59 | 13,872 | −412 | 0% |
| IVB | 211 | 10,013 | 9,971 | −42 | 9,718 | −295 | 0% |
| **BOOK** | 1,170 | **75,962** | **75,493** | −469 | **73,854** | −2,108 | |

**Realistic fills cost the book 0.6%. Doubling the overlay and doubling commission costs 2.8%.**

### How wrong can the cost assumption be?

| extra ticks per side | BOOK $ | LOCKED $ |
| --- | --- | --- |
| 0 | 75,962 | 40,039 |
| 2 | 73,622 | 39,141 |
| 4 | 71,282 | 38,243 |
| 8 | 66,602 | 36,447 |
| 12 | 61,922 | 34,651 |

**Breakeven is at 65 extra ticks per side** — you would need to slip **16 points** on every entry
and every exit before this book stopped making money.

The reason is worth stating because it is the opposite of this branch's founding result. The
original study found that at scalping horizons the round turn is the same order of magnitude as
the signal, so cost decides everything. These legs average **$47–$168 per trade** on a $2/point
contract with multi-hour holds and ATR-scaled targets. **Execution is not the binding constraint
on this book.** Selection bias is.

## 2. Out of sample, under the realistic model

| leg | research $ | DD | Sharpe | LOCKED $ | DD | Sharpe |
| --- | --- | --- | --- | --- | --- | --- |
| BOS 30m | 2,741 | 2,713 | 0.65 | 8,910 | 1,316 | 1.70 |
| BOS 60m | 3,670 | 1,196 | 1.05 | 3,895 | 974 | 1.46 |
| S/D A | 17,608 | 3,773 | 1.68 | 14,474 | 4,672 | 1.60 |
| S/D B | 5,814 | 2,691 | 0.87 | 8,411 | 4,947 | 1.43 |
| IVB | 5,894 | 1,471 | 1.87 | 4,077 | 806 | 1.87 |
| **BOOK** | **35,726** | 4,371 | **2.26** | **39,767** | 6,477 | **2.77** |

Every leg is positive on both blocks.

## 3. Walk-forward — seven forward folds, nothing refitted

These configurations were each chosen once on the research block. Walk-forward here asks whether
the **same fixed rules** keep working forward. (Whether *re-optimising* works was settled earlier
on this branch: rolling re-optimisation earned $14,580 against fixed geometry's $27,253.)

| fold | BOS 30m | BOS 60m | S/D A | S/D B | IVB | **BOOK** |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1,763 | 94 | 733 | −944 | 1,419 | **3,064** |
| 2 | 2,311 | 883 | 1,007 | 569 | −149 | **4,621** |
| 3 | 548 | 980 | 1,520 | −142 | 749 | **3,655** |
| 4 | −2,543 | 1,663 | 11,035 | 4,039 | 2,784 | **16,979** |
| 5 | 2,188 | 1,986 | 5,136 | 4,365 | 260 | **13,934** |
| 6 | 4,489 | 2,667 | 7,006 | −3,070 | 2,441 | **13,533** |
| 7 | 3,099 | 58 | 3,296 | 6,790 | 1,748 | **14,991** |
| **negative folds** | 1 | 0 | 0 | **3** | 1 | **0 of 7** |

S/D B is negative in three folds of seven on its own and the book is negative in none — that is
the diversification doing its job, and it is also the reason to hold S/D B at a small size.

## 4. Monte Carlo — three different nulls

**a) Stationary block bootstrap** of daily P&L, 10,000 paths, mean block 20 days:
p5 **$22,178**, median $39,806, p95 $58,526, P(net<0) = 0.0%.

**b) Trade-order shuffle**, 449 locked trades, 10,000 orderings. The realised sequence drew down
**$6,477**; the shuffled median is **$4,706** and p95 is **$7,413**. So the order actually realised
was *worse than typical*, and the worst 5% of orderings cost only **$935** more drawdown. The
drawdown is not a fragile artefact of sequencing.

**c) Execution noise**, 0–3 extra ticks per side drawn at random per trade, 5,000 draws:
p5 $39,054, median $39,093, p95 $39,131. It barely moves, for the reason in section 1.

**What (a) does not prove.** Every bootstrap path is resampled from a market that rose through the
whole sample. `RESEARCH_PROTOCOL.md` §4c: a bootstrap cannot detect a regime bet, and P(net<0) =
0.0% should be read as "the sequencing is not the risk", never as "this cannot lose".

## 5. Portfolio construction

Weights fitted on the **research block only**, applied unchanged to the locked block. Contracts
are integers because a fifth of an MNQ does not exist.

| scheme | BOS 30m | BOS 60m | S/D A | S/D B | IVB | research $ | DD | Sh | LOCKED $ | DD | Sh |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 contract each | 1 | 1 | 1 | 1 | 1 | 35,726 | 4,371 | 2.26 | 39,767 | 6,477 | 2.77 |
| equal weight ×3 | 3 | 3 | 3 | 3 | 3 | 107,178 | 13,112 | 2.26 | 119,302 | 19,432 | 2.77 |
| inverse volatility | 2 | 3 | 1 | 1 | 3 | 57,594 | 7,984 | 2.37 | 64,622 | 9,131 | 2.91 |
| risk parity (corr-aware) | 2 | 3 | 3 | 3 | 3 | 104,437 | 12,689 | 2.28 | 110,392 | 18,132 | 2.75 |
| **return / variance** | **1** | **2** | **1** | **1** | **3** | 51,183 | 6,525 | 2.54 | **51,816** | **7,414** | **2.97** |

**Return/variance wins on every risk-adjusted measure**: locked Sharpe 2.97 and return-over-
drawdown 6.99, against 6.14 for one contract each. Equal-weight ×3 is not a better portfolio, it
is the same portfolio with leverage — identical Sharpe, three times the drawdown.

Note what it asks for: **3 contracts of IVB and 1 of S/D A**, even though S/D A earns three times
as much in total. IVB earns less per year and far less *per unit of volatility*, which is what
sizing should respond to.

## 6. What a live account actually has to carry

| legs simultaneously active | 0 | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- | --- |
| sessions | 322 | 287 | 221 | 73 | 13 | 6 |

- **Peak 8 contracts** at once under the chosen weights, on 6 sessions; 2.5 on an average
  trading day.
- At roughly $2,200 MNQ overnight initial margin, peak margin is about **$17,600**.
- Locked-block drawdown on those weights: **$7,414**.
- **An account of about $32,000** carries this without forced deleveraging. Below that, the peak
  margin and the drawdown collide.
- Of 224 active locked sessions, **55.8% positive**, best day +$4,793, worst −$2,699, and the
  **longest run without a winning session is 9**.

## 7. The honest list of what is still wrong with this

1. **Meta-selection.** Each leg passed its own holdout, but *which five legs are in the book* was
   decided by me, after seeing those results, on the same three years. The locked block has now
   been read many times across this branch. It is no longer a clean holdout for the book as a
   whole, only for each leg individually.
2. **One instrument, one sample, one regime.** All five legs are NQ, 2022-12 to 2025-12, a period
   in which the index roughly doubled. Three of the five have a demonstrable long tilt.
3. **The forward test is already running and it is not encouraging.** The supply/demand Pine on
   2026 data — outside this sample entirely — returned a loss over roughly four months at a trade
   rate above anything in the tested period. That is unexplained and it is live evidence, which
   outranks everything in this document.
4. **Concurrency is modelled as independent legs.** Five engines each managing their own position
   can hold offsetting trades at once and pay both spreads. A live implementation should net them.
5. **No contract-roll cost.** Quarterly rolls are not charged anywhere in this repository.

## Reproduce

```
python3 research/book.py        # every leg's trades with execution metadata
python3 research/live_sim.py    # the overlay, OOS, walk-forward, Monte Carlo, portfolio
```
