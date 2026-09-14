# STUDY_TRENDDAY_EMA — the Raschke trend-day / untouched-EMA EA, tested on four markets

The strategy is `ZetaFX_Raschke_TrendDay_EMA_EA.mq5`. Over the 390-minute RTH session it builds an
EMA(20) from complete, clock-aligned 15-minute RTH closes only, seeded with the SMA of the first 20.
Each 15-minute bucket is tested against the EMA value known **before** that bucket closed; a session
whose buckets never contained the EMA is UNTOUCHED, and one with `|close − open| / range ≥ 75%` is a
TREND DAY. After a session that is both, the next full NYSE session is faded — open above the EMA is
a short, open below is a long — filled one minute after the open. The exit is a resting target at
the most recently completed RTH 15-minute EMA, replaced after every bucket, plus a hard flatten one
minute before the close. **No stop, one contract.**

Engine `research/trendday/td_core.py`, battery `research/trendday/td_run.py`, output
`results/trendday/`. Everything the EA does is implemented in the order the EA evaluates it: the
continuous cross-session EMA and its reset on an incomplete session or a calendar gap, the EA's own
2010–2027 XNYS non-full-session calendar, the 390-minute / 26-bucket completeness test, the skip when
the session-open bar has already reached the target, and the skip when the fill is no longer on the
entry side of it.

Feeds and blocks: NQ 1-minute 2022-12→2025-12 (research = the first 65% of sessions); US100 and US30
15-minute 2016→2025 (research < 2022, validation 2022–23, test 2024+); US30_ISO 15-minute 2024-08→
2026-08 (research < 2026). Costs are half the RTH spread plus entry slippage per side, plus
commission on NQ; NQ dollars are MNQ.

## 1. The one approximation, priced

A 15-minute feed cannot fill one minute after the open. NQ has both resolutions, so the gap is
measured rather than assumed:

| NQ, same rule | n | mean pts | correlation of the shared days |
| --- | ---: | ---: | ---: |
| 1-minute, fill at 09:31 (the EA) | 43 | +40.9 | — |
| 15-minute, fill at the 09:30 open | 43 | +39.0 | **0.9975** |

Identical trade set, identical days, and the 15-minute model is **1.8 points per trade WORSE**. The
approximation is conservative, so every CFD number below is a floor, not a flattery. The open-bar
skip and the wrong-side skip never fire on any feed: after a trend day that never touched its EMA,
the EMA is far from the open.

## 2. The rule as specified

| feed | block | n | win | PF | mean pts | Sharpe | max DD |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ 1m | research | 26 | 88.5% | 5.86 | +36.3 | +2.01 | 151 |
| NQ 1m | locked | 17 | 82.4% | 3.83 | +47.9 | +1.59 | 188 |
| US100 15m | research | 63 | 66.7% | 1.29 | +5.0 | +0.29 | 399 |
| US100 15m | validation | 38 | 78.9% | 2.08 | +31.2 | +1.18 | 317 |
| US100 15m | test | 24 | 83.3% | 7.53 | +45.6 | +2.05 | 157 |
| US30 15m | research | 64 | 59.4% | 1.03 | +1.4 | +0.03 | 1,380 |
| US30 15m | validation | 21 | 76.2% | 1.79 | +28.3 | +0.74 | 356 |
| US30 15m | test | 21 | 61.9% | 1.11 | +10.8 | +0.09 | 1,207 |
| US30_ISO 15m | research | 20 | 75.0% | 1.41 | +39.6 | +0.35 | 1,158 |
| US30_ISO 15m | locked | 4 | 100% | — | +122.7 | +2.10 | 0 |

It is **very selective**: 12–14% of sessions are untouched, 13–20% are trend days, and only
**4.8–6.1%** are both. Three years of NQ is 43 trades; nine years of US100 is 125.

