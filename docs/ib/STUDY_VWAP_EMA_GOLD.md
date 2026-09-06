# VWAP-EMA regime-filtered intraday strategy on XAU/USD

**Verdict — the paper reports no backtest, and measured on gold the rule loses on the block that
would choose it, beats only a control that loses more, and its one informative component inverts.**
Long: research **−0.0447 R/trade, PF 0.916** on 378 trades; locked **+0.1423, PF 1.318** on 214 —
it *grows* out of sample, the wrong shape, for the thirteenth time on this branch. Short is
negative on both blocks. A random New York entry running the identical stop, target, trail, costs
and position lock earns **−0.2573 R** on research, so the rule clears its matched control at
p 0.0025 while losing money: a rule that beats a losing null is still a losing rule.

Ships `pine/vwapema/VWAP_EMA_GOLD_strategy.pine` with the rules exactly as specified, every number
below in its header, and no edge claimed. `research/vwapema/`.

---

## 1. The uploaded file cannot run this spec, and that is the first result

`XAUUSD15.csv` (= registry `XAUUSD15_MT`, sha256 `fdd173af1c92a768`, 100,000 rows 2022-06 → 2026-08)
**has no volume column.** Its sixth field reads exactly **15 on 99.62% of rows**, the remainder are
smaller integers, its standard deviation is 0.185, and its correlation with the bar's own range is
**+0.0048** — where a real tick-volume series scores **+0.641**. It is the bar's length in minutes.

Two consequences are arithmetic, not opinion:

| what the spec needs | what the file gives |
| --- | --- |
| C5: `Volume > 1.1 × SMA20(Volume)` | fires on **33 of 100,000 bars = 0.033%** — the rule takes no trades |
| VWAP `= Σ(P·V)/Σ(V)` | with V constant this **is** the unweighted mean of the typical price |

The test was run on `XAU_ISO_15m` instead — 494,235 bars, 2004-06 → 2026-01, real broker tick
volume (mean 988, corr with bar range +0.641, C5 firing 39.7%), truncated to 2010 onward because
pre-2010 gold carries 10% zero-range bars. That is 371,586 bars and sixteen years against the
paper's one. **Always check `corr(volume, high−low)` before running a volume rule anywhere**; near
zero means the column is not volume.

The volume is still a **proxy** and the spec's own gap 3 says so: XAU/USD is OTC, so V is one
broker's tick count. Every VWAP and C5 number here inherits that.

## 2. What the paper actually claims

The spec document is right and it is worth restating: **section 6.1 of the paper states the
outcome distribution was assumed** — full win 0.30, partial 0.20, breakeven 0.08, loss 0.42 — and
Monte Carlo sampled. So 45.3% win rate, +0.414R expectancy, PF 1.76, Sharpe 3.99 and +102.2%
return are arithmetic from that assumption. There is nothing to reproduce. This is the first
measurement of the rules against gold bars.

Measured, research block, both sides:

| outcome | paper assumed | LONG measured | SHORT measured |
| --- | ---: | ---: | ---: |
| 3R target hit | 30% | **12.4%** (+2.940 R) | **12.4%** (+2.893 R) |
| trail / partial | 28% | **61.1%** (−0.190 R) | 59.0% (−0.299 R) |
| initial stop | 42% | 26.5% (−1.112 R) | 28.6% (−1.130 R) |

The target rate is measured at 12.4% on **both sides independently** against an assumed 30%, and
the dominant exit is the trail — which the paper's four-outcome table treats as a breakeven and
which is in fact a consistent small loser.

## 3. Blocks, costs, and the arithmetic the spec got wrong

Research = the first 65% of New York sessions, to **2020-05-25**; locked = the rest, read once.
Costs are gold's floor from `research/xau/xau_core.py`: 0.30 USD/oz round turn + 0.05 a side.

| quantity | spec assumes | measured |
| --- | ---: | ---: |
| 15-minute ATR | $12 (its 5.1), or $20 implied by its cost table | **$2.35** |
| cost as a fraction of risk | 0.24 R | **0.1032 R** (10.3% of a median $3.87 risk) |

The spec's own gap 6 flagged this and it is worse than flagged: its ATR is **5–8× too large**, so
its cost assumption is **2.3× the real one**. That cuts both ways. At the real cost the long side
is **positive gross (+0.0762 R, PF 1.169) and negative net (−0.0447)** — the round turn is the
whole difference. At the spec's own 0.24R it would read −0.1974.

At a 3R target the driftless break-even win rate is **27.58%**; the long side measures **26.7%**.

## 4. Which of the six conditions does anything

Pass rate among bars that already satisfy the other five, research block, long:

| condition | alone | given the other five |
| --- | ---: | ---: |
| C1 regime, `close > EMA200` | 51.8% | 72.3% |
| **C2 VWAP side, `close > VWAP`** | 50.6% | **87.8%** |
| C3 pullback to the EMA50 | 11.9% | **29.9%** |
| C4 pin bar or engulfing | 26.0% | 39.2% |
| C5 volume | 25.2% | 61.3% |
| **C6 range ≥ 0.8 ATR** | 49.8% | **92.7%** |

