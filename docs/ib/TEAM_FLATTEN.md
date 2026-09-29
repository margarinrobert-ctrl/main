# Pricing the 11:00 flatten, in the one configuration that was asked for

The user insists on a **07:00-11:00 New York entry window with a hard flatten at 11:00**. This
branch carries sixteen recorded confirmations that a hard flatten is destructive, and none of them
was measured on a rule shaped like this one. So the flatten was priced here rather than assumed
either way.

Configuration, fixed before anything was run and never varied: **US30_LONG_15m, Donchian 20 long,
entries 07:00-11:00 New York, 30-point stop / 150-point target**, with **50/150** as a declared
second geometry. `flat=660` means flat at the **11:00 OPEN** — the order goes out on the bar before,
and a signal whose fill would land at or after the cutoff is REFUSED rather than opened for zero
P&L (`STUDY_V60`). Research block only for everything chosen.

`research/us30team/session.py`, `run_f1.py`, `run_f2.py`, `run_f3.py`. The excursion walker is
`s30core._walk` with MFE/MAE and a per-trade counterfactual bolted on and **nothing else changed** —
asserted identical to `s30core.walk` on trade count, exit bar, exit reason and P&L across three
exit policies before any result was read.

**Trial count: 15 research hypotheses** — 10 flatten-ladder cells (5 exit policies x 2 geometries)
and 5 entry sub-windows. The `tie=1` pass is a robustness re-read of those same 15, not 15 more.
Give-back, the paired deltas, the dose-response and the permutation are decompositions of cells
already scored. **Reserved and read once: 9 cells** — 5 sub-windows and 2 declared cells on
B_holdout, 2 declared cells on C_forward (`US30_ISO_15m`, a different provider, 2024-08..2026-08).

---

## 1. The flatten ladder

Research block, stop-first convention, each cell against a SORTED matched random entry from the
same eligible in-window bars (400 draws). `be` is the driftless two-outcome break-even,
(30+2.29)/180 = **0.1794**; `res_win` is the target share among trades that actually resolved on a
barrier. `mde` is the minimum detectable effect at 80% power, `2.802 x sd / sqrt(n)`.

**30-point stop / 150-point target**

| exit policy | n | pts | sd | t | MDE | inside MDE | PF | res_win vs be | med hold | stop | target | cap | **bell** | ctl p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **flat 11:00** | 1124 | **+1.411** | 56.5 | 0.84 | 4.73 | yes | 1.067 | 0.115 vs 0.179 | 30 min | 63.8% | 8.3% | — | **27.9%** | 0.043 |
| flat 12:00 | 1173 | +2.539 | 60.8 | 1.43 | 4.97 | yes | 1.113 | 0.135 vs 0.179 | 30 | 68.6% | 10.7% | — | 20.6% | 0.008 |
| flat 16:00 | 1173 | +2.949 | 67.0 | 1.51 | 5.48 | yes | 1.120 | 0.159 vs 0.179 | 30 | 74.3% | 14.0% | — | 11.8% | 0.030 |
| no flat, 4h cap | 1173 | +2.508 | 63.7 | 1.35 | 5.21 | yes | 1.107 | 0.149 vs 0.179 | 30 | 72.3% | 12.7% | 15.0% | — | 0.033 |
| no flat, 1d cap | 1148 | **+3.045** | 69.8 | 1.48 | 5.77 | yes | 1.121 | **0.188 vs 0.179** | 30 | 78.2% | 18.1% | 3.7% | — | 0.053 |

**50-point stop / 150-point target**

| exit policy | n | pts | PF | res_win vs be (0.261) | med hold | bell/cap | ctl p |
|---|---|---|---|---|---|---|---|
| **flat 11:00** | 1054 | **+0.956** | 1.034 | 0.180 | 45 min | 40.5% | 0.160 |
| flat 12:00 | 1094 | +2.826 | 1.094 | 0.206 | 60 | 31.4% | 0.045 |
| flat 16:00 | 1094 | +2.898 | 1.085 | 0.235 | 75 | 18.5% | 0.123 |
| no flat, 4h cap | 1094 | +2.928 | 1.092 | 0.222 | 75 | 23.5% | 0.085 |
| no flat, 1d cap | 1053 | **+3.985** | 1.110 | **0.272 vs 0.261** | 60 | 5.3% | 0.063 |