**The shape is wrong on both feeds with real history.** US100 runs +5.0 → +31.2 → +45.6 across three
ordered blocks and US30 +1.4 → +28.3 → +10.8. A rule the author fixed before these blocks existed
should decay out of sample, not improve monotonically through it. This branch has flagged that
signature twice before and been right both times.

## 3. Matched controls

Two nulls. **Day control**: the identical fade, EMA target and flatten, on a RANDOM full session
instead of a qualified one — 2,000 draws at the rule's own trade count. **Side control**: the rule's
own days, coin-flip direction, with the target MIRRORED across the session open so the distance and
the flatten are identical (a non-fade side has the EMA on the wrong side of price and is not a
tradeable target at all; without the mirror the "control" just re-selects the fade).

| feed / block | rule | day control | p | side control | p |
| --- | ---: | ---: | ---: | ---: | ---: |
| NQ research | +36.3 | +0.3 | **0.013** | +16.3 | 0.050 |
| NQ locked | +47.9 | +4.8 | 0.097 | −18.1 | 0.050 |
| US100 research | +5.0 | −0.5 | 0.224 | +1.9 | 0.250 |
| US100 validation | +31.2 | −4.1 | **0.010** | +14.4 | 0.350 |
| US100 test | +45.6 | +7.7 | 0.056 | +2.2 | **0.000** |
| US30 research | +1.4 | −4.7 | 0.361 | +3.4 | 0.600 |
| US30 validation | +28.3 | +6.7 | 0.245 | +14.1 | 0.200 |
| US30 test | +10.8 | +10.3 | 0.494 | +40.3 | 0.550 |
| US30_ISO research | +39.6 | +5.6 | 0.221 | −3.2 | 0.300 |

The side control runs 20 independent draws, so its p-value resolution is 0.05 — read 0.050 as "the
best of twenty", not as a two-decimal result.

**US30 fails every control on every block over nine years.** US100 fails on the block it should be
strongest on and passes on the two later ones. Only NQ passes where a rule is supposed to.

## 4. Anatomy (pts/trade, NQ research | locked)

| variant | NQ | US100 research / validation / test |
| --- | ---: | ---: |
| as specified | +36.3 / +47.9 | +5.0 / +31.2 / +45.6 |
| untouched filter OFF | +12.6 / +22.6 (n 85/53) | −2 / +2 / +12 (marginal) |
| trend-day filter OFF | +11.8 / +27.2 (n 57/36) | +3 / +1 / +11 (marginal) |
| **BOTH filters OFF** | **−1.3 / +4.9** (n 453/250) | — |
| side INVERTED (mirrored) | −3.6 / −83.2 | — |
| always LONG / always SHORT | +7.3 / +16.9 and +25.5 / −46.3 | — |
| NO target, flatten only | +15.1 / +78.8 | — |
| target frozen at entry | +34.7 / +60.1 | — |
| 2x / 4x / 8x cost | +34.6 / +31.1 / +24.3 (research) | +3.5 / +0.5 / −5.5 (research) |

**Neither filter is the edge; the conjunction is.** Remove both and 453 research trades earn −1.3.
Remove either one and roughly a third of the per-trade result survives on three times the trades.
The trend-ratio threshold is a smooth ladder (50/60/65/70/75/80% → +23.5/+24.8/+26.3/+29.4/+36.3/
+35.7 on NQ research), which is the gradient a real mechanism has. The EMA period has a plateau at
20–40 and **fails at 10 and 15** (locked −93.8 and −4.4), so the period is doing work but 20 is not
a special value.

Costs barely matter on NQ — the target is far and the hold is long. On US100 research the edge is
gone by 4x.

## 5. Parameter grid, walk-forward

168 cells (EMA × trend ratio × the two filter switches).

| feed | scorable | profitable on the first block | on the last | IS→OOS Spearman |
| --- | ---: | ---: | ---: | ---: |
| NQ | 152 | 64% | 94% | +0.599 |
| US100 | 154 | 51% | 95% | **+0.132** (research→test) |

