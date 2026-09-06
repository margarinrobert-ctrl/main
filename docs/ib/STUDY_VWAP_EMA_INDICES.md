# The VWAP-EMA rule on US100, US30 and a reserved forward block

`research/vwapema/ve_markets.py`, `run_m1.py` … `run_m5.py`, `plot_m.py`.
Results in `results/vwapema/m1_*.csv` … `m5_*.csv`, figures `vwapema_indices*.png`.

## 0. Why this is the test the gold study could not be

`STUDY_VWAP_EMA_GOLD.md` measured Bhatti's spec (SSRN 6650958) on XAU/USD — the instrument it was
written for. Every number there carried the objection that the six conditions were chosen with gold
in mind, and its section 33 showed the surviving presets were a gold-rally exposure. US100 and US30
had **no part in writing the rule** and no part in tuning it until they are searched here in their
own right, so:

- the **published rule frozen** on them is the cleanest test the spec can be given;
- a cell chosen on one index and read on the other is a genuine cross-market freeze;
- **US30_ISO** — 48,937 bars from a *different provider*, 2024-08 to 2026-08, 27,436 of them
  post-dating every other file on this branch — is held as a **reserved forward block**, never
  searched, read once at the end.

Same engine as the gold study (`vecore.py`, refactored so `assemble()` takes any OHLCV frame and
`build()` still reproduces every gold figure to the cent — verified: research −0.0447 R, locked
+0.1423 R, 592 trades, unchanged).

## 1. The feeds, and three things that are not the same as gold

| feed | bars | span | peak minute-of-day | corr(volume, range) | median vol | research/locked cut |
|---|---|---|---|---|---|---|
| US100_LONG_15m | 206,703 | 2016-11-14 → 2025-10-01 | **570** | +0.713 | 1,106 | 2022-08-29 |
| US30_LONG_15m | 193,663 | 2016-11-01 → 2025-07-15 | **570** | +0.766 | 1,145 | 2022-06-28 |
| US30_ISO_15m | 48,937 | 2024-08-19 → 2026-08-26 | **570** | +0.728 | 865 | *not split* |

Registry-verified before use: US100_LONG sha256 `c449dddfbc06a943` **ok**, US30_LONG
`24dcf2e1c7ba398f` **ok**, US30_ISO rows and span exact (its recorded byte size is of the unwrapped
derivative, so rows+span are its identity).

**The clock was re-derived, not trusted.** Mean bar range by minute-of-day peaks at **570 = 09:30
New York** on all three, which is what the registry's "New York + 7" for the LONG feeds and the
ISO feed's own stated −04:00/−05:00 predict. The ISO feed agreeing is the positive control: its
offset is *stated in the file* rather than derived.

**The volume column was checked.** Both LONG feeds carry `Volume` identically **zero** and
`TickVolume` as the real column. Reading the wrong one makes C5 (`V > 1.1 × SMA20(V)`) fire on
nothing and makes the VWAP an unweighted mean — exactly the `XAUUSD15_MT` defect that made the
uploaded gold file unrunnable. `corr(volume, bar range)` is **+0.71 to +0.77** on all three here,
against **+0.005** for that fake column. It is still broker **tick** volume, not traded volume, so
every VWAP and C5 number inherits that proxy.

**Cost is cheap here, and that inverts the gold verdict on execution.** Branch stack: 0.75 points a
side on US100, 1.50 on US30, plus 0.10 slippage a side.

| feed | median risk | as % of price | round turn | **cost in R** | break-even at 3R |
|---|---|---|---|---|---|
| US100 | 39.5 pts | 0.324% | 1.70 | **0.043** | 26.1% |
| US30 | 74.9 pts | 0.244% | 3.20 | **0.043** | 26.1% |
| US30_ISO | 128.0 pts | 0.279% | 3.20 | **0.025** | 25.6% |
| *gold, for comparison* | 2.35 USD/oz | — | 0.40 | **0.170** | 29.2% |

