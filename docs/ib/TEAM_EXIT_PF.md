# Exit geometry and position management on the §12 US30 rule: what moves profit factor

Asked to improve **profit factor** on `STUDY_US30_SCALP_0711` §12's primary, varying the exit
geometry and position management only. The entry trigger (Donchian 20 long), the filters
(`+adx<=20`), the window (07:00-11:00 New York) and the 11:00 flatten are held fixed throughout.

`research/us30exit/`: `x_lib.py`, `x_run1.py` .. `x_run7.py`.

**The answer in one line: a trailing stop raises profit factor from 1.24 to 1.42 and a COIN FLIP
with the same trailing stop raises it from 0.94 to 1.00 — and at a 0.25 ATR trail the coin flip
reads PF 2.44. Profit factor is not comparable across exit geometries, and once every cell is
priced against its own null nothing in the 80-cell space beats the incumbent out of sample.**

**A note on the base arm, added after the grid ran.** §1-8 are built on `+adx<=20` because that is
the arm `STUDY_US30_SCALP_0711` §12-13 named. §18 of that study has since **withdrawn** it — its
+6.260 is a POINTS figure that inverts in ATR, and the ceiling clears 5 of 14 cells on four fresh
markets where chance is 7. **This study does not rest on it.** §9 re-runs the identical 80-cell grid
on `+ema align` and `ema34>89` and the exit verdict is the same on all three arms; §9.6 re-reads the
exit marginal in ATR units and shows the exit axis does not re-select volatility the way the arm
comparison does (trail/flatten median signal-bar ATR 0.98-1.00 against §18's 0.894). Read §9 as the
load-bearing part.

**Trial count: 255 research cells and 38 reserved reads.** 80 declared grid cells, plus 6 extra
trail-multiplier rungs, 1 extra stop rung and 2 extra target rungs added as declared neighbourhoods;
the `tie=1` pass and the control attachment in `x_run5` are re-reads of the same 80. Reserved: 5
declared cells x 2 reserved blocks, plus a 4-rung control ladder on each — the ladder being a
prediction about the NULL, not a selection. §10 then repeats the identical 80-cell grid on two more
arms (+160 research cells, +12 ladder rungs, +20 reserved cells) after a parallel workstream showed
the arm the grid was built on is the weaker of the two.

---

## 0. Transcription first

The extended walker adds four exit paths to `s30core._walk` and nothing else. On the flatten-only
policy it must reproduce the published engine exactly, and it does — **8 of 8 configurations, trade
count identical, max |Δpts| 0.00e+00**, at 30/150, 50/150, 100/200 and 150/100 under both tie-break
conventions. Everything below is the same engine.

Three mechanics were chosen so a script could place them, not so an engine could:

- the **channel exit** tests bar *t*'s close against the 10-bar low known at *t-1* and fills at the
  **open of bar t+1** — `strategy.close()` cannot sell the close of the bar that triggers it, the
  correction `STUDY_V63` forced on the flatten;
- **breakeven** and the **trail** are updated at the END of a bar and can only bind from the next
  one, and the working stop is checked BEFORE it is ratcheted, so no bar can both create and hit a
  level. At 15-minute resolution the intrabar path is exactly what is unknown.

---

## 0b. The three arms' base rates on the trigger's own bars

Measured before anything else, because on this branch a "confirmation" has turned out to be the
trigger restated eight times. Research block, 2,240 in-window Donchian-20 breakout bars:

| condition | passes breakout bars | passes all in-window bars | lift |
|---|---|---|---|
| `adx<=20` | 27.8% | 31.0% | **0.898** |
| `ema13>34>89` | 66.0% | 42.1% | 1.570 |
| `ema34>89` | 68.6% | 56.9% | 1.204 |
| `adx>=25` | 48.7% | 46.6% | 1.045 |

None is degenerate. `adx<=20` is the only one whose lift is **below 1** — it leans away from the
breakout bar, which is why it binds hardest (keeps 27.8%) and why it leaves the fewest trades on a
short reserved block. The full alignment keeps 66.0% against the slow leg's 68.6%, so the fast leg
removes 2.6 points of signal, which is the same reading §15 of `STUDY_US30_SCALP_0711` reaches from
the P&L side.

---

## 1. The population before any ranking

80 declared cells: stop {30, 50, 75, 100, 150} x target {100, 150, 200, none} x policy
{flatten | +Donchian-10 channel | +breakeven after 1R | +1.0 ATR trail}, `+adx<=20` arm, research
block, stop-first convention.

    cells scorable                   80
    share with PF > 1                98.8%
    share with total points > 0      98.8%
    share OUTSIDE its own MDE        3.8%
    median PF                        1.150
    median total points              +1,712
    trade count range                373 .. 445
    best t achieved                  2.914   (detectability needs 2.802)

**98.8% of the space is profitable**, so any top row is the maximum of ~79 profitable draws. And
only **3 of 80 cells are outside their own minimum detectable effect** — the constraint
`STUDY_US30_SCALP_0711` §9 set has not moved.

---

## 2. The marginal per axis, in four units

Read by marginal average, never by top row. `mde` is `2.802 x sd / sqrt(n)`.

**STOP (points)** — averaged over targets and policies

| stop | PF | pts/trade | total pts | n | maxDD | ret/DD | win | MDE |
|---|---|---|---|---|---|---|---|---|
| 30 | 1.155 | +2.62 | 1,121 | 426 | 776 | 1.64 | 0.308 | 7.54 |
| **50** | 1.221 | +4.56 | 1,885 | 411 | 993 | **2.64** | 0.394 | 9.43 |
| 75 | 1.186 | +3.97 | 1,611 | 399 | 1,275 | 2.19 | 0.436 | 10.65 |
| **100** | **1.222** | **+5.54** | **2,191** | 395 | 1,391 | 2.29 | 0.465 | 12.17 |
| 150 | 1.216 | +4.91 | 1,960 | 393 | 1,703 | 2.41 | 0.480 | 13.14 |

**TARGET (points)**

| target | PF | pts/trade | total pts | n | maxDD | ret/DD | win | MDE |
|---|---|---|---|---|---|---|---|---|
| 100 | 1.161 | +3.31 | 1,357 | 408 | 1,017 | 2.01 | 0.445 | 8.78 |
| **150** | **1.225** | **+4.87** | **1,977** | 404 | 1,174 | **2.49** | 0.422 | 10.08 |
| 200 | 1.200 | +4.24 | 1,725 | 404 | 1,327 | 2.17 | 0.406 | 10.70 |
| none | 1.214 | +4.85 | 1,955 | 404 | 1,393 | 2.27 | 0.394 | 12.79 |

**EXIT POLICY**

| policy | PF | pts/trade | total pts | n | maxDD | ret/DD | win | MDE | median hold |
|---|---|---|---|---|---|---|---|---|---|
| flatten only | 1.145 | +4.36 | 1,700 | 392 | 1,529 | 1.25 | 0.446 | 12.17 | 64 min |
| + channel 10 | 1.133 | +3.93 | 1,549 | 396 | 1,410 | 1.20 | 0.432 | 11.86 | 61 |
| + breakeven 1R | **1.106** | **+3.14** | **1,208** | 393 | 1,507 | **0.79** | 0.400 | 11.43 | 62 |
| **+ 1.0 ATR trail** | **1.415** | **+5.84** | **2,557** | **438** | **465** | **5.69** | 0.388 | **6.88** | **15** |

Three of the four axes give a **consistent** answer across all four units, which is not what
`STUDY_V63` found and is worth saying: the stop peaks at 50-100 rather than running monotonically
wider, the target peaks at 150, and the trail leads on every single column at once.

**The two artifacts the brief named are both absent here.** The trail is not `STUDY_V24`'s
trade-less artifact — it trades **more** (438 against 392), makes **more total** (2,557 against
1,700), and its return/drawdown is **4.5x** the flatten's, so the statistic that catches that
artifact is the one most in its favour. And the four units agree, so `STUDY_V63`'s unit
disagreement is absent too. Across the 80 cells, corr(PF, trade count) **+0.689**, corr(PF, total)
**+0.858**, corr(PF, ret/DD) **+0.973**.

**Breakeven-after-1R is the only policy that is clearly worse than doing nothing** — bottom of every
column, and 22% below the flatten on total points. `STUDY_V8_EXIT_OPT` said partial exits are worth
nothing; a breakeven stop is the same idea and it is worth less than nothing.

---

## 3. Where the trail's profit factor actually comes from

PF is `sum(wins) / sum(losses)`. It can be raised by shrinking the denominator without adding a
point of return — a third way a PF gain can be empty, distinct from both artifacts above.

| cell | n | win | gross wins | gross losses | mean win | mean loss | PF | total | pts/trade |
|---|---|---|---|---|---|---|---|---|---|
| 50/150 flatten (incumbent) | 400 | 42.8% | 13,102 | 10,598 | 76.6 | 46.3 | 1.236 | 2,504 | +6.26 |
| 100/150 flatten | 378 | 51.1% | 14,861 | 12,758 | 77.0 | 69.0 | 1.165 | 2,103 | +5.56 |
| **100/150 trail 1.0** | 436 | 39.9% | **9,173** | **6,452** | 52.7 | 24.6 | **1.422** | 2,721 | **+6.24** |
| 100/150 trail 0.5 | 451 | 47.9% | 7,617 | 3,756 | 35.3 | 16.0 | 2.028 | 3,861 | +8.56 |
| 100/150 trail 0.25 | 452 | 64.4% | 8,348 | **2,580** | 28.7 | 16.0 | **3.236** | 5,769 | +12.76 |

Read the two gross columns down the page. Against the incumbent, the 1.0 ATR trail cuts gross wins
by **30%** and gross losses by **39%** — PF rises 15% and **points a trade moves by -0.02**. Paired
on the 377 entry bars the two policies share, the trail is worth **+0.547 points a trade against a
paired MDE of 9.815**; it improves 43.0% of trades and worsens 36.6%. What total return it adds
comes almost entirely from the **59 extra trades** the earlier exits admit by freeing the position
lock (+6.58 each, +389 points) — the `STUDY_V56` mechanism, here helping rather than diluting.

---

## 4. The decisive test: a random entry carrying the identical trail

`STUDY_ABSORPTION_LEVELS` recorded a 0.25 ATR trail reading PF 1.751 while a random entry with the
same trail read 1.617. Every trail and channel cell here was given that twin — same side
distribution, same eligible in-window pool, sorted so the position lock rejects the same share
(`STUDY_V59`), same exit machinery, 300 draws.

**The trail ladder, stop 100 / target 150 held fixed, research block:**

| trail (ATR) | n | **PF** | **twin PF** | PF ratio | pts | twin pts | edge | **excess total** | ret/DD | twin ret/DD | win | median hold |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.25 | 452 | **3.236** | **2.444** | 1.324 | +12.76 | +9.23 | +3.53 | 1,597 | 25.9 | 12.0 | 64.4% | 15 min |
| 0.50 | 451 | 2.028 | 1.530 | 1.325 | +8.56 | +4.95 | +3.61 | 1,627 | 13.6 | 4.5 | 47.9% | 15 |
| 0.75 | 443 | 1.627 | 1.188 | 1.370 | +7.26 | +2.35 | +4.91 | 2,176 | 7.4 | 1.4 | 42.0% | 15 |
| 1.00 | 436 | 1.422 | 1.043 | 1.363 | +6.24 | +0.67 | +5.57 | 2,428 | 5.8 | 0.3 | 39.9% | 15 |
| 1.50 | 420 | 1.241 | 0.971 | 1.278 | +4.75 | -0.60 | +5.35 | 2,247 | 2.3 | -0.2 | 40.2% | 30 |
| 2.00 | 410 | 1.126 | 0.975 | 1.154 | +3.07 | -0.60 | +3.67 | 1,503 | 1.0 | -0.1 | 38.8% | 45 |
| 3.00 | 391 | 1.135 | 0.944 | 1.203 | +3.96 | -1.68 | +5.65 | 2,208 | 1.2 | -0.3 | 45.5% | 60 |
| **none** | 378 | 1.165 | 0.970 | 1.202 | +5.56 | -1.10 | **+6.66** | **2,519** | 1.2 | -0.2 | 51.1% | 75 |

**A coin flip with a 0.25 ATR trail reads PF 2.444 and return/drawdown 12.0.** The twin's PF rises
monotonically as the trail tightens, 0.970 → 1.043 → 1.530 → 2.444, and so does its return/drawdown,
-0.21 → 0.29 → 4.52 → 11.97. The trail is a **profit-factor multiplier applied to whatever entry it
is attached to**, exactly as `STUDY_ABSORPTION_LEVELS` found, and here the effect is far larger.

The consequence is a rule: **profit factor is not comparable across exit geometries.** Two cells
with PF 1.24 and PF 3.24 are not ranked by that number if their exits differ; the PF ratio and the
excess total are.

And on the two columns that do isolate the entry:

- **PF ratio is flat**, 1.15 to 1.37 across the whole ladder *including no trail at all*, with a
  shallow hump at 0.75-1.0.
- **Excess total peaks with NO TRAIL** (2,519) and is at its minimum at the tightest trail (1,597).

**The trail buys profit factor and buys nothing the entry is responsible for.** The tighter it is,
the more PF it manufactures and the less of the result belongs to the signal.

The remaining ambiguity is honest: the trail genuinely cuts drawdown (1,742 → 470) and genuinely
halves the MDE (12.82 → 7.28), and both are real for a trader. But the twin gets both as well, so
they are properties of the geometry and not evidence about the rule.

---

## 5. The intrabar tie-break

Stop-first (this branch's convention) against target-first, on all 80 cells.

    ambiguous share, mean over cells   0.63%   max 3.37%
    mean |convention spread|           0.840 points
    max  |convention spread|           3.218 points
    cells whose SIGN flips             0 of 80

At the geometries in this grid the tie-break does **not** decide any verdict — no sign flips, and the
spread is under a point on average. That is a change from `STUDY_US30_SCALP_0711` §2, where a
0.5N/0.5N pair was 14.03% ambiguous and the convention flipped PF from 0.604 to 1.056: **these
barriers are wide enough for a 15-minute bar to resolve.**

The exception is worth stating: the cells the convention moves most are all **tight targets under a
trail or a breakeven stop** — `50/100 +be1R` moves +3.22 points, `75/100 trail` +2.85, `30/100
trail` +2.78, at ambiguity 2.1-3.4%. On the incumbent it is +1.000 points at 0.50% ambiguity, and on
the trail candidate +1.275 at 1.38%. Those spreads are the same order as the effects being measured,
so **for any trail cell the reported figure is the pessimistic one and the true value sits up to a
point higher.** `US30_1m` would settle it and is absent.

Gap-through was measured rather than assumed: on the fixed-stop cells the exit bar opens beyond the
stop level on **0.56% to 0.99%** of stop exits, so a fill at the level is a fair assumption there.

---

## 6. The marginals re-read in excess-of-null units

Every one of the 80 cells given its own matched random entry (200 draws). `pf_ratio` = the cell's PF
over its twin's; `excess total` = (pts - twin pts) x n, the points the ENTRY is worth once the exit
geometry is paid for.

| policy | raw PF | **twin PF** | PF ratio | pts | twin pts | edge | **excess total** | n |
|---|---|---|---|---|---|---|---|---|
| flatten only | 1.145 | 0.938 | 1.222 | +4.36 | -1.92 | **+6.29** | 2,451 | 392 |
| + channel 10 | 1.133 | 0.931 | 1.218 | +3.93 | -1.93 | +5.85 | 2,315 | 396 |
| + breakeven 1R | 1.106 | 0.935 | 1.183 | +3.14 | -1.79 | +4.93 | **1,910** | 393 |
| + 1.0 ATR trail | **1.415** | **1.000** | 1.417 | +5.84 | +0.02 | +5.82 | **2,552** | 438 |

| stop | PF ratio | edge | excess total | | target | PF ratio | edge | excess total |
|---|---|---|---|---|---|---|---|---|
| 30 | 1.263 | +4.17 | 1,782 | | 100 | 1.267 | +5.53 | 2,244 |
| **50** | **1.314** | +6.29 | 2,587 | | **150** | **1.287** | **+6.34** | **2,550** |
| 75 | 1.233 | +5.22 | 2,096 | | 200 | 1.246 | +5.40 | 2,179 |
| **100** | 1.261 | **+6.87** | **2,693** | | none | 1.240 | +5.63 | 2,255 |
| 150 | 1.229 | +6.07 | 2,378 | | | | | |

**One caveat on the null, stated once.** The twin is drawn from ALL eligible in-window bars, not
from the bars the arm's own condition admits, so the excess of any cell mixes what the FILTER is
worth with what the ENTRY is worth. `STUDY_V19` requires a regime-matched control when the question
is about the filter. It is not here: the arm is held constant inside each grid, so the comparison
between exit geometries is unaffected, and only cross-arm level comparisons would need the harder
null.

Two things change when the null is priced.

**The trail's advantage nearly disappears.** In excess total the four policies are 2,451 / 2,315 /
1,910 / 2,552 — the trail is **4% above the flatten**, not 24% as raw PF says, and it is **worse per
trade in excess** (+5.82 against +6.29). The flatten's twin loses 1.92 points a trade and the
trail's twin breaks even, and that difference is the whole of the raw PF gap.

**And no-take-profit does NOT reproduce here.** Raw pts put `none` (+4.85) and 150 (+4.87) level; in
excess, target 150 leads on every column (+6.34 edge, 2,550 excess total) and `none` is third. The
reason is visible in the twin column: with no target the twin earns -0.77 a trade against -1.47 at a
150 target, because an untargeted long in a market that rose collects the drift too. **Against the
branch's 25 prior confirmations this is one market, one arm and one window — it does not overturn
them, but on this cell the incumbent's 150-point target is at or above the marginal optimum on every
unit, raw and excess alike.**

Ranking correlations across the 80: corr(raw PF, PF ratio) **+0.871**, corr(raw PF, excess total)
**+0.496**, Spearman(rank by PF, rank by excess) **+0.686**. The top row by raw PF (150/none trail,
PF 1.607) ranks **20th of 80** on excess; the top row by excess (100/none flatten) ranks 24th on PF.

**The incumbent's own row: PF 1.236 against a twin's 0.933, ratio 1.325, edge +8.13 a trade, excess
total 3,253 — rank 20/80 by PF, 6/80 by PF ratio, 3/80 by excess total.**

---

## 7. One read of the holdout and one of the different-provider forward block

Five cells declared in `x_run4`'s docstring before the read, each with its own matched twin.
C_forward is `US30_ISO_15m` after 2025-07-16 — a different provider over a span no search on this
branch has touched. B_holdout has been read by six studies, so a p-value there is descriptive.

**Points a trade**

| cell | A research | B holdout | C forward | blocks + |
|---|---|---|---|---|
| **D0 incumbent 50/150 flatten** | +6.26 | +4.60 | **+6.38** | **3/3** |
| D1 50/none flatten | +5.34 | +2.49 | +1.53 | 3/3 |
| D2 100/none flatten | +8.24 | +8.67 | **-9.73** | 2/3 |
| D3 100/150 trail 1.0 | +6.24 | +8.64 | **-3.86** | 2/3 |
| D4 150/none trail 1.0 (top row) | +8.41 | +13.00 | +0.29 | 3/3 |

**Raw profit factor**

| cell | A | B | C |
|---|---|---|---|
| D0 incumbent | 1.236 | 1.145 | **1.184** |
| D1 | 1.187 | 1.076 | 1.040 |
| D2 | 1.222 | 1.206 | **0.826** |
| D3 trail | **1.422** | **1.596** | **0.864** |
| D4 trail (top row) | **1.607** | **1.872** | 1.012 |

**Excess over the matched twin, points a trade — the column that decides it**

| cell | A | B | **C forward** |
|---|---|---|---|
| **D0 incumbent** | **+8.04** | **+4.83** | **+5.55** |
| D1 | +7.71 | +2.72 | **-1.12** |
| D2 | +9.23 | +7.95 | **-10.94** |
| D3 trail | +5.46 | +6.10 | **-7.11** |
| D4 trail (top row) | +5.73 | +8.84 | **-7.71** |

**PF ratio (cell PF / its twin's PF)**

| cell | A | B | C |
|---|---|---|---|
| **D0 incumbent** | 1.320 | 1.153 | **1.157** |
| D1 | 1.294 | 1.083 | 0.972 |
| D2 | 1.255 | 1.187 | 0.809 |
| D3 trail | 1.354 | **1.381** | **0.771** |
| D4 trail (top row) | 1.362 | **1.493** | **0.754** |

**The incumbent is the only one of the five whose excess over its own null is positive on all three
blocks, and the only one whose PF ratio stays above 1 on all three.** It also decays across the
split — 1.320 → 1.153 → 1.157 — which is the right shape.

The two trail cells have the **highest** PF ratio on A and B and the **lowest** on C, where a random
entry with their own trail beats them by 7.1 and 7.7 points a trade. That is
`STUDY_TREND_LONG`'s lesson arriving again — two blocks of one feed are not two tests — and it lands
on exactly the cells the raw-PF ranking preferred.

**Every one of the fifteen cells is inside its own MDE except D4 on the research block.** D3's PF
gain on the holdout is +0.452 with a per-trade delta of +4.05 against an MDE of 11.59; D4's is
+0.728 with +8.41 against 15.37. **No profit-factor improvement found anywhere in this study is
outside its own resolution on a block that did not choose it.**

### The mechanism prediction reproduced on both reserved blocks

Declared before the read, and a statement about the null rather than a selection: if the trail is
geometry, the CONTROL's PF must climb as the trail tightens on every block.

| trail | twin PF, A research | twin PF, B holdout | twin PF, C forward |
|---|---|---|---|
| none | 0.946 | 1.015 | 1.058 |
| 1.00 | 1.041 | 1.121 | 1.125 |
| 0.50 | 1.565 | 1.619 | 1.577 |
| **0.25** | **2.430** | **2.496** | **2.202** |

**A coin-flip entry with a 0.25 ATR trail reads PF 2.20-2.50 on three blocks and two providers.**
The rule's own PF at that rung is 3.24 / 4.97 / 1.68 — on C the coin flip wins outright. And on
C_forward the rule's PF ratio is **below 1 at every rung** (0.968, 0.768, 0.739, 0.765), so on the
one block nothing selected the rule is worse than its own twin at every trail setting.

---

## 8. The flatten, priced separately

The user keeps it on for the headline; this is what it costs, paired on the same signals.

| cell | flatten ON pts | flatten OFF pts | delta | PF on | PF off | total on | total off | ret/DD on | ret/DD off |
|---|---|---|---|---|---|---|---|---|---|
| 50/150 flatten | +6.26 | +13.18 | **+6.92** | 1.236 | 1.375 | 2,504 | 5,155 | 2.24 | 6.14 |
| 100/150 flatten | +5.56 | +10.10 | +4.54 | 1.165 | 1.179 | 2,103 | 3,505 | 1.21 | 2.63 |
| 100/150 +chan10 | +4.97 | +11.06 | +6.09 | 1.150 | 1.272 | 1,909 | 4,303 | 1.19 | 4.23 |
| 100/150 +be1R | +5.41 | +12.26 | +6.85 | 1.170 | 1.268 | 2,051 | 4,339 | 1.29 | 3.38 |
| **100/150 trail 1.0** | +6.24 | +7.00 | **+0.75** | 1.422 | 1.473 | 2,721 | 3,099 | 5.79 | 5.56 |

**The 11:00 bell costs 4.5 to 6.9 points a trade on every policy that lets a trade breathe, and
0.5 to 0.8 on the trail arms** — because a trail that exits after a median 15 minutes has usually
closed the trade before the bell can. That is another confirmation of the branch's
standing flatten finding and the largest yet measured on this rule; `TEAM_FLATTEN` priced it at +0.95 on the `base` arm at 30/150 and it
is **7x larger** on the `+adx<=20` arm at 50/150.

**One degeneracy flagged rather than reported:** with no target AND no flatten AND no cap the
position lock never releases — `100/none` with the bell off leaves **3 trades with a median hold of
1,097,505 minutes**. Any no-flatten figure needs a hold cap; the ones quoted above all have a
target.

---

## 9. THE SAME 80 CELLS ON TWO MORE ARMS -- side by side, not replacing

A parallel workstream (`research/us30rate/`, `STUDY_US30_SCALP_0711` §14-15) measured after this
grid was built that `+adx<=20` -- the arm §1-9 rest on -- is not clearly the stronger of the two
conditions, and that the two tests disagree about which is:

- against a same-selectivity random VETO over six channel rungs x three blocks, `+ema align` is
  **18/18** and `+adx<=20` is 15/18 with only **3/6 on the reserved different-provider feed**;
- on a fixed-constant walk-forward over eight annual folds `+adx<=20` is the BETTER arm
  (**6/8 folds, +3,608, worst -237** against `+ema align`'s 5/8, +2,128, worst -729);
- the permutation says the EMA arm's research path was **LUCKY** (drawdown at the 12th percentile of
  reshuffles of its own trades) where §13 found the ADX arm's was UNLUCKY (76th-87th);
- and the two arms correlate only **+0.461** in daily P&L, so they are genuinely distinct.

**Neither dominates.** So the identical 80-cell grid was re-run on `+ema align` and on
`ema34>89` -- nothing refitted, the same policies, units and reading order, only the arm changing.
`ema34>89` is carried as a REDUNDANCY CHECK rather than a third opinion: across the 80 cells it
correlates with `+ema align` at **+0.99 on raw PF and +0.98 on points a trade**, confirming from the
exit side that it is the same condition (the rate workstream measured +0.968 on daily P&L).

**Population per arm, before any ranking:**

| arm | cells | PF>1 | total>0 | outside its MDE | median PF | median total | median n | best PF | best t |
|---|---|---|---|---|---|---|---|---|---|
| `+adx<=20` | 80 | 98.8% | 98.8% | **3.8%** | 1.150 | 1,712 | 400 | 1.607 | 2.914 |
| `+ema align` | 80 | 97.5% | 97.5% | **3.8%** | 1.143 | 2,070 | 679 | 1.416 | 3.078 |
| `ema34>89` | 80 | 96.3% | 96.3% | **3.8%** | 1.121 | 1,941 | 706 | 1.420 | 3.177 |

Identical detectability on all three: **3 of 80 cells outside their own MDE**. The EMA arms carry
~1.7x the trades, so their MDEs are ~30% smaller (policy marginal 8.2-8.7 against 11.4-12.2 points)
— which is the mechanism behind the rate workstream's "the milder condition survives a short
reserved block".

### 9.1 Where the arms AGREE

**The trail wins raw profit factor on all three arms** — flatten / channel / breakeven / trail:

| arm | flatten | +chan10 | +be1R | **+trail** |
|---|---|---|---|---|
| `+adx<=20` | 1.145 | 1.133 | 1.106 | **1.415** |
| `+ema align` | 1.109 | 1.112 | 1.116 | **1.253** |
| `ema34>89` | 1.091 | 1.094 | 1.102 | **1.250** |

**And so does its own coin-flip twin, on all three arms** — the twin's PF under the trail is
**1.000 / 1.012 / 1.007** against 0.932-0.946 under every other policy. §4's mechanism reproduces on
two independent signal sets: the trail lifts the null as much as it lifts the rule.

**The trail also wins return-over-drawdown on all three** (5.69 / 3.76 / 3.30 against 0.79-1.86 for
everything else) and cuts the MDE roughly in half on all three. Both are real and both belong to the
geometry.

**150 points is the worst stop on all three arms in excess total** (2,438 / 2,191 / 1,925) and the
stop optimum is INTERIOR on all three — 50-100 on the ADX arm, 75 on both EMA arms. **This family
does not reproduce the branch's monotone-toward-wider stop finding on any arm.**

**The wide end of the target axis wins on all three** (150 or 200 or none), and 100 points is the
worst or second-worst everywhere.

### 9.2 Where they DISAGREE — and it is the excess column

| policy, EXCESS TOTAL (rule − twin, × n) | `+adx<=20` | `+ema align` | `ema34>89` |
|---|---|---|---|
| flatten only | 2,474 | **3,207** | 2,867 |
| + channel 10 | 2,302 | **3,208** | **3,064** |
| + breakeven 1R | **1,902** (last) | 2,950 | **2,746** (last) |
| **+ 1.0 ATR trail** | **2,552** (best) | **2,604** (last) | 2,764 |

**The trail is the best policy in excess on the ADX arm and the WORST on `+ema align`.** In excess
per trade it is last on both EMA arms (3.13 and 3.19 against flatten's 4.90 and 4.21) and second on
the ADX arm. Flatten-only and the channel exit are top-two on all three arms; the two ACTIVE
management policies each finish last somewhere.

And the rank correlations across the 80 cells make the point directly:

| unit | adx vs ema | adx vs slow | ema vs slow |
|---|---|---|---|
| raw PF | **+0.751** | **+0.799** | +0.990 |
| return/DD | +0.741 | +0.784 | +0.984 |
| PF ratio | +0.347 | +0.500 | +0.890 |
| points/trade | +0.326 | +0.404 | +0.976 |
| **excess total** | **−0.168** | **−0.116** | +0.810 |

**Raw profit factor ranks the 80 exit geometries almost identically on two entries that share only
46% of their daily P&L (+0.75 / +0.80), and the excess ranking is NEGATIVELY correlated (−0.17).**
That is §4's finding stated as a measurement rather than an argument: **a raw PF ranking over exit
geometries is measuring the exit, which every arm shares, and not the entry, which they do not.**
The two EMA arms, which ARE the same condition, agree on both (+0.99 and +0.81) — the control that
shows the diagnostic is working.

### 9.3 The best cell per arm, per unit

| unit | `+adx<=20` | `+ema align` | `ema34>89` |
|---|---|---|---|
| by raw PF | 150/none **trail** (1.607) | 150/none **trail** (1.416) | 150/none **trail** (1.420) |
| by ret/DD | 150/none **trail** (8.37) | 150/none **trail** (6.33) | 150/150 **trail** (5.44) |
| by **excess total** | 100/none **flatten** | 30/200 **+chan10** | 75/none **+chan10** |

**The trail is the top cell by raw PF and by return-over-drawdown on all three arms, and the top
cell by excess on none of them.** No arm's excess winner contains a trailing stop.

### 9.4 The tie-break on the new arms

| arm | mean ambiguous | max | mean \|spread\| | max \|spread\| | sign flips |
|---|---|---|---|---|---|
| `+ema align` | 0.43% | 2.47% | 0.569 pts | 2.188 | **0 of 80** |
| `ema34>89` | 0.42% | 2.49% | 0.550 | 2.154 | **1 of 80** |

Same answer as §5: at these barrier widths a 15-minute bar resolves the pair, and the convention
does not decide any verdict. The one sign flip on `ema34>89` is a cell whose points-per-trade is
within a point of zero.

### 9.5 One read of both reserved blocks on the two new arms

The same five declared cells, declared again in `x_run6`'s docstring before the read, each with its
own matched twin. **PF RATIO — the cell's PF over what its own exit machinery gives a coin flip:**

| cell | adx A / B / C | ema A / B / C | slow A / B / C | **>1** |
|---|---|---|---|---|
| **D0 50/150 flatten** | 1.312 / 1.172 / 1.131 | 1.184 / 1.060 / 1.129 | 1.171 / 1.088 / 1.147 | **9/9** |
| D2 100/none flatten | 1.271 / 1.182 / **0.800** | 1.178 / 1.009 / 1.266 | 1.147 / 1.020 / 1.211 | 8/9 |
| D4 150/none trail | 1.360 / 1.514 / **0.771** | 1.198 / 1.019 / 1.117 | 1.201 / 1.003 / 1.125 | 8/9 |
| D3 100/150 trail | 1.367 / 1.389 / **0.773** | 1.238 / **0.984** / 1.023 | 1.241 / 1.026 / 1.010 | 7/9 |
| D1 50/none flatten | 1.271 / 1.092 / **0.982** | 1.248 / **0.997** / 1.340 | 1.210 / **0.988** / 1.326 | 6/9 |

**The incumbent geometry is the only one of the five above its own null on all three blocks of all
three arms — 9 of 9 on PF ratio and 9 of 9 on excess points.** Every other cell fails somewhere, and
the two trail cells fail on the different-provider block of the ADX arm by the widest margin in the
table (PF ratio 0.771-0.773, i.e. a coin flip with the same trail earns ~30% more).

**And on the EMA arms the trail's PF ratio collapses to ~1.0 out of sample while its raw PF still
looks good.** `+ema align` D3: raw PF 1.106 on the holdout against a twin's 1.124, ratio **0.984**;
D4 raw 1.301 against a twin's 1.277, ratio **1.019**. Raw PF says the trail took 1.035 → 1.301 on
that block; the ratio says all of it was the exit machinery. Out-of-sample excess per trade on the
trail cells is +3.23 / **−0.14** / +1.06 (ema) and +3.31 / +0.60 / +0.70 (slow) against the flatten
cells' +4.68 / +1.92 / +4.71 and +6.02 / +0.35 / +14.60.

Two other things this read settles. **D2 (100/none flatten) is not portable** — it is the best
excess cell on the ADX arm and reads PF 0.826 with a −11.6-point excess on that arm's forward block,
while on the EMA arms it is 3/3. **And `ema34>89` tracks `+ema align` cell for cell out of sample
too** (D0 +2.51/+2.18/+6.55 against +2.79/+1.13/+6.79), which is the redundancy confirmed on a third
statistic. `D4` is outside its MDE on 1 of 3 blocks for every arm — the research block, always.

**Nothing in §9 tilts the verdict toward either arm.** The two arms disagree about which exit is
best in excess (trail on ADX, flatten/channel on EMA), they agree that raw PF prefers the trail and
that the trail's twin prefers it too, and they agree that the incumbent's 50/150 flatten geometry is
what survives everywhere. If anything the cross-arm read makes §4's case stronger, because the one
arm on which the trail's excess looked best is the one arm on which it inverts hardest out of sample.

### 9.6 Does the exit marginal invert in ATR units, as the ARM comparison does?

`STUDY_US30_SCALP_0711` §18, published while this grid was running, found that `+adx<=20` beats its
base by **+5.304 POINTS and by −0.0134 ATR** — the ceiling selects calmer bars (median signal-bar
ATR **0.894x** the base's) so its point advantage is carried by the high-ATR minority it keeps.
Everything in §1-9.5 is in points, so the same question had to be put to the EXIT axis. `x_run7.py`.

**The exposure is much smaller here, and the reason is measurable.** §18 compares two different
ENTRY populations; every comparison in this study holds the entry fixed. The policies do admit
slightly different trade counts, so the ATR mix can still move — and it barely does:

| arm | median signal-bar ATR, trail / flatten |
|---|---|
| `+adx<=20` | **0.9954** |
| `+ema align` | 0.9877 |
| `ema34>89` | 0.9814 |

against the 0.894 that drives §18's inversion. The exit axis does not re-select the volatility
regime.

**But the two units DO disagree on one arm, and it is the arm §18 flagged.** Spearman between the
d_pts and d_atr rankings of the four policies: `+adx<=20` **−0.400**, `+ema align` **+1.000**,
`ema34>89` **+0.800**. On the ADX arm the trail is LAST by excess points and FIRST by excess ATR.

**Excess over its own twin, both units, stop 100 / target 150:**

| arm | flatten pts | trail pts | flatten **ATR** | trail **ATR** |
|---|---|---|---|---|
| `+adx<=20` | **+6.535** | +5.467 | +0.0686 | **+0.1038** |
| `+ema align` | **+4.409** | +3.558 | **+0.1487** | +0.0836 |
| `ema34>89` | **+4.040** | +3.340 | **+0.1232** | +0.0805 |

**Flatten-only beats the trail in excess in 5 of 6 arm x unit cells.** The single exception is the
ADX arm read in ATR — one cell of six, on the arm whose points figures §18 has just withdrawn. That
is the honest location of the only evidence favouring a trail anywhere in this study, and it does
not survive being asked on a second entry condition.

**And §4's mechanism holds in the second unit too**: the matched twin's ATR-unit result is
**positive under the trail on all three arms** (+0.0364 / +0.0278 / +0.0348) and **negative under
every other policy** (−0.0176 to −0.0638). A coin flip is lifted by the trail in ATR exactly as it
is in points. Nothing about the trail's advantage belongs to the entry in either unit.

Measuring the same 12 cells in a second unit adds no configurations to the trial count.

---

## 10. Verdict

**Nothing in the exit-geometry or position-management space improves the §12 rule's profit factor in
a way that survives its own null.**

- **The trailing stop is the only thing that moves PF materially, and it is geometry.** It takes PF
  1.24 → 1.42 at 1.0 ATR and → 3.24 at 0.25 ATR, and a **coin flip with the same trail reads 1.00 →
  2.44**, replicated at 2.20-2.50 on both reserved blocks and a second provider — and in **ATR units
  as well as points**, the twin being lifted into positive territory by the trail on all three arms
  and negative under every other policy. In excess of its own twin the trail is beaten by doing
  nothing in **5 of 6 arm x unit cells**, and on the different-provider block it is **worse than its
  twin at every rung**.
- **Breakeven-after-1R subtracts on every arm** — bottom of every column on the ADX arm (22% below
  the flatten on excess total) and last or next-to-last in excess on the two EMA arms too. **The
  channel exit is a wash**: within 1% of flatten-only in excess on the ADX arm, first by a nose on
  both EMA arms, and behind flatten-only out of sample — an addition that changes nothing.
- **The incumbent's geometry is already at or above the marginal optimum.** Stop 50 leads
  return/drawdown and PF ratio and is second on excess; target 150 leads every column, raw and
  excess. On the flatten sub-grid alone, 50/150 is the best cell on PF (1.236) and on ret/DD (2.242)
  of the twenty tested.
- **It is also the only one of five declared cells positive in excess on all three blocks**
  (+8.04 / +4.83 / +5.55), the only one whose PF ratio stays above 1 on all three, and it decays
  across the split — the right shape.
- **No PF gain anywhere here is outside its own MDE on a block that did not choose it.** D4's
  +0.728 PF on the holdout is +8.41 points against an MDE of 15.37; D3's +0.452 is +4.05 against
  11.59. PF 1.2 still requires **+10.61 points a trade** and PF 1.5 **+23.62**.

**And the cross-arm replication (§9) is the strongest form of that finding.** The identical grid on
two more entry conditions puts the trail top of the raw-PF and return/drawdown tables on **all
three** arms, top of the excess table on **none**, and — decisively — **raw PF ranks the 80 exit
geometries at +0.75/+0.80 across arms that share only 46% of their daily P&L, while the excess
ranking correlates −0.17.** Raw PF is ranking the exit; excess is ranking the entry. The incumbent
50/150 flatten geometry is above its own null on **9 of 9** arm x block cells, the only one of five
declared cells that is.

**What this changes methodologically, and it is the durable output: PROFIT FACTOR IS NOT COMPARABLE
ACROSS EXIT GEOMETRIES.** A trail, a breakeven stop or a tight target rescales both the numerator
and the denominator, and the rescaling is worth up to **+1.5 PF on a coin flip**. Any request to
"improve profit factor" that is allowed to move the exit will be satisfied trivially and falsely.
Report **PF against the PF the same exit machinery gives a random entry**, and rank on **excess
total** — the two rankings correlate only **+0.686** by rank and **+0.496** by level across these
80 cells.

**The single change the evidence supports is a negative one: do not add a breakeven stop or a
trailing stop to this rule.** (The channel exit is the one addition that is never last: top-two in
excess on all three arms and the excess winner on both EMA arms — but it is behind flatten-only on
the ADX arm and behind it out of sample, so it is a coin flip against doing nothing, not an
improvement.) If a trail is wanted for drawdown control rather than for
edge, that is a defensible and separate decision — it cuts maximum drawdown 1,742 → 470 and halves
the MDE — but it must be argued as sizing, and its profit factor must not be quoted beside the
flatten's.

**What would move it** is unchanged from `STUDY_US30_SCALP_0711` §11: pooling the window across
US100 and NQ, and 1-minute US30 bars — which would also settle the one place the tie-break still
bites here, the tight-target trail cells.