**The 11:00 bell is the worst cell on its own axis in both geometries, and it is the only cell in
either that is worse than every alternative.** Ordered by how much clock is allowed: 11:00 < 12:00
< 4h cap ~ 16:00 < 1-day cap, monotone in both geometries except that 16:00 and the 4h cap tie
(they are nearly the same policy — a 4-hour cap on a 07:00-11:00 entry can only reach 15:00).

Two things to read beside the headline. **Every one of the ten cells is inside its own MDE**, so
none of them is distinguishable from zero on this sample — `STUDY_US30_SCALP_0711` §8-9 already
established that per-trade dispersion here (56-87 points) makes anything under ~5 points a trade
undetectable, and the flatten's effect is under that. And note the **`res_win` column**: at 30/150
under the bell the barrier pair resolves 11.5% of the time against a driftless bound of 17.9%, and
**only the 1-day cap gets it above its own bound (18.8%)**. The barrier system needs time to clear
its own arithmetic.

---

## 2. What the clock closes, and what those trades became

The mechanism, which matters more than the number. For every trade the bell closed, the same
position with the same barriers was carried forward to its stop, its target or 96 bars — a per-trade
counterfactual that does not change the trade set.

| cell | closed by clock | worth at the bell | became if held | delta | → target | → stop |
|---|---|---|---|---|---|---|
| 30/150 flat 11:00 | **314 (27.9%)** | **+35.03 pts** | **+43.49** | **+8.46** | **35.0%** | 49.7% |
| 30/150 flat 12:00 | 242 (20.6%) | +42.81 | +49.48 | +6.67 | 36.0% | 43.8% |
| 30/150 flat 16:00 | 138 (11.8%) | +53.33 | +61.54 | +8.22 | 35.5% | 29.0% |
| 30/150 no flat, 4h cap | 176 (15.0%) | +47.24 | +56.62 | +9.38 | 36.4% | 35.8% |
| 50/150 flat 11:00 | **427 (40.5%)** | +26.21 | +33.98 | +7.77 | 34.9% | 48.2% |

**The bell closes winners.** Of the 314 trades it closes at 30/150, **81.5% are in profit at the
moment it fires**, and **35.0% of them were on their way to the +150 target**. Split by whether the
trade was winning when the clock hit it:

| at the bell | n | worth then | became | MFE reached | → target | → stop |
|---|---|---|---|---|---|---|
| winning | 256 | +45.16 | +51.79 | 3.39 ATR | 39.5% | 44.9% |
| losing | 58 | -9.67 | +6.85 | 1.06 ATR | 15.5% | 70.7% |

Both groups improve if held, which is the pre-registered prediction confirmed: the bell is
truncating trades on their way to a 1:5 payoff, exactly the tail `STUDY_V63` found the money in.

**Per exit reason, contribution to the book (pts/trade), 30/150 research:**

| policy | stop | target | cap | bell | book |
|---|---|---|---|---|---|
| flat 11:00 | **-20.60** | +12.22 | — | **+9.79** | +1.41 |
| flat 12:00 | -22.16 | +15.87 | — | +8.83 | +2.54 |
| flat 16:00 | -23.98 | +20.65 | — | +6.27 | +2.95 |
| no flat, 4h | -23.34 | +18.76 | +7.09 | — | +2.51 |
| no flat, 1d | -25.26 | **+26.76** | +1.54 | — | +3.05 |

Read the two middle columns together. As the bell is relaxed the stop contribution worsens by
4.66 points and the **target contribution improves by 14.54** — the barrier pair is net-negative at
the bell (-8.38) and net-positive with a day (+1.50). That is the whole mechanism in two columns.
It also produces a sentence that is true and easy to misread: **under the 11:00 bell the flatten is
the only profitable exit reason in the cell (+9.79 of a +1.41 book)** — and that is not an argument
for it, because those same exits are worth +43.49 rather than +35.03 if left alone.

---

## 3. Give-back

In ATR at the SIGNAL bar, never in R (`STUDY_V43`: R = stop x whatever, so dividing by it puts the
stop back in the denominator).

| block | trades the bell closes | MFE reached | realised gross | **give-back** | median | p90 | reached >= 1 ATR |
|---|---|---|---|---|---|---|---|
| A_research | 314 (27.9%) | 2.96 ATR | 1.76 ATR | **1.20 ATR = 25.4 pts** | 0.72 ATR | 2.86 | 77.1% |
| B_holdout | 80 (14.5%) | — | — | **0.86 ATR** | — | — | — |
| C_forward | 19 (6.7%) | — | — | **0.35 ATR** | — | — | — |