**The VWAP condition — the paper's headline — removes about an eighth of the signals**, and the
range floor removes a fourteenth. The binding condition is C3, the EMA50 pullback. Seventh time on
this branch a proposed confirmation has turned out to be nearly implied by the trigger it confirms.
Within C4, **engulfing supplies 84% of signals and the pin bar 22%** (6.5% both), so the pin-bar
half is close to decorative.

Drop-one on the short side improves the rule by removing C3 (+0.036), C4 (+0.056) or C6 (+0.039) —
three of the six subtract there.

## 5. The matched control, run as a gate

Same side, same 0.5×ATR initial stop, same 3R target, same close-only EMA trail, same costs and
one-position lock; only the entry bar is random, drawn from the New York population at the rule's
own rate and re-simulated end to end.

| side | block | n | R/trade | PF | random entry | p |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| LONG | research | 378 | −0.0447 | 0.916 | −0.2573 | **0.0025** |
| LONG | locked | 214 | +0.1423 | 1.318 | −0.1280 | **0.0025** |
| SHORT | research | 283 | −0.1421 | 0.751 | −0.2900 | 0.0325 |
| SHORT | locked | 168 | −0.2147 | 0.614 | −0.2072 | 0.5225 |

The entry does carry information — it beats a coin flip on three of four cells. **The exit machine
loses money on any entry, and the rule loses less.** `STUDY_IB_US30_OPTUNA` reached the same
sentence from the other direction one study ago.

## 6. The exit architecture is the problem

| arm | n | R | PF | share exiting on the trail |
| --- | ---: | ---: | ---: | ---: |
| as specified | 378 | −0.045 | 0.916 | 61.1% |
| no EMA20 tightening | 378 | **−0.045** | **0.916** | 61.1% |
| no 3R target | 375 | −0.050 | 0.905 | 73.6% |
| no target and no tightening | 375 | −0.011 | 0.979 | 73.6% |
| wider initial stop (1.5 ATR) | 372 | −0.010 | 0.972 | 86.8% |
| **wider stop, no target** | 371 | **+0.004** | **1.013** | 92.5% |
| flatten at the session close | 380 | −0.101 | 0.801 | 40.3% |

**Section 7.4 of the spec is dead code.** Turning the EMA20 final-leg tightening off reproduces the
result *to the cent*, because floating profit almost never reaches 2.5R before the trail fires; the
`ema_tight` ladder confirms it (20 and 34 identical, 10 differs by 0.0006).

The stop axis is **monotone toward wider** (0.25N −0.0826 → 1.5N −0.0095) — the eighth family on
this branch to do that — and no target ties for best, the twentieth time. The session flatten is
destructive, the fifteenth confirmation.

**The volume weighting does nothing.** Swapping the volume-weighted anchor for the unweighted
session mean of the same typical price gives −0.0436 against −0.0447. That is `STUDY_V63`'s
finding (+0.0096 Sharpe over 69,003 matched pairs) reproduced on a third market.

## 7. The parameter neighbourhood, and a bug of mine

The corrected ladder (see below) puts **the spec's own value at rank 2 to 4 on every one of eight
axes** — never best, never worst. Four of forty cells are positive on research.

| axis | spec | its rank | best rung |
| --- | ---: | ---: | --- |
| EMA regime | 200 | 3 of 5 | 100 (+0.0027) |
| EMA pullback | 50 | 3 of 5 | 70 (−0.0152) |
| EMA tighten | 20 | 2 of 3 | 10 (−0.0441) |
| ATR length | 14 | 2 of 3 | 7 (−0.0422) |
| initial stop | 0.5 | 4 of 5 | 1.5 (−0.0095) |
| volume multiple | 1.1 | 4 of 5 | 2.0 (+0.3745) |
| range floor | 0.8 | 2 of 4 | 1.3 (−0.0099) |
| wick/body | 2.0 | 3 of 4 | 1.5 (−0.0290) |

That is the shape of parameters chosen by convention rather than fitted to gold, which is to the
spec's credit — and they are not good ones.

**MY OWN BUG, caught by the plateau being too perfect.** The first neighbourhood run swept the EMA
and ATR periods against series cached in `build()`, so five rungs returned *identical numbers to
four decimals*. CLAUDE.md already records that signature: a suspiciously flat block is a bug, not a
plateau. `vecore.periods()` recomputes any period-dependent series a ladder moves. The locked read
used the spec's own values throughout and is unaffected.

## 8. The one component that carried information — and it inverts

Raising C5 from 1.0× to 2.0× is monotone on research and **beats a random filter that keeps the
same number of the same signal bars at every rung** — so it is not the restrictiveness artifact
`STUDY_V12` warns about:

| C5 multiple | research R | random filter | p | locked R (descriptive) | random filter | p |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1.0 | −0.0678 | −0.1327 | 0.030 | +0.1534 | +0.1271 | 0.243 |
| 1.1 (spec) | −0.0447 | −0.1315 | 0.005 | +0.1423 | +0.1339 | 0.420 |
| 1.3 | +0.0143 | −0.1350 | 0.003 | +0.1030 | +0.1412 | 0.690 |
| 1.5 | +0.1439 | −0.1479 | 0.000 | +0.1053 | +0.1428 | 0.643 |
| 2.0 | +0.3745 | −0.1587 | 0.000 | +0.0982 | +0.1468 | 0.623 |

**Spearman(multiple, R) is +1.000 on research and −0.900 on locked**, and every locked rung fails
its own control. The locked column is a *second* look at that block — the pre-declared read was the
rule as specified — so it is descriptive and labelled so. It is reported because a component that
holds would be worth more than the rule, and this one does not hold.

## 9. By year, and the paper's own sample

Nine of sixteen full years are positive on the long side. 2015 is −0.622 R; 2016 +0.308.

**2024 — the calendar year the paper names — is the second-best year in sixteen**: +0.2440 R,
PF 1.55, win 41.3% on 46 trades, against the paper's claimed +0.414 R, PF 1.76, 45.3%. So even the
year the paper points at reads about 60% of its assumed expectancy, and it sits inside the locked
block, chosen by nothing.

## 10. Parity

`ve_parity.py` runs the shipped script's order model — tick-rounded fill-relative bracket placed
with the entry, exit-bar marker updated before the entry test. Against the engine: **trade counts
0.998 and 1.000, R correlation 0.978 and 0.970, same exit bar 96.6%**, gap +7.8% research / +3.0%
locked on the long side.

One difference is structural: the research exits **at** the close that breaches the EMA, and
`strategy.close()` fills at the **next bar's open**. Since 61% of trades die there this looked like
it should matter, and it does not — it moves the exit bar on **63% of trades** and the result by
about **1% of R** (−0.0413 → −0.0407), because the trail fires on a close that has already
breached. Worth knowing before trusting or distrusting a close-only trail on a Strategy Tester report.

## 11. What would move it

Not a parameter. The entry carries a little information and the exit architecture spends more than
it, so the honest change is a different exit — and the grid already says which direction: wider
stop, no target, no session flatten, which is a swing system and not the intraday framework the
paper describes. The volume filter is the only component worth revisiting and it would need a
market that did not choose it.

---

# Part 2 — the paper itself, 3,600 Optuna trials, IS/OOS, Monte Carlo and correlation matrices

**Verdict — no configuration of this strategy is a proven edge on gold.** Three Optuna finalists
plus the published rule were read once on the locked block. All four beat a matched random entry
(p 0.000–0.033) and **not one separates from zero**: the day-block bootstrap gives P(mean ≤ 0) of
**0.054, 0.075, 0.096 and 0.176**. The deflated Sharpe is **0.000** for all four at 3,660 counted
trials. fANOVA puts **0.85–0.90 of every objective on the volume multiple** — the one component
already shown to invert across the split. And **94% of the best finalist's locked result comes from
2025–26**, a stretch in which gold rose about 60%.

## 12. The PDF confirms the restatement, and one reading was ambiguous

Read directly, the paper's §3.2–§4.4 match the spec document condition for condition, and §6.1 is
explicit in its own words: *"The backtest **simulates** 247 trades… Trade outcome distributions are
**parameterised** from the strategy's structural logic: … **modelled** to produce full wins (3R)
with probability 0.30, partial wins with probability 0.20, breakevens 0.08, and full losses 0.42."*
Nothing was fitted to gold.

One ambiguity is the paper's own. §3.1 says the VWAP is *"anchored to the New York session open
(13:30 UTC)"* and reset at *"session close (20:00 UTC)"*. **Those are not the same thing** — 13:30
UTC is 09:30 New York only under daylight saving and 08:30 New York in winter. Both readings are
now implemented and searched:

| session reading | research | locked |
| --- | ---: | ---: |
| New York wall clock 09:30–16:00 | 378 trades, −0.0447 R, PF 0.916 | 214, +0.1423, PF 1.318 |
| literal fixed 13:30–20:00 UTC | 448 trades, −0.0229 R, PF 0.957 | 257, +0.1664, PF 1.360 |

The literal UTC reading is the slightly better one, so Part 1 used the *less* flattering of the two.

## 13. The search: 3,600 trials over all fourteen axes, research only

Every free number the paper leaves unjustified, plus the target, side, session reading and session
flatten. Three TPE studies of 1,200 (total R, profit factor, return-over-drawdown), a floor of 120
research trades, and every trial's locked result logged and never used to select.