Gold's round turn is **17% of risk**; on the indices it is **2.5–4.3%**. The gold study's finding
that "the rule is positive gross and negative net, and the round turn is the whole difference"
**cannot** be the explanation here. Whatever is wrong on the indices is not cost.

## 2. Base rates on the trigger's own bars, before any P&L

`pass_given_others` — the share of bars *already admitted by the other five conditions* that a
condition also passes. A condition near 100% there is the trigger restated and can contribute
nothing (the branch has now measured that for RSI 94.7%, Aroon 100.0%, MACD 99.8%, MFI 91.7%,
EMA13>48 90.9% and the stochastic).

| condition | US100 L / S | US30 L / S | US30_ISO L / S |
|---|---|---|---|
| C1 close vs EMA200 | 76 / 55 | 70 / 57 | 79 / 67 |
| C2 close vs VWAP | 86 / 86 | 78 / 82 | 86 / 90 |
| C3 **EMA50 pullback** | **33 / 29** | **29 / 29** | **30 / 33** |
| C4 candle (wick or engulf) | 41 / 43 | 35 / 37 | 48 / 54 |
| C5 volume spike | 73 / 80 | 67 / 74 | 73 / 81 |
| C6 range ≥ 0.8 ATR | **95 / 97** | **97 / 98** | **96 / 98** |
| ambiguity band | 91 / 85 | 83 / 79 | 84 / 82 |

**C6 is inert on every feed and both sides** — a bar that already passes a volume spike and a
candle pattern has a range ≥ 0.8 ATR 95–98% of the time. C2, the VWAP condition the paper names in
its title, passes 78–90%. **C3, the EMA50 pullback, is the only binding condition**, at 29–33% —
the same reading the gold study got (29.9%). The rule is, mechanically, a pullback-to-the-EMA50
filter with five decorations.

## 3. Gate 1 — the published rule, frozen, on markets that chose nothing

R per trade, then percent of entry price. Both are reported because they disagree in sign on
several rows: R divides by a risk that varies with ATR, percent of price does not, and percent is
the safe unit.

| feed | side | block | n | R | % of price | PF | win % | control p |
|---|---|---|---|---|---|---|---|---|
| US100 | LONG | research | 502 | −0.012 | +0.014 | 0.978 | 28.3 | 0.273 |
| US100 | LONG | LOCKED | 269 | −0.018 | −0.008 | 0.966 | 27.5 | 0.647 |
| US100 | SHORT | research | 357 | +0.017 | −0.012 | 1.032 | 28.3 | **0.010** |
| US100 | SHORT | LOCKED | 225 | **−0.151** | −0.053 | 0.714 | 24.9 | 0.793 |
| US30 | LONG | research | 333 | **+0.198** | +0.015 | 1.402 | 31.5 | **0.003** |
| US30 | LONG | LOCKED | 177 | −0.076 | −0.007 | 0.859 | 28.2 | 0.663 |
| US30 | SHORT | research | 293 | −0.177 | −0.031 | 0.705 | 22.9 | 0.703 |
| US30 | SHORT | LOCKED | 187 | −0.043 | +0.002 | 0.916 | 26.2 | 0.303 |
| US30_ISO | LONG | (forward) | 168 | +0.041 | +0.015 | 1.082 | — | 0.133 |
| US30_ISO | SHORT | (forward) | 175 | −0.037 | −0.039 | 0.928 | — | 0.487 |

**Two cells clear a matched control on research and both invert.** US30 long goes +0.198 R at
p 0.003 → −0.076 at p 0.663; US100 short goes +0.017 at p 0.010 → **−0.151** at p 0.793. Ten of
the twelve feed × side × block cells are unprofitable in R, and the two profitable ones on the
locked side are within noise of zero.

**The win rate is its own break-even.** Break-even at the specified 3R geometry is 26.1%; the
measured win rates are 22.9% to 31.5%. The barriers are being hit by noise.