At 50/150 the research give-back is 1.40 ATR = 30.0 points on 40.5% of trades.

**And the give-back number does not isolate the bell, which is the honest caveat.** The trades that
resolved on a barrier give back **1.27 ATR** — MORE than the 1.20 ATR the flattened ones give back —
because at a 1:5 payoff most trades peak and then die whatever closes them. Give-back is a property
of the geometry, not of the clock. The counterfactual in §2 is the correct isolator and it is the
number to quote: **+8.46 points on the trades the bell closes = +2.36 points on the whole book.**

That book figure is the optimistic bound, because holding longer keeps the position lock closed and
refuses later signals. §4's paired measurement is the realisable version.

---

## 4. Paired on the entry bar — only the exit differs

Comparing two exit policies by their book means confounds the exit with the trade set. Matched on
entry bar, 30/150:

| block | alternative to flat 11:00 | shared trades | **delta** | t | MDE | inside MDE |
|---|---|---|---|---|---|---|
| A_research | flat 12:00 | 1124 | **+1.106** | 1.64 | 1.89 | yes |
| A_research | flat 16:00 | 1124 | **+1.416** | 1.29 | 3.08 | yes |
| A_research | no flat, 4h cap | 1124 | **+0.949** | 1.08 | 2.46 | yes |
| A_research | no flat, 1d cap | 1088 | **+1.854** | 1.47 | 3.54 | yes |
| B_holdout | flat 12:00 | 551 | +0.085 | 0.10 | 2.47 | yes |
| B_holdout | flat 16:00 | 551 | +0.376 | 0.32 | 3.33 | yes |
| B_holdout | no flat, 4h cap | 551 | +0.132 | 0.12 | 3.15 | yes |
| B_holdout | no flat, 1d cap | 547 | +0.901 | 0.72 | 3.50 | yes |
| C_forward | flat 12:00 | 284 | -0.209 | -0.26 | 2.25 | yes |
| C_forward | flat 16:00 | 284 | +0.464 | 0.41 | 3.17 | yes |
| C_forward | no flat, 4h cap | 284 | +0.389 | 0.35 | 3.16 | yes |
| C_forward | no flat, 1d cap | 284 | -0.193 | -0.15 | 3.50 | yes |

**The 11:00 bell costs +0.95 to +1.85 points a trade on research, positive in 4 of 4 alternatives,
and positive in 4 of 4 on the holdout as well.** The unpaired book comparison in §1 says +1.10 to
+1.63, so the two framings agree; the paired one is the smaller and more honest number because it
does not credit the extra trades a longer hold refuses.

**And none of it is detectable.** Every delta is inside its own MDE at t 0.10-1.64. The direction
is 8 of 8 on the two US30L blocks; on C_forward it splits 2-2, and there the bell binds on only
6.7% of trades so there is almost nothing to measure.

---

## 5. The dose-response — the strongest evidence here

`STUDY_V17`: a gradient that reproduces is worth more than a rank that does not. The paired cost of
the bell against how often the bell actually binds, across the five declared entry sub-windows:

| block | flatten share → | | | | | Spearman | Pearson |
|---|---|---|---|---|---|---|---|
| A_research | 18.6% → +1.09 | 27.9% → +0.95 | 29.6% → +1.23 | 38.8% → +1.55 | **56.3% → +2.91** | **+0.900** | +0.936 |
| B_holdout | 5.4% → -0.65 | 14.5% → +0.13 | 16.7% → +0.39 | 23.3% → +0.47 | **35.4% → +1.12** | **+1.000** | +0.968 |
| C_forward | 0.0% → 0.00 | 6.7% → +0.39 | 8.2% → +0.19 | 12.6% → +0.71 | **24.3% → +6.59** | **+0.900** | +0.903 |

**The more often the bell fires, the more it costs — Spearman +0.90 / +1.00 / +0.90 on three
blocks including a different-provider forward feed.** No single cell in this study separates from
noise; this gradient reproducing three times, once on data no search here has touched, is the only
thing in the study that does more than one block's worth of work. The B_holdout column is perfectly
monotone across all five windows.

---

## 6. Entry sub-windows under the bell

Five declared cells, 30/150, flat 11:00, matched random entry from the same window.