**Population:** 2,257 scorable, **62% profitable on research**. corr(research, locked) = **+0.43**
Pearson — high for this branch, and `STUDY_V64_OPTUNA` explains why: TPE concentrates in its own
good region, so the correlation is measured over a restricted range. Top 1% by research: +49.9 →
locked +19.7, against the population's locked mean +6.2.

**The marginals say what the objective actually is:**

| axis | direction | Spearman with research R |
| --- | --- | ---: |
| **volume multiple** | monotone up: 0.8–1.17 → −0.029, 1.62–2.05 → **+0.065** | **+0.379** |
| **target R** | monotone up: ≤2.6 → −0.052, 5.9–8.0 → **+0.054** | **+0.369** |
| ATR length | mild | +0.117 |
| everything else | flat | ≤ 0.09 |
| session flatten | **on 33.7% positive, off 65.3%** | destructive |

**fANOVA: `vol_mult` carries 0.850 / 0.896 / 0.878 of the three objectives.** Everything else is
under 0.08. The optimiser is tuning the volume filter and nothing else — and Part 1 §8 already
established that the volume filter's research gradient (Spearman **+1.000**) becomes **−0.900** on
the locked block. `vol_mult` also correlates **−0.618 with the trade count**, so much of what it
buys is selectivity.

The three finalists are all long-only, all no-flatten:

| study | configuration | research |
| --- | --- | --- |
| total R | NY session, EMA 150/82/55, ATR 26, stop 0.40, vol 0.88, range 0.97, wick 3.69, 7.01R target | 296 trades, +0.1948 R, PF 1.343 |
| PF | UTC session, EMA 370/50/45, ATR 25, **stop 2.47 (box edge)**, vol 1.72, 4.65R target | 135, +0.2035, PF 1.879 |
| ret/DD | UTC session, EMA 200/52/30, ATR 27, stop 0.92, vol 1.63, 2.35R target | 175, +0.2489, PF 1.669, ret/DD 10.06 |

## 14. The one locked read

Multiplicity first: 3,600 Optuna trials + 60 research looks from Part 1 = **3,660**.

| finalist | block | n | R/trade | PF | ret/DD | random entry | p vs control | **bootstrap P(mean ≤ 0)** |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| as published | research | 378 | −0.0447 | 0.916 | −0.72 | −0.2480 | 0.003 | 1.000 |
| as published | **locked** | 214 | +0.1423 | 1.318 | 1.70 | −0.1482 | 0.000 | **0.054** |
| total R | research | 296 | +0.1948 | 1.343 | 3.05 | | | |
| total R | **locked** | 160 | +0.2000 | — | — | | | **0.096** |
| PF | research | 135 | +0.2035 | 1.879 | 6.83 | −0.0613 | 0.005 | 0.008 |
| PF | **locked** | 79 | +0.1819 | 1.670 | 2.15 | −0.0146 | 0.013 | **0.075** |
| ret/DD | research | 175 | +0.2489 | 1.669 | 10.06 | −0.1672 | 0.000 | 0.004 |
| ret/DD | **locked** | 95 | +0.1097 | 1.252 | **0.85** | −0.0880 | 0.033 | **0.176** |

Two of the four decay (the right shape); the total-R finalist and the published rule grow. **Every
one clears its matched control and none clears zero** — `STUDY_V15_BOOK`'s split, reproduced
exactly: a control asks "is this better than a random entry with the same geometry", a bootstrap
asks "is this better than nothing", and here the answer is yes to the first and no to the second,
because the random entry loses money.

The ret/DD finalist's headline metric collapses **10.06 → 0.85** out of sample.

## 15. Monte Carlo

Day-block bootstrap for the edge (resample days with their trades attached), permutation for the
path (reorder the realised sequence — it cannot move the endpoint, only the drawdown).

| finalist | n | mean R | 95% CI | P(mean≤0) | realised DD | MC median DD | **MC p99 DD** | DD percentile |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| total R | 160 | +0.2000 | [−0.107, +0.539] | 0.096 | 17.8 R | 15.0 | **29.7** | 0.72 |
| PF | 79 | +0.1819 | [−0.054, +0.455] | 0.075 | 6.7 | 4.9 | **9.4** | 0.85 |
| ret/DD | 95 | +0.1097 | [−0.127, +0.356] | 0.176 | 12.2 | 8.6 | **16.5** | 0.89 |
| as published | 214 | +0.1423 | [−0.031, +0.328] | 0.054 | 17.9 | 12.2 | **23.0** | 0.93 |

**Every confidence interval contains zero.** The drawdown percentiles run 0.72–0.93, so the
realised paths were on the *unlucky* side of their own reshuffles — but the p99 is still **1.4–1.7×
the realised drawdown**, and that is the sizing number.

Parameter perturbation at ±10% leaves all four positive in 100% of draws — but the total-R
finalist is beaten by **only 6.7% of its own neighbours**, which is the signature of a cell picked
off a spike. The PF finalist sits below its neighbourhood (63.3% beat it), which is the healthy
shape.

