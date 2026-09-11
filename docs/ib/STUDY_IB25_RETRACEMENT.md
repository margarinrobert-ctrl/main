# The "IB 25 retracement" as posted

> **CORRECTION, 2026-09-04.** The first version of this study applied slippage in the trader's
> FAVOUR — the entry and exit signs were both inverted, paying 2 × slip = 0.5 points = **$1.00 an
> MNQ trade** instead of charging it. It was caught by the MNQ cost-sensitivity table, where
> expectancy *rose* with the assumed slippage, which is impossible for a fixed trade set. Every
> figure below is the corrected one and every corrected figure is **worse**: the rule as posted
> goes from −0.0114 to **−0.0169 %/trade** on research, and the one near-break-even variant goes
> from +0.0004 to **−0.0050**. The conclusion is unchanged and strengthened. Slippage hurts only
> if the entry is worse by `+ side × slip` and the exit by `− side × slip`; getting one of the two
> backwards halves the charge, getting both backwards pays it out.

`research/ib25/`, `results/ib25/`. NQ 1-minute, 923 RTH sessions, 2022-12-26 → 2025-12-11.

## Verdict

**It does not work on NQ over three years, and the reason is arithmetic rather than execution.**
As posted it scores **−0.0169 % of entry price per trade, PF 0.807** on the research block and
+0.0097 / PF 1.111 on the locked block — losing on the block that would select it, which is the
wrong shape. It is **negative gross** (−0.0047 before any cost), so there is nothing for better
fills to recover. And it **loses to a random entry minute** in the same window with the same side
and the same barriers: **p 0.845**.

The post's own best observation is correct and does not help. Moving the stop to 75% *does* raise
the win rate — 48.4% → 66.4% — and expectancy stays negative, because **the win rate tracks the
driftless break-even at every rung**:

| Stop | Reward:risk | Win rate | Driftless break-even | % / trade |
| ---: | ---: | ---: | ---: | ---: |
| 0.35 | 2.50 | 32.5% | 28.6% | −0.0089 |
| **0.50 (as posted)** | 1.00 | 48.4% | 50.0% | **−0.0169** |
| 0.625 | 0.67 | 56.5% | 60.0% | −0.0224 |
| **0.75 (the post's suggestion)** | 0.50 | **66.4%** | 66.7% | −0.0125 |
| 1.00 | 0.33 | 74.2% | 75.0% | **−0.0046** |

The win rate is the barrier geometry, not an edge. Widening the stop buys exactly the win rate the
geometry implies and no more.

## How it was transcribed

Session VWAP anchored to 09:30. Nothing before the 10:20 close. The morning range runs 09:30 to
min(now, 10:30) — the post says draw the fib at 10:21 and keep adjusting until 09:30–10:30 is
formed, which is a **running** range that freezes at 10:30. Direction from the VWAP slope. A
resting limit at 25% of the range measured from the target-side extreme, target that extreme, stop
at 50%. No new setup after 12:00 or once the range is swept. **One live order, one trade per
session** — `STUDY_V15_BOOK` and `STUDY_V34_MECHANIC` both caught this branch's own engines holding
a *book* of resting limits where a script holds one, which inflated every limit-entry figure they
produced.

**Three things the post leaves to judgement had to be made explicit, and each is a free
parameter:**

| Post | Codified as |
| --- | --- |
| "VWAP sloping in your direction" | VWAP change over N minutes ÷ ATR, against a threshold |
| "price hasn't chopped around it too much" | count of closes across the VWAP since 09:30, against a ceiling |
| "the IB high or low is swept" | price trading beyond the frozen 09:30–10:30 range voids the session and cancels a resting order |

These are my codifications. A discretionary trader reading "sloping and not choppy" by eye may
select differently — but the 16-cell grid below bounds how much that can be worth.

Scored in **percent of entry price**. The risk is `(stop − retr) × range`, a difference of two
fractions of a swept range, which is the denominator trap `STUDY_V58_INITIAL_BALANCE` and
`STUDY_SWEEP_110K` were caught by. **Here it does not fire** — mean R and mean points agree in sign
in all five risk quintiles — but R is still reported only as a diagnostic.

## As posted

| Metric | Research | Locked |
| --- | ---: | ---: |
| Trades | 345 | 182 |
| % of price / trade | **−0.0169** | +0.0097 |
| Total % | −5.82 | +1.77 |
| Profit factor | **0.807** | 1.111 |
| Win rate | 48.4% | 57.1% |
| Max drawdown | −7.21% | −1.65% |
| Points / trade | −3.27 | +2.21 |

57.1% of sessions produce a trade. Exit mix on research: 52% stop, 48% target.
Bootstrap: research P(mean ≤ 0) **0.965**; locked 0.275, CI [−0.0214, +0.0411].

## The two judgement calls earn nothing

16 cells of VWAP-slope threshold × VWAP-cross ceiling, research block:

| Slope threshold | Max crosses | Trades | % kept | % / trade | PF |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.00 | 99 (off) | 345 | 100% | −0.0169 | 0.807 |
| 0.00 | 5 | 126 | **37%** | −0.0168 | 0.831 |
| 0.10 | 12 | 304 | 88% | −0.0147 | 0.833 |
| 0.20 | 99 | 296 | 86% | **−0.0194** | 0.786 |
| 0.20 | 5 | 123 | 36% | −0.0131 | 0.868 |

**The chop ceiling removes 63% of the sample and changes the per-trade result by 0.0001.** The
slope threshold is monotonically *harmful* with the chop filter off (−0.0169 → −0.0194 as it
tightens). Not one of the sixteen cells is positive. These are the two conditions the post is most
insistent about.

## The other components

| Variant | Trades | % / trade | PF |
| --- | ---: | ---: | ---: |
| as posted | 345 | −0.0169 | 0.807 |
| **no sweep veto** | 400 | **−0.0136** | 0.840 |
| no 12:00 cutoff (to 15:00) | 348 | −0.0170 | 0.806 |
| **longs only** | 196 | **−0.0322** | **0.669** |
| **shorts only** | 205 | **−0.0061** | 0.930 |
| slope window 60 min | 231 | −0.0111 | 0.880 |

**The sweep veto costs money** and the 12:00 cutoff is free and worthless — the two "don't trade
after" rules are the two that change nothing or hurt. And the long side is the loser: buying the
pullback toward the range high loses −0.0322 while the short side is nearly flat, **in a market that rose
89% over the sample**.

## The retracement ladder — 25% is not the mechanism, and depth does not rescue it

| Retracement | Trades | % / trade | PF | Win rate | Break-even |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.10 | 300 | −0.0215 | 0.671 | 77.0% | 80.0% |
| 0.15 | 352 | −0.0201 | 0.751 | 67.0% | 70.0% |
| **0.25 (as posted)** | 345 | −0.0169 | 0.807 | 48.4% | 50.0% |
| 0.35 | 300 | **−0.0270** | 0.658 | 23.3% | 30.0% |
| 0.50 | 267 | **−0.0051** | 0.951 | 35.6% | 33.3% |

Non-monotone, and **the win rate is at or below its own break-even at every rung except 0.50**.
`STUDY_V58_INITIAL_BALANCE` found this axis cleanly monotone on a *different* IB family — a
breakout retracement — where deeper was better all the way to 0.50 at p 0.000. **That does not
reproduce on this geometry**, which fades back toward the range extreme rather than retracing a
break. The two families share a fib tool and nothing else.

## The nulls

| Variant | Observed | Control median | Control 5–95% | p |
| --- | ---: | ---: | --- | ---: |
| as posted | −0.0169 | −0.0088 | [−0.0223, +0.0040] | **0.845** |
| retr 0.50 / stop 0.75 / 60-min slope | −0.0067 | −0.0225 | [−0.0433, −0.0011] | 0.122 |

The control keeps the session, the side, the target, the stop and the flatten, and moves only the
entry **minute** — so it prices the limit mechanic and the session selection and asks what the fib
*level* adds. As posted, a random minute beats it three times in four.

> **A control-construction error was caught here and is recorded rather than quietly fixed.** The
> first build had the target and stop signs swapped, so every control trade exited instantly in
> profit: median **+0.1513** with a 5–95% band of **zero width**. A null with no spread is broken.
> `STUDY_V59` caught the same class of error from the other direction. Diagnose a control by its
> spread, not only its median.

## Zero cost — is it execution?

| Variant | Net % / trade | **Gross % / trade** | Cost as % of risk |
| --- | ---: | ---: | ---: |
| as posted | −0.0169 | **−0.0047** | 8.4% |
| retr 0.50 / stop 0.75 | **−0.0050** | **+0.0071** | 8.8% |

**As posted it is negative before any cost is charged**, so better fills cannot rescue it. The
deeper variant *is* a cost problem — gross +0.0071 against a round turn worth 8.8% of risk — and
that is the only version with anything to recover.

## The one locked read

Roughly 40 research cells were scored (6 retracement rungs, 5 stops, 16 filter cells, 8
ablations). **Two** configurations were read on the locked block.

| Variant | Block | n | % / trade | Total % | PF | Win | Break-even |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| as posted | research | 345 | −0.0169 | −5.82 | 0.807 | 48.4% | 50.0% |
| as posted | **locked** | 182 | +0.0097 | +1.77 | 1.111 | 57.1% | 50.0% |
| retr 0.50 / stop 0.75 | research | 214 | −0.0067 | −1.43 | 0.938 | 36.0% | 33.3% |
| retr 0.50 / stop 0.75 | **locked** | 103 | +0.0099 | +1.02 | 1.080 | 37.9% | 33.3% |

Both are positive on the locked block and negative on research — **the wrong shape**, the tenth
occurrence on this branch. A rule chosen on research should look better there; the holdout is
where an edge decays, not where it appears. Locked bootstrap P(mean ≤ 0) is 0.275 and 0.378, so
neither locked read separates from zero either.

## Priced as MNQ

`research/ib25/run_ib25_mnq.py`; `results/ib25/mnq.txt`. **The study was already run on MNQ
economics** — this branch's NQ cost model uses a point value of 2.0, which *is* the Micro E-mini
Nasdaq-100 (the full-size NQ is 20). What follows is the dollar view.

| | |
| --- | --- |
| MNQ | $2.00 a point, tick 0.25 points = **$0.50** a contract |
| Price impact | 1 tick spread + 1 tick slippage a side = **$2.00** a round turn |
| Fees | **$1.44** a round turn (CME + NFA + clearing + broker) |
| **Total round turn** | **$3.44** = 1.720 points |
| Median risk | 26.6 points = **$53.12** a contract, so the round turn is **6.5% of risk** |

### One MNQ contract

| Variant | Block | n | $/trade | Total $ | PF | Win | Max DD $ | Best | Worst |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| as posted | research | 345 | **−6.55** | −2,259 | 0.797 | 48.4% | −2,773 | +297 | −192 |
| as posted | locked | 182 | +4.42 | +804 | 1.111 | 57.1% | −727 | +238 | −212 |
| retr 0.50 / stop 0.75 | research | 214 | −2.20 | −471 | 0.945 | 36.0% | −1,195 | +203 | −176 |
| retr 0.50 / stop 0.75 | locked | 103 | +4.20 | +432 | 1.075 | 37.9% | −1,681 | +480 | −212 |

### The caveat that only bites in dollars

`STUDY_US100` established that this branch's NQ price **levels** are synthetic — the stored series
runs above the real index early and converges late. Measured here against US100 over 862
overlapping days the ratio is **1.2563 → 1.0182**. Percent of price, R and win rates are
unaffected; **dollars are not**, because a dollar is points × $2 and the stored points carry the
same inflation. Deflating each trade by the ratio on its own date:

| Variant | Block | $/trade deflated | as stored | Total deflated | as stored | Inflation |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| as posted | research | **−5.86** | −6.55 | −2,021 | −2,259 | **11.7%** |
| as posted | locked | +4.31 | +4.42 | +784 | +804 | 2.6% |
| retr 0.50 / stop 0.75 | research | −1.96 | −2.20 | −419 | −471 | **12.4%** |
| retr 0.50 / stop 0.75 | locked | +3.91 | +4.20 | +403 | +432 | 7.2% |

The inflation is largest on the research block, which is the early part of the sample. Read the
deflated column for an MNQ account.

### The arithmetic in MNQ terms

**As posted:** median risk $53.12, round turn $3.44 (6.5% of risk), reward:risk 1.00, driftless
break-even win rate 50.0% against an actual **48.4%**. Gross **−0.053 points = −$0.11 a trade**;
net **−$6.55**. Break-even needs the win rate to rise **1.6 points**.

**retr 0.50 / stop 0.75:** reward:risk 2.00, break-even 33.3% against an actual **36.0%** — the
only geometry whose win rate clears its own bar. Gross **+2.119 points = +$4.24 a trade**, net
**−$0.20**. That one is a genuine cost problem; the posted geometry is not.

### One MNQ contract, as an account

| Variant | Block | Trades/yr | $/yr | Max DD $ | Account for 3× the drawdown |
| --- | --- | ---: | ---: | ---: | ---: |
| as posted | research | 180 | **−1,053** | −2,480 | $7,440 |
| as posted | locked | 175 | +755 | −705 | $2,115 |
| retr 0.50 / stop 0.75 | research | 112 | −218 | −1,102 | $3,307 |
| retr 0.50 / stop 0.75 | locked | 99 | +388 | −1,618 | $4,854 |

MNQ day-trade margin is typically $50–100, so buying power is not the constraint — **the drawdown
is**. On the research block one contract loses about **$1,050 a year** and draws down $2,480,
which needs roughly a $7,400 account to carry at 1 contract.

### Cost sensitivity in ticks

| Variant | Ticks/side | Round turn $ | Research $/trade | Locked $/trade |
| --- | ---: | ---: | ---: | ---: |
| as posted | 0 (fees only) | 1.44 | **−3.21** | +7.19 |
| as posted | 1 | 2.44 | −4.09 | +6.23 |
| as posted | **2 (assumed)** | **3.44** | **−4.98** | +5.27 |
| as posted | 4 | 5.44 | −6.74 | +3.35 |
| retr 0.50 / stop 0.75 | 0 (fees only) | 1.44 | **+0.70** | +6.80 |
| retr 0.50 / stop 0.75 | 1 | 2.44 | −0.19 | +5.84 |
| retr 0.50 / stop 0.75 | **2 (assumed)** | **3.44** | −1.07 | +4.88 |

**As posted it is negative on research even at zero price impact** — fees alone, which no one
achieves. The deeper variant is positive only at fees-only and turns negative by one tick a side.

**On the full-size NQ** every dollar figure is ×10 with a round turn near $24 — proportionally
*cheaper* relative to a ×10 risk, so NQ is the better contract for this rule. It does not change
the sign, because the posted geometry is negative before any cost.

## What would change the verdict

- **A different market.** This is one instrument. US100 and US30 are 15-minute feeds here, which
  cannot resolve a 10:20 close or a 1-minute limit fill, so the rule as specified is not testable
  on them and this is a single-market result.
- **The discretion.** "Not choppy" applied by eye may select sessions my cross-count does not. The
  16-cell grid says no setting of either filter turns the sign, which bounds but does not
  eliminate that.
- **The one variant worth watching**, not trading: retracement 0.50 with a 0.75 stop and a
  60-minute slope window is the only cell that comes near its control (p 0.122) and the only one
  whose win rate clears its own break-even (36.0% against 33.3%). It is **gross-positive
  (+$4.24 a trade) and net-negative (−$0.20)** — a pure cost problem, unlike the posted geometry. That is the deep-limit mechanic this branch has documented six times over —
  and at 25% it is not deep enough to pay for the barriers.