| window | A_research pts | PF | ctl p | bell binds | B_holdout pts | PF | ctl p |
|---|---|---|---|---|---|---|---|
| **07:00-11:00** | **+1.411** | 1.067 | 0.050 | 27.9% | -0.571 | 0.976 | 0.333 |
| **08:00-11:00** | **+1.409** | 1.068 | 0.040 | 29.6% | **+1.017** | 1.043 | 0.160 |
| 07:00-09:30 | +0.797 | 1.035 | 0.188 | 18.6% | -1.818 | 0.930 | 0.590 |
| 09:30-11:00 | +0.065 | 1.003 | 0.115 | 38.8% | -1.866 | 0.919 | 0.418 |
| 10:00-11:00 | -0.351 | 0.977 | 0.253 | 56.3% | -1.455 | 0.930 | 0.398 |

Transfer A→B: **Spearman +0.600 / Pearson +0.701** — the ranking is directionally preserved, which
is far better than this branch's usual, and it rescues nothing: **four of the five holdout cells
lose money**, the best cell swaps from 07:00-11:00 to 08:00-11:00, and every cell on both blocks is
inside its MDE (4.7-5.4 on A, 7.4-10.8 on B). Seventh time a session preference has failed to
transfer here — this time as a decay rather than an inversion.

The one thing that IS mechanical: **the later the window starts under a fixed 11:00 bell, the more
the bell binds and the worse the cell does**, which is §5 restated. 07:00-11:00 and 08:00-11:00 are
indistinguishable (+1.411 vs +1.409). **09:30-11:00 is the worst of the four windows that end at
11:00**, which contradicts the branch's standing "if trading 07:00-11:00, trade 09:30-11:00"
finding — and the reason is visible: a 09:30 start leaves 90 minutes to a 1:5 target, so 38.8% of
its trades die on the clock.

---

## 7. The intrabar tie-break bracket

`STUDY_US30_SCALP_0711` §2 recorded that at 0.5N the convention was worth 5.27 points a trade and
flipped the sign. At 30/150 the target sits 150 points away, so both barriers rarely land in one
15-minute bar:

| block / cell | ambiguous | stop-first | target-first | **spread** | PF stop-first | PF target-first | sign flip |
|---|---|---|---|---|---|---|---|
| A 30/150 flat 11:00 | 0.71% | +1.411 | +2.692 | **1.281** | 1.067 | 1.129 | no |
| A 30/150 flat 12:00 | 0.77% | +2.539 | +3.920 | 1.381 | 1.113 | 1.177 | no |
| A 30/150 no flat, 4h | 0.77% | +2.508 | +3.889 | 1.381 | 1.107 | 1.167 | no |
| A 30/150 no flat, 1d | 0.78% | +3.045 | +4.457 | 1.411 | 1.121 | 1.178 | no |
| A 09:30-11:00 | 0.60% | +0.065 | +1.140 | 1.075 | 1.003 | 1.060 | no |
| A 10:00-11:00 | **0.00%** | -0.351 | -0.351 | **0.000** | 0.977 | 0.977 | no |
| **B 30/150 flat 11:00** | 1.09% | **-0.571** | **+1.389** | **1.960** | 0.976 | 1.058 | **YES** |
| B 30/150 no flat, 4h | 1.03% | +0.226 | +2.088 | 1.862 | 1.009 | 1.082 | no |
| C 30/150 flat 11:00 | 1.76% | +5.931 | +9.100 | **3.169** | 1.243 | 1.382 | no |
| C 30/150 no flat, 4h | 1.69% | +5.167 | +8.207 | 3.041 | 1.203 | 1.330 | no |

Three things, in order of importance.

**The convention is worth 1.3 to 3.2 points a trade on the LEVEL — the same order as the flatten's
own cost.** Any statement about whether a cell here makes money is a statement about the tie-break
as much as about the market. `US30_1m` would settle it and is absent from disk.

**Say it plainly where it bites: the holdout's verdict on the flatten cell is not knowable at this
resolution.** `B 30/150 flat 11:00` reads -0.571 stop-first and +1.389 target-first — a sign flip
on the one reserved block that is supposed to arbitrate.

**But the exit COMPARISON is convention-free.** The paired delta of §4 is identical to six decimal
places under both conventions — spread exactly 0.000 in 12 of 12 cells — because all 8 ambiguous
research trades resolve before the bell and therefore identically in both arms. The ladder ordering
is likewise unchanged (flat 11:00 worst under both). **So the convention prices the level and not
the verdict on the flatten**, and the flatten's cost is the one number in this study that does not
inherit the 15-minute measurement problem.