## 16. Correlation matrices

**(a) Parameter → performance**, Spearman over 2,257 scorable trials: `vol_mult` **+0.379** and
`tgt_R` **+0.369**; every other axis is under +0.12 and `range_mult` is negative. Two axes carry
the whole search, and one of them inverts out of sample.

**(b) Finalists' daily R on the locked block** (267 overlapping days):

| | total R | PF | ret/DD | published |
| --- | ---: | ---: | ---: | ---: |
| total R | 1.000 | 0.391 | 0.282 | 0.461 |
| PF | 0.391 | 1.000 | **0.678** | 0.330 |
| ret/DD | 0.282 | 0.678 | 1.000 | 0.467 |
| published | 0.461 | 0.330 | 0.467 | 1.000 |

**(c) Year-to-year R across the sixteen years** puts total-R against the published rule at
**+0.965** and PF against ret/DD at **+0.936**. Three "different" optimised configurations are two
strategies, and one of them is the published rule with a different volume threshold.

## 17. Where the locked result comes from

| finalist | locked total R | **share from 2025–26** | R/trade **before** 2025 | n before 2025 | top 5% of trades |
| --- | ---: | ---: | ---: | ---: | ---: |
| total R | +32.0 | **94.4%** | **+0.015** | 123 | 174% of net |
| PF | +14.4 | 43.4% | +0.110 | 74 | 96% |
| ret/DD | +10.4 | 69.6% | +0.036 | 89 | 89% |
| as published | +30.5 | 23.8% | +0.130 | 178 | 97% |

Gold rose roughly 60% in 2025. **The optimiser's best cell is 94% that rally** and earns +0.015 R
a trade without it. This is the spec's own checklist item 8 — "a long-only-biased system in a gold
bull run is a beta bet" — and the search made it worse, not better: the published rule is the
*least* concentrated of the four.

## 18. Walk-forward, with the selection re-run inside each fold

Expanding folds, twelve out-of-fold years, a fixed 300-cell menu re-ranked in every training
window, beside a random cell from the same menu and the paper's constants:

| arm | all 12 folds | **excluding 2025** | folds positive |
| --- | ---: | ---: | ---: |
| re-optimised each fold | +0.1490 | **+0.0593** | 9 / 12 |
| a RANDOM cell | +0.0943 | **+0.1047** | 7 / 12 |
| the paper's constants | −0.0139 | −0.0185 | 7 / 12 |

The re-optimiser appears to win — on one fold, 2025, where it took **four trades** at +1.136 R.
**Remove that fold and a random cell from the same menu beats it.** Median trades per fold are 14
for the chosen arm against 34 for the constants: the optimiser buys low-count cells, as it has in
every previous study here.

## 19. Why your Strategy Tester shows 204 trades and this shows 592

Same rule, same span, same timeframe. The difference is **C5**, and C5 reads your broker's tick
volume. Switching C5 off takes the long side from 592 trades to 904, so that single condition is
selecting a third of the population — and one XAUUSD feed's tick count is not another's. **This
strategy's signal set is broker-dependent**, which is a portability problem the paper does not
discuss and which no amount of parameter tuning fixes. It also means a Strategy Tester result on
one data provider does not transfer to another.

## 20. The answer to "find the mean performance that is a proven edge"

There is not one in this family on this data, and the chain is:

1. **No finalist's locked bootstrap excludes zero** (P(mean≤0) 0.054 to 0.176).
2. **Deflated Sharpe 0.000** for all four at 3,660 counted trials.
3. Every finalist beats **only a control that loses money**.
4. **fANOVA 0.85–0.90 on the volume multiple**, whose gradient inverts +1.00 → −0.90 across the split.
5. The best research cell is a **spike** — 6.7% of its own neighbours beat it.
6. **94% of its locked result is the 2025 gold rally**; +0.015 R a trade without it.
7. The walk-forward advantage is **one fold of four trades**; strip it and a random cell wins.

What *would* change the answer is not more search. It is a second gold feed to test whether the
volume-dependent signal set is real, and a longer stretch of non-rallying gold — the locked block
contains one of the largest bull runs in the metal's history, and every positive number here leans
on it.

---

# Part 3 — walk-forward and the formal overfitting test

**Verdict — the published rule is not overfitted, and the search around it is, severely.** Those
are two different findings and they need two different tests. CSCV over 1,199 sampled
configurations x 193 months gives **PBO = 0.561**: the in-sample winner lands *below* the
out-of-sample median in 56% of 12,870 symmetric splits, so selecting the in-sample best is worse
than picking at random. The slope of out-of-sample on in-sample performance is **−1.27**. And in a
13-fold walk-forward with the selection re-run each fold, the optimiser is the **worst of three
arms**: +5.6 R against a random cell's +27.0 R and the published constants' +15.6 R.

## 21. Three questions that all get called "overfitting"

