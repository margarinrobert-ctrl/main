# US30 07:00-11:00 New York: the arithmetic before the rule

Asked to improve a 07:00-11:00 US30 scalp. This branch has attacked that exact cell four times
already (`STUDY_DL50`, `STUDY_MR30`, `STUDY_VP_DONCHIAN_US30`, `STUDY_SCALP_REQUIREMENTS`), so
rather than a fifth search the question was put arithmetically first: **what does a scalp need
here, and what does the window actually deliver.** `research/us30scalp/`.

## 0. The data decides more than the rule does

`python research/datasets.py`: **`US30_1m` is MISSING.** The finest US30 series on disk is
`US30_LONG_15m` (193,942 bars, sha256 24dcf2e1c7ba398f, verified identical to the studied copy), so
**a 07:00-11:00 session is SIXTEEN BARS**. Everything below inherits that — the true 1-minute exit
path cannot be walked (`STUDY_ATME_LIVE` cut a result fivefold on exactly that), and any barrier
pair tight enough to sit inside one bar is decided by the tie-break rather than by the market.

Blocks: A = US30L before 2023-01-01, B = the rest, C = `US30_ISO_15m` after 2025-07-16 — a
DIFFERENT PROVIDER over a span no search here has touched. A and B are heavily spent (six studies)
so a p-value there is descriptive; C is the only genuinely unread one.

## 1. What the geometry costs

Median in-window ATR(14) is **31.17 points** on a 26,542 index; the round turn is 2.29 points =
0.0086% of price.

| stop | risk (pts) | cost / risk | break-even win | driftless | cost costs |
|---|---|---|---|---|---|
| 0.5N | 15.6 | **14.69%** | 57.35% | 50% | 7.35 pts |
| 0.75N | 23.4 | 9.80% | 54.90% | 50% | 4.90 |
| 1.0N | 31.2 | 7.35% | 53.67% | 50% | 3.67 |
| 1.5N | 46.8 | 4.90% | 52.45% | 50% | 2.45 |
| 2.0N | 62.3 | 3.67% | 51.84% | 50% | 1.84 |
| 2.5N | 77.9 | 2.94% | 51.47% | 50% | 1.47 |
| 3.0N | 93.5 | 2.45% | 51.22% | 50% | 1.22 |

Against what the population delivers (resolved win rate, every in-window bar, research block):

    0.5N   break-even 57.35%   actual 43.21%   short by 14.1 points
    1.0N              53.67%          47.68%           6.0
    1.5N              52.45%          48.26%           4.2
    2.0N              51.84%          49.03%           2.8
    3.0N              51.22%          49.20%           2.0

**The shortfall narrows monotonically as the barriers widen and never closes.** That is the
frontier: the tighter the scalp, the further from break-even it starts, and the mechanism is
measured rather than asserted.

## 2. At scalp geometry the verdict is not knowable on this data

**14.0% of 0.5N/0.5N trades touch both barriers inside one 15-minute bar.** Resolved stop-first —
this branch's convention — and target-first, on the identical population:

| geometry | ambiguous | stop-first | target-first | **spread** | stop-first PF | target-first PF |
|---|---|---|---|---|---|---|
| 0.5N/0.5N | 14.03% | -4.764 | +0.510 | **5.274 pts** | 0.604 | **1.056** |
| 0.75N/0.75N | 6.83% | -3.731 | -0.194 | 3.537 | 0.766 | 0.986 |
| 1.0N/1.0N | 4.19% | -3.224 | -0.746 | 2.478 | 0.838 | 0.960 |
| 1.5N/1.5N | 1.69% | -2.968 | -1.673 | 1.295 | 0.888 | 0.935 |
| 2.0N/2.0N | 0.69% | -2.751 | -2.188 | 0.564 | 0.914 | 0.931 |

**The convention flips the sign at scalp geometry** — PF 0.604 against 1.056 — and is worth 5.27
points a trade, which is larger than any edge on offer anywhere in this study.
`STUDY_VOLBO_BREAKOUT` settled the same question by dropping to 1-minute bars and finding the
ambiguous share was exactly 0.000; here that is impossible because `US30_1m` is absent. **So a
sub-1N barrier result on US30 is a statement about the tie-break, not about the market**, and no
amount of filtering changes which of the two numbers is true.

## 3. No declared trigger beats the population it sits in

Seven declared triggers (Donchian 20 and 10 both sides, the `STUDY_MR30` displacement fade at two
settings, EMA 13>48) x three measurable geometries, research block only, each against a matched
random entry drawn from the same eligible in-window bars, 400 draws, sorted so the position lock
rejects the same share:

**0 of 21 cells clear p <= 0.05 where 1.1 are expected by chance, and every one of the 21 is
unprofitable.** Best in the table is `donch20 long 1.5N/1.5N` at **-0.983 pts, p 0.155** — it beats
a control that loses 2.83, which is `STUDY_IB_US30_OPTUNA`'s sentence again: *a rule that beats a
losing null is still a losing rule*.

The sides split as drift predicts and not as a signal would: longs beat their controls in 8 of 9
long cells, shorts lose to theirs in every short cell. And always-in long in the window is negative
at all three geometries (-3.22 / -2.97 / -2.75 pts), so there is no drift to harvest here either at
a symmetric barrier pair.

## 4. What the window DOES support is not a scalp

175-cell declared geometry sweep (5 stops x 5 targets including NO TARGET x 4 hold caps x flatten
on/off) on the Donchian 20 long, research only, read by MARGINAL AVERAGE:

| axis | best setting | marginal pts | worst setting | marginal pts |
|---|---|---|---|---|
| target | **NO TARGET** | **+1.707** | 1.5N | -1.291 |
| stop | 1.5N | +0.831 | 3.0N | -0.942 |
| flatten | **OFF** | +0.147 | ON | -0.740 |
| hold cap | 16 bars | -0.137 | none | -0.616 |

No target is the only positive setting on its axis — the **25th** time on this branch — and the
flatten is negative, the **16th**. The marginal consensus is **1.5N stop, no target, 16-bar cap, no
flatten**, and it reads research **+4.05 pts / PF 1.110 / 32.4% win / median hold 105 MINUTES**.

**That is not a scalp.** It is a morning-entered swing trade with no target that runs into the
afternoon, and it is what the window supports precisely because widening the barriers is the only
thing that moved the arithmetic in §1.

One read, and it inverts:

| feed | block | n | pts | PF | control p | always-in |
|---|---|---|---|---|---|---|
| US30L | A research | 1043 | +4.047 | 1.110 | 0.168 | -0.026 |
| US30L | B holdout | 484 | **-5.494** | 0.886 | 0.853 | +1.854 |
| US30I | **C forward** (different provider) | 230 | -0.516 | 0.992 | 0.568 | -1.883 |

It clears no control on any block, and on the holdout **always-in beats it** (+1.854 against
-5.494). Cost is not the objection for this cell — at ZERO cost it still reads PF 1.181 on research
and the whole cost ladder (0x through 2x) stays positive there — so what fails is the transfer, not
the friction.

## 5. The one component that helped on both blocks is the window itself

Donchian 20 long at 1.5N/1.5N, window and flatten separated, because `STUDY_V61_SESSION` showed
they are different questions:

| configuration | research | holdout |
|---|---|---|
| all hours, no flatten | -0.232 (PF 0.991) | -2.814 (PF 0.903) |
| **07-11 window, no flatten** | **+0.707 (PF 1.025)** | **-0.704 (PF 0.980)** |
| 07-11 window + flat 11:00 | -0.983 (0.959) | -0.234 (0.992) |
| all hours + flat 11:00 | -2.151 (0.907) | -3.665 (0.850) |

**Restricting to 07:00-11:00 improves the rule on BOTH blocks** (+0.94 pts research, +2.11 pts
holdout) — the window is worth keeping. The FLATTEN is mixed (-1.69 research, +0.47 holdout), which
is a weaker version of the branch's standing finding rather than a contradiction of it.

Hour by hour inside the window, population long at 1.5N/1.5N: on research **10:00-11:00 is the only
positive hour** (+0.046 pts, PF 1.002) and 07:00-08:00 the worst (-3.062), reproducing
`STUDY_TREND_PULLBACK` exactly — and on the holdout it INVERTS, 10:00-11:00 going to -2.422 while
09:00-09:30 becomes the best. Sixth time a session preference has failed to transfer here.


## 6. Corrected: the user's definition is 20-150 POINTS and up to four hours

Sections 1-5 tested ATR-multiple barriers and called the wide end "not a scalp". That was my
framing, not the brief's. On US30's **31.17-point in-window ATR, 20 points is 0.64N and 150 points
is 4.81N**, and four hours is exactly the 16-bar cap — so §4's marginal consensus already sat
INSIDE the definition, and this is the space that should have been swept first. What that range
costs:

| stop | in ATR | cost / risk | break-even 1:1 | 1:2 | 1:3 |
|---|---|---|---|---|---|
| 20 pts | 0.64N | **11.45%** | 55.72% | 37.15% | 27.86% |
| 30 | 0.96N | 7.63% | 53.82% | 35.88% | 26.91% |
| 50 | 1.60N | 4.58% | 52.29% | 34.86% | 26.14% |
| 100 | 3.21N | 2.29% | 51.15% | 34.10% | 25.57% |
| 150 | 4.81N | **1.53%** | 50.76% | 33.84% | 25.38% |

**AND IN THIS SPACE THE TRIGGER SEPARATES FROM THE POPULATION FOR THE FIRST TIME.** 168 declared
cells (7 stops x 8 targets including none x 3 hold caps), entries 07:00-11:00, the cap binding
rather than a bell, research only:

    population (every in-window bar, long):   2.4% of cells profitable, best PF 1.026
    Donchian 20 long:                        45.2% of cells profitable, best PF 1.107

The trigger beats the population's marginal by **+2.7 to +3.7 points a trade at every setting**.
That is a genuine difference and nothing earlier in this study produced one.

**The marginals inside the brief's own range are monotone and they point at its top end:**

| axis | best | ... | worst |
|---|---|---|---|
| **stop** | 150 pts +0.352 (PF 1.002) | 100 +0.217, 75 -0.199, 50 -0.792, 40 -0.932, 30 -1.014 | **20 pts -1.866 (PF 0.864)** |
| **target** | **none +1.897 (PF 1.061)** | 150 +1.158, 100 +1.197, 75 +0.155, 50 -0.644, 40 -1.388 | **20 pts -3.837 (PF 0.741)** |
| **hold** | **4h -0.137** | 2h -0.817 | 1h -0.860 |

So within 20-150 points the **top of the range works and the bottom destroys it** — a 20-point
target reads PF 0.741 against no target's 1.061 — and the four-hour cap is at the good end of its
own axis, not a constraint that is costing anything.

