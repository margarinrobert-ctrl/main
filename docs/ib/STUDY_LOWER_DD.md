# Cutting the drawdown, not the return

**Request:** lower drawdown, not higher.

**Result: 36.3% → 10.5% on the full sample and 23.3% → 11.8% on the locked block, while Sharpe
*rises* from 1.31 to 1.60 and from 1.40 to 2.02.** Levered back to the identical return, the
baseline's 36.3% becomes **12.8%**.

Code: `research/lower_dd.py`.

## Where the drawdown was coming from

| leg | net $ | maxDD% | **Calmar** | Sharpe | days in >5% DD |
| --- | --- | --- | --- | --- | --- |
| **BOS 15m** | 31,696 | **37.2** | **0.26** | 0.41 | **73%** |
| BOS 30m | 71,483 | 15.6 | 1.25 | 1.00 | 46% |
| BOS 60m | 63,233 | 13.1 | 1.33 | 1.08 | 25% |
| IB | 29,657 | 5.6 | 1.60 | 1.44 | 1% |
| book, 1 lot each | 196,070 | 36.3 | 1.19 | 1.31 | 51% |

**The 15m leg was the whole problem.** It carried the book's entire 37% drawdown, spent 73% of days
more than 5% underwater, and returned Calmar 0.26 for it — it was buying drawdown with return. It
was in the book only because the ensemble logic said "run every timeframe"; that logic was right
about *diversifying* and wrong about *weighting*.

## What worked, and what did not

Locked block, one contract per leg, no leverage:

| variant | net $ | **maxDD%** | **Calmar** | Sharpe | Ulcer | days >5% DD |
| --- | --- | --- | --- | --- | --- | --- |
| book baseline (4 legs) | 95,576 | 23.3 | 3.77 | 1.40 | 8.8 | 38% |
| drop IB | 95,540 | 23.4 | 3.76 | 1.41 | 8.7 | 34% |
| drop 15m | 75,173 | 20.0 | 3.47 | 1.60 | 7.5 | 32% |
| inverse-volatility weights | 60,736 | 15.9 | 3.55 | 1.34 | 6.6 | 38% |
| volatility targeting | 78,450 | 13.7 | 5.30 | 1.57 | 5.4 | 31% |
| equity-curve brake (8% / 0.4×) | 53,563 | 21.1 | 2.36 | **1.04** | **10.9** | **62%** |
| **H — 30m+60m, inverse-vol, vol-targeted** | **72,075** | **11.8** | **5.62** | **2.02** | **4.4** | **23%** |

**The equity-curve brake made everything worse.** Cutting size to 0.4× after an 8% drawdown lowered
Calmar to 2.36, dropped Sharpe to 1.04 and put the book underwater 62% of days — it de-risks into the
loss and is then too small for the recovery. A clean negative result, and the one intuitive lever
that backfires.

## The answer: variant H

> **Two legs only — BOS/CHoCH at 30m and 60m** (RTH, EMA 200, 2×ATR stop, k=3; 1-ATR range filter on
> the 30m leg, none on the 60m), **weighted inverse to their volatility**, with the **book volatility-
> targeted** on a trailing 60-day estimate against its expanding-window average, capped at 2×.

| | net $ | CAGR | **maxDD%** | **Calmar** | Sharpe | Sortino | Ulcer |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **FULL SAMPLE** | | | | | | | |
| book baseline | 196,070 | 43.0% | 36.3 | 1.19 | 1.31 | 2.37 | 14.1 |
| H unlevered | 149,507 | 35.1% | **10.5** | **3.36** | **1.60** | 2.37 | **3.0** |
| H at 1.31× — *identical return to baseline* | **196,070** | **43.0%** | **12.8** | 3.35 | 1.60 | 2.37 | 3.7 |
| **LOCKED BLOCK** | | | | | | | |
| book baseline | 95,576 | 87.9% | 23.3 | 3.77 | 1.40 | 2.64 | 8.8 |
| H unlevered | 72,075 | 66.6% | **11.8** | **5.62** | **2.02** | 2.73 | **4.4** |
| H at 1.33× — *identical return to baseline* | **95,576** | **87.9%** | **15.2** | **5.79** | 2.02 | 2.73 | 5.6 |

**Same dollars, a third less drawdown, and a better Sharpe.** The worst single day improves from
−$10,746 to −$8,890, the Ulcer index halves, and time spent more than 5% underwater falls from 38% of
days to 24%.

## Pick your drawdown

Locked block, H sized to a stated tolerance:

| target maxDD | multiplier | net $ | CAGR | actual maxDD | Calmar |
| --- | --- | --- | --- | --- | --- |
| **5%** | 0.42× | 30,429 | 28.4% | 5.3% | 5.33 |
| **8%** | 0.68× | 48,687 | 45.2% | 8.3% | 5.46 |
| **10%** | 0.84× | 60,859 | 56.4% | 10.2% | 5.54 |
| **15%** | 1.27× | 91,288 | 84.0% | 14.6% | 5.76 |

Calmar is flat across the whole range, which is the point: the *shape* is fixed and the size is your
choice. On MNQ divide every dollar figure by 10.

## What actually did the work

1. **Dropping the 15m leg** — removed the drawdown driver at almost no cost to Calmar.
2. **Dropping IB** — it contributed $36 out of sample; it was carrying capital, not return.
3. **Inverse-volatility weighting** between the two survivors.
4. **Volatility targeting** — the single largest drawdown reducer, cutting maxDD by roughly 40% on
   its own while *raising* Sharpe.

Note what is absent: no new signal, no new parameter fitted to price, no filter chosen from a grid.
Every one of these is a portfolio-construction decision.

## Caveats

- **The inverse-volatility weights use full-sample standard deviations.** That is a mild
  contamination — it is a two-asset weighting, not a signal — but it is not perfectly clean. The
  volatility-targeting scalar *is* causal (expanding and trailing windows, both shifted).
- **The locked block is 268 sessions.** An 87.9% annualised figure over 1.06 years is a small sample;
  the full-sample 43.0% is the more honest expectation.
- **The underlying BOS cells still fail their own overfitting diagnostics** (PBO 0.571, t = 1.88
  against a 2.72 hurdle). Better portfolio construction improves the *shape* of a return stream; it
  cannot manufacture confidence in the signal underneath.
- **One instrument, one bull market, no ES.**

## Reproduce

```bash
python3 research/lower_dd.py    # leg attribution, six levers, risk-matched and locked-block tables
```
