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
