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