**And it is not cost.** The zero-cost arm moves US100 long research −0.012 → +0.075 and US30 long
research +0.198 → +0.264, but the round turn is only 0.043 R — the R shift is larger than that
because small-risk trades weight more in a mean of ratios. In percent of price the whole cost is
0.011–0.013% a trade. On gold the cost *was* the difference; here removing it entirely still leaves
US100 long at +0.016 R on the locked block.

**The flatten is destructive again** — US30 long research +0.198 → +0.106 with it on, US100 long
locked −0.018 → −0.053. Sixteenth confirmation on this branch.

**No take profit is better on 4 of 6 feed × side cells** and much better on US30 long locked
(−0.076 → +0.058). And **all six Optuna finalists below independently chose `use_tgt = False`** —
the twenty-first time no-target has won here.

**The volume weighting does nothing.** Running the identical rule with an unweighted session mean
price in place of the VWAP moves the result by ≤0.02 R on every cell and changes the sign on none.
Third market on which that has now been measured (`STUDY_V63`, `STUDY_VWAP_EMA_GOLD`).

## 4. The search — 4,800 Optuna trials, research blocks only

Fourteen axes (the paper's ten free numbers plus the target, the side, the session reading and the
flatten), multivariate TPE, 800 trials × 3 objectives × 2 feeds. US30_ISO is never searched. Every
trial's locked result is logged and never used to choose; it exists only so the transfer can be
measured, which is a diagnostic of the search and not a result.

**Population shape before any top row:**

| feed | objective | scorable | % profitable research | % profitable locked | corr(res, lock) | top 1% research → locked | whole population locked |
|---|---|---|---|---|---|---|---|
| US100 | total R | 796 | 89.4 | **29.8** | +0.111 | +0.367 → **+0.030** | −0.036 |
| US100 | PF | 646 | 93.3 | 48.5 | +0.107 | +0.676 → **+0.012** | −0.002 |
| US100 | ret/DD | 778 | 90.4 | 42.0 | +0.004 | +0.550 → **−0.045** | −0.012 |
| US30 | total R | 715 | 85.2 | 40.7 | +0.342 | +0.736 → **+0.046** | −0.013 |
| US30 | PF | 545 | 88.6 | 51.7 | +0.225 | +0.958 → **−0.026** | **+0.012** |
| US30 | ret/DD | 636 | 91.0 | 69.2 | +0.420 | +0.908 → **−0.017** | **+0.045** |

**85–93% of every population is profitable on research and 30–69% on locked**, so a top row is the
maximum of several hundred positive draws. The top 1% of the research ranking reads **+0.37 to
+0.96 R in sample and −0.045 to +0.046 out of it** — and in three of six studies it is **at or
below the whole population's locked mean**. Selecting on research bought nothing, or less than
nothing.

**The marginals, which is how a grid should be read:**

- **The side is the market, not the rule.** US100's search likes SHORT (research +0.188 against
  long's +0.012) and it does not hold (locked −0.021); US30's likes LONG (+0.285 research,
  **+0.030 locked**), the only side/feed marginal positive on both blocks.
- **The stop is monotone toward TIGHTER on research and toward WIDER on locked, on both feeds**
  (US100 locked −0.033 → +0.002; US30 −0.011 → **+0.038** across the quartiles). Ninth family on
  this branch whose stop axis runs toward wider out of sample.
- **The flatten is destructive on both feeds** (US30 research +0.268 off against +0.068 on).
- **The volume multiple is monotone toward HIGHER on both feeds AND on both blocks** — US100
  locked −0.051 → +0.013, US30 −0.016 → **+0.068** — and **fANOVA gives it 0.40–0.46 of the US30
  objective and 0.22–0.43 of the US100 one**. It is the only axis with a gradient that survives the
  split, and on gold this same axis was the one that inverted. It gets its own test in §7.
- **`ambig` — the band that excludes bars too close to the EMA200 — carries 0.20–0.85 of the
  objective on US100.** That is a *distance from the MA200* condition wearing an ambiguity
  costume, which is the one filter family this branch has repeatedly found to work
  (`STUDY_V40`: a moving average is priced by its DISTANCE; `STUDY_V51`: the MA200 is a floor).