Marginal averages say the same thing as the anatomy: `untouched=1` and `trend=1` are the only two
axes that lift every block on every feed.

**Re-selecting the grid destroys the strategy.** Rolling folds, the whole grid re-fitted on the
trailing window and read once on the next:

| feed | stitched OOS, cells chosen by the search | the SHIPPED constants over the same folds |
| --- | ---: | ---: |
| NQ | +30.8 on 46 trades | **+67.3 on 14** |
| US100 | **−0.4 on 390** | **+30.1 on 73** |
| US30 | **−1.2 on 407** | +26.6 on 59 |

The search reliably picks loose cells with many trades and no edge. Fourth time on this branch that
parameter search has bought nothing.

## 6. Monte Carlo and the tail

| feed / block | n | P(mean ≤ 0) | 95% CI of the mean | realised DD percentile | DD p99 |
| --- | ---: | ---: | ---: | ---: | ---: |
| NQ research | 26 | 0.002 | [+14.0, +57.7] | 0.81 | 194 |
| NQ locked | 17 | 0.033 | [−2.5, +104.4] | 0.74 | 288 |
| US100 research | 63 | **0.257** | [−10.5, +19.8] | 0.61 | 669 |
| US100 validation | 38 | 0.047 | [−5.9, +65.4] | 0.20 | 814 |
| US100 test | 24 | 0.001 | [+17.7, +74.1] | 0.98 | 167 |
| US30 research | 64 | **0.448** | [−37.4, +34.6] | 0.82 | 1,780 |
| US30 test | 21 | **0.470** | [−162.2, +201.8] | 0.16 | 1,945 |

Bootstrap for edge uncertainty, permutation for path risk. Two realised drawdowns sit at percentile
0.11–0.22 of their own permutation distribution, which means the observed path was **lucky**: size
for the p99, not the realised.

**The entire downside is 27 unstopped clock exits.** Pooled over all four feeds, 271 target exits
average **+0.222% of price** and 27 clock exits average **−1.077%**, worst −3.14%. Those 9% of
trades carry −93% of net. The three worst trades on every feed are flatten exits: US30 −1,179 points,
US100 −317, NQ −124. A no-stop system's whole risk lives in the days the fade never comes back.

## 7. All four markets in comparable units

Points are not comparable across four instruments, so the unit is percent of entry price.

| feed | n | mean % of price | win | p5 | worst | clock exits |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ 1m | 43 | +0.200 | 86.0% | −0.45 | −0.91 | 2% |
| US100 15m | 125 | +0.131 | 73.6% | −1.18 | −2.86 | 9% |
| US30 15m | 106 | **+0.028** | 63.2% | −0.81 | −3.14 | 13% |
| US30_ISO 15m | 24 | +0.132 | 79.2% | −0.52 | −2.93 | 4% |
| **pooled** | **298** | **+0.104** | 72.1% | −0.97 | −3.14 | 9% |

Pooled bootstrap P(mean ≤ 0) = **0.0054**. All four feeds are positive in these units, and US30 is
positive only because the unit is not the one that failed its control.

**A DENOMINATOR TRAP, CAUGHT IN THE ACT.** The natural "R" of a target-only system is the
entry-to-target distance. In that unit the same 298 trades score **−0.213** with a worst of
**−114.3 R** — one US30 trade whose entry-to-EMA gap was 0.0001% of price. When the session opens
almost exactly on the EMA the denominator collapses and the ratio explodes. Identical pathology to
the channel stop in `STUDY_SWEEP_110K`. Percent of price cannot collapse; use it.

**The cost floor is real and the fix is monotone.** Requiring a minimum entry-to-EMA gap lifts the
pooled result at every rung — 0.104 → 0.115 → 0.122 → 0.148 → 0.239 at floors of 0/0.10/0.20/0.40/
0.60% — and the same ladder is monotone on the RESEARCH blocks alone (+0.054 → +0.078), so it is not
a reserved-block choice. It costs two thirds of the trades to get there, and US30 turns negative at
the 0.60 rung, so it is a real property of the geometry rather than a shippable setting.

