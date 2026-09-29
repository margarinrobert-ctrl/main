# Pooling the 07:00-11:00 New York window across US30, US100 and NQ

`STUDY_US30_SCALP_0711` sections 8-11 established that the obstacle in this window is **statistical
power and not the rule**: per-trade dispersion of 157.1 points on a mean of +0.683, a research-block
minimum detectable effect of 10.74 points a trade, and a best-of-1,176-cells t of 1.348 against the
2.802 detectability requires and a search noise floor of 3.301. Its named next step was to pool the
window across the two other index feeds, on the arithmetic that three markets triple the trade count
and take the MDE from 10.74 to roughly 6.2 points — bringing PF 1.1 (+5.53 points) inside the
sample's resolution for the first time.

This is that execution, and nothing else. No new search: **54 pooled cells**, declared before any
read, plus **three cells read once on the holdouts**. `research/us30team/`.

**The short answer: pooling bought the power it promised and did not bring the effect into
resolution, because the effect shrank faster than the error bar did.** The MDE fell from 0.1849 to
0.1340 ATR a trade — 5.73 to 4.15 US30 points, better than the 6.2 predicted — and the pooled mean
fell from US30's +0.0481 to +0.0184, so the t-statistic went **down**, 0.729 to 0.386. The reason is
structural and is measured in §4: **0 of 54 cells are positive on all three markets**, and the three
markets are really two, because 85.3% of NQ's signal bars are US100 signal bars at the identical
timestamp.

---

## 1. The data, and three clocks re-derived rather than inherited

`python research/datasets.py` first. `US30_1m`, `US30_5m` and `US100_15m` are MISSING; the three
feeds used here are on disk and verified identical to the studied copies. **`NQ_1m` is stamped in
UTC and every other feed on this branch is already New York** — a loader that forgets to convert
puts a 09:30 window at 04:30, which has bitten this branch before — so NQ is loaded through
`nqdata.load_bars` (tz-aware UTC → New York), the tz then dropped, and resampled 1m → 15m.

Mean bar range by minute-of-day must peak at minute 570 = 09:30 New York. That is the branch's
standing positive control for a feed's offset, and it is re-run here on all three:

| market | source | bars (15m) | span (New York) | sessions | peak minute | = | RTH / overnight range |
|---|---|---|---|---|---|---|---|
| US30 | `US30_LONG_15m` | 193,942 | 2016-10-26 → 2025-07-15 | 2,704 | **570** | 09:30 | 3.67x |
| US100 | `US100_LONG_15m` | 206,703 | 2016-11-14 → 2025-10-01 | 2,747 | **570** | 09:30 | 4.07x |
| NQ | `NQ_1m` → 15m | 70,685 | 2022-12-26 → 2025-12-11 | 923 | **570** | 09:30 | 4.20x |

All three pass. A peak at minute 270 would have meant the NQ conversion had not happened.

**Blocks are each market's own first 70% of sessions**, because the spans barely overlap:

| market | research cut | research sessions | holdout sessions |
|---|---|---|---|
| US30 | 2022-12-04 | 1,892 | 812 |
| US100 | 2023-02-08 | 1,922 | 825 |
| NQ | 2025-01-22 | 646 | 277 |

**NQ_1m begins 2022-12-26, so NQ's entire history sits inside the other two markets' holdout
calendar.** The pooled research block is therefore three market-specific blocks, not one calendar —
US30 and US100 contribute 2016-2022 and NQ contributes 2023-2025. That is stated as a property of
the design rather than hidden, and §3 shows it cuts both ways: it makes NQ's contribution nearly
independent of the other two, and it means the pooled estimate averages over different regimes.

---

## 2. What the window costs on each market, and why a point barrier is not one barrier

In-window (07:00-11:00) research-block medians:

| market | median price | median ATR(14) | ATR as % of price | round turn | **cost / ATR** |
|---|---|---|---|---|---|
| US30 | 26,499 | 31.00 | 0.117% | 2.29 pts | **7.39%** |
| US100 | 8,310 | 13.63 | 0.164% | 1.215 pts | **8.92%** |
| NQ | 18,918 | 22.82 | 0.121% | 1.72 pts | **7.54%** |

The three are within 1.5 points of one another as a fraction of volatility, which is what makes them
poolable at all. Cost as a fraction of the stop, and the driftless break-even it implies at 1:3:

| stop | US30 in ATR | cost/risk | BE 1:3 | US100 in ATR | cost/risk | BE 1:3 | NQ in ATR | cost/risk | BE 1:3 |
|---|---|---|---|---|---|---|---|---|---|
| 30 pts | 0.97N | 7.63% | 26.91% | **2.20N** | 4.05% | 26.01% | **1.31N** | 5.73% | 26.43% |
| 50 pts | 1.61N | 4.58% | 26.15% | **3.67N** | 2.43% | 25.61% | **2.19N** | 3.44% | 25.86% |
| 100 pts | 3.23N | 2.29% | 25.57% | **7.34N** | 1.22% | 25.30% | **4.38N** | 1.72% | 25.43% |

**The declared points grid is a different geometry on every market.** 30 points is a 0.97 ATR stop on
US30 and a 2.20 ATR stop on US100 — not a tighter version of the same trade, a different trade.
`STUDY_TURTLE_15M` recorded the same error in its cross-market form (NQ's 1.72-point round turn
charged in gold's points, reported as PF 0.35). The grid was therefore run **twice**: once in points
exactly as declared, and once at the same distances expressed as ATR multiples fixed on US30's
research median ATR of 31.00, so the geometry is matched:

    30 pts on US30 = 0.968N  ->  US30  30.0 pts   US100  13.2 pts   NQ  22.1 pts
    50 pts on US30 = 1.613N  ->  US30  50.0 pts   US100  22.0 pts   NQ  36.8 pts
   100 pts on US30 = 3.225N  ->  US30 100.0 pts   US100  43.9 pts   NQ  73.6 pts

Everything is pooled in **ATR units at the signal bar** (primary, and immune to `STUDY_US100`'s
synthetic-level caveat on NQ) and in **percent of entry price** (secondary — NQ's stored levels are
a back-adjusted continuous contract, so percent is inflated there and ATR units are not).

---

## 3. The overlap matrix — the number that decides whether pooling buys anything

`STUDY_TREND_LONG` measured 68% of NQ's triggers firing on the exact same 15-minute bar on US100.
Measured here on the Donchian-20 long in the 07:00-11:00 window, over the span each pair **shares**:

| pair | shared span | n(a) | n(b) | same bar a→b | b→a | within ±2 bars a→b | b→a |
|---|---|---|---|---|---|---|---|
| **NQ / US100** | 1,006 d | 1,201 | 1,252 | **85.3%** | **81.9%** | **93.8%** | **93.7%** |
| NQ / US30 | 929 d | 1,135 | 1,042 | 32.0% | 34.8% | 56.2% | 58.7% |
| US100 / US30 | 3,163 d | 3,663 | 3,267 | 38.6% | 43.3% | 59.4% | 65.0% |

**NQ and US100 are the same index on two feeds, and worse than the branch's recorded figure — 85.3%
of NQ's in-window breakout bars are US100 breakout bars at the identical timestamp, 93.8% within two
bars.** Adding NQ to US100 is not adding a market. US30 is the genuinely separate object at 32-39%.

Inside the pooled **research** sample the picture is different, and only because of the calendar
accident in §1:

| pair | shared research span | same bar | ±2 bars | shared research dates |
|---|---|---|---|---|
| NQ / US100 | 37 d | 82.0% | 95.1% | 19 of 332 / 1,010 |
| NQ / US30 | 0 d | n/a | n/a | **0** of 332 / 909 |
| US100 / US30 | 2,207 d | 39.8% | 59.9% | **710** of 1,010 / 909 |

So the pooled research block contains one heavily-overlapping pair that barely coexists in time
(NQ/US100), and one moderately-overlapping pair that coexists on 710 dates (US100/US30).

**Daily-return correlation of the three legs**, on the marginal-consensus cell, daily sums in ATR
units over shared dates:

| pair | shared dates | correlation |
|---|---|---|
| US100 / US30 | 690 | **+0.2934** |
| NQ / US100 | 19 | **+0.9668** |
| NQ / US30 | 0 | n/a |

The 19-date NQ/US100 figure is thin but unambiguous, and it agrees with the 85.3% bar overlap: they
are one leg. Pooled daily sd is 3.409 against 5.254 for the sum of the legs' sds — a
diversification ratio of **0.649** against the 0.577 three independent legs would give.

**Every pooled standard error in this study is clustered on the calendar date across all three
markets**, so a date on which all three fire counts once. The effective sample size follows as
(sd / SE_clustered)²:

| | nominal n | effective n | retention |
|---|---|---|---|
| pooled, ATR consensus cell | 2,754 | **2,247** | **81.6%** |
| pooled, ATR best-t cell | 2,498 | 1,988 | 79.6% |
| pooled, PTS consensus cell | 2,678 | 2,153 | 80.4% |

The clustered SE is **1.11x** the naive sqrt(n) figure. The overlap penalty is real and it is
modest — an 18% haircut, not the two-thirds one the 85.3% bar overlap might suggest, precisely
because NQ's research block does not coexist with the other two's.

---

## 4. The declared grid — population and marginals before any top row

    trigger   Donchian {10, 20, 40} LONG
    stop      {30, 50, 100} points, and the same distances as ATR multiples {0.968N, 1.613N, 3.225N}
    target    {100, 150, NO TARGET} points, and {3.225N, 4.838N, none}
    entries   07:00-11:00 New York, FLAT AT THE 11:00 OPEN
              (so the four-hour cap is the bell and there is no hold axis to search)
    = 27 cells x 2 parameterisations = 54 POOLED CELLS, research blocks only.

Shorts are not in the grid: `STUDY_US30_SCALP_0711` §3 found shorts lose to their controls in every
short cell while longs beat theirs in 8 of 9, which is drift and not a signal.

**Population first.**

| grid | cells | profitable (ATR units) | profitable (percent) | mean PF | best PF | best abs t |
|---|---|---|---|---|---|---|
| ATR | 27 | **29.6%** | 0.0% | 0.9686 | 1.0327 | 2.190 |
| POINTS | 27 | **0.0%** | 3.7% | 0.9237 | 0.9651 | 1.925 |

Detectability requires abs t ≥ 2.802. The best abs t anywhere is **2.190 and it belongs to a
negative cell** (`don10 3.2253N/3.2253N`, −0.1128 ATR). **The best positive t in 54 cells is 0.514.**
E[max abs t | pure noise] over 54 non-independent cells is at most 3.060.

**The points grid is 0% profitable pooled and the matched-geometry grid is 29.6%** — §2's
arithmetic showing up as a result. Marginal averages, pooled, ATR units per trade:

| axis | ATR grid | POINTS grid |
|---|---|---|
| Donchian | 10 −0.0671 · **20 +0.0064** · 40 −0.0370 | 10 −0.1196 · 20 −0.0603 · 40 −0.1159 |
| stop | **0.968N −0.0175** · 1.613N −0.0243 · 3.225N −0.0558 | 30 −0.0679 · 50 −0.1112 · 100 −0.1167 |
| target | 3.225N −0.0417 · 4.838N −0.0376 · **none −0.0184** | 100 −0.0911 · 150 −0.0992 · none −0.1055 |

**Every setting of every axis of the points grid is negative.** On the ATR grid `don20` is the only
positive setting on any axis, and **no target is the best setting on the target axis** — the 26th
time on this branch. The marginal consensus is `don20 / 0.968N / no target`.

**And the effect is not common across the three markets, which is what decides whether pooling is
legitimate at all.** Per-market means with Cochran's Q and I² on the inverse-variance weights:

- **0 of 54 cells are positive on all three markets.**
- Sign agreement: US30↔US100 **21 of 54**, US30↔NQ **21 of 54** — both *below* the 27 chance
  expects — against US100↔NQ **50 of 54**, which is the 85.3% bar overlap restated.
- Cochran's Q is significant at 0.05 in **0 of 54** cells and median I² is **0.0%**.

Read those together and not separately. Q with three studies and standard errors this wide has
almost no power, so failing to reject homogeneity is not evidence of it; what the sign structure
says is that there are **two objects here, the Dow and the Nasdaq, and they disagree**, while the
two Nasdaq feeds agree with each other 93% of the time because they are the same index.

---

## 5. The MDE ladder — pooling did buy resolution

Minimum detectable effect at 80% power, two-sided α 0.05, from **date-clustered** standard errors,
on the ATR marginal consensus cell `don20 0.968N / no target`:

| subset | n | dates | n_eff | mean (ATR) | SE | t | **MDE80** | vs US30 | in US30 points |
|---|---|---|---|---|---|---|---|---|---|
| US30 | 1,089 | 894 | 1,074 | **+0.0481** | 0.0660 | +0.729 | 0.1849 | 1.00x | 5.73 |
| US100 | 1,230 | 982 | 1,225 | −0.0009 | 0.0658 | −0.014 | 0.1844 | 1.00x | 5.72 |
| NQ | 435 | 325 | 438 | −0.0011 | 0.1154 | −0.010 | 0.3233 | 1.75x | 10.02 |
| US30+US100 | 2,319 | 1,186 | 1,854 | +0.0221 | 0.0520 | +0.426 | 0.1456 | 0.79x | 4.51 |
| US30+NQ | 1,524 | 1,219 | 1,511 | +0.0341 | 0.0575 | +0.592 | 0.1612 | 0.87x | 5.00 |
| US100+NQ | 1,665 | 1,288 | 1,610 | −0.0010 | 0.0581 | −0.017 | 0.1628 | 0.88x | 5.05 |
| **all three** | **2,754** | **1,492** | **2,247** | **+0.0184** | **0.0478** | **+0.386** | **0.1340** | **0.72x** | **4.15** |

**The power prediction was right and slightly conservative.** The study forecast the MDE falling
from 10.74 to ~6.2 points; on this cell it falls from **5.73 to 4.15 US30 points, a factor of
0.72**, against the 0.63 three fully independent markets would have delivered. The 0.09 shortfall
is the overlap and the sd heterogeneity, and it is small.

**And the pooled edge is smaller than US30's alone.** SE fell 1.38x; the mean fell 2.6x. The
t-statistic went **0.729 → 0.386**. Pooling improved the instrument and shrank the thing being
measured, because US100 and NQ both read ≈0 on this cell where US30 reads +0.048.

**What a profit factor requires on this cell's own geometry, against that MDE.** From the pooled
realised mean win W = 2.746 ATR, mean loss L = 1.029 ATR and win rate 27.7%: w* = PF·L/(W + PF·L).

| target PF | needs win rate | delta on observed | = edge/trade (ATR) | in US30 pts | edge / MDE | detectable? |
|---|---|---|---|---|---|---|
| 1.05 | 28.23% | +0.49p | +0.0369 | +1.14 | 0.28x | no |
| 1.10 | 29.18% | +1.44p | +0.0729 | +2.26 | **0.54x** | **no** |
| **1.20** | 31.01% | +3.27p | +0.1419 | +4.40 | **1.06x** | **YES** |
| 1.50 | 35.98% | +8.24p | +0.3293 | +10.21 | 2.46x | YES |
| 2.00 | 42.83% | +15.09p | +0.5881 | +18.23 | 4.39x | YES |

The same table on **US30 alone**: PF 1.20 needs +0.1390 against an MDE of 0.1849 = **0.75x, not
detectable**; PF 1.50 is 1.74x and is.

**So pooling moved exactly one rung.** PF 1.2 crossed from undetectable to detectable
(0.75x → 1.06x). **PF 1.1 did not** (0.39x → 0.54x) — it needs about ten independent markets of
this kind over this span, and this study has two.

---

## 6. Matched random entry, and the win rate against its own bound

Same number of signals drawn from the same eligible in-window bars of the same market, same side,
**sorted** so the position lock rejects the same share (`STUDY_V59`: unsorted draws exploded the
null's spread and made everything fail). 300 draws, combined across markets draw-for-draw so the
pooled null carries the same market mix. Research blocks:

| cell | market | n | rule (ATR) | null median | excess | p |
|---|---|---|---|---|---|---|
| don20 0.968N/none | US30 | 1,089 | +0.0481 | −0.0403 | +0.0884 | 0.093 |
| | US100 | 1,230 | −0.0009 | −0.0594 | +0.0585 | 0.230 |
| | NQ | 435 | −0.0011 | −0.0579 | +0.0567 | 0.353 |
| | **POOLED** | **2,754** | **+0.0184** | **−0.0543** | **+0.0727** | **0.060** |
| don20 1.613N/none | **POOLED** | 2,498 | +0.0323 | −0.0490 | +0.0813 | **0.087** |
| don20 30pts/100pts | **POOLED** | 2,678 | −0.0379 | −0.0450 | +0.0071 | 0.457 |

**Nothing clears 0.05**, and the null itself is negative in every row — a random entry with this
geometry in this window loses 0.04-0.06 ATR a trade, so what the rule is beating is a losing null.
`STUDY_IB_US30_OPTUNA`'s sentence again: *a rule that beats a losing null is still a losing rule.*

Null-spread diagnostic: sd(null mean) / rule's own clustered SE = **0.870-0.888**. The null is
slightly *tighter* than the estimate it is testing — the random entries spread across the whole
window while the rule's cluster — so the control test is marginally **liberal** here, and p 0.060 is
if anything the optimistic reading. (`STUDY_V59` wants this near 1.0; it also warns that a control
whose median sits far below the rule and still cannot reject is broken. Its trade count is stable at
2,212 ± 18.)

**Win rate beside its own driftless break-even**, on the one declared cell with a two-outcome
barrier pair:

| cell | market | n | resolved | target hits | break-even | delta | flatten share | ambiguous |
|---|---|---|---|---|---|---|---|---|
| don20 30pts/100pts | US30 | 1,143 | 886 | 22.8% | 24.8% | **−2.0p** | 22.5% | 1.49% |
| | US100 | 1,102 | 539 | 11.7% | 24.0% | **−12.3p** | 51.1% | 0.09% |
| | NQ | 433 | 345 | 18.3% | 24.4% | **−6.1p** | 20.3% | 0.00% |

All three fall short of their own bound, US100 by twelve points because a 30-point stop is 2.20 ATR
there and half its trades never resolve before the bell. The no-target cells have no two-outcome
bound and are printed as n/a rather than as 50%.

**The intrabar tie-break is not deciding anything here.** The ambiguous share is 0.00-1.49%, against
the 14.03% `STUDY_US30_SCALP_0711` §2 measured at 0.5N/0.5N where the convention flipped the sign.
These barriers are wide enough that the question does not arise.

**Sharpe, zero-filled over every session in the block** (`STUDY_V17`: over traded days only a filter
is paid for trading less):

| cell | US30 | US100 | NQ |
|---|---|---|---|
| don20 0.968N/none | +0.267 | −0.005 | −0.006 |
| don20 1.613N/none | +0.260 | +0.133 | −0.159 |
| don20 30pts/100pts | +0.446 | −0.388 | −0.784 |

---

## 7. One read of the holdouts

Three cells, declared before the read: the two marginal consensus cells and the ATR grid's single
best-t cell. Stated multiplicity: 54 pooled cells were scored on research.

| cell | block | n | mean (ATR) | SE | t | MDE80 | inside? | PF |
|---|---|---|---|---|---|---|---|---|
| don20 0.968N/none | research | 2,754 | +0.0184 | 0.0478 | +0.386 | 0.1340 | no | 1.025 |
| | **holdout** | 1,258 | **−0.0605** | 0.0674 | −0.898 | 0.1889 | no | 0.916 |
| don20 1.613N/none | research | 2,498 | +0.0323 | 0.0630 | +0.514 | 0.1764 | no | 1.033 |
| | **holdout** | 1,136 | **−0.0693** | 0.0905 | −0.766 | 0.2536 | no | 0.930 |
| don20 30pts/100pts | research | 2,678 | −0.0379 | 0.0611 | −0.621 | 0.1711 | no | 0.962 |
| | **holdout** | 1,340 | **−0.0568** | 0.0585 | −0.972 | 0.1638 | no | 0.924 |

All three are negative on the pooled holdout, and per market the only positive holdout reading
anywhere is US100 at +0.0142 on one cell. Matched random entry on the pooled holdout: p **0.540 /
0.633 / 0.647** — the rule is *worse* than a random entry with the same geometry on all three.

Nothing here is inside its own MDE on either block, in either direction.

---

## 8. What would actually close the gap

On the pooled consensus cell: mean +0.0184 ATR, clustered SE 0.0478, MDE 0.1340. The 2,754 trades
came from 17.7 market-years (5.9 calendar years × 3 markets) = 156 a market-year, 467 a calendar
year across all three.

**Detecting the observed pooled edge at 80% power needs 145,274 trades = 311 calendar years of all
three markets.** `STUDY_US30_SCALP_0711` computed 1,528 years for US30 alone on its own geometry; the two figures
are not a clean ratio because the cells differ, but both say the same thing — the observed edge is
not a quantity any attainable sample resolves.

Turned round — how many markets **as independent of each other as US30 is of the Nasdaq** would be
needed for each profit factor to sit exactly at the edge of resolution over this same span:

| target PF | edge needed (ATR) | markets required | this study has |
|---|---|---|---|
| 1.05 | +0.0369 | 39.5 | |
| 1.10 | +0.0729 | **10.1** | **2 effective** |
| 1.20 | +0.1419 | **2.7** | (3 nominal) |
| 1.50 | +0.3293 | 0.5 | |

**PF 1.2 is now inside resolution and PF 1.1 needs roughly ten genuinely independent index feeds.**
The registry lists none that would help much: XAUUSD is the only uncorrelated series on this branch
and it is a different asset class with a cost floor three times the indices'; US30_ISO is the same
Dow from a second provider; US100_ISO is the same Nasdaq. Adding another equity index feed adds
about a third of a market, not a market.

---

## Verdict

**Pooling worked as a power play and answered the question in the negative.**

- **The MDE fell as predicted, slightly better.** 0.1849 → **0.1340 ATR** a trade, 5.73 → **4.15
  US30 points**, a factor of 0.72 against the 0.63 three independent markets would give. The
  clustered standard error is only 1.11x the naive one and effective n is **81.6%** of nominal, so
  the overlap penalty is an 18% haircut, not a fatal one.
- **And it did not bring the observed effect into resolution, because the effect shrank faster.**
  US30 alone reads +0.0481 ATR at t 0.729; pooled reads **+0.0184 at t 0.386**. The instrument
  improved 1.38x and the measurand fell 2.6x.
- **Exactly one rung moved.** PF 1.2 crossed from 0.75x of the MDE to **1.06x — detectable for the
  first time**. PF 1.1 went 0.39x → 0.54x and remains out of reach; it needs about ten independent
  markets and this study has two.
- **There were never three markets.** 85.3% of NQ's in-window signal bars are US100 signal bars at
  the identical timestamp (93.8% within ±2), daily leg correlation +0.967 — worse than the 68% the
  branch already recorded. US30 is the one separate object at 32-39%.
- **And the two objects disagree.** 0 of 54 cells is positive on all three markets; US30↔US100 and
  US30↔NQ sign agreement is 21 of 54, *below* the 27 chance expects, against US100↔NQ's 50 of 54.
  Cochran's Q rejects homogeneity nowhere and median I² is 0.0%, but Q has no power at k=3 — the
  sign structure is the informative statistic and it says pooling is averaging two disagreeing
  estimates, not concentrating one.
- **The points parameterisation is 0% profitable and the matched-ATR one is 29.6%**, because 30
  points is 0.97N on US30 and 2.20N on US100. Express a cross-market barrier in ATR before pooling
  anything — `STUDY_TURTLE_15M` from the other side.
- **Best positive t in 54 cells is 0.514**; the largest abs t belongs to a losing cell. Nothing
  clears a matched random entry on research (best p 0.060, against a null that itself loses money),
  and on the holdout all three declared cells are negative and *worse* than a random entry
  (p 0.540 / 0.633 / 0.647).
- No target is the best setting on its axis for the 26th time; the flatten is on by construction
  here so it is not tested.

**Trial count: 54 pooled cells on research, plus 3 cells read once on the holdouts.** The per-market
tables are decompositions of the same 54 cells, not additional looks.

**What this settles for the branch.** The pooled-window idea is now spent as a route to resolving
this family: it delivers the arithmetic it promised and the arithmetic is not enough, because the
only market with a positive reading is the one that was already known to have it, and the two feeds
added are one feed. The remaining levers are unchanged and are both about measurement rather than
sample size — **1-minute US30 bars** (which would settle the sub-1N tie-break and the entry
precision, though `STUDY_US30_SCALP_0711` notes a four-hour cap keeps the rate near one trade a
session whatever the bar size) and a cheaper round turn. A fourth *equity index* feed is worth
about a third of a market and will not move this.

`research/us30team/pool.py`, `run_p1.py` (clocks, cost, overlap), `run_p2.py` (the 54-cell grid),
`run_p3.py` (MDE ladder, PF arithmetic, heterogeneity, controls), `run_p4.py` (leg correlation,
break-even, Sharpe, the holdout read).