**All six finalists chose no take profit.** Two sit on a box edge (`ema_tight` at 60, `ema_pull` at
120), which means the optimum is outside the box and widening it just moves the optimum to the new
ceiling.

## 5. The one locked read

**Multiplicity stated first: 4,800 Optuna trials + ~40 research looks in M1 = 4,840.**

| feed | cell | research R (control p) | **locked R** | locked PF | locked control p | locked bootstrap P(≤0) |
|---|---|---|---|---|---|---|
| US100 | Optuna total R | +0.339 (**0.000**) | +0.078 | 1.131 | 0.100 | 0.534 |
| US100 | Optuna PF | +0.651 (**0.010**) | +0.121 | 1.238 | 0.147 | 0.427 |
| US100 | Optuna ret/DD | +0.277 (**0.000**) | −0.024 | 0.941 | 0.317 | 0.617 |
| US30 | Optuna total R | +0.330 (**0.010**) | +0.044 | 1.081 | 0.200 | 0.270 |
| US30 | Optuna PF | +0.938 (**0.000**) | +0.058 | 1.125 | 0.230 | 0.543 |
| US30 | Optuna ret/DD | +1.122 (**0.000**) | −0.018 | 0.963 | 0.343 | 0.666 |
| US100 | As published L | −0.012 (0.273) | −0.018 | 0.966 | 0.647 | 0.593 |
| US30 | As published L | +0.198 (**0.003**) | −0.076 | 0.859 | 0.663 | 0.605 |

**All six finalists clear their control on research at p ≤ 0.010 and not one clears it on locked
(best 0.100). Not one bootstrap excludes zero on locked (best 0.270).** Research profit factors of
2.48, 3.54 and 4.02 land at 1.24, 1.13 and 0.96.

**Deflated Sharpe.** `var_trials` measured over the 4,116 scorable trials' own per-trade Sharpes
is 0.006178 (sd 0.0786), so **E[max Sharpe | pure noise] over 4,840 looks is 0.2892** — and the
best per-trade Sharpe achieved by any cell is **0.1446**. Every DSR is **0.000 to 0.024**. The best
thing the search found is *below what noise alone delivers* at this trial count.

**Path risk.** MC p99 drawdown is **1.3× to 3.3×** the realised drawdown on every cell — that is
the sizing number. Three research paths sit at the 0.003–0.104 percentile of a reshuffle of their
own trades, i.e. they were unusually smooth; their locked paths are not.

**Three optimised cells are one strategy.** The US30 finalists correlate **0.60–0.91** with each
other in daily R (the gold study measured 0.965 for the same thing); US100's correlate 0.27–0.31
and all three correlate 0.28–0.48 with the *published short* rule, because all three are short.
Across feeds the correlation is ≈0.00 — US100 and US30 cells are genuinely different trades even
though the indices correlate 0.758 in returns.

## 6. The three questions that all get called "overfitting"

`STUDY_VWAP_EMA_GOLD` §21 separates them; they have different answers here too, and this time they
differ **by market**.

**(a) Is the rule fitted?** Rolling walk-forward, 36 months train / 12 test, **nothing
re-selected**:

| feed | cell | folds | IS | OOS | gap | corr(IS, OOS) |
|---|---|---|---|---|---|---|
| US100 | As published | 5 | +0.026 | +0.023 | **+0.003** | −0.311 |
| US100 | Optuna total R | 5 | +0.316 | +0.318 | **−0.002** | −0.184 |
| US100 | Optuna ret/DD | 4 | +0.218 | +0.062 | +0.155 | −0.322 |
| US30 | As published | 5 | +0.176 | +0.081 | +0.095 | +0.248 |
| US30 | Optuna PF | 3 | +0.722 | +0.097 | **+0.625** | −0.424 |
| US30 | Optuna ret/DD | 4 | +0.701 | −0.003 | **+0.704** | +0.493 |