## 8. Regimes

- **Volatility** (realised over the prior 20 sessions): US100's lowest tercile earns +3.6 against
  +31.1 and +28.3 in the upper two. NQ's top tercile is +74.2. The rule wants a moving market.
- **Trend location**: US100 earns +42.1 when price is BELOW its 200-session EMA against +3.2 in the
  middle tercile. NQ is the same shape (+76.7 below). The fade pays in the drawdowns, not the melt-ups.
- **Gap size**: on NQ the widest entry-to-EMA tercile earns +76.1 against +18.6 for the narrowest —
  the same finding as the cost floor in §7, from the other direction.
- **Year**: US100 is negative in 2016, 2019 and 2020 and makes 2024 alone (+1,012 of +2,598 net).
  US30 makes 2020 (+1,091) and loses 2018 (−1,138). Two years carry each feed.
- **Weekday**: NQ Friday earns +104.0 against +20 to +37 on the other four days, on 8 trades. That is
  a calendar condition on a tiny sample, and this branch bans them from rule search for that reason.

## 9. Funded evaluation

The rule trades on **5.8% of sessions**, so an evaluation clock is the binding constraint, not the
drawdown. On a $50,000 account with a 6% target, 4% trailing drawdown and 2% daily loss:

| MNQ contracts | P(pass) in 60 sessions | in 120 | in 250 | P(bust), 120 |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 0.0% | 0.0% | 1.2% | 0.0% |
| 2 | 0.6% | 5.4% | 33.1% | 0.0% |
| 4 | 10.7% | 30.4% | 59.2% | 25.8% |
| 8 | 31.3% | 59.1% | 71.4% | 26.5% |
| 16 | 57.0% | 74.2% | 75.1% | 22.4% |

At one or two contracts it does not lose — it never finishes. Sized to finish, a quarter of attempts
bust on a strategy with no stop. Print P(neither) beside P(pass) or the table lies.

## 10. Verdict

**Not ready for live trading, and the reasons are specific.**

1. **US30 is null over nine years**, on every block and against both controls (p 0.245–0.494), with
   P(mean ≤ 0) of 0.45. A third of the pooled sample carries no edge at all.
2. **US100 fails on research (p 0.224) and passes on the two later blocks.** Passing out of sample
   while failing in sample is the wrong shape, and the whole family improves monotonically across
   three ordered blocks on both long feeds.
3. **NQ is the only feed that behaves correctly** — day control p 0.013 on research, 0.097 on locked,
   decaying in the right direction — and it is 43 trades over three years.
4. **The parameter search actively destroys it**, which is evidence the constants were not fitted to
   these blocks, and also that there is nothing to tune.
5. **No stop.** 9% of trades never reach the target, they carry −93% of net, and the worst is −3.14%
   of price in one session. The realised drawdowns were lucky draws from their own permutation
   distributions.

What is genuinely there: the conjunction of "untouched EMA" and "trend day" selects sessions whose
next open reverts, the direction call is real where it works at all, and the pooled result across
four feeds is +0.104% of price at P(mean ≤ 0) = 0.005. What is not there is a second market that
confirms it in the block where it should be strongest.

**No entry in `EDGE_LIBRARY.md`.** The bar is a mechanism that clears a matched control on a block it
was not selected on; the untouched-EMA filter clears one on NQ research and misses on NQ locked
(0.097), fails on US100 research, and fails on US30 everywhere. One feed's research block is not a
footing. What would change the verdict is a fifth instrument with a long history, or a stop.

## 11. The Pine port, and what its order model does that the engine's does not

`pine/trendday/TRENDDAY_EMA_strategy.pine`. `research/trendday/td_parity.py` re-implements the
SHIPPED SCRIPT's order model from the Pine file — Pine's fill rules included, so an order placed at a
bar's close fills at the next bar's open and a resting `strategy.exit(limit=)` set at a bar's close is
live from the next bar — and diffs it against `td_core.walk` trade for trade.

