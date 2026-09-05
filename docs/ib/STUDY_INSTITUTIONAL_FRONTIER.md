# The PF 2.0 / 200-trades-a-year intraday target: the arithmetic, the frontier, the book, and meta-labeling

`research/inst/`, `results/inst/`. Asked for an intraday strategy with a profit factor of at least
2.0 at 200 or more trades a year, using the most advanced techniques available. This study answers
with four measurements rather than a search: what the target needs arithmetically, where the
empirical PF-versus-trade-count frontier of the largest verified configuration space on this branch
actually sits, what a book of every validated intraday leg reaches, and what meta-labeling with a
tail-preserving objective adds. Research blocks only, except the single stated locked reads.

## Verdict

**The target is not on this data.** Over **2,792,878 intraday configurations** (NQ 5/15/30m, RTH
entries, hold caps of 2–6.5 hours, ≥40 research trades) **zero** reach PF 2.0 at 200 trades a year
*even on the research block*, where 89.5% of cells are profitable and the best cell reads PF 7.3.
PF ≥ 2.0 exists in 442,847 cells and their median trade count is **31 a year**. The envelope of the
best research PF at each minimum count, and what that exact cell then does on the locked block:

| ≥ trades/yr | cells | best PF, research | that cell, locked |
|---|---|---|---|
| 25 | 2,535,299 | 6.057 (28/yr) | 2.661 (24/yr) |
| 50 | 1,289,557 | 3.553 | 1.458 |
| **100** | 434,346 | **2.173** | **1.514** (104/yr) |
| 150 | 198,255 | 1.824 | 0.754 |
| **200** | 104,364 | **1.616** | **0.878** |
| 300 | 37,028 | 1.458 | 0.981 |
| 500 | 7,329 | 1.236 | 0.982 |
| 800 | 1,133 | 1.048 | 0.972 |

The in-sample frontier is smooth — roughly PF 2.2 at 100 trades a year, 1.6 at 200, 1.5 at 300,
1.2 at 500 — and beyond 100 trades a year none of it survives the split. Population transfer over
the 2.79M cells: corr(PF research, PF locked) **+0.149**; the top 1% by research PF reads **3.48 →
1.22** on locked, identical to the population's 1.22. The deflated Sharpe of the best research cell
at N = 2.79M is 0.87, and that cell reads PF 0.90 locked — the DSR prices multiplicity, not regime.

## 1. The arithmetic

Stop = 1, target = q, all-in cost c in stop units. PF 2.0 needs a win rate of
w* = 2(1+c) / (2(1+c) + q − c). Against the driftless base 1/(1+q):

| q | base | c = 0 | c = 0.06 | c = 0.20 | lift needed at c = 0.06 |
|---|---|---|---|---|---|
| 0.5 | 66.7% | 80.0% | 82.8% | 88.9% | **+16.1 pts** |
| 1.0 | 50.0% | 66.7% | 69.3% | 75.0% | **+19.3 pts** |
| 2.0 | 33.3% | 50.0% | 52.2% | 57.1% | **+18.9 pts** |
| 3.0 | 25.0% | 40.0% | 41.9% | 46.2% | **+16.9 pts** |

PF 2.0 needs a **16–20 point** lift in win rate over a coin flip at every geometry after costs. The
largest honest lifts measured on this branch in sixty studies are **+1 to +5 points**. On NQ 5m at
a scalping stop the round turn is ~24% of risk (c ≈ 0.24), which pushes the requirement past 89%
at 1:2. The target is not a hard version of what this data does; it is a different order of
magnitude.

## 2. The intraday constraint, priced directly

Same 2.79M cells, marginal average by hold cap:

| hold cap | research PF | locked PF | trades/yr |
|---|---|---|---|
| 2h | 1.457 | 1.184 | 68 |
| 4h | 1.518 | 1.263 | 66 |
| 6.5h | 1.542 | 1.204 | 66 |
| swing (480 bars) | 1.551 | 1.241 | 66 |

The constraint costs little on this base (2h against swing: −0.09 PF research, −0.06 locked). What
it cannot buy is *count*: the trade count is set by the entry, not the exit, and every cell above
~150 a year loses its PF out of sample regardless of how long it holds.

