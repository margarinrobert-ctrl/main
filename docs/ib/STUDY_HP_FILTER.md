# The Hodrick-Prescott momentum strategy, and the 70× leak it invites

Source: QuantConnect, *The Momentum Strategy Based On The Low Frequency Component Of Forex
Market* (Jing Wu, June 2018), implementing Harris & Yilmaz, *A momentum trading strategy based on
the low-frequency component of the exchange rate*, JBF 33(9), 2009.

**Method.** Decompose price with a Hodrick-Prescott filter into trend + cycle, keep the trend (the
"low-frequency component"), and apply an MA(m, n) crossover to **that** rather than to price. Long
when the trend turns up, short when it turns down. λ = 100, MA(1, 2), daily bars.

**The published result is already negative** — Sharpe −0.309 to 0.480 across six FX pairs,
10–15 trades in six and a half years, drawdowns 19–53%. The note is honest about why:

> "the entry of new data into the filter model can cause the trend line to change the trend
> through past data, makes it harder to identify the trend accurately"

That sentence is the reason this study exists. `research/hpfilter.py` implements both readings.

## The trap: HP is a two-sided filter

The HP trend solves `min Σ(y−x)² + λΣ(Δ²x)²` **jointly over the whole series**, so the fitted x_t
depends on y at t+1, t+2, … Run it once over a price history and the resulting "trend" is not a
signal — it is a partial answer key. Applied causally (re-solved every bar on a trailing window,
keeping only the endpoint) it is legitimate.

The two differ by more than a rounding error: on a random walk their one-bar **changes** — which
is what the MA rule reads — correlate only **0.685**.

## What that is worth, measured

MNQ, 2022-12-27 → 2025-12-11, 765 daily RTH bars, 1 contract, itemised fees plus one tick each side.

| daily, λ=100, MA(1,2) | fills | net $ | Sharpe | max DD $ |
| --- | ---: | ---: | ---: | ---: |
| **causal** (rolling refit, endpoint only) | 116 | **8,893** | **0.43** | 10,284 |
| **full-sample** (one solve, leaky) | 42 | **83,789** | **3.95** | 4,949 |

**9.4× the money and 9× the Sharpe, from the filter alone.** Note the leaky version also trades
*less* (42 fills vs 116) — knowing the future removes the spurious turns.

On this repo's own timeframes it stops being subtle:

| | fills | net $ | Sharpe | max DD $ |
| --- | ---: | ---: | ---: | ---: |
| 30m causal | 8,033 | **−7,480** | **−0.18** | 13,987 |
| 30m full-sample | 2,059 | **+519,532** | **12.96** | **1,031** |
| 60m causal | 3,948 | **−2,883** | −0.07 | 9,410 |
| 60m full-sample | 1,046 | **+384,489** | **9.07** | **1,024** |

A **Sharpe of 12.96 with a $1,031 drawdown, on a strategy that actually loses money.** The
drawdown collapsing by 93% while profit multiplies is the tell: no real edge produces an equity
curve that smooth.

## The causal strategy, judged on its own

| | net $ | Sharpe | max DD $ |
| --- | ---: | ---: | ---: |
| buy and hold, 1 contract | **24,796** | **1.12** | 10,798 |
| HP causal MA(1,2) λ=100 | 8,893 | 0.43 | 10,284 |

It earns **a third of buy-and-hold at 40% of the Sharpe**, with a drawdown larger than its own net
profit, on a sample where NQ rose 89%. Against a control that flips position the same number of
times on random days: **p = 0.238**. It does not beat random.

Intraday it is outright negative. The published null replicates.

## The parameter surface is the diagnostic

The note reports sensitivity "in a non-monotonic way". Confirmed independently — research-block
net $, causal:

| | MA(1,2) | MA(1,3) | MA(1,4) | MA(1,5) | MA(1,6) | MA(1,8) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| λ=10 | −2,661 | 524 | −951 | −740 | −2,688 | 2,190 |
| **λ=100** | **4,232** | −756 | −398 | 2,284 | 1,540 | −1,734 |
| λ=1600 | −6,347 | −8,415 | −6,858 | −5,307 | −5,837 | −2,664 |
| λ=6400 | −2,348 | −2,405 | 1,301 | 1,145 | −1,388 | −3,316 |
| λ=10000 | −2,246 | −1,527 | 657 | 314 | −902 | −3,310 |

**19 of 30 cells are negative**, and the shipped setting's immediate neighbours are −756 and
−2,661. λ=100/MA(1,2) is a coincidence, not a mechanism.

Now the same grid under the leak:

| | MA(1,2) | MA(1,3) | MA(1,4) | MA(1,5) | MA(1,6) | MA(1,8) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| λ=10 | 56,790 | 50,385 | 49,413 | 49,443 | 45,261 | 34,001 |
| λ=100 | 48,028 | 41,665 | 40,293 | 36,254 | 35,013 | 36,495 |
| λ=1600 | 32,069 | 31,243 | 32,388 | 33,355 | 33,976 | 32,139 |
| λ=6400 | 23,449 | 23,430 | 24,023 | 24,794 | 24,348 | 17,332 |
| λ=10000 | 15,322 | 15,250 | 14,965 | 16,934 | 17,211 | 16,626 |

**30 of 30 positive, smoothly ordered, every cell a good strategy.** That contrast is the reusable
result:

> **If every cell of a parameter surface is profitable, suspect look-ahead before celebrating.**
> A real edge is a ridge on a noisy surface. A leak is a plateau.

λ=10 leaks *most* ($56,790) because a small λ tracks price closely — so the "trend" is nearly the
price series itself, future included.

## What this generalises to

Nothing here is specific to Hodrick-Prescott. Every **zero-phase / two-sided / centred** smoother
has the same property, and each is one library call away from being used as a signal:

* `scipy.signal.filtfilt` — forward-backward, zero phase **by construction**
* centred moving averages, `pandas.rolling(center=True)`
* LOESS / Savitzky-Golay over a symmetric window
* wavelet denoising with symmetric boundary extension
* `seasonal_decompose`, STL, and most "trend extraction" utilities
* any full-series `scipy.optimize` fit used as a per-bar feature

The rule: **a filter is only a signal if bar t's value would be unchanged had the series ended at
bar t.** `research/hpfilter.py::leak_check` is that test — recompute on a truncated series and
compare.

## Verdict

The strategy does not work here, causally, on any timeframe tested — which agrees with the note's
own conclusion and with Harris & Yilmaz's caution. It is **not** added to the book.

What is worth keeping is the measurement: this branch now has a case where the difference between
a legitimate and an illegitimate implementation of the *same published method* is **−$7,480
against +$519,532**, and where the illegitimate one looks like the best strategy ever tested here.
That is the fourth leakage trap found on this branch, after `ent_bar`, the IVB `session_index`
look-ahead, and ranking feature importance over both blocks.