**On a 1-minute chart the port is exact.**

| NQ 1-minute | value |
| --- | ---: |
| trades, engine vs script | 43 vs 43 |
| same entry bar / same side / same exit bar | 43/43, 43/43, 43/43 |
| P&L correlation | **1.0000** |
| mean points, engine vs script | +40.88 vs +40.97 |

The +0.09 is the flatten and nothing else: the engine closes at the CLOSE of the session's last bar,
and `strategy.close_all()` cannot sell the close of the bar that triggers it, so the script places
the order one bar earlier and fills at that last bar's OPEN. One trade in 43 exits on the clock, so
the whole difference is one bar on one trade. Same lesson as the `flat_open` fix in
`STUDY_NEW_DESIGN`.

**On a coarser chart the script is a DIFFERENT STRATEGY, and the harness is what showed it.** The
direction is decided from the session-open bar's open, so the earliest fill Pine can reach is the
open of the bar AFTER it: minute 1 on a 1-minute chart, minute 5 on a 5-minute chart, minute 15 on a
15-minute chart. The §1 parity block filled the 15-minute model at the 09:30 open, which Pine cannot
do with a market order. Diffing the script against the engine on the same 15-minute files:

| feed | engine trades | script trades | same side / exit bar | P&L corr | mean gap |
| --- | ---: | ---: | ---: | ---: | ---: |
| US100 15m | 125 | 98 | 97/97, 97/97 | 0.903 | −5.7 pts |
| US30 15m | 106 | 94 | 87/87, 87/87 | 0.930 | +12.8 pts |

Every shared trade agrees on side and exit bar and **none agrees on the entry bar**, which is the
signature of a pure fill-timing difference rather than a rule difference. But a fifth to a quarter of
the trades simply do not exist: price reaches the EMA during 09:30–09:45 and the trade is never
opened. **Section 2's US100 and US30 figures therefore describe the EA, not this script on a
15-minute chart.**

The same delay measured on NQ, where every resolution is available:

| chart | fill minute | n | mean pts | win | PF |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1-minute | 1 | 43 | +40.97 | 86.0% | 4.68 |
| 5-minute | 5 | 39 | +50.15 | 84.6% | 5.01 |
| 15-minute | 15 | 29 | +44.89 | 79.3% | 4.28 |

The later fills score HIGHER per trade on FEWER trades, which is selection and not improvement: the
trades that survive to a later fill are the ones price had not already reverted. Net points are
+1,762 / +1,956 / +1,302. Forty-three trades cannot separate those, and the trade sets differ by a
quarter, so read this as three related strategies rather than one sampled three ways. **Run the
script on a 1-minute chart**; the `Require a 1-minute chart` input enforces it and is on by default.

One EA behaviour is deliberately not ported: the check that the fill price is still on the entry side
of the target. Pine cannot see a fill price before ordering, and the check never fired once across
four feeds and 298 trades — when a session has just trended without touching its EMA, the EMA is far
from the next open. A gap through the target would in any case exit at the target on the fill bar,
because the resting limit is live from that bar.

## 12. A 127,008-cell sweep: can it be loosened 5x and still pay?

`research/trendday/td_sweep.py`, `td_analyse.py`, `td_finalist.py`; output in
`results/trendday/sweep_*.csv`, `sweep_analysis.txt`, `finalist.txt`.