| question | test | answer |
| --- | --- | --- |
| Is the published rule fitted to gold? | rolling walk-forward, **nothing re-selected** | No — it was never fitted; its median in-sample rank across 12,870 splits is **0.444**, a below-median cell in its own grid |
| Is the search overfit? | walk-forward with the selection **re-run each fold** | Yes — re-optimising is the worst of three arms |
| What is P(backtest overfitting)? | **CSCV / PBO** (Bailey, Borwein, López de Prado & Zhu) | **0.561 — severe** |

## 22. The published rule rolled forward, nothing re-selected

36 months train, 12 months test, 13 folds. No parameter is chosen — only the market changes.

| out-of-sample year | n IS | IS R | n OOS | **OOS R** |
| --- | ---: | ---: | ---: | ---: |
| 2013 | 141 | −0.0567 | 36 | **+0.1503** |
| 2014 | 151 | +0.0050 | 35 | +0.0933 |
| 2015 | 127 | +0.0575 | 16 | **−0.6222** |
| 2016 | 87 | −0.0147 | 32 | +0.3077 |
| 2017 | 83 | +0.0380 | 45 | −0.0811 |
| 2018 | 93 | −0.0404 | 22 | −0.1126 |
| 2019 | 99 | +0.0376 | 30 | −0.1794 |
| 2020 | 97 | −0.1186 | 45 | +0.0909 |
| 2021 | 97 | −0.0388 | 31 | +0.0564 |
| 2022 | 106 | +0.0043 | 39 | +0.1969 |
| 2023 | 115 | +0.1176 | 38 | −0.1976 |
| 2024 | 108 | +0.0178 | 46 | +0.2440 |
| 2025 | 123 | +0.0927 | 34 | +0.0373 |

Mean IS **+0.0078**, mean OOS **−0.0012**, and **corr(IS, OOS) across folds = −0.434**. Eight of
thirteen folds are positive on each side. The in-sample result of a three-year window
*anti-predicts* the next year even when nothing is being fitted — that is regime, not overfitting,
and it is the reason a single good window means nothing here.

## 23. PBO — the formal test

Per-month return matrix, 1,199 sampled configurations plus the published rule, 193 months, 16
contiguous blocks, all **C(16,8) = 12,870** symmetric splits. For each split: take the in-sample
best configuration, find its rank among all configurations out of sample, and take the logit.

```
PBO = 0.561            the IS winner is below the OOS median in 56.1% of splits
median OOS rank        0.455
mean logit             -0.373
```

Bailey et al.'s reading: PBO above 0.5 means the selection procedure is **actively harmful** —
you would do better choosing a configuration at random than choosing the one that backtested best.

The degradation is severe and the *direction* is the finding:

```
IS-best mean statistic   +0.2454   ->   its out-of-sample   +0.0139     (94% evaporates)
share of IS winners that are OOS-positive                    60.7%
slope of OOS on IS                                           -1.2671
```

A negative slope means the *better* a configuration looked in sample, the *worse* it did out of
sample. This is the same thing the Optuna study's fANOVA said from another angle: the search is
tuning the volume multiple, whose gradient inverts across the split, so the harder it optimises the
further it walks in the wrong direction.

## 24. Walk-forward with the selection re-run each fold

Three arms over the same 13 out-of-sample years: re-optimise on the training window, take the
published constants, or take a random cell from the same 1,199-configuration menu.

| arm | total R | mean per fold | folds positive |
| --- | ---: | ---: | ---: |
| re-optimised each fold | **+5.57** | +0.428 | 5 / 13 |
| a RANDOM cell | **+27.02** | +2.079 | 9 / 13 |
| the published constants | **+15.56** | +1.197 | 8 / 13 |

**A random cell beats the optimiser 4.9x, and the author's untuned constants beat it 2.8x.** This
is the eleventh re-optimiser on this branch to lose to the constants it was trying to improve, and
the first to also lose to a coin flip.

Note the shape of the optimiser's failure in the fold table: its *in-sample* totals climb steadily
(13.5 → 47.2 R) across the folds while its out-of-sample results do not follow at all. It is
finding better and better fits to windows that do not repeat.

## 25. What this does and does not say

It does **not** say the published rule is overfit. It was never fitted to gold; it sits at median
rank in its own parameter grid; its ten numbers rank 2nd to 4th of 3–5 on every one of eight
ladders (Part 1 §7). Whatever is wrong with it is not curve-fitting.

It says that **any attempt to improve it by search on this data will make it worse out of sample**,
and that its own year-to-year variation is large enough (−0.62 to +0.31 R) that a three-year window
carries no information about the next one. Combined with Part 2 — no candidate separates from zero,
deflated Sharpe 0.000, 62–94% of the good locked results coming from the 2025 rally — the family
has neither a demonstrable edge nor a route to one through optimisation.

---

# Part 4 — the same battery, per preset

