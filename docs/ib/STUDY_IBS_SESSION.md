# STUDY_IBS_SESSION — the Zeta FX IBS New York session EA: stability, Monte Carlo, clusters, walk-forward

**Brief.** An MQL5 expert (`ZetaFX_IBS_NY_Session_EA.mq5`, v2.00) was uploaded with the
instruction: parameter stability test, Monte Carlo on every parameter set, cluster analysis and
walk-forward, plugged into this harness. Four feeds: US100 15m (2016-11 to 2025-10), US30 15m
(2016-10 to 2025-07), NQ 1m (2022-12 to 2025-12) and US30 ISO 15m (2024-08 to 2026-08, whose
2026 tail nothing on this branch has ever selected on).

**Verdict in one paragraph.** The EA is a long-only, multi-day mean-reversion holder: buy at the
cash close after a session that closed in its bottom fifth, hold up to five sessions or until a
session closes in its top fifth, stop one session-range below. Its 2,352-cell grid is positive
almost everywhere on the research blocks (US100 99.9%, NQ 96.4%, US30 78.1% of cells) because
the indices rose, and a **random session with the identical stop, exit rule and hold earns most
of what the rule earns** (+0.13 / +0.09 / +0.14 R on the three research blocks against the
default's +0.24 / +0.05 / +0.22). The default clears that control on US100's research and
validation blocks (p 0.031, 0.001) and on nothing else that was reserved: US100 test p 0.51
(+0.115 R against the control's +0.120), US30 test p 0.52, NQ locked p 0.46, and the one
reserved block it does clear — US30 ISO 2026, p 0.035 on 27 trades — is one where the control
itself is negative. The surface is smooth (neighbourhood coherence 0.96–0.98), so there is no
spike to reject, but **no selector in the walk-forward beats the author's own defaults out of
sample** (US100: chosen cells +0.17–0.22 R at median walk-forward efficiency 0.09–0.39 against
the default's +0.23 at 0.91), and the optimiser's favourite axis, a 0.5× stop, is the R
denominator shrinking, not the account growing. What this strategy owns is an exposure —
overnight long index after a weak close — that the last decade paid; nothing measured here
distinguishes it from that exposure out of sample.

Everything below was produced by `research/ibs/ibs_run.py`; outputs in `results/ibs/`.

## 1. The order model, and what the feeds forced

`research/ibs/ibs_core.py` re-implements `zfxProcessClosedBar` as a cached tensor: a trade's
outcome depends only on its entry session and the geometry, so the price walk is done once per
(session, stop multiple) and once per (session, exit threshold, hold), and every cell is an
array lookup plus a position-lock loop. `research/ibs/ibs_parity.py` is the same order model
written the slow way, one bar at a time, and the two are diffed trade-for-trade.

Two things the parity walk caught that reading did not:

* **After a stop the EA is flat at that session's close and re-enters on the same session.**
  The first tensor waited a session, as it correctly does after a rule exit (the EA returns
  after the exit branch). 11 of 114 NQ default-cell trades differed.
* **"The first tick of the next M1 bar" is not 16:00 on a CFD feed.** The US30 15m feed has no
  bars between 16:00 and 18:30 New York on 94% of days; US100 and the ISO feed have a
  17:00–18:00 break. The EA sends the order when the next tick arrives, so on US30 the "16:00"
  fill is the 18:30 re-open, and on the 21% of US30 days that also lack a 15:45 bar the EA
  never fires (it triggers only on the bar opening at `end - 1`). Both are now modelled, and
  each fill pays the spread tier of its own bar.

After both fixes: **9 of 9 configurations on three markets identical, every trade, correlation
1.000000** (`results/ibs/parity.txt`). The one remaining difference is a trade whose exit falls
past the end of the file, which the tensor cannot take and the naive walk leaves open.

Sessions: US100 2,149, US30 1,757, NQ 735, US30 ISO 515 (168 in 2026). Session ranges: US100
median 160 points, US30 281, NQ 223, US30 ISO 417. Costs are the branch's retail CFD assumptions
from `research/scalp/core.py`, charged by the session of the fill bar; bid/ask is in none of
these feeds.

## 2. Parameter stability (research blocks: US100 and US30 before 2022; NQ first 65%)

Grid: entry IBS {10…40} × exit IBS {50…90} × max hold {1…10} × stop multiple {0.5…3.0}, 2,352
cells, the EA's defaults (20 / 80 / 5 / 1.0) inside every axis.

| research block | cells R>0 | PF>1.2 | median R | median PF | EA default R (PF, win) | default percentile |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| US100 | 99.9% | 94.8% | +0.139 | 1.53 | +0.245 (1.67, 62%) | 93.2% |
| US30 | 78.1% | 32.4% | +0.032 | 1.10 | +0.049 (1.10, 49%) | 64.2% |
| NQ | 96.4% | 76.0% | +0.101 | 1.39 | +0.216 (1.59, 62%) | 91.3% |

**Read the share of the grid before its top row.** On US100 the ranking's top is the maximum of
2,350 profitable draws.

**Marginal average per axis** (mean R over all cells at each level; STUDY_V11's rule, read the
axis, never the cell):

| axis | US100 | US30 | NQ |
| --- | --- | --- | --- |
| entry | 20 best (+0.190); 10 worst (+0.098) | 15 best (+0.098); 25 worst (+0.010) | 10 best (+0.200); 35 worst (+0.068) |
| exit | monotone up to 90 (+0.203) | monotone up to 90 (+0.075) | 90 best (+0.130), flat 60–75 |
| hold | rises to 5 (+0.170), flat after | rises to 10 (+0.056) | rises to 3 (+0.138), flat after |
| stop mult | 0.5 best in R (+0.187), 3.0 worst (+0.097) | 0.5 NEGATIVE (−0.007), 2.0 best (+0.063) | 1.0 best (+0.172) |

Two axes agree across all three feeds: **a wider exit threshold (90) is better than the
default 80**, and **a longer maximum hold is at worst neutral**. The stop-multiple axis
disagrees between feeds in R, and §6 shows why that axis is not what it looks like.

**Neighbourhood coherence** — correlation between a cell's R and the mean R of its ±1
neighbours on the 4-D grid: **US100 0.981 (sign agreement 99.9%), US30 0.962 (94.3%)**. The
surface is a smooth hill. That rejects nothing (a plateau is necessary, not sufficient); it means
no cell here is a spike, including the defaults.

**Rank stability, research → validation (2022-23)**, the honest version of a heatmap:

| feed | Spearman over 2,352 cells | research top decile: research R → validation R | all-cell validation mean |
| --- | ---: | --- | ---: |
| US100 | +0.108 | +0.279 → +0.067 (74% positive) | +0.092 |
| US30 | +0.313 | +0.141 → +0.105 (97% positive) | +0.063 |

On US100 **the research top decile earns less on validation than the average cell**. On US30 the
ranking carries some information.

**Two-feed agreement.** 1,837 of 2,352 cells (78.1%) are positive on both research blocks; 513
on US100 only; 0 on US30 only. The top 100 by the minimum of the two feeds' R agree on exit 90
(68 of 100) and hold ≥ 7 (64 of 100) and on little else (entry spread over 10/15/20/40, stop
multiple over every level). Consensus cell by mode per axis: **15 / 90 / 10 / 1.0**. The best
two-feed plateau cell: **15 / 90 / 10 / 1.5**. Both are declared here, before any reserved block
was read.

## 3. Monte Carlo on every cell

For each of the 2,352 cells on each research block, 2,000 bootstrap draws with replacement
(edge uncertainty: P(mean R ≤ 0) and a 5–95% interval) and 2,000 permutations of the realised
order (path risk: maximum drawdown in fixed R, and compounded at 1% of equity per trade as the
EA sizes). The compounded ENDPOINT comes from the bootstrap, not the permutation — permuting
trades cannot change a product any more than a sum, and the first draft here printed the same
number for the median and the 5th percentile until that was fixed.

| research block | median P(mean≤0) | cells P<0.05 | cells P<0.01 | median-cell DD, fixed R | 1%-risk DD median / p95 | cells with P(DD>10%)>½ | 1%-risk equity, median cell (5th pct) | cells whose 5th pct < 1.0 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| US100 | 0.007 | 83.5% | 54.6% | 6.3 R | 6.2% / 9.7% | 26.3% | 1.316 (1.079) | 19.3% |
| US30 | 0.287 | 10.0% | 1.1% | 11.2 R | 10.8% / 16.2% | 53.0% | 1.058 (0.864) | 90.5% |

**EA default, US100 research:** P(mean ≤ 0) 0.004, interval [+0.09, +0.41] R; drawdown median
6.9 R (p95 11.0 R), at 1% risk 6.8% (p95 10.5%), P(DD > 10%) 0.07; equity multiple over the
block median 1.49, 5th percentile 1.16. **US30 research:** P(mean ≤ 0) **0.308**, interval
[−0.11, +0.22]; drawdown 14.4 R (p95 22.5 R), 13.7% (p95 20.4%) at 1% risk, P(DD > 10%) 0.90;
equity median 1.07, 5th percentile 0.82.

Three things to read out of that rather than into it. **83.5% of US100 cells "pass" at
P < 0.05** — that is the shape of a grid sitting on drift, not 1,964 discoveries; the same grid
on US30 passes 10%, and 5% would be chance. **The cells with the lowest P are the WIDE stops**
(3.0× range dominates both lists): a 3.0× stop is rarely hit, so every trade is a small positive
drift harvest with a small variance, which is exactly what a bootstrap rewards and exactly what
the R-ranked top of the grid punishes. And **the 1%-risk drawdowns are modest** — median cell
6–11%, p95 10–16% — because a 1%-of-equity risk with a 40–60% win rate and 150–250 trades
simply cannot draw down far; that is the sizing, not the strategy, and the branch's rule stands
that sizing creates no edge.

The full per-cell tables are `results/ibs/mc_US100_research.csv` and `mc_US30_research.csv`.

## 4. Cluster analysis — how many strategies does the grid contain?

Cells were clustered on the correlation of their per-session R over the research block
(average linkage, cut at within-cluster correlation 0.7), and separately k-means (k=4) on
the metric profile [R, PF, win, stop share, drawdown, n].

| feed | clusters at 0.7 | largest | components for 90% of variance | research top decile spans |
| --- | ---: | ---: | ---: | ---: |
| US100 | 117 | 206 cells | 37 | 43 clusters |
| US30 | 137 | 120 cells | 47 | 61 clusters |

So unlike the branch's earlier grids ("the top 25 was one rule wearing 25 hats") this grid is
genuinely diverse — the entry threshold and hold change the trade set a lot (entry-set Jaccard
against the default along the entry axis: 0.51 / 0.71 / 1.00 / 0.76 / 0.62 / 0.54 / 0.44). That
diversity is what makes the 78% agreement with a random-entry control meaningful: it is not one
trade set scoring 2,352 times.

What the clusters say when validation is read for the cluster rather than the cell:

* **US100.** The three best research clusters (14, 20 and 10 cells, all centred on entry 30 /
  exit 90 / stop 0.6–0.75, research R +0.32–0.34) decay to **+0.024, −0.005 and +0.062** on
  validation, with only 50–70% of their members positive. The clusters that HELD are the wide-stop
  ones: entry 15–18 / exit 90 / hold 10 / stop 2.0 (+0.256 → +0.158, 100% positive) and entry 30 /
  exit 90 / hold 4 / stop 1.0 (+0.225 → +0.215).
* **US30.** The best research clusters are all entry 15 / exit 90 / hold 4–10 / stop 1.0–1.25
  (+0.16–0.21) and they hold on validation (+0.14–0.16, 100% positive).
* **k-means.** On both feeds the profile with the highest research R is the tight-stop, low-win
  profile (US100: R +0.203, win 45%, stop 0.5; US30: the same profile is NEGATIVE, −0.027, win
  35%), and it has the WORST validation on US100 (+0.047 against +0.101–0.202 for the others).
  The high-win, wide-stop profile (PF 1.87, win 70%, stop 2.0) is the one whose validation R
  matches its research R.

## 5. Walk-forward — selection re-run inside every fold

One calendar year out of sample, train on the trailing three years (rolling) or on everything
before (anchored), the whole 2,352-cell sweep re-run per fold, three selectors: best cell by R,
best cell by plateau (neighbour mean), and the EA default held fixed. Folds 2019–2025 (2025
partial). WFE = out-of-sample R ÷ in-sample R of the chosen cell.

| feed / mode | selector | OOS n | OOS R | OOS PF | win | years > 0 | median WFE |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| US100 rolling | best R | 261 | +0.176 | 1.27 | 35% | 6/7 | 0.09 |
| | plateau | 314 | +0.168 | 1.25 | 34% | 5/7 | 0.39 |
| | **default** | 260 | **+0.231** | **1.63** | 61% | 6/7 | **0.91** |
| US100 anchored | best R | 271 | +0.171 | 1.25 | 33% | 5/7 | 0.16 |
| | plateau | 258 | +0.224 | 1.35 | 36% | 6/7 | 0.25 |
| | default | 260 | +0.231 | 1.63 | 61% | 6/7 | 0.84 |
| US30 rolling | best R | 189 | +0.133 | 1.24 | 46% | 7/7 | 0.35 |
| | plateau | 188 | +0.096 | 1.16 | 42% | 5/7 | 0.45 |
| | default | 234 | +0.135 | 1.30 | 53% | 7/7 | 0.23 |
| US30 anchored | best R | 197 | +0.145 | 1.28 | 48% | 7/7 | 0.45 |
| | plateau | 189 | +0.092 | 1.20 | 51% | 6/7 | 0.45 |
| | default | 234 | +0.135 | 1.30 | 53% | 7/7 | 0.39 |

**The optimiser never beats the defaults on US100 and ties them on US30.** On US100 it buys the
same thing in every fold — exit 90 and a 0.5× stop — and that cell's in-sample R of +0.47–0.62
becomes +0.02–0.04 in 2021–2023. The default's per-year R on US100 is positive in 8 of 10
calendar years (2018 −0.10, 2025 −0.08) and on US30 in 8 of 10 (2018 −0.22, 2025 +0.03 R but
−69 points). NQ: 2023 +0.44, 2024 +0.03, 2025 −0.06.

## 6. The stop-multiple axis is the R denominator

The EA sizes 1% of equity on `session range × multiplier`, so R is what its account
experiences, and the grid's best cells in R are the tight-stop ones. In POINTS they are the
worst. US100 research, default geometry with only the multiple varied:

| stop mult | n | R / trade | points / trade | win | total points |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0.5 | 179 | **+0.377** | +15.2 | 40% | 2,712 |
| 0.75 | 172 | +0.254 | +20.8 | 52% | 3,577 |
| 1.0 | 167 | +0.245 | +30.2 | 62% | 5,041 |
| 1.5 | 155 | +0.201 | +30.0 | 70% | 4,653 |
| 2.0 | 151 | +0.166 | +39.5 | 72% | 5,959 |
| 3.0 | 147 | +0.133 | **+47.1** | 73% | 6,921 |

A tighter stop halves the denominator and the same points become more R; the walk-forward's
"best" cells are this, and it is the same lesson as STUDY_SWEEP_110K's channel stop: **anything
ranked in R has to be re-read in points before the ranking is believed.** It is also why the
k-means tight-stop profile is the one that fails validation on US100 and is negative outright on
US30 (a 0.5× range stop on the Dow is hit 70% of the time).

## 7. The reserved blocks, read once

Three cells declared in §2, read on every reserved block with a matched control: 1,000 draws
of random sessions from the same block with the identical stop multiple, exit threshold and
hold, position lock included, same number of entries. `p` is the share of draws whose mean R
reaches the cell's. `index` is the block's close-to-close move in median session ranges.

**EA default 20 / 80 / 5 / 1.0**

| block | sessions | n | R | pts | PF | win | control R | p | index |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| US100 research | 1,263 | 167 | +0.245 | +30 | 1.67 | 62% | +0.130 | **0.031** | +121 |
| US100 validation | 498 | 96 | +0.287 | +64 | 1.87 | 61% | +0.076 | **0.001** | +2 |
| US100 **test** | 433 | 56 | +0.115 | +39 | 1.27 | 59% | +0.120 | 0.510 | +35 |
| US30 research | 1,266 | 174 | +0.049 | +38 | 1.10 | 49% | +0.095 | 0.756 | +86 |
| US30 validation | 480 | 78 | +0.179 | +73 | 1.43 | 55% | +0.016 | **0.034** | +3 |
| US30 **test** | 379 | 46 | +0.042 | −8 | 1.10 | 54% | +0.050 | 0.517 | +18 |
| NQ research | 477 | 79 | +0.216 | +50 | 1.59 | 62% | +0.144 | 0.190 | +43 |
| NQ **locked** | 258 | 35 | +0.070 | +57 | 1.15 | 54% | +0.056 | 0.463 | +15 |
| US30 ISO 2024-25 | 352 | 47 | +0.076 | +25 | 1.19 | 57% | −0.004 | 0.217 | +18 |
| US30 ISO **2026** | 168 | 27 | +0.142 | +133 | 1.37 | 56% | −0.148 | **0.035** | +11 |

**Consensus 15 / 90 / 10 / 1.0**: fails its control on every block (research p 0.137 / 0.136,
test p 0.555 / 0.204, NQ locked +0.024 R p 0.376) except US30 ISO 2026 (+0.364 R, p 0.049, n 17).

**Plateau 15 / 90 / 10 / 1.5**: US100 research p 0.028, validation p 0.044, test p 0.413; US30
research p 0.239, validation 0.177, **test p 0.067 (+0.229 R against +0.049)**; NQ locked +0.087
p 0.163; US30 ISO 2026 +0.110 p 0.167. The best-behaved of the three and still not a pass.

**What the table says.** The control earns +0.09 to +0.14 R on the research blocks, which is
most of what any cell earns: random long entries at the close with a one-range stop and a
five-session hold were paid by these indices. The rule's excess over that is +0.11 R on US100
research, −0.05 R on US30 research, and on the three genuine test blocks (US100 test, US30 test,
NQ locked) it is **−0.005, −0.008 and +0.014 R**. The 2026 block is the one place the default
beats its control (n 27), and it does so because the control is negative there, not because the
rule improved.

**Cost stress**, R per trade at 0× / 1× / 1.5× / 2× the assumed spread and slippage, test-type
blocks: the default moves from +0.125 to +0.105 on US100 test, +0.057 to +0.027 on US30 test,
+0.077 to +0.062 on NQ locked. **Costs are not the obstacle**; a one-to-five-day hold against a
one-range stop is cost-insensitive, unlike every scalp on this branch.

**Exit split** (default, test blocks): stops average −1.03 R (US100 n 23, US30 n 19), rule and
clock exits +0.92 / +0.80 R (n 33 / 27). A stop is hit in 34–47% of trades depending on the
block; there is no barrier edge to find, the P&L is the drift of the trades that were not
stopped.

## 8. What would change the answer

* **A short side.** Everything here is long in a decade that rose. A mirrored short (sell after a
  session closing in its top fifth) is the cheapest test of whether IBS carries information or
  the trade is just long exposure; on this branch shorts have lost by existing, so it would need
  its own control.
* **A control that is volatility-matched.** The random-session control matches the geometry, not
  the day's volatility; low-IBS sessions are wide-range sessions, and a stop sized in ranges is
  wider on them. The ADX lesson (`STUDY_TREND_LONG`) applies.
* **Bid/ask.** Not in any feed; the 2× stress covers a doubled spread but not a broker whose
  overnight financing on a CFD is the real cost of a five-session hold, which is not modelled
  at all here and would take roughly 0.02–0.03% of notional per night off every held trade.

## 9. Files

| file | what |
| --- | --- |
| `research/ibs/ibs_core.py` | feeds, sessions, the cached tensor, position lock, matched control |
| `research/ibs/ibs_parity.py` | the EA's order model bar by bar, diffed against the tensor |
| `research/ibs/ibs_run.py` | `stability`, `montecarlo`, `cluster`, `walkforward`, `judge` |
| `pine/ibs/IBS_SESSION_strategy.pine` | the TradingView port; stop from the signal close, a deviation measured at 0.000 R on NQ and −0.010 to +0.027 R on the CFD feeds |
| `results/ibs/*.txt`, `*.csv` | every table above, every cell's sweep and Monte Carlo |
