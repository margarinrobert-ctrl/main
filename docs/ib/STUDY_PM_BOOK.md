# What is holding the profitability goal down, and the book that clears it

`research/pm/` — `pm_book.py`, `run_p1.py`, `run_p2.py`.

Asked as a portfolio manager would ask it rather than as a researcher: not *does this rule beat its
control*, but *why is this programme not producing a tradeable return, and what does it take*.

## The diagnosis, in three layers

**1. Arithmetic.** Every leg on this branch earns **+0.04 to +0.08 R** (`STUDY_V31_MONTECARLO`), and
the minimum detectable effect at any realistic trade count is *larger than that*
(`STUDY_US30_SCALP_0711` §10: MDE 10.74 points against a PF-1.2 requirement of +10.61, with
`E[max t | noise]` over a search already exceeding the detection threshold). **No single-strategy
search on this data can confirm a single strategy.** That is why forty studies end "ships nothing" —
it is a property of effect size against sample size, and more searching makes it worse, not better,
because it raises the noise floor the winner has to clear.

**2. The wrong question was being asked at the wrong level.** The branch puts a *research* question
to each *leg* ("does it beat its matched control") and gets **no**, every time. `STUDY_ALLOCATION`
put the *portfolio* question to the *book* ("does it beat zero") and got
**P(mean ≤ 0) 0.0000–0.0012 on every arm**. Both answers are correct. A book of N near-uncorrelated
legs has Sharpe ≈ `s·√N / √(1+(N−1)ρ)`, and on this branch ρ is not only small but **stable** —
pairwise leg correlation transfers research-to-reserved at **+0.7051**, the most transferable
quantity ever measured here.

**3. A construction defect, and this one is fixable.** `STUDY_ALLOCATION` built its book on a
**global** research cut — `min` over legs of each leg's own research end = **2021-12-17** — which is
set by a *single* leg (APM_VWAP/US30). Every NQ leg begins 2022-12-27, a **year after it**. So the
one object on this branch that clears zero was built on **11 of 23 legs**, excluding the two
highest-scoring strategies in `STUDY_TOP5` — **FTM_ORB/NQ** (+6.38 %/yr) and **V56_CVD/NQ** (+7.94) —
for a calendar bookkeeping reason and not an evidential one.

## The fix is the honest construction anyway