Nine axes: EMA period (7) × bucket length (2) × trend ratio (7) × **maximum touched buckets** (6,
generalising the EA's untouched flag so 0 is the rule and 99 is off) × minimum entry gap (4) ×
target fraction (3) × stop (3) × maximum hold (3) × flatten time (2) = **127,008 cells per market**,
run on all four feeds. Two phases: the day filter depends only on (EMA, bucket) so it is walked once
per pair and cached as per-session statistics plus the EMA after every bucket, and every other axis
then costs a walk over the qualified sessions only. 127,008 cells in **18 seconds** on NQ.

**Selection is on research only, scored by the WORST of the three long feeds** so a cell has to work
everywhere rather than average out. The reserved blocks are read once, at the end, carrying the
multiplicity: a Bonferroni threshold over 127,008 tests is 3.9e-07 and nothing here is within
several orders of magnitude of it.

### The ask is not available at any price

The shipped rule takes 26 / 63 / 64 research trades on NQ / US100 / US30, so 5x means 130 / 315 /
320 — about a quarter of all sessions against the shipped 5%.

| gate, on research, on all three long feeds at once | cells |
| --- | ---: |
| 5x entries | 29,538 |
| PF ≥ 2.0 | 194 |
| **5x entries AND PF ≥ 2.0** | **0** |
| 5x entries and PF ≥ 1.5 | 0 |
| 5x entries and PF ≥ 1.3 | 0 |
| 5x entries and PF ≥ 1.2 | 40 |
| 4x, 3x or 2x entries and PF ≥ 2.0 | 0 |

Not one configuration in 127,008 reaches five times the entries at a profit factor of two on all
three markets, and that is **before** any out-of-sample penalty — it is the in-sample block, the
easiest number the data can produce.

### The frontier, and it is monotone

Best worst-feed research profit factor available at each entry multiple:

| entries | 1.0x | 1.5x | 2.0x | 2.5x | 3.0x | 4.0x | 5.0x | 8.0x |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| best min PF | 1.92 | 1.85 | **1.70** | 1.58 | 1.41 | 1.36 | **1.28** | 1.20 |

Entries and profit factor trade against each other smoothly across two decades of data on three
instruments. That is a property of the geometry, not a search failure: the day filter is the edge
(§4), so every additional trade is drawn from a pool that has less of it.

**The top 1,000 cells by worst-feed profit factor have a MEDIAN ENTRY MULTIPLE OF 0.42x.** The best
configurations in the grid trade *less* than the shipped rule, not more.

### The best thing the sweep found, and why it still fails

The best worst-feed profit factor at 2x entries is EMA 15, trend ratio 50%, **up to 2 touched
buckets**, full EMA target, flatten three quarters of the way through the session. It holds
everywhere:

| feed | research | reserved blocks |
| --- | ---: | --- |
| NQ | n 82, PF 1.70, +13.5 | locked n 38, PF 1.67, +25.8 |
| US100 | n 140, PF 2.12, +13.3 | validation PF 1.44, test PF 1.85 |
| US30 | n 145, PF 1.72, +16.3 | validation PF 1.34, test PF 2.04 |
| US30_ISO | n 50, PF 1.23, +17.0 | locked PF 1.01 |

Matched day controls: NQ p 0.050 / 0.117, US100 p 0.000 / 0.034 / 0.067, US30 p 0.004 / 0.178 /
0.044. Pooled in percent of price, research +0.0794% at P(mean ≤ 0) 0.0005 and the reserved blocks
+0.0937% at 0.0125. Via vectorbt on the stitched four-feed equity: **Sharpe 0.97 against the shipped
cell's 0.79**, total return 84.1% against 34.5%, and max drawdown −12.45% against −6.86%.

**And its EMA axis is a spike.** Moving that one axis a single rung:

| EMA period | 10 | **15** | 20 | 25 |
| --- | ---: | ---: | ---: | ---: |
| worst-feed research PF | 1.01 | **1.70** | 0.96 | 0.97 |

`STUDY_V16_MOMENTUM` rejected its own best cell pre-holdout for exactly this, and the rule on this
branch is that a plateau is necessary though not sufficient. Every other axis of this cell is fine —
trend ratio 1.39/1.70/1.75/1.52, minimum gap 1.70/1.72/1.65, target fraction 1.39/1.70/1.70, and a
stop makes it worse (1.70 → 1.19) — but one spiked axis out of nine is enough.

**No coherent cell exists at any useful level.** Requiring every immediate neighbour on every axis to
clear a floor on the worst feed:

| gate | cells |
| --- | ---: |
| ≥ 2x entries, every neighbour ≥ 1.50 / 1.40 / 1.30 | 0 / 0 / 0 |
| ≥ 3x entries, every neighbour ≥ 1.30 / 1.20 | 0 / 0 |
| ≥ 5x entries, every neighbour ≥ 1.20 / 1.10 | 0 / 0 |

The highest floor any cell reaches is a worst-neighbour PF of **1.23 at 2x**, **1.18 at 3x** and
**1.07 at 5x**. For reference the shipped cell's own worst neighbour is 0.75 — so the shipped rule
is no more coherent than its loosenings, which is consistent with §5's finding that its constants
were not fitted here either.

### And the ranking does not transfer

Spearman correlation of a cell's per-trade mean between blocks, over ~124,000 scorable cells:

| feed | research → next | research → last |
| --- | ---: | ---: |
| NQ | −0.074 | — |
| US100 | +0.109 | +0.219 |
| US30 | +0.124 | **−0.204** |

Top-decile transfer is real on US100 but **negative on US30's test block** (+26.8 against a
population of +31.5). A ranking that does not transfer means the 2x cell's out-of-sample survival is
one draw, not skill.