---

## 8. Drawdown, separately from return

Daily P&L zero-filled over all 1,915 research sessions (`STUDY_V17`: over traded days only a filter
is paid for trading less), 4,000-draw permutation of the daily series — a PATH question only
(`STUDY_V31`: permuting cannot change the endpoint).

| A_research, 30/150 | total | realised DD | percentile of its own permutations | MC p50 | MC p99 | p99 / realised | ret/DD |
|---|---|---|---|---|---|---|---|
| **flat 11:00** | 1586 | **1694** | **0.653** | 1515 | 2843 | 1.68x | **0.94** |
| flat 12:00 | 2978 | 1340 | 0.389 | 1439 | 2677 | 2.00x | 2.22 |
| flat 16:00 | 3459 | 1335 | 0.275 | 1560 | 2911 | 2.18x | 2.59 |
| no flat, 4h cap | 2942 | **1283** | **0.226** | 1545 | 2902 | 2.26x | 2.29 |
| no flat, 1d cap | 3496 | **1235** | **0.139** | 1599 | 3052 | 2.47x | **2.83** |

**In this configuration the flatten does not reduce drawdown — it increases it by 32-37%, and cuts
return-over-drawdown by two thirds.** That inverts `STUDY_V63`, and the mechanism is visible in one
column: **the worst single trade is -32.3 points in every arm**, because the 30-point stop already
caps every loss. A bell cannot remove a losing tail that a hard stop has already removed; all it
can remove is the winning one. V63's flatten helped because that design had NO target and a 480-bar
cap, so its drawdown came from long adverse holds — this one cannot.

The permutation reproduces V63's warning about the comfort being luck, pointing the other way:
**flatten-OFF's low drawdown sits at the 14th-23rd percentile of reshuffles of its own trades**, so
it was a smooth path rather than a structurally safe one, while flatten-ON sits at the 65th and was
rougher than a reshuffle. **At MC p99 the two are nearly equal (2843 vs 2902-3052) while
flatten-off's return is 1.9-2.2x** — so even sized for p99, which is the number to size for, the
bell buys nothing.

**And this is the one section that does not replicate.** B_holdout: DD 1997 (pct 0.79) with the
bell against 2089 (0.77) without — a wash. C_forward: **1018 (0.85) with against 1457 (0.98)
without** — there the bell does lower drawdown. Report it as research-block-only.

---

## 9. Reserved reads

Declared before either block was opened: flat 11:00 against no-flat-4h-cap, 30/150, 07:00-11:00.

| feed | block | n | pts | t | MDE | PF | res_win vs be | bell binds | ctl | ctl p |
|---|---|---|---|---|---|---|---|---|---|---|
| US30L | A_research | 1124 | +1.411 | 0.84 | 4.73 | 1.067 | 0.115 / 0.179 | 27.9% | -1.60 | **0.038** |
| US30L | A_research (no flat 4h) | 1173 | +2.508 | 1.35 | 5.21 | 1.107 | 0.149 / 0.179 | — | -0.73 | **0.013** |
| US30L | B_holdout | 551 | **-0.571** | -0.22 | 7.37 | 0.976 | 0.138 / 0.179 | 14.5% | -1.54 | 0.368 |
| US30L | B_holdout (no flat 4h) | 580 | +0.226 | 0.08 | 7.90 | 1.009 | 0.173 / 0.179 | — | -0.93 | 0.335 |
| US30I | **C_forward** | 284 | **+5.931** | 1.42 | 11.72 | 1.243 | 0.193 / 0.179 | 6.7% | -1.33 | **0.028** |
| US30I | **C_forward** (no flat 4h) | 296 | +5.167 | 1.22 | 11.84 | 1.203 | 0.205 / 0.179 | — | -2.00 | **0.025** |

Both arms clear their matched control on A and on C and neither does on B. Two qualifications that
outrank that.

**Everything clears a control that loses money** — the null earns -0.73 to -2.00 points on every
block — which is `STUDY_IB_US30_OPTUNA`'s sentence: a rule that beats a losing null is still a rule
that has not been shown to make money. Every cell is inside its own MDE.

**And a 30-point stop is a different geometry in each block** (`STUDY_DL50`): median in-window
ATR(14) runs **31.17 / 38.06 / 53.31** points, so 30 points is **0.96N on research, 0.79N on the
holdout and 0.56N on the forward block**. That is why C's median hold is ZERO minutes with 75%
stopping out, and it is why the bell binds on only 6.7% there — on C the trades are dead before the
clock can reach them. C's "the bell is fine" reading is really "the bell has almost nothing left to
close", and the 1.76% ambiguous share there is the highest in the study.