`corr(IS, OOS)` is negative in 6 of 8 rows **with nothing re-selected** — a three-year window
anti-predicts the next year even for a fixed configuration. That is regime, not curve-fitting. The
two cells with essentially zero gap are the published rule on US100 and the US100 total-R cell; the
two US30 grid winners carry gaps of +0.63 and +0.70.

**(b) Is the search overfit?** Walk-forward with the selection **re-run inside every training
fold**, beside a random cell from the same 400-configuration pool and the author's constants. Over
all five folds US100's re-chosen arm looks like the first winner this branch has seen (+0.858 sum
against the constants' +0.099 and a random cell's −0.388) and US30's is the worst arm (−0.828
against −0.247 and +0.202).

**That US100 win is entirely pre-cut.** The fixed arms had already seen the training data of the
early folds, so only the folds whose *test* window starts after the research/locked cut are a clean
comparison — and there the re-chosen arm is **the worst arm on both feeds**:

| feed | folds | re-chosen | random cell | as published |
|---|---|---|---|---|
| US100 | 2 | **−0.174** | −0.052 | +0.011 |
| US30 | 2 | **−0.358** | −0.008 | −0.138 |

The US100 all-fold win came from one fold (2019-11 → 2020-11, +1.184). **Twelfth re-optimiser on
this branch to lose to its author's constants, and the second to also lose to a coin flip.** Two
folds cannot separate anything; the honest statement is that the search has not demonstrated value
on either market.

**(c) What is P(overfit)?** CSCV over a 400-cell × ~106-month return matrix, 12 blocks, all
C(12,6) = 924 symmetric splits:

| feed | PBO | median logit | slope of OOS on IS | IS-best cell: IS → OOS |
|---|---|---|---|---|
| US100 | **0.126** | +2.09 | +0.185 | +0.582 → +0.166 |
| US30 | **0.517** | −0.09 | +0.097 | +1.630 → **−0.118** |

**The two markets give opposite answers.** On US100 the selection is not pathological (PBO 0.126)
and the in-sample winner keeps a third of its edge; on US30 PBO is 0.517 — above the half that
means the procedure is *actively harmful* — and the in-sample winner goes from +1.63 to **−0.118**.
Both slopes are positive here, unlike gold's −1.27.

**Where each cell sits in its own pool** (median in-sample rank across the 924 splits):

| feed | as published | Optuna total R | Optuna PF | Optuna ret/DD |
|---|---|---|---|---|
| US100 | **0.165** | 0.926 | 0.980 | 0.634 |
| US30 | **0.485** | 0.832 | 0.975 | 0.985 |

The published rule sits **below the median of its own pool on both feeds** — the cleanest single
sign that a configuration was chosen by convention and not by search — and every Optuna cell sits
at the top, with nowhere to go but down. Same signature the gold study recorded (published 0.443,
fitted presets 0.707–0.984).

## 7. The reserved forward block — US30_ISO, read once

48,937 bars from a **different provider**, 2024-08 → 2026-08, 27,436 of them post-dating every
other file on this branch. Nothing here was searched on it.

| chosen on | cell | n | R | % of price | PF | control p | bootstrap P(≤0) |
|---|---|---|---|---|---|---|---|
| US30 | **Optuna total R** | 325 | **+0.157** | +0.033 | **1.311** | 0.103 | **0.084** |
| US30 | Optuna PF | 98 | −0.097 | −0.013 | 0.809 | 0.580 | 0.638 |
| US30 | Optuna ret/DD | 105 | −0.082 | −0.002 | 0.821 | 0.520 | 0.534 |
| US100 | Optuna total R | 193 | −0.104 | −0.032 | 0.813 | 0.450 | 0.855 |
| US100 | Optuna PF | 26 | −0.504 | −0.079 | 0.290 | 0.905 | — |
| US100 | Optuna ret/DD | 106 | −0.039 | −0.027 | 0.912 | 0.553 | 0.689 |
| — | As published LONG | 168 | +0.041 | +0.015 | 1.082 | 0.133 | 0.287 |
| — | As published SHORT | 175 | −0.037 | −0.039 | 0.928 | 0.487 | 0.829 |