**Verdict — the two SWEEP presets are overfitted, the three Optuna presets are not, and the
published one was never fitted at all.** The test that separates them is the walk-forward
generalization gap, because five of the six were fitted on this data by my own search and one was
not.

| preset | fitted? | folds | IS | OOS | **gap** | OOS positive | verdict |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Sweep neighbourhood | yes | 5 | +0.227 | **−0.058** | **+0.285** | 2/5 | **OVERFIT** |
| Sweep top row | yes | 7 | +0.347 | +0.081 | **+0.266** | 4/7 | **OVERFIT** |
| Optuna ret/DD | yes | 12 | +0.213 | +0.150 | +0.062 | 9/12 | holds |
| As published | **no** | 13 | +0.008 | −0.001 | +0.009 | 8/13 | never fitted |
| Optuna PF | yes | 11 | +0.195 | +0.203 | −0.008 | 10/11 | holds |
| Optuna total R | yes | 13 | +0.203 | +0.226 | −0.023 | 10/13 | holds |

The split is clean and it is not the one you would guess. **The exhaustive-grid winners are the
overfitted ones**; the Optuna cells, chosen from a continuous space by a sampler that concentrates
rather than maximising over 108,000 discrete draws, keep their out-of-sample result. The two sweep
cells are also the two that trade least (61 and 53 locked trades), which is why they support only
5 and 7 folds — the maximum of a large grid buys a low-count cell, as it did in `STUDY_V42` and
`STUDY_V64_OPTUNA`.

## 26. Where each preset sits in its own parameter pool

Median in-sample rank across the 12,870 CSCV splits, among 1,199 sampled grid cells:

| preset | median IS rank | p90 rank swing |
| --- | ---: | ---: |
| Optuna PF | 0.984 | 0.10 |
| Optuna ret/DD | 0.984 | 0.13 |
| Optuna total R | 0.931 | 0.32 |
| Sweep top row | 0.913 | 0.31 |
| Sweep neighbourhood | 0.707 | 0.53 |
| **As published** | **0.443** | 0.48 |

The five fitted presets sit in the top decile of their own pool by construction. **The published
rule sits below the median** — which is exactly what a configuration chosen by convention rather
than by search should look like, and is the cleanest single piece of evidence that it is not
curve-fitted.

## 27. A method note: symmetric CSCV cannot measure a fixed cell's rank drop

My first pass reported a `rank_drop` of **exactly 0.000 for all six presets**, which is not a
result — it is a property of the design. In combinatorially symmetric CSCV, for every split the
**complement is also a split**, so a fixed column's in-sample rank distribution is *identical* to
its out-of-sample rank distribution, and both the difference of medians and the median of the
pairwise differences are identically zero.

PBO escapes this because its subject — the argmax — **changes with the split**; a fixed column's
subject does not. For a fixed cell the informative quantities are the **dispersion** of the
per-split rank swing (`p90_drop` above) and the walk-forward gap.

One more thing the exercise showed: **adding fitted cells to the CSCV pool lowers PBO**, from
**0.561** over the grid alone to **0.465** with the five fitted presets included, because it hands
the in-sample argmax a pre-selected winner. Report PBO over a pool that contains nothing chosen on
the data being tested.

## 28. What this changes, and what it does not

It changes which presets are trustworthy as *configurations*: prefer the Optuna cells or the
published defaults over the two sweep cells, and treat "sweep neighbourhood-best" as the worst of
the six despite its being the best-looking locked number in Part 2 (+0.2624 R). The neighbourhood
criterion that `STUDY_V38` found valuable did not protect it here.

It changes nothing about the family. Part 2 stands: **not one preset separates from zero** on the
locked block (bootstrap P(mean ≤ 0) 0.054 to 0.184), deflated Sharpe is 0.000 for all of them, and
62–94% of the good locked results come from the 2025–26 gold rally. A preset can be perfectly
un-overfitted and still have nothing under it — which is the position the published rule has been
in since Part 1.

---

# Part 5 — why the two Optuna presets "hold", and what that turns out to mean

**Verdict — they hold because they trade more, and every one of them is a degraded way of being
long gold.** On the same days, entering at the session open with **the same ATR stop** earns more
per trade than the rule in **11 of 12 preset-blocks**, and more per unit of drawdown in 11 of 12.
The generalization gap correlates **−0.95 with the number of walk-forward folds a preset supports**,
which is arithmetic, not mechanism.

## 29. Four explanations, tested

| explanation | test | result |
| --- | --- | --- |
| A. It is gold beta | regress monthly R on gold's monthly return | every preset positive-beta; the beta term is 24–113% of total R |
| B. It is sample size | corr(folds, gap) across the six | **−0.951** |
| C. It is low selectivity | signals as a share of session bars | 0.15–0.69%, and the *most* selective are the ones that fail |
| D. It is an edge | beat always-long on its own days with the same stop | **1 of 12** |

## 30. The correlation matrix

Monthly R, 193 months:

| | published | Opt totR | Opt PF | Opt retDD | Swp top | Swp nbhd | **GOLD** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| published | 1.00 | 0.47 | 0.37 | 0.56 | 0.59 | 0.53 | **0.22** |
| Optuna totR | 0.47 | 1.00 | 0.24 | 0.39 | 0.38 | 0.43 | **0.28** |
| Optuna PF | 0.37 | 0.24 | 1.00 | 0.65 | 0.61 | 0.55 | **0.26** |
| Optuna retDD | 0.56 | 0.39 | 0.65 | 1.00 | 0.71 | 0.65 | **0.30** |
| Sweep top row | 0.59 | 0.38 | 0.61 | 0.71 | 1.00 | **0.91** | **0.24** |
| Sweep nbhd | 0.53 | 0.43 | 0.55 | 0.65 | 0.91 | 1.00 | **0.22** |

Two things. The **two sweep cells correlate 0.91** with each other — they are one configuration
with two names, which is why they fail together. And every preset correlates **0.22–0.30 with gold
itself**, modest in variance terms (R² 0.05–0.09) but enough that the beta term accounts for
**24% to 113%** of each one's total R. For the published rule it is **112.7%** — the entire result
is the gold exposure and then some.

## 31. Why *these two* hold: it is the fold count

| preset | trades | folds | gap |
| --- | ---: | ---: | ---: |
| Optuna totR | 456 | 13 | **−0.023** |
| Optuna PF | 214 | 11 | **−0.008** |
| As published | 592 | 13 | +0.009 |
| Optuna ret/DD | 270 | 12 | +0.062 |
| Sweep top row | 164 | 7 | +0.266 |
| Sweep nbhd | 145 | 5 | +0.285 |

**corr(folds, gap) = −0.951; corr(trades, gap) = −0.690.** A generalization gap shrinks toward zero
as the fold estimate gets less noisy. The two presets that "hold" are the two with the most trades
and the most folds. That is a statistical property of the measurement, not a property of the
strategy — and it is why "it held out of sample" is a much weaker statement than it sounds.

## 32. The decisive test — and it is not close

On the same days, buy the first bar of the session, carry **the same ATR stop the rule uses**, and
exit on the same bar the rule exited. This control cannot be accused of taking more risk: its worst
trades match the rules' to two decimals (rule −1.05 to −1.49 R, control −1.06 to −1.58).

| preset | block | rule R | session-open + same stop | rule ret/DD | control ret/DD |
| --- | --- | ---: | ---: | ---: | ---: |
| As published | locked | +0.142 | **+0.235** | 1.70 | **5.39** |
| Optuna totR | locked | **+0.200** | +0.114 | **1.80** | 1.37 |
| Optuna PF | locked | +0.182 | **+0.497** | 2.15 | **13.06** |
| Optuna ret/DD | locked | +0.110 | **+0.506** | 0.85 | **8.50** |
| Sweep top row | locked | +0.224 | **+0.818** | 0.76 | **11.43** |
| Sweep nbhd | locked | +0.262 | **+0.884** | 0.69 | **9.22** |

**11 of 12 preset-blocks lose, on both per-trade R and return-over-drawdown.** The single exception
is Optuna total-R on the locked block (+0.200 against +0.114) — one cell, one block, and its
research block loses.

The six conditions are not selecting good days and then trading them well. They are selecting days
on which gold rose, and then **entering late and worse** than simply being there.

## 33. And the one that "holds" best is the most gold-dependent

Fold-level, 13 folds: mean total R in folds where gold rose vs folds where it fell.

| preset | gold rose | gold fell | ratio |
| --- | ---: | ---: | ---: |
| **Optuna totR** | **+9.17** | **+0.28** | **32×** |
| Optuna PF | +3.42 | +2.00 | 1.7× |
| Optuna ret/DD | +3.43 | +3.21 | 1.1× |
| As published | +2.07 | +0.97 | 2.1× |
| Sweep top row | +2.21 | +6.33 | 0.35× |
| Sweep nbhd | +0.42 | +3.94 | 0.11× |

The preset with the smallest generalization gap — Optuna total R, the one that looked most robust —
earns **32× more in folds where gold rose** and essentially nothing when it did not. Its
correlation with the fold's gold return is +0.485, the highest of the six. It "holds out of sample"
because gold rose in 9 of the 13 out-of-sample folds.

The only preset whose result is roughly *independent* of the fold's gold direction is **Optuna
ret/DD** (+3.43 vs +3.21, corr +0.119) — and that one has a positive gap (+0.062), loses to the
session-open control by 0.40 R, and has the worst locked bootstrap of the three (P(mean ≤ 0) 0.176).

## 34. The answer

"Holds out of sample" here decomposes into: **trades enough to have a stable estimate** (the fold
count), **is long in a market that rose** (the beta and the fold split), and **is not a better way
of being long than the naive alternative** (the session-open control). None of the three is an
edge, and the third rules one out.
