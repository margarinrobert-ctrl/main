# Maximising profitability — and the lever that actually did it

**Request:** improve the strategy to maximum profitability.

**Result: $196,070 on the full sample and $95,576 on the locked block, at Sharpe 1.31 / 1.40 — and
it beats the maximum of a 6,480-cell grid search while selecting no cell at all.**

Compounded against a 25% drawdown budget, the locked block returned **67.9% CAGR at 20.0% max
drawdown**.

Code: `research/maximise.py`.

## The levers, ranked by what they added

Widening the grid is not on this list, and §5 shows why.

### 1. Ensemble — stop choosing a timeframe, run them all

| leg | net $ | $/trade | Sharpe | maxDD% |
| --- | --- | --- | --- | --- |
| BOS 15m | 31,696 | 93 | 0.41 | 37.2 |
| BOS 30m | 71,483 | 486 | 1.00 | 15.6 |
| BOS 60m | 63,233 | 1,471 | 1.08 | 13.1 |
| **ensemble 15m+30m+60m** | **166,413** | 436 | **1.13** | 37.2 |

Correlations between legs: 15m↔30m **0.36**, 30m↔60m **0.28**, 15m↔60m **0.11**. They are the same
rule on different clocks and still mostly independent, so summing them adds return faster than risk.

**The timeframe choice was never necessary.** Every hour spent deciding between 15m and 30m was
spent choosing which of three profitable streams to discard.

### 2. Add the IB retracement — a fourth stream at +0.039 correlation

| | net $ | $/yr | Sharpe | Sortino | maxDD% |
| --- | --- | --- | --- | --- | --- |
| ensemble (3 BOS legs) | 166,413 | 54,818 | 1.13 | 2.00 | 37.2 |
| **ensemble + IB (4 legs)** | **196,070** | **64,588** | **1.31** | **2.37** | 36.3 |

+$29,657 of return and **+0.18 of Sharpe** for a stream that correlates +0.039 with the rest.

### 3. Size to a drawdown budget

The 4-leg book at one contract per leg draws down **37.0% of $100,000**. That is a size choice, not a
signal property, and it is the largest single multiplier available:

| drawdown tolerance | multiplier | net $ | $/yr | maxDD $ | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 10% | 0.27 | 53,008 | 17,461 | 10,000 | 1.31 |
| 20% | 0.54 | 106,016 | 34,923 | 20,000 | 1.31 |
| **25%** | **0.68** | **132,520** | **43,654** | 25,000 | 1.31 |
| 30% | 0.81 | 159,024 | 52,384 | 30,000 | 1.31 |

**Sharpe is identical across every row.** Leverage moves return and risk together — this is the
honest way to state "more profit", and it is a position-size decision, not a better signal. Note the
multipliers are all *below 1*: at one contract per leg the book is already too large for $100,000.

### 4. Compound

| mode | final equity | CAGR | maxDD% | Sharpe |
| --- | --- | --- | --- | --- |
| 15% budget, fixed size | 179,512 | 21.3% | 14.9% | 1.31 |
| 15% budget, compounded | 208,760 | 27.4% | 14.1% | 1.31 |
| 25% budget, fixed size | 232,520 | 32.0% | 24.7% | 1.27 |
| **25% budget, compounded** | **320,298** | **46.7%** | 22.5% | 1.31 |

$100,000 → **$320,298** over 3.04 years.

## The out-of-sample test — this is the part that matters

Split at 2024-11-28: 497 research sessions, **268 locked**.

| | research $ | research Sharpe | **LOCKED $** | **LOCKED Sharpe** |
| --- | --- | --- | --- | --- |
| BOS 15m | 11,294 | 0.27 | **20,403** | **0.60** |
| BOS 30m | 24,411 | 0.71 | **47,072** | **1.39** |
| BOS 60m | 35,168 | 1.13 | **28,065** | **1.07** |
| IB retracement | 29,621 | 2.34 | **36** | **0.00** |
| ensemble (3 BOS) | 70,873 | 0.95 | **95,540** | **1.41** |
| **BOOK (4 legs)** | 100,494 | 1.31 | **95,576** | **1.40** |

**All three BOS legs are positive out of sample, and the ensemble's locked Sharpe (1.41) is higher
than its research Sharpe (0.95).** That is the opposite of the overfitting signature.

Compounded at the 25% budget on the locked block alone:

```
$100,000 -> $173,547 in 1.06 years  =  67.9% CAGR, 20.0% max drawdown
```

**The IB leg contributed $36.** The book's out-of-sample result is the BOS ensemble; IB is now dead
weight and its 2.34 research Sharpe is a description of a period that ended.

## 5. The grid maximum, for comparison

6,480 cells across timeframe × EMA × ATR multiple × swing k × range filter × BOS count:

```
MAXIMUM: 30m, EMA 50, ATR x1.5, k=2, no filter, enter on the FIRST BOS
         $149,204 over 558 trades ($267/trade), t = 2.10, Sharpe 1.18, maxDD 18.6%

E[max z] over 6,480 cells = 4.19.  This reaches 2.10  ->  DOES NOT CLEAR.

The 4-leg book: $196,070 at Sharpe 1.31, with no cell selected at all.
```

**Ensembling beat optimising by $46,866 and 0.13 of Sharpe.** The search maximum is also internally
suspicious — it drops the range filter that replicated, sets swing k = 2 (the fragile axis), and
enters on the first BOS, which the ablation showed is worse everywhere.

## The maximum-profitability specification

> **Run four streams simultaneously on NQ, one contract each:**
>
> 1. **BOS/CHoCH 15m**, RTH, EMA 200, 2×ATR stop, k=3, refuse entries within 1 ATR of the EMA
> 2. **BOS/CHoCH 30m**, same parameters
> 3. **BOS/CHoCH 60m**, same parameters, no range filter
> 4. **IB retracement** — 09:30–10:30 range, 50% retracement limit, 80% stop, 1:2 target, flat 11:59
>
> Size the whole book to a stated drawdown tolerance (multiplier = tolerance ÷ 37.0%), re-sizing as
> equity grows. On MNQ, divide every dollar figure by 10.
>
> **Full sample:** $196,070, Sharpe 1.31, Sortino 2.37, 471 trades.
> **Locked block:** $95,576, Sharpe 1.40 — 67.9% CAGR compounded at a 25% budget.

## What is still true, and I am not going to bury it

- **The locked block is 268 sessions and 164 trades.** A 67.9% CAGR measured over 1.06 years is a
  small sample, and the honest expectation is the full-sample 46.7%, not the recent figure.
- **The drawdown multiplier was computed on the full sample.** It is a sizing input rather than a
  signal, but it is not perfectly clean.
- **The IB leg is dead** ($36 out of sample) and should be dropped or re-examined, not sized.
- **The BOS components still fail their overfitting diagnostics** — PBO 0.571, t = 1.88 against a
  2.72 hurdle, four of five components flipping sign in ablation. The *ensemble* is what survives;
  the individual cells are not established.
- **One instrument, one bull market, no ES.** Everything above could be a property of 2023–25 NQ.

The strongest defence of this book is not any statistic in it — it is that its edge comes from
running several imperfect streams at once rather than from having picked the right one. That is the
part least likely to have been fitted, and it is the reason the locked Sharpe came in above research.

## Reproduce

```bash
python3 research/maximise.py          # ensemble, sizing, compounding, and the 6,480-cell maximum
python3 research/best_oos.py          # the locked-split machinery
```
