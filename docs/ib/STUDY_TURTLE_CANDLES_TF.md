# Candlestick features and a real timeframe parameter on the Turtle Long-Only script

`research/tcandle/` — `tc_core.py`, `tc_feat.py`, `run_c0.py` … `run_c4.py`.

Two asks, taken in the order the evidence requires: the timeframe question first, because it changes
what the primary *is*, and the candlestick question second, because a feature layer can only be
built on a primary that has already cleared its own gate.

The kernel is not rewritten. `turtle15/pine_parity.run_pine` already transcribes this exact order
model — System 1 and System 2, the skip-after-a-winner rule, the ladder's rungs all resting at once,
the stop re-anchored to every fill, one exit at the higher of the ATR stop and the channel low — and
it takes the entry gate as a `mask`, so the hook this study needs already exists and nothing had to
be parameterised into a frozen kernel.

## 1. The timeframe finding: a bar count is not a setting

Every length in the script is a **bar count**. `entry1 = 20` is 5 hours on a 15-minute chart and 80
hours on a 240-minute one, so the four presets are not four settings of one strategy — they are four
different strategies, and the HUD's red "WRONG TIMEFRAME" warning is the script correctly refusing to
answer a question it was never asked. `STUDY_V57_REVERSE_ENGINEER` recorded the live version of this:
a 90-minute pivot and a 600-minute window, run as raw bar counts on a 1-minute chart, became 3 and 20
minutes — one thirtieth of their reach — and the rule could not see the setups it was being asked
about.

So the axis was swept in **both readings**, three markets × five timeframes × two blocks:

* **CARRIED** — 20/55/10/20 bars at every timeframe. What the script does today.
* **MATCHED** — the *time* reach of the 240m preset held constant, so the bar counts scale by 240/tf
  (at 30m that is 160/440/80/160).

Marginal average over the three markets, percent of entry price per trade:

| tf | carried research | matched research | carried locked | matched locked |
|---|---|---|---|---|
| 15m | −0.0512 | **+0.0076** | −0.0388 | −0.0234 |
| 30m | −0.0471 | **+0.0534** | −0.0164 | −0.0274 |
| 60m | −0.0525 | **+0.0525** | −0.0940 | −0.0601 |
| 120m | −0.0354 | **+0.0084** | −0.0486 | **+0.0132** |
| 240m | +0.0369 | +0.0369 | −0.0467 | −0.0467 |

**Carried is negative at every timeframe except the one it was measured on. Matched is positive at
four of five.** Paired cell by cell, excluding 240m where the two readings coincide by construction,
matched beats carried in **9 of 12 research cells and 9 of 12 locked cells** (mean +0.0770 and
+0.0250 per trade).

**And it is not the usual trade-count artifact.** The matched reading keeps only 12–64% of the
trades, which is exactly the shape that has faked an improvement repeatedly on this branch — so the
same comparison was run on **total** return, where trading less is a cost rather than a free win.
Matched beats carried in **11 of 12 research cells and 9 of 12 locked cells** there too, and the gap
is not marginal: mean total return over the twelve cells is **−38.13% carried against −0.91% matched**
on research and **−16.50% against +0.25%** on the locked block. The bar-count reading is not merely
worse per trade; it is what makes the strategy lose money on any chart faster than the one its preset
names.

What that does and does not say. It is a **units fix, not a fitted parameter** — nothing here was
chosen to make a number larger, and the reference reach is the preset's own. It does not make the
system profitable: the matched locked marginals are still negative at three of five timeframes. The
claim is only that the script currently throws away most of its own reach the moment it is moved, and
that the fix costs nothing.

## 2. Candlestick patterns: the trigger does not restate them, it excludes them

The base-rate check comes before any P&L. Eight separate families on this branch turned out to be the
trigger wearing a second name — RSI ≥ 55 on 94.7% of breakout bars, Aroon osc ≥ 0 on 100.0%, MACD > 0
on 99.8–100.0%, MFI ≥ 50 on 91.7%, EMA13 > 48 on 82.6%, +DI > −DI on 97.8%, close > EMA50 on 93.7%,
and the VWAP-EMA spec's C1 at a coefficient of variation of exactly zero — so the first question asked
of a candlestick pool is how often it passes on the bars the rule already fires on.

The answer here is a different failure mode, and it is arithmetic. A System 1 entry needs
`high > max(high[1..20])`, and that maximum **includes the previous bar's high**, so `high > high[1]`
follows by construction — measured at **100.00% of signal bars across all fifteen market × timeframe
cells**. Every pattern whose definition requires `high <= high[1]` is therefore *unavailable*:

| | patterns |
|---|---|
| **never fires** (5 of 32) | `harami_bull`, `harami_bear`, `inside_bar`, `piercing`, `dragonfly` |
| **under 5%** (14 of 32) | `dark_cloud`, `marubozu_bear`, `gap_dn`, `three_black`, `kicker_bull`, `gravestone`, `evening_star`, `hammer`, `three_inside_up`, `gap_up`, `tweezer_top`, `engulf_bear`, `marubozu_bull`, `shooting_star` |
| **usable middle** (13 of 32) | the rest |
| **over 50%** | **none** |

So candlesticks are the first confirmation family tested here that is *not* the trigger restated —
no discrete pattern passes even half the signal bars. They fail the availability test instead: **19 of
32 cannot support a test at all**, and the textbook advice to "confirm the breakout with a bullish
reversal pattern" asks for several patterns that a breakout bar makes impossible.

The continuous shape readings behave the other way, as expected: `bull_share_10` passes 93.3% of
signal bars, `up_closes_5` 85.8% and `close_vs_prev_hi` 82.5% — those *are* the trigger restated.

## 3. Gate 1: the presets pass on the market with three years and fail on the two with nine

Before a single feature is scored, the primary is scored alone against a **matched random entry** —
same gate-eligible bars, same ATR stop, same ladder, same channel exit, same position lock, and the
same **System 1 / System 2 mix**, because a System 2 entry is exited on the 20-bar channel and a
System 1 entry on the 10-bar one, so an all-System-1 control gets a systematically tighter exit and
the comparison flatters the rule. Drawn bars are sorted before use (`STUDY_V59`: an unsorted control
let the position lock reject an arbitrary share of each draw and made a rule beating its null by
+0.18 score p 0.404).

| market | tf | preset | block | n | %/trade | PF | control | p |
|---|---|---|---|---|---|---|---|---|
| NQ | 240 | T1 | research | 32 | **+0.3183** | 3.76 | −0.0123 | **0.010** |
| NQ | 240 | T1 | locked | 23 | −0.0361 | 1.45 | −0.1870 | 0.204 |
| NQ | 240 | T2 | research | 36 | **+0.2608** | 3.19 | −0.0051 | **0.025** |
| NQ | 240 | T2 | locked | 31 | −0.1539 | 0.99 | −0.1080 | 0.612 |
| NQ | 60 | T4 | research | 117 | +0.0185 | 2.10 | −0.0398 | **0.050** |
| NQ | 60 | T4 | locked | 73 | −0.1718 | 0.83 | −0.0908 | 0.935 |
| US100L | 240 | T1 | research | 100 | −0.0702 | 1.57 | −0.1415 | 0.264 |
| US100L | 240 | T1 | locked | 56 | +0.1391 | 1.99 | −0.0873 | 0.065 |
| US100L | 120 | T3 | research | 260 | −0.0934 | 1.52 | −0.0883 | 0.542 |
| US100L | 120 | T3 | locked | 120 | +0.1439 | 2.20 | −0.0629 | **0.005** |
| US100L | 60 | T4 | research | 356 | −0.1037 | 1.54 | −0.0684 | 0.906 |
| US30L | 240 | T1 | research | 102 | −0.0937 | 1.25 | −0.0432 | 0.741 |
| US30L | 120 | T3 | research | 234 | −0.0359 | 1.76 | −0.0418 | 0.458 |
| US30L | 60 | T4 | research | 341 | −0.0302 | 1.66 | −0.0357 | 0.388 |

**3 of 10 research cells clear p ≤ 0.05 against 0.5 expected — and all three are NQ**, the market
with three years of data and 32–117 trades. Every cell on the two feeds carrying nine years fails,
and their per-trade result is negative on research in **6 of 6**. The pattern is
`STUDY_V12_DONCHIAN_3020` exactly: the instrument that chose the settings is the one that passes.

Two readings that have to stay attached to the passes:

* **The control loses money in every cell** (median −0.005 to −0.187 %/trade). "Clears its matched
  control" here means the rule beats a null that is itself unprofitable, which is a weaker statement
  than clearing zero — `STUDY_V15_BOOK`'s split, and `STUDY_IB_US30_OPTUNA`'s sentence: a rule that
  beats a losing null is still a losing rule unless it also clears zero.
* **The two cells that pass on the locked block both fail on research** (US100L 120m T3, 0.542 →
  0.005; US100L 240m T1, 0.264 → 0.065). A rule chosen on research should look better there. That is
  the wrong shape, for the fifteenth time on this branch, and it is treated as a defect rather than a
  result.

**Cost is not the objection here, which is rare.** The round turn is **0.6% to 1.9% of the 2.0N
stop** on every cell, against the 24% a 0.75×ATR scalping stop carries on this data. Nothing in this
study is a cost problem.