---

## Verdict

**The 11:00 flatten costs money in this exact configuration, by about a point a trade, and that
cost is real in direction and undetectable in size.**

- **What it costs:** **+0.95 to +1.85 points a trade** on research, paired on identical entries so
  only the exit differs (t 1.08-1.64, MDE 2.46-3.54 — all inside). Unpaired book comparison agrees
  at +1.10 to +1.63 at 30/150 and +1.97 to +3.03 at 50/150. Positive in 4 of 4 alternatives on
  research and 4 of 4 on the holdout; 2 of 4 on the forward block, where the bell binds on 6.7% of
  trades and there is nothing to measure. In MNQ-free terms on US30 at $5 a point, one contract on
  ~130 trades a year: roughly **$620-1,200 a year given away**.
- **Why:** it closes **27.9% of trades, 81.5% of them in profit** (mean +45.16 points), and
  **35.0% of the trades it closes were on their way to the +150 target**. Held on, they are worth
  +43.49 rather than +35.03. Under the bell the barrier pair resolves 11.5% winners against a
  driftless bound of 17.9% and contributes **-8.38 points a trade**; give it a day and it resolves
  18.8% and contributes +1.50.
- **Give-back:** **1.20 ATR = 25.4 points**, mean, on the trades the clock closes (median 0.72,
  p90 2.86; 77.1% had reached at least 1 ATR). **But it is not the flatten's number** — trades that
  resolved on a barrier give back 1.27 ATR, more, so give-back is a property of a 1:5 payoff rather
  than of the clock. The counterfactual (+8.46 points on those trades = +2.36 on the book) is the
  isolator, and §4's paired +0.95 is what is actually realisable.
- **Tie-break spread: 1.28 points on research, 1.96 on the holdout, 3.17 on the forward block**, at
  an ambiguous share of 0.71-1.76%. That is the same order as the effect being measured, so no
  statement here about whether a cell makes money is knowable at 15-minute resolution — and
  **`B_holdout flat 11:00` flips sign outright** (-0.571 stop-first, +1.389 target-first). The
  flatten's cost is the exception: the paired delta is **identical to six decimal places under both
  conventions, 12 of 12 cells**, because the ambiguous trades resolve before the bell in both arms.
- **The drawdown benefit does not exist here and does not survive the permutation anyway.** The
  bell raises realised drawdown 1283 → 1694 (+32%) and cuts ret/DD 2.29 → 0.94, because the
  30-point stop already caps every loss at -32.3 points, leaving the bell nothing but winners to
  cut. Flatten-off's lower drawdown IS partly luck — 14th-23rd percentile of its own permutations,
  V63's warning intact — but at MC p99 the two arms are within 8% of each other while flatten-off
  returns 1.9-2.2x. On B the two are a wash and on C the bell is better, so this section is
  research-block only.
- **The strongest evidence in the study is the gradient, not any cell.** The cost of the bell rises
  with how often the bell binds at **Spearman +0.900 / +1.000 / +0.900** across five entry windows
  on three blocks, including a different-provider feed no search here has touched. That reproduces
  in three directions where nothing else reproduces once.

**If the 11:00 flatten is non-negotiable, the cheapest way to hold it** is to keep the entry window
at 07:00-11:00 or 08:00-11:00 (indistinguishable, +1.411 vs +1.409) and NOT to move the start later
— 09:30-11:00 and 10:00-11:00 give the bell 38.8% and 56.3% of the trades and cost 1.5x and 3.1x as
much as the full window. **The cheapest relaxation that keeps a same-day flat is 12:00**, which
recovers +1.11 of the +1.85 available and still closes everything before lunch.

**What this does NOT establish.** No cell here separates from zero: the research block's MDE is
4.7-5.9 points a trade against effects of 1-3, and `STUDY_US30_SCALP_0711` §9-10 already showed
that detecting anything smaller than a PF-1.2 rule on this feed would take decades. Nothing in this
study contradicts that; it prices one exit choice inside a configuration whose edge remains
unproven. Pooling the window across US100 and NQ is still the single highest-value next step — it
triples the trade count, takes the MDE from ~4.7 to ~2.7 points, and would bring a 1-point flatten
cost inside the sample's resolution for the first time.