**AND THE POINTS PARAMETERISATION IS ITSELF COSTING SOMETHING.** Re-run at the SAME distances
expressed in ATR:

    points grid:  45.2% profitable   mean PF 0.9472   best 1.107
    ATR grid:     49.4% profitable   mean PF 0.9920   best 1.157

and the two **disagree about the stop**: the points grid is monotone toward wider (150 pts best,
+0.352) while the ATR grid peaks in the middle (1.28N +1.005, 1.60N +0.857) and puts **4.81N
worst at -0.434**. `STUDY_DL50` measured why — a fixed 50-point stop is 4.23 ATR in 2016 and 1.10
ATR in 2025 — so a points grid confounds geometry with era, and the apparent "wider is always
better" is partly the ATR drifting down across the sample.

## 7. And in that space nothing clears its control either

Seven declared triggers at the marginal consensus (150-pt stop, no target, 4h cap), research only,
each against a matched random entry from the same eligible in-window bars:

| trigger | n | pts | PF | control | excess | p |
|---|---|---|---|---|---|---|
| fade n8 k2.0 | 1679 | +0.683 | 1.012 | -2.355 | +3.038 | 0.260 |
| fade n4 k1.5 | 1841 | +0.608 | 1.011 | -1.354 | +1.962 | 0.315 |
| donch20 long | 936 | **+2.016** | **1.040** | +0.668 | +1.347 | 0.368 |
| ema13>48 long | 1349 | -0.216 | 0.996 | +0.566 | -0.781 | 0.593 |
| donch20 short | 857 | -6.333 | 0.898 | -3.990 | -2.343 | 0.703 |

**0 of 7 clear p <= 0.05 where 0.4 are expected.** Eight declared geometries on the best trigger:
**0 of 8**, best p 0.280. The mean-reversion fade now ranks above every breakout, which is the
thirteenth route to that conclusion here, and it still does not clear.

One read of the consensus cell:

| feed | block | n | pts | PF | control p | always-in |
|---|---|---|---|---|---|---|
| US30L | A research | 1679 | +0.683 | 1.012 | 0.260 | **+1.548** |
| US30L | B holdout | 760 | -2.276 | 0.968 | 0.393 | -0.210 |
| US30I | **C forward** | 374 | **+6.206** | **1.074** | 0.075 | +2.642 |

**On research always-in beats it** (+1.548 against +0.683), and the block where it looks best is
the one opened LAST — better out of sample than in, the wrong shape yet again. Day-block bootstrap
against zero: research P(mean <= 0) **0.444**, holdout **0.631**, with a daily CI of
[-7.86, +10.10] points. Nothing separates from zero on either block.


## 8. The null was sound, and diagnosing it produced the number that governs everything