**One of six finalists survives the forward block** — US30's total-R cell, +0.157 R at PF 1.311 on
325 trades, the largest sample of any finalist there. It does not clear its matched control
(p 0.103) or exclude zero (0.084), but it is the only one pointing the right way, and it is also
the finalist with the smallest walk-forward gap among the US30 cells. Five of six are negative and
the US100 cells are negative on all three counts.

## 8. Cross-market freeze

| chosen on | read on | cell | n | R | % of price | PF | control p |
|---|---|---|---|---|---|---|---|
| US30 | US100 | Optuna total R | 1,542 | +0.069 | +0.023 | 1.118 | **0.047** |
| US30 | US100 | Optuna PF | 413 | +0.057 | +0.048 | 1.120 | 0.237 |
| US30 | US100 | Optuna ret/DD | 439 | +0.083 | +0.037 | 1.169 | 0.190 |
| US100 | US30 | Optuna total R | 546 | −0.096 | −0.009 | 0.837 | 0.210 |
| US100 | US30 | Optuna PF | 72 | −0.087 | +0.004 | 0.842 | 0.320 |
| US100 | US30 | Optuna ret/DD | 319 | +0.014 | +0.011 | 1.032 | 0.133 |

**The direction is asymmetric and it follows the side.** All three US30 cells are LONG and all
three are positive on US100, which had no part in choosing them (one clears its control at p 0.047).
All three US100 cells are SHORT and two of three are negative on US30. Both markets rose over the
sample — US100 +420%, US30 +144% — so a long cell transferring and a short cell not transferring
is what drift predicts, not what an edge predicts.

## 9. Long vs short in bull vs bear

Same causal label as the gold study: the daily close against its own 200-day EMA, **lagged one
session**, applied as a filter and **re-simulated** (a refused signal frees the position lock and
admits a later one).

**These indices are far more one-sided than gold.** Bull share of session bars: US100 **82.1%**,
US30 **80.6%**, US30_ISO **83.7%**, against gold's 63.4%. There is barely a bear sample to test.

| feed | side | block | cells | bull beats both | bear beats both |
|---|---|---|---|---|---|
| US100 | LONG | LOCKED | 8 | **6** | 2 |
| US100 | SHORT | LOCKED | 8 | 7 | 1 |
| US30 | LONG | LOCKED | 7 | **2** | **5** |
| US30 | SHORT | LOCKED | 7 | 6 | 1 |

**The gold finding does not transfer.** There, a bull filter helped LONG in 6 of 6 presets on the
locked block. Here it helps 6 of 8 on US100 long and only **2 of 7 on US30 long**, where bear-only
is better in 5 of 7. A regime preference that reverses between two indices correlated 0.758 in
returns is not a property of the rule.

**And the always-in control settles it on all three feeds.** Same days, same side, entry at the
first New York bar, carrying **the rule's own ATR stop**:

| side | regime | cells | rule R | always-in R | mean edge | rule wins |
|---|---|---|---|---|---|---|
| LONG | bull | 45 | +0.065 | **+0.317** | −0.252 | 12 |
| LONG | bear | 34 | +0.060 | +0.164 | −0.103 | 12 |
| SHORT | bull | 46 | −0.072 | +0.289 | −0.362 | 6 |
| SHORT | bear | 33 | −0.073 | +0.149 | −0.222 | 8 |

**The rule beats always-in in 38 of 158 cells (24%)**, and the mean edge is negative in every
side × regime cell and on every feed (US100 −0.272, US30 −0.237, US30_ISO −0.210). The gold
study's decisive test reproduces on three more markets.