## 3. The book of everything validated here

Every intraday leg on the branch (FTM ORB, APM VWAP, TFI, trend-day, VWAP drift), every feed it
runs on, one unit each, pooled by calendar in percent of entry price with each feed's own costs.
Daily returns between legs correlate **0.01–0.19** — the diversification is real. Pooled:

| book | research | reserved |
|---|---|---|
| all 5 legs × feeds | 515 trades/yr, **PF 1.079**, Sharpe 0.57 | 787/yr, PF 1.180, Sharpe 1.32 |
| research-positive legs only (7 leg×feed, PF > 1.10 on research) | **129/yr, PF 1.402, Sharpe 2.13** | **186/yr, PF 1.608, Sharpe 2.87** |
| trend-day + APM only | 42/yr, PF 1.528 | 63/yr, PF 2.030 |
| FTM ORB alone | 170/yr, PF 1.370 | 229/yr, PF 1.269 |

The research-selected book is the strongest honest object here: 129–186 trades a year at
PF 1.40–1.61, Sharpe 2.1–2.9, win 55–58%. It still needs **+15.3 points of win rate** to reach
PF 2.0 at its own win/loss sizes, **73–91% of its net comes from the top 5% of trades**, and the
reserved block reads better than research (1.61 vs 1.40), which is the wrong shape and coincides
with 2022+ being one long up-regime on the two indices that carry it.

## 4. Meta-labeling with the tail preserved

The one modelling technique the branch had not yet run in its proper form: a primary rule (the
≥300-trades/yr envelope cell, 5m, Donchian 15/30, 1.5N adaptive stop, no target, 4h cap, MA200
floor, prior-session-high gate; research PF 1.446 at 344/yr, locked 1.051) generates the trades; a
secondary model predicts each trade's **R** — regression, not win/lose, because V28/V32/EMA48
all measured that a classifier keeps the high-probability trades and discards the tail a breakout
earns in — from 40 causal features at the signal bar; the top fraction by predicted R is kept.
Purged and embargoed sequential folds, a shuffled-label twin beside each model, a same-selectivity
random filter as the null.

| model | OOF IC | keep 80% | keep 60% | keep 40% | twin IC / keep-60 PF |
|---|---|---|---|---|---|
| base | — | PF 1.407 at 344/yr | | | |
| ridge | +0.031 | 1.409 (p 0.48) | 1.256 (p 0.84) | 1.522 at 138/yr (p 0.32) | +0.012 / **1.455** |
| LightGBM | +0.026 | 1.557 at 276/yr (p 0.06) | 1.506 (p 0.28) | 1.599 at 138/yr (p 0.21) | +0.048 / **1.511** |

The shuffled twins read PF 1.46 and 1.51 at keep-60 — the same as the real models. Nothing clears
its random-filter null at p ≤ 0.05. **The pre-declared locked read (ridge, keep 60%) inverts**:
locked base PF 1.051 at 331/yr → kept PF **0.865** at 185/yr, IC −0.015, random filter p 0.660.
Ridge's largest coefficient is RSI14 at **−1.31** — momentum negative at the signal bar, the
eleventh route to mean reversion on this branch. The regression objective did preserve the tail
(p90 of R rose 5.19 → 6.53 in the kept set); it just had nothing to preserve out of sample.

## What would change the answer