Drop the global cut. Give every leg its **own** availability date: a leg may enter the book only on
dates *after its own research block ends*, which is exactly what a desk does — you cannot trade a
strategy before you have developed it. That admits all 23 legs, and as a side effect it **removes the
caveat `STUDY_ALLOCATION` had to attach to its own headline** ("a leg whose research block extends
past the cut had its parameters chosen inside the book's reserved window, so the absolute level is
not a clean out-of-sample number for the legs"). Under per-leg availability **every daily return in
this book is out of sample for the leg that produced it.**

| book | days | yrs | %/yr | vol | **Sharpe** | maxDD | ret/DD |
|---|---|---|---|---|---|---|---|
| **all 23, equal weight** | 1,173 | 4.65 | **+3.70** | 2.30 | **+1.611** | 2.28 | **+7.56** |
| all 23, causal inverse-vol | 1,173 | 4.65 | +2.27 | 1.38 | +1.646 | 1.08 | +9.76 |
| 11 legs (the published cut) | 1,173 | 4.65 | +3.26 | 2.25 | +1.451 | 2.28 | +6.67 |

**Fixing the construction is worth +0.16 Sharpe** (1.451 → 1.611) and +13% of return, on the same
calendar, with nothing fitted. Day-block bootstrap on the 23-leg book: mean/day **+0.0147%**,
**P(mean ≤ 0) = 0.0010**, 95% CI [+0.0061, +0.0242].

## The return is a leverage decision, not a strategy decision

Unlevered the book earns **+3.70%/yr at 2.30% vol** with a realised max drawdown of 2.28% and an
**MC p99 drawdown of 3.91%** (1.72× realised — this branch has measured that ratio at 1.2–3.5× in
every study that ran the permutation, and it is the number to size against).

| target | leverage | ann vol | realised DD | **MC p99 DD** |
|---|---|---|---|---|
| 5 %/yr | 1.35× | 3.10% | 3.08% | 5.28% |
| 10 %/yr | 2.70× | 6.21% | 6.16% | 10.56% |
| **15 %/yr** | **4.05×** | 9.31% | 9.24% | **15.85%** |
| 20 %/yr | 5.41× | 12.41% | 12.32% | 21.13% |
| 30 %/yr | 8.11× | 18.62% | 18.48% | 31.69% |

**A drawdown tolerance picks the row.** There is no configuration search anywhere in this repository
that changes this table; only ρ and N do.

## The ceiling, and it is not leg count

Mean pairwise leg correlation **+0.0387** over 253 pairs. Mean solo leg Sharpe, **zero-filled over
its own live calendar**, **+0.380**. Then `s·√N / √(1+(N−1)ρ)`:

| N legs | predicted book Sharpe |
|---|---|
| 11 | 1.070 |
| **23** | **1.340** (measured: **1.611**) |
| 40 | 1.518 |
| 100 | 1.729 |
| ∞ | **1.93** |

Theory and measurement agree within the error bar, and the answer is blunt: **adding more legs of
this kind cannot take the book past Sharpe ≈ 1.9, however many are added** — 23 → 200 legs buys
1.34 → 1.82. **The lever is ρ, not N.** A genuinely independent asset class is worth more than any
number of further equity-index strategies, and the registry names three that are absent from disk
(XAUUSD 5m, EURUSD 30m, BTCUSDT 15m — gold correlates 0.057–0.070 with the indices).

**One measurement error of my own, caught here and worth carrying**: the first pass measured solo leg
Sharpe on each leg's **active days only**, giving **+1.132** and predicting a book Sharpe of 3.99
against a measured 1.61. Zero-filled it is **+0.380** — a factor of **2.98** — and the prediction
lands. A leg that trades twenty times a year prints a large ratio on those twenty days and
contributes almost nothing over 252. `CLAUDE.md`'s standing rule, violated in the first draft of the
very calculation that exists to price it.

## What this is not

These post-research spans have been read before — by `STUDY_TOP5` and `STUDY_ALLOCATION` — so this
is a **descriptive re-read of spent blocks, not a fresh pre-registered test**, and no p-value here
should be quoted as one. Four further qualifications stay attached:

- **Sharpe 1.611 ± 0.527**, 95% CI **[0.58, 2.64]** over 4.65 years. Real, and wide. A Sharpe
  standard error falls only with **time**, not with more searching — which is the whole reason the
  single-strategy programme cannot be rescued by effort.
- **The full-book era is short.** On the 414 days where ≥ 20 of 23 legs are live (2024-11-28 →
  2026-08-25) the book reads **+1.85%/yr at 1.54% vol, Sharpe +1.199 ± 0.781**, bootstrap
  P(mean ≤ 0) 0.0315. Positive, and it cannot separate 1.2 from 1.6 or from 0.4.
- **85.1% of days are underwater.** This is a grinding book, not a comfortable one.
- **Drop-one says 7 of 23 legs subtract**, the worst being VWAP_DRIFT/US100 (+0.076 Sharpe if
  removed), IBS_SESSION/US30 (+0.072) and TFI/US30 (+0.054) — the US30 legs again, reproducing
  `STUDY_ALLOCATION`'s finding that the legs its selection dropped were all US30. Acting on that
  ranking is selection on the same data; `STUDY_ALLOCATION` already walked it forward and found leg
  *selection* clears a random-subset null at the **99.5th percentile** while leg *weighting* clears
  nothing.

## The recommendation

1. **Trade the book, not the leg.** It is the only object here that clears zero, and the leg-level
   verdicts that keep coming back negative are answering a different question.
2. **Use per-leg availability.** It is both more honest and worth +0.16 Sharpe.
3. **Size from the MC p99 column**, not the realised drawdown.
4. **Stop searching for a better single strategy on these four feeds** — the MDE says it cannot be
   confirmed, and the ceiling says it would not move the book much if it could.
5. **The one thing that raises the ceiling is a lower-ρ asset class.** Re-uploading gold, FX and
   crypto is worth more than any further parameter search on this branch.