Read the control's own level before crediting anything against it: a session-open entry with an
ATR stop and an EMA trail earns **+0.15 to +0.32 R on both sides** in markets that rose 144% and
420%. That is the trail's asymmetry plus drift, not a direction call — the same warning
`STUDY_TURTLE` attached to a random-entry control that earned +0.586 R where the index rose 247%.

## 10. What replicates from the gold study, and what does not

**Replicates on three more markets:**

| finding | gold | US100 / US30 / US30_ISO |
|---|---|---|
| the paper's own conditions are mostly the trigger restated | C2 87.8%, C6 92.7%, C3 29.9% binding | C2 78–90%, C6 **95–98%**, C3 **29–33%** binding |
| all six free numbers rank mid-ladder | 2nd–4th of 3–5 on all eight axes | median in-pool IS rank 0.165 / 0.485 |
| the search buys research score and not locked score | research climbed with effort, locked did not | top 1% research +0.37…+0.96 → locked −0.05…+0.05 |
| optimised cells are one strategy wearing several names | corr 0.965 | US30 finalists corr **0.60–0.91** |
| the session flatten is destructive | yes | yes, both feeds |
| no take profit wins | yes | **6 of 6 finalists chose no target** |
| the volume weighting does nothing | yes | yes, ≤0.02 R on every cell |
| **always-in beats the rule** | 11 of 12 preset-blocks | **120 of 158 cells** |

**Does not replicate:**

- **Cost is not the story here.** On gold the round turn is 17% of risk and the rule is positive
  gross / negative net. On the indices it is 2.5–4.3%, and removing it entirely leaves the rule
  within noise of zero.
- **The bull-regime preference reverses.** Gold: bull-only best in 6 of 6. US30 long: bull-only
  best in only 2 of 7 locked cells, bear-only better in 5 of 7.
- **PBO disagrees by market** — 0.126 on US100 against 0.517 on US30 — where gold gave a single
  0.561. And the slope of OOS on IS is positive on both indices where gold's was −1.27.
- **The volume multiple's gradient holds instead of inverting.** On gold that axis was monotone on
  research and reversed on locked; here it is monotone toward higher on **both feeds and both
  blocks**, and it carries 0.40–0.46 of the US30 objective. That is the one thing in this family
  worth a dedicated test, and it gets one in §11.

## 11. The volume multiple — the one axis with a gradient, tested properly

M2 found `vol_mult` monotone toward higher on both feeds and, unusually, on both blocks, carrying
0.22–0.46 of every objective. On gold the same axis was monotone on research and **inverted** on
locked. So it gets the branch's test rather than another marginal: seven rungs (0.8 → 2.4) on every
feed and both sides, each against a **random filter keeping the same number of the un-gated rule's
signal bars, re-simulated end to end**, with the selectivity reported and the range condition (C6)
removed in a second arm because a volume spike is not independent of a bar's range.

**The gradient is real.** Spearman(vol_mult, R), 10 feed × side × block cells:

| cell | with C6 | C6 removed |
|---|---|---|
| US100 long research / locked | +0.750 / +0.750 | +0.643 / +0.429 |
| US100 short research / locked | +0.429 / +0.964 | +0.464 / +0.857 |
| US30 long research / locked | +0.964 / +0.929 | **+1.000** / +0.857 |
| US30 short research / locked | −0.321 / +0.964 | −0.214 / +0.714 |
| **US30_ISO long / short (forward)** | **+0.000 / −0.429** | **−0.214 / −0.393** |

Eight of ten are positive, and removing C6 barely moves them — so it is **not** the range confound.
US30 long on the locked block runs −0.114 R at 0.8 to **+0.143** at 2.4, monotone, on a block that
chose nothing.

**And it is worth nothing.** Against a same-selectivity random filter, **0 of 70 rungs clear
p ≤ 0.05, where 3.5 are expected by chance** — fewer than chance. Best p anywhere is **0.060**
(US30 long research at the published 1.1) and the best on any locked block is 0.180. The C6-removed
arm gives the same answer: 0 of 70. The rule beats its own control in only 46 of 70 rungs.