### Verdict on the sweep

**5x entries at PF 2.0 does not exist in this family.** The best available at 5x is PF 1.28, and at
2x it is 1.70 with a spiked EMA axis and no coherent neighbourhood anywhere in the grid. Fifth time
on this branch that a large parameter search has bought nothing: `STUDY_SWEEP_110K` (110,250 cells),
`STUDY_V14_WINDOW_GRID` (1,290,240), `STUDY_TREND_PULLBACK_2` (5,723,136), §5 above, and now this.

If a looser version is wanted anyway, the honest statement is: **about twice the entries at a profit
factor near 1.7, holding on all four feeds and roughly a fifth better on Sharpe than the shipped
rule, chosen from 127,008 and sitting on a spike in its EMA.** That is a candidate to watch forward,
not a validated setting, and the sweep is the reason to distrust it rather than the reason to trust
it.

**A note on vectorbt.** The sweep itself cannot be expressed in vectorbt's signal framework — the
target trails a session EMA that is recomputed per bucket behind a causal touch test, which is
path-dependent state, not a vectorisable signal — so the 127,008-cell search runs on the compiled
walk above. vectorbt 1.1.0 is used for what it is genuinely good at: the portfolio statistics on the
finalists' stitched equity, quoted in this section.

## 13. A Donchian channel on the 3x, 5x and 8x rungs — 543,948 more cells

`research/trendday/td_sweep2.py`, `td_dc_analyse.py`, `td_dc_final.py`; output
`results/trendday/dc_analysis.txt`, `dc_final.txt`.

Section 12's frontier tops out at profit factor 1.41 / 1.28 / 1.20 at three, five and eight times
the shipped entry count. A Donchian channel was added in the three ways that make sense for a fade,
all causal and all at session scale over the n **completed** sessions before the one being judged:

- **GATE** — the qualifying session must have closed at the extreme of its own channel, an up trend
  day in the top `dc_gate` of it and a down day in the bottom. The structural reading of "trend day"
  that the |close − open| / range ratio only approximates.
- **STOP** — the fade is cut when price breaks the channel against it, from three quarters of the way
  inside the channel out to half a width beyond it.
- **TARGET** — aim at the channel midpoint instead of the live EMA. Direction still comes from the
  EMA; a midpoint on the wrong side of the open is skipped rather than inverted.

Eleven axes, **543,948 cells per market**, all four feeds, same discipline as section 12: research
only, scored by the worst of the three long feeds, one reserved read.

### It does not raise the rungs

