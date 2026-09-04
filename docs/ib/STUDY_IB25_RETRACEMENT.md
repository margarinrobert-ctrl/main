# The "IB 25 retracement" as posted

`research/ib25/`, `results/ib25/`. NQ 1-minute, 923 RTH sessions, 2022-12-26 → 2025-12-11.

## Verdict

**It does not work on NQ over three years, and the reason is arithmetic rather than execution.**
As posted it scores **−0.0114 % of entry price per trade, PF 0.866** on the research block and
+0.0141 / PF 1.165 on the locked block — losing on the block that would select it, which is the
wrong shape. It is **negative gross** (−0.0047 before any cost), so there is nothing for better
fills to recover. And it **loses to a random entry minute** in the same window with the same side
and the same barriers: **p 0.746**.

The post's own best observation is correct and does not help. Moving the stop to 75% *does* raise
the win rate — 48.4% → 66.4% — and expectancy stays negative, because **the win rate tracks the
driftless break-even at every rung**:

| Stop | Reward:risk | Win rate | Driftless break-even | % / trade |
| ---: | ---: | ---: | ---: | ---: |
| 0.35 | 2.50 | 32.5% | 28.6% | −0.0034 |
| **0.50 (as posted)** | 1.00 | 48.4% | 50.0% | **−0.0114** |
| 0.625 | 0.67 | 56.5% | 60.0% | −0.0169 |
| **0.75 (the post's suggestion)** | 0.50 | **66.4%** | 66.7% | −0.0070 |
| 1.00 | 0.33 | 74.2% | 75.0% | +0.0009 |

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
| % of price / trade | **−0.0114** | +0.0141 |
| Total % | −3.92 | +2.57 |
| Profit factor | **0.866** | 1.165 |
| Win rate | 48.4% | 57.1% |
| Max drawdown | −5.71% | −1.53% |
| Points / trade | −2.27 | +3.21 |

57.1% of sessions produce a trade. Exit mix on research: 52% stop, 48% target.
Bootstrap: research P(mean ≤ 0) **0.887**; locked 0.188, CI [−0.0172, +0.0454].

## The two judgement calls earn nothing

16 cells of VWAP-slope threshold × VWAP-cross ceiling, research block:

| Slope threshold | Max crosses | Trades | % kept | % / trade | PF |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.00 | 99 (off) | 345 | 100% | −0.0114 | 0.866 |
| 0.00 | 5 | 126 | **37%** | −0.0113 | 0.885 |
| 0.10 | 12 | 304 | 88% | −0.0092 | 0.892 |
| 0.20 | 99 | 296 | 86% | **−0.0139** | 0.843 |
| 0.20 | 5 | 123 | 36% | −0.0076 | 0.922 |

**The chop ceiling removes 63% of the sample and changes the per-trade result by 0.0001.** The
slope threshold is monotonically *harmful* with the chop filter off (−0.0114 → −0.0139 as it
tightens). Not one of the sixteen cells is positive. These are the two conditions the post is most
insistent about.

## The other components

| Variant | Trades | % / trade | PF |
| --- | ---: | ---: | ---: |
| as posted | 345 | −0.0114 | 0.866 |
| **no sweep veto** | 400 | **−0.0082** | 0.900 |
| no 12:00 cutoff (to 15:00) | 348 | −0.0115 | 0.864 |
| **longs only** | 196 | **−0.0268** | **0.711** |
| **shorts only** | 205 | **−0.0007** | 0.991 |
| slope window 60 min | 231 | −0.0056 | 0.936 |

**The sweep veto costs money** and the 12:00 cutoff is free and worthless — the two "don't trade
after" rules are the two that change nothing or hurt. And the long side is the loser: buying the
pullback toward the range high loses −0.0268 while the short side is flat, **in a market that rose
89% over the sample**.

## The retracement ladder — 25% is not the mechanism, and depth does not rescue it

| Retracement | Trades | % / trade | PF | Win rate | Break-even |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.10 | 300 | −0.0160 | 0.740 | 77.0% | 80.0% |
| 0.15 | 352 | −0.0146 | 0.810 | 67.0% | 70.0% |
| **0.25 (as posted)** | 345 | −0.0114 | 0.866 | 48.4% | 50.0% |
| 0.35 | 300 | **−0.0215** | 0.714 | 23.3% | 30.0% |
| 0.50 | 267 | **+0.0004** | 1.004 | 35.6% | 33.3% |

Non-monotone, and **the win rate is at or below its own break-even at every rung except 0.50**.
`STUDY_V58_INITIAL_BALANCE` found this axis cleanly monotone on a *different* IB family — a
breakout retracement — where deeper was better all the way to 0.50 at p 0.000. **That does not
reproduce on this geometry**, which fades back toward the range extreme rather than retracing a
break. The two families share a fib tool and nothing else.

## The nulls

| Variant | Observed | Control median | Control 5–95% | p |
| --- | ---: | ---: | --- | ---: |
| as posted | −0.0114 | −0.0061 | [−0.0196, +0.0068] | **0.746** |
| retr 0.50 / stop 0.75 / 60-min slope | −0.0012 | −0.0198 | [−0.0406, +0.0017] | 0.081 |

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
| as posted | −0.0114 | **−0.0047** | 8.4% |
| retr 0.50 / stop 0.75 | +0.0004 | +0.0071 | 8.8% |

**As posted it is negative before any cost is charged**, so better fills cannot rescue it. The
deeper variant *is* a cost problem — gross +0.0071 against a round turn worth 8.8% of risk — and
that is the only version with anything to recover.

## The one locked read

Roughly 40 research cells were scored (6 retracement rungs, 5 stops, 16 filter cells, 8
ablations). **Two** configurations were read on the locked block.

| Variant | Block | n | % / trade | Total % | PF | Win | Break-even |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| as posted | research | 345 | −0.0114 | −3.92 | 0.866 | 48.4% | 50.0% |
| as posted | **locked** | 182 | +0.0141 | +2.57 | 1.165 | 57.1% | 50.0% |
| retr 0.50 / stop 0.75 | research | 214 | −0.0012 | −0.26 | 0.988 | 36.0% | 33.3% |
| retr 0.50 / stop 0.75 | **locked** | 103 | +0.0143 | +1.47 | 1.118 | 37.9% | 33.3% |

Both are positive on the locked block and negative on research — **the wrong shape**, the tenth
occurrence on this branch. A rule chosen on research should look better there; the holdout is
where an edge decays, not where it appears. Locked bootstrap P(mean ≤ 0) is 0.188 and 0.326, so
neither locked read separates from zero either.

## What would change the verdict

- **A different market.** This is one instrument. US100 and US30 are 15-minute feeds here, which
  cannot resolve a 10:20 close or a 1-minute limit fill, so the rule as specified is not testable
  on them and this is a single-market result.
- **The discretion.** "Not choppy" applied by eye may select sessions my cross-count does not. The
  16-cell grid says no setting of either filter turns the sign, which bounds but does not
  eliminate that.
- **The one variant worth watching**, not trading: retracement 0.50 with a 0.75 stop and a 60-minute
  slope window is the only cell that comes near its control (p 0.081), is gross-positive, and is
  break-even net. That is the deep-limit mechanic this branch has documented six times over —
  and at 25% it is not deep enough to pay for the barriers.