The mechanism is the one this branch keeps re-finding: **the ladder is a selectivity ladder**. It
takes the kept share from 92% down to 33%, and restrictiveness alone raises a profit factor
(`STUDY_V12`: an ATR-expansion filter looked like PF 1.42 → 1.77 and was indistinguishable from a
random filter of the same selectivity). The control climbs with the rule.

**The two cells that are genuinely unseen are the two that do not have the gradient.** On the
reserved forward block the long ladder is flat (ρ +0.000) and the short ladder is negative
(−0.429). The axis that carries the search's whole objective disappears on the only data no search
has touched.

## 12. vectorbt as a second engine

Run as a **transcription check first** — the trade count must match before any P&L difference is
read. vectorbt has failed transcription three times on this branch (`STUDY_V46`, `V51`, `V53`);
the two avoidable defects are handled as in the gold study (`sl_stop`/`tp_stop` as per-bar arrays
so an ATR stop anchored at the signal bar is expressible; the close-only EMA trail supplied as an
explicit boolean exit). Both arms run with tightening off, which M1 measured inert.

| feed | variant | engine n | vbt n | ratio | engine pts | vbt pts | gap |
|---|---|---|---|---|---|---|---|
| US100 | trail live on the fill bar (wrong) | 771 | 641 | 0.831 FAIL | +3.14 | +6.60 | — |
| US100 | trail cannot fire on the fill bar | 771 | 761 | **0.987 PASS** | +3.14 | +5.86 | **+86.8%** |
| US30 | trail live on the fill bar (wrong) | 510 | 434 | 0.851 FAIL | +5.78 | +5.19 | — |
| US30 | trail cannot fire on the fill bar | 510 | 510 | **1.000 PASS** | +5.78 | +6.32 | **+9.2%** |
| US30_ISO | trail live on the fill bar (wrong) | 168 | 144 | 0.857 FAIL | +9.04 | +1.50 | — |
| US30_ISO | trail cannot fire on the fill bar | 168 | 165 | **0.982 PASS** | +9.04 | +2.97 | **−67.1%** |

**The fill-bar defect reproduces on all three feeds** — letting the close-only trail fire on the
bar the position filled costs 14–17% of the trade count, exactly as it did on gold (0.841 there).

**And the intrabar convention is worth more than any edge measured here, with no consistent sign.**
Once transcription passes, the same signals priced by the two engines differ by **+86.8% on US100,
+9.2% on US30 and −67.1% on US30_ISO**. When the ATR stop and the close-only trail fall inside one
bar this branch takes the stop and vectorbt resolves it by its own order; `STUDY_V38` measured 2.1×
and `STUDY_V41` 22.9× for the same class of disagreement. A second engine is a second opinion about
*execution*, never a correction to the research — and on this rule it is the largest number on the
page.

## 13. Verdict

The rule as published does not have an edge on US100 or US30. Two cells clear a matched control on
research and both invert; the win rate is its own break-even at the specified geometry; **cost is
2.5–4.3% of risk here, so unlike gold this is not an execution question**; and the paper's own
conditions are mostly the trigger restated, with only the EMA50 pullback binding.

4,800 trials of search bought research score and nothing else — six finalists, none clearing a
control or excluding zero out of sample, every deflated Sharpe below the noise floor of 0.289 at
the counted trial count, and the re-optimiser losing to both the author's constants and a random
cell on the folds that post-date the cut. One finalist survives the reserved forward block
(+0.157 R, PF 1.311 on 325 trades) without clearing anything.

The one axis with a persistent gradient — the volume multiple — is a selectivity ladder that
clears its control in **0 of 70** rungs and has no gradient at all on the forward block.

And the framing test settles it on three more markets: on the same days, same side, an entry at the
session open carrying **the rule's own ATR stop** beats the rule in **120 of 158 cells**. The six
conditions select days that moved and then enter later and worse than simply being there.

**Ships nothing.** The Pine script's header carries these numbers beside the gold ones; no preset
is recommended for either index.