Not another technique on this data. The three things that would move the frontier are the ones
this branch has flagged for a year: **bid/ask data** (every cost here is an assumption, and cost is
the binding term at every count above 150 a year), **a second regime** (the reserved blocks are one
up-move; the book's better-out-of-sample shape says so), and **an order-flow feed** (the CVD is a
proxy, and the only real one — BTC's taker flow — sits on a 0.2% round turn). Within what is here,
the honest offer is the research-selected book at ~130–190 trades a year and PF 1.4–1.6, sized
for a p99 drawdown, not a single rule at PF 2.

## Addendum: the ≥100-trades/yr envelope cell, shipped

`research/inst/cell100.py`, `pine/inst/FRONTIER100_strategy.pine`. The only envelope cell whose
profit factor held across the split, pinned exactly: **NQ 15m, Donchian 55 entry on the high,
20-bar channel exit, adaptive stop 1.5 ATR calm / 0.5 ATR high-vol, no target, 26-bar (6.5h)
hold cap, (close − SMA200)/ATR ≥ 2, CHOP(14) ≤ 40, RTH entries, CVD off.**

| | n | trades/yr | PF (R) | PF (%) | win | %/trade | total | max DD | p90 R |
|---|---|---|---|---|---|---|---|---|---|
| research | 200 | 104 | 2.173 | 2.158 | 23.5% | +0.0791 | +15.8% | 2.1% | 6.6 |
| locked | 108 | 104 | 1.514 | 1.798 | 23.1% | +0.0666 | +7.2% | 4.1% | 5.1 |

Median hold is one bar; 21–23% of trades run to the cap; 82% of research net comes from the top
5% of trades. **The one-rung neighbourhood holds on both blocks** — ent 40: 2.16 → 1.50; exit 10 /
30: 2.02 / 2.17 → 1.45 / 1.48; stop 2.0: 1.89 → 1.37; MA floor 1: 1.93 → 1.68; CHOP 45: 1.83 →
1.35 (stop 1.0 collapses to 8 trades/yr). That is rarer on this branch than a research pass, and
it is still the maximum of 434,346 draws read once; it has not been run on US100/US30 and has not
cleared a matched random-entry control. Ships with every number in the header.

## Addendum 2: EMA200 support, the 20/50 cross and a pullback to EMA20, measured on this cell

`research/inst/cell100_ema.py`, `results/inst/cell100_ema.txt`. Asked why these three were not in
the script's menu. They were not in the frontier's declared axes, and they had last been measured
on a different base (`STUDY_TURTLE_SCALP_EMA`). A filter is a property of its geometry
(`STUDY_V52`), so they are measured here on the cell itself and now sit in the menu, default OFF.

| gate | on signal bars | lift | research n / PF | locked n / PF | random filter p |
|---|---|---|---|---|---|
| cell as shipped | — | — | 200 / 2.158 | 108 / 1.798 | — |
| EMA200 support, within 3 ATR | 5.2% | **0.18×** | 23 / 1.493 | 17 / 0.740 | 0.650 |
| EMA200 support, within 2 ATR | 1.6% | 0.08× | 7 / 0.687 | 5 / 0.000 | — |
| EMA200 touched within 5 bars | 10.0% | 0.68× | 39 / 1.614 | 23 / 2.682 | — |
| 20 > 50 > 200 state | 84.9% | 2.04× | 168 / **2.422** | 90 / **1.489** | **0.003** |
| fresh 20/50 cross within 5 | 7.3% | 2.18× | 27 / 2.915 | 12 / 1.672 | — |
| pullback to EMA20 within 3 | 10.0% | 0.14× | 41 / 4.708 | 24 / 3.738 | — |
| pullback to EMA20 within 5 | 20.6% | 0.26× | 79 / 2.559 | 44 / 2.216 | 0.090 |
| pullback to EMA20 within 10 | 50.8% | 0.58× | 140 / 2.216 | 70 / 1.827 | — |
| **the full ask** (support 3 + state + pullback 5) | — | — | **3** | 1 | — |

Three things the table settles. **The full ask leaves three trades in two years**, because
"within 3 ATR of the EMA200" and the cell's own "at least 2 ATR above the SMA200" are close to
mutually exclusive — the support reading keeps 5% of the cell's signals and the floor is what made
the cell. **The 20>50>200 state is the one gate that clears its control** (p 0.003), and it reads
better on research and worse on locked (2.16 → 2.42 in, 1.80 → 1.49 out): the shape this branch
does not ship on. **The pullback's lift is 0.14–0.58×** — it removes the clean breakouts — and
while its surviving trades read well on both blocks (within 5: 2.56 → 2.22), it cuts the count to
41 a year, below the 100 the cell was chosen for, and fails its control at p 0.090. All three are
in the menu with these numbers; none is on by default.
