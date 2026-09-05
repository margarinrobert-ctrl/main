# The six shipped 30-minute legs, run unchanged on EURUSD

## Why this test is worth more than the two before it

Every previous cross-instrument check on this branch carried an objection.

* **US100 over the overlapping calendar** was not a second test at all — 68% of NQ's triggers fired
  on the *identical 15-minute bar* (`STUDY_TREND_LONG.md`).
* **US100 before 2022-12-26** was a genuine test, but of the same underlying index.

EURUSD is a **different asset class** over a period that shares **not one bar** with the NQ file: it
ends 2022-02-22 and NQ starts 2022-12-26. 18.6 years against NQ's three. Nothing was refitted — the
conditions, side, ATR stop multiple, 1R target and flatten time are exactly as shipped.

Two things necessarily change and are stated rather than hidden. The clock conditions ("first 120
minutes", "flat at 15:00") are New York *equity*-session windows applied to a market with no equity
session; they still land on the London/New York overlap, EURUSD's busiest period, but they were not
chosen for it. And costs come from the feed's **measured spread** rather than an assumption — the
first test here that can (`STUDY_SPREAD_TRUTH.md`).

Scoring is in **R units**, never dollars: EURUSD trades at 1.1 and NQ at 20,000. Each leg is scored
against a **minute-of-day matched control** — random entries, same side, geometry and clock — and
the six are corrected together at BH q=0.10. Three of the nine legs are 15-minute rules and cannot
be tested: the EURUSD source is 30-minute.

## The result

| leg | side | stop | n | win | E[R] | control | excess | p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **V1** | long | 3.0×ATR | 1,501 | 53.03% | **+0.0360** | −0.0357 | **+0.0716** | **0.000** |
| V2L | long | 2.5×ATR | 975 | 48.82% | +0.0025 | −0.0034 | +0.0059 | 0.367 |
| M1 | long | 1.0×ATR | 565 | 46.19% | −0.0994 | −0.0905 | −0.0089 | 0.560 |
| M2 | short | 1.0×ATR | 554 | 45.49% | −0.1203 | −0.1048 | −0.0155 | 0.637 |
| V2 | short | 1.0×ATR | 996 | 40.96% | −0.1850 | −0.1095 | −0.0755 | 0.995 |
| M4 | long | 4.0×ATR | 98 | 41.84% | −0.1026 | +0.0008 | −0.1034 | 0.990 |

**One of six survives BH at 0.10, and it is V1.** It is also positive in absolute terms where its
control is negative, so this is not a relative-to-a-bad-null artifact.

Tripling the stop slippage changes nothing that matters: V1's excess goes **+0.0716 → +0.0736** and
the ordering is unchanged. V1 is a wide-stop leg with only 31% stop exits, so slippage is not where
its result lives.

## What this makes V1

Third independent confirmation, on three different footings:

1. **NQ**, where it was selected — and it *decays* across the split ($37.7/trade research → $30.0
   locked), which is the right shape and which five of the nine legs do not have.
2. **US100's nine unseen years** — +9.2 excess over base, p 0.0001.
3. **EURUSD, a different asset class over a non-overlapping era** — +0.0716 R, p 0.000.

No other rule on this branch has three. V2L, which passed on US100 (+8.5, p 0.0050), does **not**
transfer here (p 0.367) — which retrospectively suggests its US100 pass owed something to being the
same index. M4 collapses again to 98 trades at −0.103 R, consistent with `STUDY_M4_ANATOMY.md`
having shown it is a day filter wearing a barrier costume rather than a rule.

## The qualification, which is real

Split into four sub-periods, each scored against its own matched control:

| period | n | win | E[R] | control | excess | p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2003–2007 | 211 | 54.50% | +0.0029 | −0.0294 | +0.0322 | 0.257 |
| 2008–2012 | 410 | 50.49% | −0.0176 | −0.0356 | +0.0180 | 0.310 |
| 2013–2017 | 485 | 54.64% | +0.0680 | −0.0350 | **+0.1030** | **0.000** |
| 2018–2022 | 395 | 52.91% | +0.0699 | −0.0380 | **+0.1078** | **0.010** |

**The sign is positive in all four**, which is the part that matters — a spurious result has no
reason to be four-for-four. But the magnitude is concentrated in the second half, and the first two
blocks are individually indistinguishable from their controls. The honest reading is that V1's edge
is *consistent* over 18.6 years and *strong* over the last nine, not that it is uniform.

## Where the money comes from, and it is not purely the barriers

| exit | share | mean R |
| --- | ---: | ---: |
| target | 33.6% | +0.9906 |
| stop | 30.9% | −1.0106 |
| flat 15:00 | 35.4% | +0.0425 |

Median hold 10 bars (5 hours). The barrier pair contributes about **+0.021 R** and the time exit
about **+0.015 R** — so roughly 57/43. This branch's rule is that "a 1R rule earning at the *time*
stop is a direction bet, not a barrier edge"; V1 is not purely one or the other here, and the
barrier component is the larger half. On NQ the same leg exits on a stop 28% of the time, so the
mix is broadly comparable.

## What it does not show

EURUSD's clock conditions were inherited, not chosen, so a version of V1 fitted to FX's own session
structure would likely be better — and that is exactly the search this test is not allowed to run
without spending the independence it just bought. The rule stays as shipped.

`research/eurusd_legs.py`, `research/run_eurusd_legs.py`.
