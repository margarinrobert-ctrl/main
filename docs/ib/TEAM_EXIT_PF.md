# Exit geometry and position management on the §12 US30 rule: what moves profit factor

Asked to improve **profit factor** on `STUDY_US30_SCALP_0711` §12's primary, varying the exit
geometry and position management only. The entry trigger (Donchian 20 long), the filters
(`+adx<=20`), the window (07:00-11:00 New York) and the 11:00 flatten are held fixed throughout.

`research/us30exit/`: `x_lib.py`, `x_run1.py` .. `x_run5.py`.

**The answer in one line: a trailing stop raises profit factor from 1.24 to 1.42 and a COIN FLIP
with the same trailing stop raises it from 0.94 to 1.00 — and at a 0.25 ATR trail the coin flip
reads PF 2.44. Profit factor is not comparable across exit geometries, and once every cell is
priced against its own null nothing in the 80-cell space beats the incumbent out of sample.**

**Trial count: 249 research cells and 38 reserved reads.** 80 declared grid cells, plus 6 extra
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

## 9. Verdict

**Nothing in the exit-geometry or position-management space improves the §12 rule's profit factor in
a way that survives its own null.**

- **The trailing stop is the only thing that moves PF materially, and it is geometry.** It takes PF
  1.24 → 1.42 at 1.0 ATR and → 3.24 at 0.25 ATR, and a **coin flip with the same trail reads 1.00 →
  2.44**, replicated at 2.20-2.50 on both reserved blocks and a second provider. In excess of its
  own twin it is worth **4% more than doing nothing in total and less per trade**, and on the
  different-provider block it is **worse than its twin at every rung**.
- **The channel exit and breakeven-after-1R both subtract**, on every unit, in sample and out.
  Breakeven-after-1R is the worst object in the study — 22% below the flatten on excess total.
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

**What this changes methodologically, and it is the durable output: PROFIT FACTOR IS NOT COMPARABLE
ACROSS EXIT GEOMETRIES.** A trail, a breakeven stop or a tight target rescales both the numerator
and the denominator, and the rescaling is worth up to **+1.5 PF on a coin flip**. Any request to
"improve profit factor" that is allowed to move the exit will be satisfied trivially and falsely.
Report **PF against the PF the same exit machinery gives a random entry**, and rank on **excess
total** — the two rankings correlate only **+0.686** by rank and **+0.496** by level across these
80 cells.

**The single change the evidence supports is a negative one: do not add a breakeven stop, a channel
exit or a trailing stop to this rule.** If a trail is wanted for drawdown control rather than for
edge, that is a defensible and separate decision — it cuts maximum drawdown 1,742 → 470 and halves
the MDE — but it must be argued as sizing, and its profit factor must not be quoted beside the
flatten's.

**What would move it** is unchanged from `STUDY_US30_SCALP_0711` §11: pooling the window across
US100 and NQ, and 1-minute US30 bars — which would also settle the one place the tie-break still
bites here, the tight-target trail cells.
