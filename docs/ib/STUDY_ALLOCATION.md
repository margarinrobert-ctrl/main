# Allocation across the legs that already exist

`STUDY_TOP5` ended with "what would move it is MORE RESERVED BLOCKS, not more strategies", and
`STUDY_INSTITUTIONAL_FRONTIER` found that the strongest honest object on this branch is a BOOK
of the legs that already pass. Neither study ever chose portfolio WEIGHTS on research and read
them once out of sample. This one does, with equal weight as the null and a random draw from
the same simplex as the second null.

`research/alloc/` — `allocbuild.py` / `allocbuild2.py` (the leg tables at 1x and 2x cost),
`alloccore.py`, `run_a1.py` … `run_a5.py`, `plot_alloc.py`.

## 0. The construction, and what it is and is not out of sample for

Twenty-three (strategy, feed) legs are built from `research/top5/t5_adapt.py`, which is the only
thing on this branch that puts eight engines into one unit — percent of entry price at one unit
per trade, zero-filled over every date in the book's calendar.

The book's research window is every date at or before

    cut = min over legs of (the last date of that leg's own research block)  =  2021-12-17

so on every book-research date, every leg is inside its own research block. **Two consequences
must stay attached to every number here.** First, a leg whose own research block extends past
the cut had its PARAMETERS chosen using dates inside the book's reserved window, so the absolute
level of a reserved read is not a clean out-of-sample number for the legs. It is clean for the
ALLOCATION, which is the only thing this study varies: every arm including the equal-weight null
carries the identical leg contamination, so the comparison between arms is honest even though
the level is not. Second, **the cut excludes every NQ leg** — NQ begins 2022-12-26, after it —
so FTM_ORB and V56_CVD, the two strongest legs in `STUDY_TOP5`, are absent. This is a US100 +
US30 book.

Eleven legs clear 30 active research days and 10 active reserved days: APM_VWAP, IBS_SESSION,
TFI, TRENDDAY and VWAP_DRIFT on US100 and US30, plus CMMA on US100.

## 1. The correlation matrix transfers, which is not what this branch usually finds

Pairwise daily-return correlation on research against the same pair on reserved, 55 pairs:

| pairs | n | research \|rho\| | reserved \|rho\| | corr(research, reserved) | sign kept |
|---|---|---|---|---|---|
| all | 55 | 0.0618 | 0.0848 | **+0.7051 P / +0.5898 S** | 0.655 |
| SAME strategy, two indices | 5 | 0.1929 | 0.2569 | +0.5792 / +0.3000 | 1.000 |
| DIFFERENT strategies | 50 | 0.0487 | 0.0676 | **+0.5276 / +0.4881** | 0.620 |

The obvious dismissal — that the transfer is only "the same strategy on two indices is
correlated in every block" — is wrong: different-strategy pairs transfer at +0.53 Pearson on
their own. Against research-to-locked transfer correlations of −0.03 to +0.2 for profit factor,
expectancy and feature IC elsewhere on this branch, **the covariance structure is the most
transferable thing measured here.**

Read the magnitudes before getting excited. Different-strategy pairs average |rho| 0.049 on
research and 0.068 on reserved, and only 62% keep their sign. What transfers is that these legs
are all nearly uncorrelated with each other and stay that way — which is a real and useful fact,
and is also why a covariance ESTIMATE has very little left to add over a diagonal one.

The same table for the two inputs a mean-variance optimiser needs:

    corr(research sd,     reserved sd)     = +0.9317 P / +0.9636 S
    corr(research mean,   reserved mean)   = +0.9245 P / +0.7182 S   sign kept 0.818
    corr(research Sharpe, reserved Sharpe) = +0.6301 P / +0.6545 S

Volatility is the reliable one, as it is everywhere. The mean's Pearson +0.92 is carried by one
leg — IBS_SESSION/US100 sits at 0.047 where the other ten sit between −0.014 and +0.017 — so
Spearman +0.718 is the honest figure, and the eleven legs are five strategies on two feeds, so
the effective sample is nearer six than eleven.

## 2. A single fit says mean-variance wins by +0.35 Sharpe. A walk-forward says +0.08.

Five schemes fitted on research and read once after the cut:

| scheme | research Sharpe | reserved total | reserved Sharpe | reserved ret/DD | vs equal, paired p |
|---|---|---|---|---|---|
| equal | 0.903 | 14.51 | 1.463 | 6.76 | — |
| inverse vol | 0.752 | 10.38 | 1.618 | 7.60 | 0.963 |
| risk parity | 0.770 | 10.34 | 1.678 | 8.19 | 0.950 |
| minimum variance | 0.578 | 8.75 | 1.489 | 8.83 | 0.941 |
| **mean-variance** | 1.631 | **22.37** | **1.812** | **10.20** | **0.009** |

Against 2,000 uniform draws from the same simplex, mean-variance's reserved Sharpe sits at the
99.4th percentile and its total at the 93rd. Sliding the split across ten positions from 40% to
85% of the history, mean-variance beats equal weight at nine of ten.

Then re-fit the weights at every rebalance on an expanding window and stitch the out-of-sample
pieces — eight annual folds over the whole history — and the advantage collapses to **+0.083
Sharpe**, stable at 252-, 126- and 63-day rebalancing (+0.083 / +0.051 / +0.070). Risk parity,
which loses under the single fit, gets +0.068.

**The two disagree for a readable reason, and it is worth carrying.** Every sliding cut ENDS ON
THE SAME DATE, so ten "tests" share their tail; they are one test with ten start points. A
walk-forward uses each out-of-sample piece exactly once. `STUDY_DL50` used sliding cuts to ask
whether a research-minus-holdout GAP was positive everywhere, which the shared tail does not
damage; using them to ask whether a SCHEME WINS is a different question and the overlap decides
it. Prefer the walk-forward whenever both are available.

## 3. The largest number in the study is leverage

Under the walk-forward, `w` proportional to the research mean ("mean tilt", no covariance at
all) returns **58.36** against the equal-weight book's 21.88 — 2.7x the money, and it beats
equal weight in 6 of 8 folds at paired p 0.0055. Scaled to the equal-weight book's own realised
volatility it returns **19.85, LESS than equal weight**, and its Sharpe is 1.082 against 1.193.

| scheme | total | total at matched vol | Sharpe | ret/DD | pct of 500 random allocators (Sharpe) |
|---|---|---|---|---|---|
| equal | 21.88 | 21.88 | 1.193 | 6.97 | 86.8 |
| inverse vol | 14.19 | 22.12 | 1.206 | 7.03 | 89.0 |
| risk parity | 14.17 | 23.13 | 1.261 | 7.43 | 93.4 |
| minimum variance | 11.36 | 19.27 | 1.050 | 7.03 | 70.2 |
| mean-variance | 27.69 | 23.40 | 1.275 | 10.33 | 93.8 |
| mean tilt | **58.36** | **19.85** | 1.082 | 9.22 | 74.6 |
| inv-vol × mean tilt | 43.20 | 23.22 | 1.266 | 10.34 | 93.4 |

At matched volatility all seven schemes fall into a band of 19.3 to 23.4 around equal weight's
21.9. **§9's "sizing creates no edge" applies to allocation exactly as it applies to a single
strategy, and a total-return column is the wrong place to read an allocation result.** Report
every allocation arm at matched volatility or the concentrated arm wins by construction.

**And no scheme clears the 95th percentile of 500 random allocators run through the identical
procedure** — the best is mean-variance at 93.8, i.e. p 0.062. Per fold, inverse vol, risk
parity and minimum variance beat equal weight in **2 of 8 folds each**; their whole Sharpe
advantage is lower volatility, not better selection.

## 4. Choosing the LEGS is worth more than choosing the weights, and it clears its null

Rank the legs by their Sharpe **inside every training window** and hold the top k, equal
weighted, walking forward:

| held | total | Sharpe | ret/DD | total at matched vol |
|---|---|---|---|---|
| all 11 | 21.88 | 1.193 | 6.97 | 21.88 |
| top 2 | 35.70 | 0.714 | 4.87 | 13.10 |
| top 3 | 54.15 | 1.381 | 12.84 | 25.33 |
| **top 4** | 46.87 | **1.438** | 10.52 | **26.38** |
| top 5 | 41.56 | 1.351 | 12.31 | 24.79 |
| top 8 | 29.40 | 1.298 | 8.19 | 23.81 |
| top 11 | 21.88 | 1.193 | 6.97 | 21.88 |

The shape is a hump peaking at four legs and decaying monotonically to eleven — the fifth
independent confirmation of `STUDY_SEMIVARIANCE`'s finding that **a decorrelated leg still has
to have an edge**. Drop-one on the equal-weight book agrees: removing VWAP_DRIFT/US30 is worth
+0.086 Sharpe, IBS_SESSION/US30 +0.056 and TFI/US30 +0.044 (all three lose money standalone),
while removing IBS_SESSION/US100 costs −0.274.

**Against a RANDOM SUBSET OF THE SAME SIZE, 400 draws, re-drawn inside every fold:**

    top 3   Sharpe +1.381 at percentile 99.5   (random median +0.690)
    top 5   Sharpe +1.351 at percentile 99.2   (random median +0.921)
    top 8   Sharpe +1.298 at percentile 94.2   (random median +1.078)

That is the one result in this study that clears its own null decisively, and it is the right
null — it holds the number of legs fixed, so the finding is not "concentration helps".

Crossed with the weighting schemes, selection and weighting stack: `top 5 × risk parity` reads
Sharpe **1.581** and ret/DD **14.90** against all-legs equal weight's 1.193 / 6.97, and
`top 4 × risk parity` 1.535 / 12.38. Risk parity is near-useless on eleven legs (+0.068 Sharpe)
and strong on the top five (+0.230 over top-5 equal) — once the losing legs are gone, minimising
variance stops minimising the good legs away.

## 5. And it does not clear zero

Paired block bootstrap of the daily difference against the all-legs equal-weight book, **at
matched volatility so the difference cannot be leverage**:

| arm | vol-matched mean daily excess | P(<=0) |
|---|---|---|
| top 5 × risk parity | +0.003572 | **0.058** |
| top 4 × equal | +0.002257 | 0.127 |
| top 5 × equal | +0.001459 | 0.200 |
| all 11 × risk parity | +0.000626 | 0.365 |

None clears p <= 0.05. This is `STUDY_V15_BOOK`'s split reproduced on an allocation rather than
a strategy: **clearing a matched control and clearing zero are different questions**, and eight
annual folds can answer the first and not the second. Per fold at matched volatility, all three
selected arms beat equal weight in **5 of 8 folds** where chance is 4 — and the gain is
concentrated in two folds (2020-10..2021-09 and 2022-09..2023-09). The most recent fold
(2025-08..2026-08) is negative for every arm including equal weight.

## 6. The selection is stable, and mostly it is picking the same five legs

Top-5 holds TFI/US100, IBS_SESSION/US100 and APM_VWAP/US100 in **8 of 8** folds,
IBS_SESSION/US30 in 7 and TRENDDAY/US100 in 6. Freezing that set and never re-choosing gives
Sharpe 1.270 and ret/DD 9.12 against re-selection's 1.351 and 12.31 — so **re-selection is worth
about +0.08 Sharpe over simply holding the five legs it usually picks, and holding those five is
worth +0.077 over holding all eleven.** The fixed arm was constructed by reading what the
walk-forward held, so it is contaminated in its own favour and still loses, which makes the
small re-selection win more credible rather than less. It is also the first time on this branch
that a re-selection procedure has beaten a fixed set at all — the fourteenth such comparison,
after thirteen losses.

## 7. Costs

Rebuilt with **2x every feed's assumed cost** and run through the identical procedure:

| arm | Sharpe 1x | Sharpe 2x | ret/DD 1x | ret/DD 2x |
|---|---|---|---|---|
| all 11 × equal | 1.193 | 0.841 | 6.97 | 4.81 |
| all 11 × risk parity | 1.261 | 0.875 | 7.43 | 4.32 |
| top 4 × equal | 1.438 | **1.229** | 10.52 | 8.73 |
| top 5 × risk parity | 1.581 | 1.236 | 14.90 | 8.35 |

Nothing flips sign. The selected books degrade LESS than the all-legs book (top 4 keeps 85% of
its Sharpe against all-legs' 70%) because the legs selection drops — VWAP_DRIFT above all — are
the high-turnover, cost-sensitive ones. Cost is not the binding objection to a book, which is
unusual on this branch and is the `STUDY_TOP5` finding again: these legs hold wider barriers
longer, so a fixed round turn is a smaller fraction of the trade.

## 8. The case for a book at all

Walk-forward, same procedure, every leg run alone:

| | Sharpe | ret/DD |
|---|---|---|
| best single leg (IBS_SESSION/US100) | 0.940 | 8.47 |
| all-11 equal-weight book | 1.193 | 6.97 |
| top-4 equal-weight book | 1.438 | 10.52 |
| top-5 × risk parity | 1.581 | 14.90 |

**The equal-weight book beats every one of its eleven legs on Sharpe** and ten of eleven on
return-over-drawdown. That is the largest effect in the study and it needed no fitting at all.
Everything after it — weighting +0.07, selection +0.16, the two together +0.39 — is smaller than
the step from one leg to eleven.

## 9. The two Monte Carlos: it clears zero, and the best-looking path was the luckiest

Bootstrap WITH REPLACEMENT for the edge, PERMUTE for the path. Day-block bootstrap, 4,000 draws:

| arm | n | total | Sharpe | mean/day | 95% CI | P(mean <= 0) |
|---|---|---|---|---|---|---|
| walk-fwd all 11, equal | 1996 | 21.88 | 1.193 | 0.0110 | [0.0049, 0.0173] | **0.0005** |
| walk-fwd all 11, risk parity | 1996 | 14.17 | 1.261 | 0.0071 | [0.0032, 0.0110] | 0.0008 |
| walk-fwd all 11, mean-variance | 1996 | 27.69 | 1.275 | 0.0139 | [0.0071, 0.0213] | 0.0000 |
| walk-fwd top 4, equal | 1996 | 46.87 | 1.438 | 0.0235 | [0.0129, 0.0346] | 0.0000 |
| walk-fwd top 5, risk parity | 1996 | 31.40 | 1.581 | 0.0157 | [0.0087, 0.0230] | 0.0000 |
| single-fit reserved, equal | 1178 | 14.51 | 1.463 | 0.0123 | [0.0044, 0.0205] | 0.0012 |
| single-fit reserved, mean-variance | 1178 | 22.37 | 1.812 | 0.0190 | [0.0094, 0.0294] | 0.0000 |

**Every arm's 95% CI excludes zero.** That is `STUDY_V15_BOOK`'s split running the OTHER WAY from
§5: the book clears ZERO comfortably and no arm clears its own matched null. Both are true and
neither is the other. What is being bought by allocating is not "a profitable book" — eight legs at
equal weight already gives that — it is a claim about *which* weights, and that claim is the one
that does not separate.

Permutation of each arm's own daily series, 4,000 reshuffles:

| arm | realised DD | MC median | MC p95 | **MC p99** | percentile of realised | p99 / realised |
|---|---|---|---|---|---|---|
| walk-fwd all 11, equal | 3.14 | 3.18 | 4.92 | 5.99 | 0.480 | 1.91 |
| walk-fwd all 11, risk parity | 1.91 | 1.88 | 2.91 | 3.40 | 0.527 | 1.78 |
| walk-fwd all 11, mean-variance | 2.68 | 3.62 | 5.60 | 6.76 | **0.088** | 2.52 |
| walk-fwd top 4, equal | 4.46 | 4.88 | 7.63 | 9.13 | 0.340 | 2.05 |
| walk-fwd top 5, risk parity | 2.11 | 2.83 | 4.41 | 5.36 | **0.078** | 2.54 |
| single-fit reserved, equal | 2.15 | 2.13 | 3.34 | 4.02 | 0.512 | 1.87 |
| single-fit reserved, mean-variance | 2.19 | 2.31 | 3.58 | 4.28 | 0.413 | 1.95 |

**The two arms with the best return-over-drawdown are the two whose realised path was luckiest.**
Mean-variance sits at the 8.8th percentile of reshuffles of its own trades and top-5 × risk parity
at the 7.8th, against 48-53% for the two un-selected equal-weight arms — so their drawdown
advantage is substantially a draw, not a property. Re-read return-over-drawdown at the p99
drawdown instead of the realised one and the ranking survives but the gap collapses:

    top 5 x risk parity   14.90 realised  ->  5.86 at p99
    top 4 x equal         10.52           ->  5.14
    all 11, mean-variance 10.33           ->  4.10
    all 11, equal          6.97           ->  3.65

2.14x becomes 1.61x. **Size for the p99 and the case for selection is weaker than §4 makes it
look** — which is the same correction the permutation has forced on every other candidate here.

The practical numbers for the shipped-shape book (walk-forward top 5 × risk parity): **82.8% of
days underwater, longest underwater run 339 days**, max drawdown 2.11 against an MC p99 of 5.36.

## 10. Profit factor, and the unit trap in asking for it

**A book has no trade-level profit factor.** Eleven legs net against each other inside a day, so
the only PF a portfolio has is over its DAILY series, and that number is not comparable to the
trade-level PF every other study here quotes. Both are below.

Day-level, walk-forward:

| arm | day PF | day win rate | mean up day | mean down day | payoff |
|---|---|---|---|---|---|
| all 11, equal | 1.325 | 47.9% | +0.104 | -0.072 | 1.44 |
| all 11, inverse vol | 1.308 | 47.6% | +0.071 | -0.049 | 1.44 |
| all 11, risk parity | 1.332 | 47.5% | +0.067 | -0.045 | 1.47 |
| all 11, minimum variance | 1.328 | 48.1% | +0.053 | -0.037 | 1.43 |
| all 11, mean-variance | 1.395 | 52.5% | +0.121 | -0.096 | 1.26 |
| top 3, equal | 1.519 | 57.0% | +0.362 | -0.316 | 1.14 |
| **top 4, equal** | **1.528** | 57.3% | +0.275 | -0.242 | 1.14 |
| top 5, equal | 1.481 | 55.6% | +0.230 | -0.195 | 1.18 |
| top 5 × risk parity | 1.497 | 54.7% | +0.173 | -0.140 | 1.24 |
| single-fit reserved, equal | 1.416 | 49.1% | +0.103 | -0.070 | 1.47 |
| single-fit reserved, mean-variance | 1.589 | 51.4% | +0.120 | -0.080 | 1.50 |
| single-fit RESEARCH, equal | 1.235 | 46.3% | +0.088 | -0.061 | 1.43 |

**SELECTION CHANGES HOW THE BOOK EARNS, NOT ONLY HOW MUCH.** Equal weight over eleven legs makes
money on a MINORITY of days — 47.9% — carried by a 1.44 payoff. Dropping to the top four takes the
day win rate to 57.3% and the payoff DOWN to 1.14. Same family, opposite shape: the losing legs
were contributing small frequent losses against the good legs' larger wins, and removing them
converts a payoff book into a hit-rate book. Weighting does not do this — every weighting scheme on
all eleven legs sits at 47.5-48.1% and 1.43-1.47, i.e. it rescales the same shape.

**AND PF GIVES A SHARPER VERDICT ON SELECTION THAN SHARPE DID.** Against the same two nulls:

    500 random allocators, same procedure:   p5 1.187  median 1.278  p95 1.411
        all 11, equal          1.325  at percentile  73.0
        all 11, risk parity    1.332  at percentile  75.8
        all 11, mean-variance  1.395  at percentile  92.6
        top 4, equal           1.528  at percentile 100.0
        top 5 x risk parity    1.497  at percentile  99.6

    400 random SUBSETS of the same size, re-drawn each fold:
        top 3   PF 1.519  at percentile  98.0   (random median 1.224)
        top 4   PF 1.528  at percentile  99.8   (random median 1.235)
        top 5   PF 1.481  at percentile 100.0   (random median 1.268)

On Sharpe no weighting scheme reached the 95th percentile (§3) and selection reached 99.5 (§4); on
PF weighting still tops out at 92.6 and selection reaches **100.0 against both nulls**. The two
statistics agree on the ranking and PF separates it more cleanly, because it is not penalised by
the volatility that concentration adds.

**THE SHAPE IS WRONG AT BOOK LEVEL, AND IT IS THE LEGS' OWN SHAPE.** Equal weight reads day PF
**1.235 on research against 1.416 on the reserved block**, and the legs do the same thing: median
leg trade-PF **1.089 research -> 1.255 reserved**, with TRENDDAY/US100 going 1.119 -> 2.556 and
APM_VWAP/US30 0.858 -> 1.182. Nine of eleven legs improve out of sample. That is the wrong shape by
this branch's own standard, it is inherited rather than created by the allocation, and it is the
same regime statement the per-fold table makes — the gain is concentrated in 2020-2021 and
2022-2023, and the most recent fold is negative for every arm.

Leg trade-level PF, for contrast (**not** comparable to the day-level table above):

| leg | research n | research PF | reserved n | reserved PF |
|---|---|---|---|---|
| APM_VWAP/US100 | 174 | 1.624 | 134 | 1.576 |
| IBS_SESSION/US100 | 166 | 1.580 | 153 | 1.543 |
| TFI/US100 | 357 | 1.253 | 256 | 1.485 |
| TRENDDAY/US100 | 62 | 1.119 | 63 | 2.556 |
| IBS_SESSION/US30 | 173 | 1.197 | 125 | 1.255 |
| TRENDDAY/US30 | 62 | 1.089 | 44 | 1.264 |
| CMMA/US100 | 1285 | 1.012 | 977 | 1.171 |
| VWAP_DRIFT/US100 | 1170 | 1.017 | 984 | 1.003 |
| TFI/US30 | 330 | 0.993 | 247 | 0.999 |
| VWAP_DRIFT/US30 | 966 | 0.859 | 776 | 1.053 |
| APM_VWAP/US30 | 148 | 0.858 | 119 | 1.182 |

The three legs below PF 1.0 on research — APM_VWAP/US30, VWAP_DRIFT/US30, TFI/US30 — are exactly
the three the drop-one in §4 says to remove, and all three are US30. The selection is not finding
a subtle interaction; it is declining to trade the legs that lose.

## Verdict

Build the book; be careful what you claim for the allocation on top of it.

- **Diversification is real and free.** Eleven legs at equal weight beat the best of them by
  +0.25 Sharpe, with pairwise correlations averaging 0.05-0.08 that transfer at +0.53 across
  different strategies. Nothing is fitted.
- **Dropping the losing legs is worth about +0.16 Sharpe and clears a random-subset null at the
  99th percentile.** It is the one thing here that beats its own null. It is also nearly
  equivalent to just never trading the three legs that lose money standalone.
- **Weighting is worth about +0.07 Sharpe and clears nothing.** Risk parity is the best of the
  five and reaches the 93rd percentile of random allocators, not the 95th.
- **The combined best arm does not separate from zero** (P(mean excess <= 0) 0.058 at matched
  volatility, 5 of 8 folds) and its most recent fold is negative.
- **Every total-return figure in an allocation study is a leverage figure until it is scaled to
  a common volatility**, and the largest raw number here inverts when it is.
- **The book clears zero and no arm clears its own null.** Every day-block bootstrap CI excludes
  zero (P(mean <= 0) 0.0000-0.0012) while the paired test against equal weight reads 0.058 at best
  — diversification is the part that is established; allocation on top of it is not.
- **On profit factor the selection verdict is cleaner than on Sharpe**: day PF 1.528 for the top
  four against equal weight's 1.325, at the 100.0th percentile of both nulls, where no weighting
  scheme passes 92.6.
- **The two best-looking arms had the luckiest paths** (realised drawdown at the 8th percentile of
  their own reshuffles against 48-53% for the un-selected arms); at MC p99 drawdown their
  return-over-drawdown advantage falls from 2.14x to 1.61x.

What would move it: NQ legs, which this construction cannot use because NQ begins after the
common cut — and more folds. Eight annual folds is what stops the strongest arm reaching p 0.05,
and the fix is calendar time, not another scheme.