`STUDY_V59` records that a control whose median sits far below the rule and which still cannot
reject anything is broken, and S7's headline had exactly that shape: an excess of **+3.04 points**
failing at **p 0.260**. Diagnosed rather than assumed:

    fade n8 k2.0   sd(null mean) / sd(rule's own standard error) = 1.134
    donch20 long                                                = 1.005
    null trade count: target 1679, actual 1104.7 +- 14.0 (min 1065, max 1149)

The null is as tight as the estimate it is testing and its trade count is stable, so it is
correctly specified. One construction note for reuse: the control is handed the rule's
POST-lock count and then has the lock applied again, so it settles at ~34% fewer trades than the
rule; that makes the test slightly conservative rather than invalid, and the fix is to over-draw by
the reciprocal of the lock's rejection rate.

**What the diagnostic actually found is the dispersion.** Per-trade sd is **157.1 points on a mean
of +0.683**, so with 1,679 trades the standard error of the mean is 3.84 points and the rule sits
**0.18 standard errors from zero**. Its excess over the null is 0.70 null sd. The p-value is not a
verdict on the rule — it is a statement that this sample cannot resolve effects of this size.

Event structure, measured because a 4-hour cap inside a 4-hour window nearly forces it:
`donch20 long` opens only one trade on **98.3%** of sessions (2.43 in-window signals offered per
session), so the rule is very nearly *the first break after 07:00* rather than *a break*. Reduced
to first-signal-only it is unchanged in verdict — **0 of 14 cells clear, 0.7 expected**. Concurrency
is **max 1, mean 1.00, 12.3% of bars in a position**, so there is no hidden portfolio; exits are
70.9% clock, 29.1% stop, 0% target.

## 9. Anything worth trading here is detectable, and anything undetectable is not worth trading

At sd 157.1 points and 272 trades a year, the minimum detectable effect at 80% power:

| trades | years at this rate | MDE (pts/trade) | as % of a 150-pt stop |
|---|---|---|---|
| 500 | 1.8 | 19.69 | 13.1% |
| **1,679 (the research block)** | **6.2** | **10.74** | **7.2%** |
| 5,000 | 18.4 | 6.23 | 4.2% |
| 20,000 | 73.5 | 3.11 | 2.1% |

And what each profit factor requires, from the observed win 129.78 / loss 104.04 / win rate 0.4479:

| target PF | needs win rate | = edge | detectable in |
|---|---|---|---|
| 1.1 | 0.4686 (+2.1 pts) | +5.53 pts/trade | 6,341 trades (23 yrs) |
| **1.2** | 0.4903 (+4.2) | **+10.61** | **1,723 trades (6 yrs)** |
| 1.5 | 0.5460 (+9.8) | +23.62 | 347 trades (1 yr) |
| 2.0 | 0.6159 (+16.8) | +39.96 | 121 trades |

**The frontier inverts the usual complaint.** Six years is not a small sample for a PF-1.5 rule — it
is a large one, and a PF-1.2 rule lands almost exactly at the sample's resolution. The sample is
insufficient only for edges too small to be worth trading. Detecting the observed +0.68 pts would
take **415,506 trades = 1,528 years**.

## 10. The search's own noise floor exceeds the detection threshold

Every declared trigger x the full geometry space — **1,176 scorable cells**, research only:

    profitable                        10.6%
    best t achieved                    1.348
    detectable at 80% power requires   t >= 2.802
    E[max t | pure noise] over 1,176   t  = 3.301
    cells reaching 2.802:  0 of 1,176
    cells reaching 3.301:  0 of 1,176

**Over a space this size a detectable edge and the search's luckiest draw are the same number.**
The threshold a configuration must clear to be trusted (2.802) is BELOW what pure noise produces as
its best of 1,176 draws (3.301), so a search this wide cannot separate the two even in principle —
and the best thing actually found reaches less than half of either. Deflation says the same from
the other side: trial Sharpe sd 0.09704 per session gives **E[max Sharpe | null] = 0.32031 against
a best achieved of 0.03377**, an order of magnitude below its own noise floor, with 1,401 counted
looks across S1-S8.

Best cell per trigger, by t — and note the ordering, because it reverses §7:

| trigger | geometry | n | pts | sd | **t** | Sharpe | PF | win | med min |
|---|---|---|---|---|---|---|---|---|---|
| **donch20 long** | 30 / 150 / 4h | 1173 | +2.508 | 63.7 | **1.348** | 0.535 | 1.107 | 26.7% | 30 |
| donch10 long | 30 / 150 / 4h | 1474 | +1.701 | 63.7 | 1.025 | 0.408 | 1.072 | 25.4% | 45 |
| donch20 short | 75 / 150 / 4h | 963 | +2.753 | 94.5 | 0.904 | 0.341 | 1.068 | 39.0% | 90 |
| fade n8 k2.0 | 150 / none / 4h | 1679 | +0.683 | 157.1 | 0.178 | 0.071 | 1.012 | 44.8% | 240 |

The mean-reversion fade led §7 on points and is LAST on t, because its dispersion is 2.5x the
Donchian's. **Ranking by mean chose the widest, noisiest cell in the space.** Across the whole grid
the four statistics are nonetheless one statistic wearing four names — corr(mean, t) **+0.990**,
corr(t, Sharpe) **+1.000**, corr(PF, Sharpe) **+0.997** — so it is the TOP ROW that differs, not the
ranking, which is precisely why a top row should never be read.

## 11. The ranking transfers and the level does not

Across all 1,176 cells, research against holdout:

    corr(research pts, holdout pts)   +0.6898 Pearson / +0.6965 Spearman
    top 1% by research:  research +3.230  ->  holdout -1.339
    whole population:                          holdout -4.172
    holdout-profitable share: population 4.7%,  research top 1% 45.5%

**Selecting on research works** — it lifts the holdout-profitable share **9.7-fold**, from 4.7% to
45.5%, and a +0.69 transfer correlation is far above this branch's usual -0.03 to +0.2. **And it is
not enough**, because the space it is selecting within is so negative that its top 1% still lands
at -1.34 points and below a coin flip. Same structure as `STUDY_VP_DONCHIAN_US30`: the direction
survives, the size does not. This is the cleanest case on the branch of a search that is working
correctly and has nothing to find.

The best cell read once — chosen from 168 geometries on research, so its research p is
post-selection and 400 control draws cannot resolve the 0.0003 a Bonferroni over that grid needs:

| feed | block | n | pts | t | Sharpe | PF | win | control p |
|---|---|---|---|---|---|---|---|---|
| US30L | A research | 1214 | +2.076 | 1.332 | 0.536 | 1.093 | 30.5% | **0.000** |
| US30L | B holdout | 604 | **-1.987** | -0.896 | -0.542 | 0.919 | 23.8% | 0.425 |
| US30I | C forward | 304 | +2.776 | 0.837 | 0.739 | 1.118 | 27.0% | 0.130 |

It is the only cell in the study to clear a control anywhere, and it does so on the block that
chose it, then inverts.


## 12. The rule the team's evidence implies — positive on all three blocks, and still not proven

The three agents produced two component findings that reproduced across three blocks and two
providers: **ADX is inverted** (ceilings beat their block's base 12/12, floors 6/24, `adx>=25`
negative 6/6) and **the EMA ALIGNMENT carries where the state does not** (`ema13>34>89` positive
6/6 with the pool's most stable lift; `ema13>48` passes 84.2% of breakout bars and is the trigger
restated). ATR was at chance both ways. Nobody had built the rule those three statements imply.

Declared in full before running — Donchian 20 long, 07:00-11:00 with the 11:00 flatten, geometries
30/150 and 50/150 points, five arms including the conventional `adx>=25` stack **as the arm that
must lose if the inversion is real**. Ten research cells, nothing else tried, then one read of
B_holdout and one of C_forward.

**The prediction held at both geometries:**

| geometry | base | +adx<=20 | +ema align | +both | **conventional (+adx>=25)** |
|---|---|---|---|---|---|
| 30/150 | +1.411 | +3.753 | +3.106 | **+4.972** | +2.516 |
| 50/150 | +0.956 | +6.260 | +2.794 | **+6.613** | +1.419 |

Every arm built from the team's findings beats the base; the conventional stack is beaten by both
of its own components taken separately.

**Across all three blocks, per arm:**

| arm | A research | B holdout | C forward | cells positive | mean | clears control | **outside its MDE** |
|---|---|---|---|---|---|---|---|
| base | +1.183 | **-1.086** | +5.272 | 4/6 | +1.790 | 1/6 | **0/6** |
| **+adx<=20** | +5.007 | +3.442 | +7.474 | **6/6** | **+5.308** | 2/6 | **0/6** |
| **+ema align** | +2.950 | +1.947 | +7.523 | **6/6** | +4.140 | 2/6 | **0/6** |
| +both | +5.792 | +6.772 | +0.753 | 5/6 | +4.439 | 1/6 | **0/6** |
| conventional | +1.967 | **-3.065** | +10.088 | 4/6 | +2.997 | **0/6** | **0/6** |

**Both single filters are positive on all six cells — research, holdout, and a different-provider
forward feed — and each turns a holdout the base LOSES on into a positive one.** `adx<=20` at
50/150 clears its research control at **p 0.010** with a day-block bootstrap of **0.037**, the only
cell in the entire study to exclude zero. The conventional `adx>=25` stack clears **0 of 6** and is
the only arm negative on the holdout. That is the inversion confirmed out of sample.

**And every one of the thirty cells is inside its own MDE — 0 of 6 for every arm.** The best cell
(`+both`, 50/150, holdout) delivers **+8.51 points against an MDE of 24.84**. The bar for a
tradeable rule is unchanged: PF 1.2 requires **+10.61 points a trade** and the best arm delivers
+6.61 on research and +8.51 on the holdout. Out of sample no cell clears a control at p<=0.05
(best 0.070). Trade counts fall hard with the filters — `+both` is 227 / 87 / 43 across the three
blocks — which is where the MDE goes.

**What would settle it, exactly.** `+adx<=20` at 50/150 carries sd 73.2 on 400 research trades for
an MDE of 10.26 while delivering 6.26. Detecting an effect that size at 80% power needs
**n = (2.802 x 73.2 / 6.26)^2 = 1,073 trades**, against 400 in hand — roughly **16 years at this
window's rate, against the 8.7 years US30L carries.** That is the first number in this study naming
a reachable condition rather than an impossible one: doubling the US30 history would settle this
rule, and the different-provider forward feed is accumulating it in real time at ~65 trades a year.


## 13. The full battery on `+adx<=20`: four Monte Carlos, three blocks, a fixed walk-forward, three matrices

Figures: `research/us30scalp/s10_oos_walkforward.png`, `s10_montecarlo_correlations.png`.
Code: `s10lib.py` (ADX kernel asserted identical to the §12 reference, max |diff| 0.000e+00 over
193,928 bars), `run_s10.py`, `plot_s10.py`.

**Out of sample, points a trade:**

| arm | A research | B holdout | C forward (different provider) |
|---|---|---|---|
| **+adx<=20** | **+6.260** | **+4.596** | **+6.382** |
| +ema align | +2.794 | +1.126 | +6.787 |
| +both | +6.613 | +8.515 | **-1.378** |
| base | +0.956 | -1.601 | +4.613 |
| conventional | +1.419 | **-3.269** | +11.417 |

`+adx<=20` is the only arm positive on all three with a tight spread (+4.6 to +6.4); `+both` and
the conventional stack each swing by 10-15 points between blocks.

**Monte Carlo on `+adx<=20`** — four different questions, kept separate:

| | research | holdout |
|---|---|---|
| **bootstrap (EDGE)** P(mean<=0) | **0.037** | 0.229 |
| 95% CI, points/day | [-0.52, +14.45] | [-8.02, +18.53] |
| **permutation (PATH)** realised DD | 1117 | 1081 |
| percentile of realised | 0.760 | 0.865 |
| **MC p99 / realised** | **1.62x** | 1.38x |
| **execution** P(<=0) | **0.000** | **0.000** |
| **price jitter**, indicators recomputed, sign kept | **1.000** | **0.993** |

The rule is robust to everything that is not the sample: 250 execution draws (slippage U(0,2x),
cost U(0.5x,2x) applied inside the walk) never turn it negative, and 150 price-jitter draws with
**ADX, both EMAs, ATR and the Donchian channel all recomputed from jittered bars** keep the sign
1.000 / 0.993 of the time. What it is not robust to is its own sample size: the research bootstrap
excludes zero at 0.037 and the holdout's does not at 0.229. **And the realised drawdown sits at the
76th and 87th percentile of reshuffles of its own trades — the path was UNLUCKY, not lucky, so the
sizing number is MC p99 = 1.62x the realised drawdown, not less.**

**Walk-forward with the constants FIXED** — the honest test for a derived rule — eight calendar
folds:

| arm | folds positive | mean pts/trade |
|---|---|---|
| **+both** | 5/8 | **+14.638** |
| **+adx<=20** | **6/8** | +9.236 |
| random arm | 5/8 | +3.817 |
| +ema align | 5/8 | +3.439 |
| **re-chosen each fold** | **4/8** | **+1.189** |
| base | 4/8 | +1.119 |
| conventional | 5/8 | **-0.687** |

**The re-optimiser loses again** — 4/8 folds at +1.189 against the fixed `+adx<=20`'s 6/8 at
+9.236, and it also loses to a RANDOM arm (+3.817). Fifteenth such comparison on this branch. It
picked `conventional` twice and got -23.798 in 2020 for it. Two more things the fold table says
that no summary statistic does: **2023 and 2024 are negative for every single arm** — a two-year
drawdown the equity curves make plain — and **2025 supplies +36.253 for `+adx<=20` and +76.297 for
`+both`**, so a large share of the mean sits in one year.

**Three correlation matrices, three different questions.**

*Between the arms (daily P&L, research):* `+adx<=20` correlates **0.052** with the conventional
stack — they are opposite ADX readings and behave that way — and **0.328** with always-long, the
lowest of any arm, so it is the least drift-like object in the set. `+ema align` correlates 0.742
with the conventional stack, which is why the conventional stack is not simply noise.

*Between the conditions on the SIGNAL BARS:* `adx<=20` vs `ema align` is **-0.1185**, confirming
the team's cross-family 0.236 on a different construction — ADX and EMA are genuinely separate
axes here, which is unusual on this branch and is why the two filters stack at all. `adx<=20` vs
`adx>=25` is -0.6043, the expected mirror.

*Arms across blocks:* the rank correlation of the arm ordering is **A→B +0.900**, and
**A→C -0.400, B→C -0.700**. **The ranking transfers perfectly between two blocks of the same feed
and INVERTS on a different provider.** That is `STUDY_TREND_LONG`'s lesson arriving one more time —
two blocks of one data feed are not two tests — and it is the reason `+both`, which looks best on
A and B, is the arm that dies on C.

**What the battery changes, and what it does not.** It removes execution, data noise and path
luck as explanations, and it identifies `+adx<=20` as the arm whose result is most stable across
providers rather than merely largest. It does not move the detectability bar: the holdout bootstrap
still fails to exclude zero, every cell is still inside its MDE, and the forward block disagrees
about which arm is best.

## Verdict

**§12 is the current state and the one thing worth acting on: the rule derived from the team's
component findings — Donchian 20 long with an ADX CEILING and/or the EMA alignment, and NO ATR
condition — is positive on all six research / holdout / forward cells, turns a holdout the base
loses on into a profit, and clears a research control at p 0.010 with a bootstrap of 0.037. It is
also inside its own MDE in every cell, so it is confirmed in direction and unproven in size.
Removing `adx>=25` is the single change the evidence supports without qualification.**

Read §8-11 for why that qualification is unavoidable. They settle the question the earlier sections
could only circle: **this window,
at 15-minute resolution and this cost, cannot support a verifiable scalp — and the obstacle is
statistical power, not the rule.**

- **Per-trade dispersion is 157 points on a mean of +0.68**, so the research block's minimum
  detectable effect is **10.74 points a trade** and the observed edge sits 0.18 standard errors
  from zero. Detecting it would take 1,528 years.
- **But a PF-1.2 rule needs +10.61 and a PF-1.5 rule +23.62**, both at or inside that resolution.
  Six years is a LARGE sample for anything worth trading here; it is small only for edges that are
  not.
- **The best of 1,176 cells reaches t = 1.348 against the 2.802 detectability requires — and
  against a search noise floor of 3.301.** The luckiest draw of a null search this wide would look
  more convincing than a genuinely detectable edge, so no configuration selected this way can be
  trusted, and none came close anyway. Best Sharpe is an order of magnitude below its own noise
  floor.
- **The research ranking genuinely transfers (+0.69) and it does not rescue anything** — selection
  lifts the holdout-profitable share from 4.7% to 45.5% and still lands at -1.34 points a trade.

**What would move it, in order.** (1) **Pool the window across US100 and NQ**: three markets triples
the trade count and takes the MDE from 10.74 to ~6.2 points, which brings PF 1.1 (+5.53) inside the
sample's resolution for the first time. That is the single highest-value next step and the feeds are
on disk. (2) **1-minute US30 bars**, which fix the MEASUREMENT — the tie-break of §2 and entry
precision — though not the sample size, since a 4-hour cap keeps the rate near one trade a session
whatever the bar size. (3) A cheaper round turn: at a 20-point stop the fee is 11.45% of risk.

The best object found, offered as a SHAPE and with no edge claimed: **Donchian 20 long, 30-point
stop, 150-point target, four-hour cap, entries 07:00-11:00** — a 1:5 payoff won 26.7% of the time
with a 30-minute median hold, which is a scalp in the brief's own terms. Research PF 1.107 at
control p 0.000; holdout PF 0.919 at p 0.425; forward-block PF 1.118 at p 0.130.

Sections 6-7 use the brief's definition and supersede the framing in §1-5, which tested a tighter
geometry than was asked for.

**Inside 20-150 points the shape of the answer is clear and consistent, and none of it clears a
control.** The trigger does separate from the population (45.2% of cells profitable against 2.4%),
the marginals are monotone and point at the TOP of the stated range — 100-150 point stop, no target
or 150, the full four hours — and a 20-point target is the single most destructive choice available
(PF 0.741). Express the barriers in ATR rather than points: the ATR grid is better on every summary
(49.4% vs 45.2% profitable, mean PF 0.992 vs 0.947) and the two disagree about the stop because a
fixed point distance is a different geometry in 2016 than in 2025.

But 0 of 7 triggers and 0 of 8 geometries clear a matched random entry, always-in beats the best
cell on research, the bootstrap does not exclude zero on either block, and the cell reads better on
the forward block than on the one that chose it.

The rest of the verdict, on the tighter geometry I first tested:

- **A scalp needs a win rate this population does not have.** At 0.5N the break-even is 57.35% and
  the population delivers 43.21% — 14 points short, on a cost that is 14.7% of the risk. Widening
  closes the gap monotonically to ~2 points at 3.0N and never past it.
- **Below 1N the tie-break decides the answer**, and the two conventions disagree in sign
  (PF 0.604 vs 1.056, a 5.27-point spread). `US30_1m` would settle it; it is absent.
- **Nothing in the declared pool beats a matched random entry** — 0 of 21, every cell losing.
- **What the window supports is a 105-minute no-target trade**, and even that inverts out of sample
  and clears no control on three blocks including a different provider.
- **Keep the window, drop the scalp.** 07:00-11:00 improved the base on both blocks; the barriers,
  the target and the flatten are what took it apart.

What would move it, in order: **1-minute US30 bars** (settles §2 and unlocks the true exit path),
then a cheaper round turn — at 0.5N the fee is 14.7% of risk, so the 2.29-point assumption is
carrying the whole scalp verdict and no feed here can check it.

---

## 14. The trade-rate ladder: raising `n` makes the detectability *worse*, and the ranking of the two arms inverts

`research/us30rate/` — `r_lib.py`, `run_r1.py`, `run_r2.py`.

§10 left one number governing everything: the minimum detectable effect is `2.802·sd/√n`, and the
best arm delivers +6.26 points against an MDE of 10.26 on 400 trades. §12 put the requirement at
**1,073 trades against the 400 in hand**. Two axes can raise `n` — more markets, or a higher event
rate. The entry channel is the only parameter that changes the rate without touching the mechanism,
the geometry, the session or the cost, so it is the one to test.

**Why a ladder is readable where a grid is not.** §10 established that over 1,176 cells
`E[max t | pure noise] = 3.301`, already above the `t = 2.802` detection threshold — so no
configuration selected from a space that size could be believed even if one had scored. Over the
**18 cells declared here** (six ordered channel rungs × three arms, all six rungs reported) the same
expression gives **1.854**, comfortably below the threshold. The distinction is the whole reason
this run is admissible. Nothing here is permitted to pick a channel.

### 14.1 A shorter channel raises the count and loses the edge faster

Research block, `+adx<=20`, by channel:

| channel | n | trades/yr | pts | MDE | delivered / MDE | n needed | years needed |
|---|---|---|---|---|---|---|---|
| 10 | 511 | 82.8 | +3.379 | 8.89 | 0.380 | 3,533 | 42.7 |
| 15 | 447 | 72.4 | +4.905 | 9.65 | 0.508 | 1,732 | 23.9 |
| **20** | **400** | **64.8** | **+6.260** | **10.26** | **0.610** | **1,075** | **16.6** |
| 30 | 337 | 54.6 | +3.060 | 11.10 | 0.276 | 4,435 | 81.2 |
| 40 | 312 | 50.5 | +2.357 | 11.32 | 0.208 | 7,192 | 142.3 |
| 55 | 254 | 41.1 | +3.245 | 12.43 | 0.261 | 3,724 | 90.5 |

Halving the channel from 20 to 10 buys **28% more trades and costs 46% of the per-trade edge**, so
the ratio of the delivered effect to its own MDE *falls* 0.610 → 0.380 and the years-to-verify rises
16.6 → 42.7. The `spearman(rate, t)` readings have no consistent sign across the three blocks
(+0.714 / −0.314 / +0.657 for this arm), so there is no gradient to exploit in either direction.
**The trade rate is not a lever on detectability here.** Cross-market pooling stays the only axis
that raises `n` without paying for it in edge — and §11's pooling workstream measured that the
pooled edge shrank faster than the error bar, so both routes are now closed.

The unfiltered base is worse still: at every rung it needs **15,000 to 53,000 trades**, i.e. more
than a century of this window.

### 14.2 The ranking of the two arms inverts once the channel is varied

§13's headline was that `+adx<=20` was the only arm positive on all three blocks. **That was true at
channel 20 and is not true of the condition.** Across the ladder, versus each arm's own base at the
same rung:

| | positive delta | forward-feed rungs |
|---|---|---|
| `+adx<=20` | **15 of 18** | −7.461, −3.547, −5.005 at channels 30/40/55 |
| `+ema align` | **18 of 18** | positive at all six |

All three of `adx<=20`'s failures are on `US30_ISO`, the reserved different-provider block, at the
long channels. Against a **same-selectivity random VETO** (400 draws, re-simulated, so a refused
signal releases the position lock — `STUDY_AUCTION`) the split is the same and sharper:

| arm | beats its own null median | research | holdout | **forward** | cells at p≤0.05 (0.9 expected) |
|---|---|---|---|---|---|
| `+adx<=20` | 15 / 18 | 6/6 | 6/6 | **3/6** | 7 |
| `+ema align` | **18 / 18** | 6/6 | 6/6 | **6/6** | 5 |

On the block nobody chose, `adx<=20` is a coin flip against a random gate of its own selectivity
(median p 0.617) while `ema align` is 6/6 (median p 0.301). Neither is *significant* there. **The
EMA alignment is the more robust of the two conditions and §13 named the wrong one**, because §13
read a single channel.

**The correction has a readable mechanism and it is not mysterious.** `ema align` keeps 54–85% of
signals and its selectivity *rises* with the channel; `adx<=20` keeps 19–34% and its selectivity
*falls*. At channel 55 on the forward feed that leaves `adx<=20` **61 trades** against `ema align`'s
166. So part of the inversion is sample size rather than mechanism — which is exactly why the
condition with the *milder* selectivity is the one that survives a short reserved block, and is a
reason to prefer it that has nothing to do with which is the better filter in principle.

### 14.3 Eighteen cells are not eighteen tests

The rungs share their trades — Jaccard between channel signal sets runs 0.455 (10 vs 55) to 0.880
(30 vs 40). Applying Bailey/López de Prado's `N̂ = ρ̄ + (1−ρ̄)·M` to the arm's own signal sets:

- `+adx<=20`: mean pairwise Jaccard **0.585** → **3.07 effective rungs** of 6; 15/18 becomes 8/9,
  binomial **p = 0.0195**.
- `+ema align`: mean pairwise Jaccard **0.839** → **1.80 effective rungs** of 6; 18/18 becomes 5/5,
  binomial **p = 0.0312**.

So `ema align`'s perfect record is worth *less* than its 18/18 looks — its rungs are very nearly one
test — while `adx<=20`'s messier record is spread over more genuinely distinct trade sets. Both land
near p 0.02–0.03 after the correction, which is the honest reading: **two conditions, each about one
and a half real confirmations, neither detectable on the reserved block.**

One more caveat that outranks all of the above: **on the holdout the base loses money at every rung**
(−0.44 to −5.05 points) and both filters merely rescue it, so those "clears" are against a null that
is itself losing — `STUDY_IB_US30_OPTUNA`'s sentence again. A rule that beats a losing null is still
a rule with nothing established.

---

## 15. Decomposing the promoted condition: the fast EMA is a coin flip and removing it is free

`research/us30rate/run_r3.py`, `run_r4.py`.

§14 promoted `ema13>34>89` over `adx<=20`, so the stack is worth taking apart before anything is
built on it. Two of this branch's own findings say to check: `STUDY_V40`/`STUDY_V51` — a moving
average is priced by its **distance**, not its crossing — and `STUDY_V16`/`STUDY_V41` — the state
form of an EMA condition passes 82–91% of breakout bars and is nearly free of information. Seven
declared readings at channel 20, one fitted number (the distance median, taken on the research
block and carried unchanged), 21 cells at `E[max t | noise] = 1.90`.

**The base-rate check binds for once.** Every reading passes 44–92% of the trigger's own bars at
lifts of 1.19–2.32x. Nothing here is the trigger restated — the ninth time that check has been run
on this branch and one of the few times the whole pool survived it.

Delta over the same-rung base, all three blocks:

| reading | research | holdout | forward | positive | min p |
|---|---|---|---|---|---|
| A `ema13>34>89` | +1.838 | +2.727 | +1.499 | **3/3** | 0.052 |
| B `ema13>ema34` | +0.836 | **−1.323** | **−2.435** | 1/3 | 0.130 |
| **C `ema34>ema89`** | +1.556 | **+3.780** | +1.297 | **3/3** | **0.030** |
| D `close>ema89` | +0.818 | +0.249 | +0.563 | 3/3 | 0.070 |
| E `dist>=0` | +0.818 | +0.249 | +0.563 | 3/3 | 0.070 |
| F `dist>=median` | **+4.202** | **−6.238** | +4.248 | 2/3 | 0.003 |
| G `dist>=1.5 ATR` | +0.436 | −0.543 | −2.217 | 1/3 | 0.320 |

**The slow half is the whole condition.** `ema34>ema89` alone is 3/3 with the best p in the table
and beats the full alignment on the holdout. **The fast inequality is negative on both
out-of-sample blocks.** Confirmed on the six-rung ladder §14 declared, 18 (rung × block) cells each:

| reading | positive | p≤0.05 | median p | mean delta | holdout mean | forward mean |
|---|---|---|---|---|---|---|
| `align 13>34>89` | 18/18 | 6 | 0.092 | +2.675 | +4.315 | +2.269 |
| `slow 34>89` | 18/18 | **7** | 0.098 | **+2.708** | **+4.486** | **+2.337** |
| `fast 13>34` | **9/18** | 2 | **0.575** | **−0.324** | −0.112 | −1.397 |

`fast 13>34` on its own is a coin flip — 9 of 18, median p 0.575 against a random gate of its own
selectivity, mean delta negative, mean PF exactly 1.000.

**Read the head-to-head honestly: the slow half beats the full alignment in only 6 of 18 cells at a
mean advantage of +0.033 points a trade.** They are the same condition. So the finding is *not* that
dropping the 13-EMA makes money — it is that **dropping it costs nothing while removing a
parameter**, and that is the reason to do it. The aggregate out-of-sample means and totals tilt the
same way (holdout +4.486 vs +4.315, forward +2.337 vs +2.269, both totals higher), which is
corroboration and not a second result.

Two negatives worth keeping:

- **`E` reproduces `D` to the cent**, as it must — `close > ema89` *is* `(close−ema89)/ATR >= 0`.
  That was included as a construction check on my own readings and it passed.
- **The distance reading does not transfer on this base.** `F` is the best cell on research
  (+4.202, p 0.003) and on the forward feed (+4.248) and the **worst** on the holdout (−6.238,
  p 0.990); `G`, V51's 1.5 ATR floor frozen at the value a different market chose, is 1/3 and
  negative on the reserved feed. So `STUDY_V40`'s distance-beats-state finding **does not
  reproduce at this geometry** — `STUDY_V52`'s lesson that a filter is a property of a geometry
  rather than of a market, reached a third time.

**The rule the two sections leave standing** is Donchian 20 long, 07:00–11:00 New York, flat at the
11:00 open, 50-point stop / 150-point target, `EMA34 > EMA89`. One condition, not three, not the ADX
ceiling §13 named. Every cell of it is still inside its own MDE.