| entries | without Donchian | with Donchian | change |
| --- | ---: | ---: | ---: |
| 3x | 1.41 | 1.49 | **+0.07** |
| 5x | 1.25 | 1.27 | **+0.02** |
| 8x | 1.06 | 1.08 | **+0.01** |

That comparison is within this grid, so the axes are otherwise identical. **The Donchian axes
multiply the cell count by 129, and the best-of gain is +0.07, +0.02 and +0.01.** Searching 129
times harder raises a maximum-of-draws by more than that on its own. There is no rung where the
channel earns its place.

Each use alone, at the same rungs:

| entries | none | gate only | stop only | midpoint target only | gate + stop |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3x | 1.41 | 1.36 | 1.49 | 1.37 | 1.38 |
| 5x | 1.25 | 1.17 | 1.27 | 1.14 | 1.16 |
| 8x | 1.06 | 1.05 | 1.08 | 1.02 | 1.05 |

**The gate and the midpoint target both make it worse at every rung.** Only the "stop" ever helps,
and the next paragraph is why that word is in quotes.

### The stop that helps is not a stop

Every finalist at 3x, 5x and 8x sets the stop at 1.25 or 1.5 — a quarter to a half of a channel
width **beyond** the extreme — and **0% of their trades ever exit on it**. What that setting
actually does is refuse the trade when the session opens already beyond an extended channel edge. It
is an entry filter wearing a stop's name, and its whole contribution is trading less.

The first pass only tested stops at or beyond the extreme, which is why none fired. Re-run with the
stop placed **inside** the channel it does fire — 19% of trades at three quarters inside, 9% at the
midpoint, 36% at the extreme itself — and none of those cells reaches the frontier at any rung. A
Donchian stop that actually stops does not pay for what it costs, which is the same answer §4 gave
for a gap-multiple stop (1.70 → 1.19).

### Everything else points the same way as section 12

- **Coherence got WORSE, not better.** Requiring every immediate neighbour on every axis to hold,
  the best worst-neighbour profit factor is **1.07 at 3x** and **0.99 at 5x**, against 1.18 and 1.07
  without the Donchian. Extra axes bought extra spikes.
- **The top 1,000 cells have a median entry multiple of 0.05x.** With more knobs the search runs
  *further* from the ask, not closer.
- **The reserved blocks decay with every extra trade.** Research → reserved profit factor: the 3x
  cell 1.44 → 1.15, the 5x cell 1.19 → 1.11, the 8x cell 1.08 → 1.11.

### The whole ladder in vectorbt, four feeds stitched

| configuration | n | PF | annualised | Sharpe | Sortino | max DD | Calmar | stop exits |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| shipped (1x) | 298 | 1.65 | 4.49% | 0.79 | 1.22 | −6.86% | 0.65 | 0% |
| best 2x, no Donchian | 748 | 1.60 | 9.15% | **0.97** | 1.52 | −12.45% | **0.73** | 0% |
| best 3x with Donchian | 1,068 | 1.28 | 4.37% | 0.71 | 0.94 | −8.33% | 0.52 | 0% |
| best 5x with Donchian | 1,798 | 1.15 | 4.98% | 0.50 | 0.63 | −19.74% | 0.25 | 0% |
| best 8x with Donchian | 2,567 | 1.10 | 3.91% | 0.42 | 0.53 | −17.36% | 0.23 | 0% |

Every risk-adjusted measure falls monotonically as entries rise, and drawdown roughly triples from
1x to 5x. **The 2x cell from section 12, with no Donchian at all, remains the best thing found in
671,000 configurations across two sweeps** — and section 12 already disqualified it for sitting on a
spike in its EMA axis.

### Verdict

**A Donchian channel does not raise the 3x, 5x or 8x rungs.** The frontier is a property of the day
filter: the untouched-EMA-plus-trend-day conjunction *is* the edge (§4), so every additional trade is
drawn from a pool with less of it, and no second indicator refills it. Sixth large search on this
branch to buy nothing, and the second on this family.
