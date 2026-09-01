# STUDY_FTM_ALPHA2 — FTM opening-range breakout 1.8.0-alpha.2 against the RC1 already measured

**Brief.** `FTM_OPENING_RANGE_BREAKOUT_MNQ_v1_8_0_ALPHA2.cs` (2,712 lines of NinjaScript, flagged
by its own header as an uncompiled, unreconciled draft) with "test this", plus the same three
index feeds. The file keeps the complete 1.4.1-rc.1 parent that `STUDY_FTM_ORB_BACKTEST.md`
already walked over 1.05M one-minute bars — admission geometry, touch veto, the quarterly kNN
direction model, the 120-session warm-up, sizing, the managed stop, the 15:30 conditional exit
and the 16:00 flatten — and changes the ordered entry policy in exactly two places:

| | RC1 | alpha.2 |
| --- | --- | --- |
| prior-session-disagreement branch | observe 2 completed minutes, then flip | observe **1** minute, then flip ("H5 delay1 flip") |
| intraday-continuation flip | flip, sized by the parent's caps | flip, **capped at 1 contract** ("H2 vote1 flip cap1") |
| direct near-VWAP action, control action | unchanged | unchanged |

So the test is the same simulator, the same bars, two knobs. `research/ftm/ftm_sim.py` now takes
`prior_bars` and `h2_cap`; RC1 is `(2, 0)` and reproduces the earlier study to the trade
(342 trades, $11,661, +0.1620 R); alpha.2 is `(1, 1)`. `research/ftm/ftm_alpha2.py`, output in
`results/ftm/alpha2_report.txt`.

**Verdict.** Alpha.2 is RC1 minus $641. The same 342 sessions trade, 321 of them identically;
the 21 that differ net $1,604 under RC1 and $964 under alpha.2. It still clears the matched
control (+0.1551 R against a random quarter-hour entry's +0.0612, p 0.006), and every
qualification from the RC1 study still outranks that: the top 5% of trades are **121% of net**,
the **15:30 conditional exit alone is $14,208 of an $11,020 net**, 2023 is flat, and the second
half of the sample earns half the first. Nothing in the alpha.2 policy touches any of that.

**The 15-minute CFD feeds cannot run this strategy.** The opening range is fifteen exact
one-minute bars, the admission test requires "15 exact one-minute constituents", and every
refinement branch observes the next one-minute bar and blocks the day if it is missing. On US30
and US100 15-minute data those rules are not approximable; the only honest run is NQ 1-minute,
as before.

## 1. The four variants, FixedDollar ($535 risk, cap 2, $50,000)

| variant | n | net | PF | win | R / trade | max DD | ret/DD | Sharpe | P(R ≤ 0) | streak |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| RC1 (prior 2 bars, no H2 cap) | 342 | $11,661 | 1.351 | 47.4% | +0.1620 | −$3,032 | 3.85 | 1.46 | 0.005 | 9 |
| H5 only (prior 1 bar) | 342 | $11,462 | 1.348 | 47.1% | +0.1551 | −$2,870 | 3.99 | 1.44 | 0.006 | 9 |
| H2 cap only | 342 | $11,220 | 1.339 | 47.4% | +0.1620 | −$3,032 | 3.70 | 1.42 | 0.005 | 9 |
| **alpha.2 (both)** | 342 | **$11,020** | 1.335 | 47.1% | **+0.1551** | −$2,870 | 3.84 | 1.40 | 0.006 | 9 |

The two knobs are independent and additive: H5 costs $199, the H2 cap costs $441, together
$641. Trade count, win rate, losing streak and the bootstrap are unchanged because the knobs
touch 21 sessions out of 342.

## 2. The 21 sessions that differ

**Sixteen prior-session flips fire one minute earlier.** Same side, same size; the fill moves
from the 10:02 / 10:17 / 10:32 open to 10:01 / 10:16 / 10:31. Eleven of the sixteen close
within a few dollars of the RC1 trade; the other five swing by the full stop or target because a
one-minute-different entry sits on the other side of a barrier: 2023-10-16 −$202 → +$21,
2025-04-08 +$248 → −$202, 2025-04-25 −$405 → −$5, 2025-09-03 +$202 → −$168. Net across the
sixteen: RC1 +$726, alpha.2 +$523. A one-minute delay is not a mechanism; it is which side of
a coin the entry lands on, and here four coins landed two each way.

**Five intraday flips are halved.** Same time, same side, one contract instead of two:
2023-09-13 +$315 → +$158, 2024-05-09 −$12 → −$6, 2024-06-24 −$129 → −$64, 2025-05-06 +$773 →
+$386, 2025-07-15 −$64 → −$32. Net across the five: RC1 +$883, alpha.2 +$441. The cap halves the
path's best trade along with its losers, and the path was net positive, so the cap costs money
on this sample. Its rationale in the header is defensive, and the sample cannot say whether it
will be; the sample says it was not.

## 3. Alpha.2 by action, and everything that carries it

| action | n | net | win | R / trade | contracts |
| --- | ---: | ---: | ---: | ---: | ---: |
| control (1.4.1-rc.1) | 242 | $9,530 | 47.9% | +0.18 | 1.35 |
| direct near-VWAP | 62 | $797 | 43.5% | +0.10 | 1.56 |
| H5 delay-1 flip | 16 | $523 | 56.3% | +0.18 | 1.12 |
| H2 vote-1 flip cap-1 | 22 | $171 | 40.9% | +0.05 | 1.00 |

**86% of the net is the unchanged parent's control action.** The three named alpha.2 actions
sum to $1,491 on 100 trades, and the direct action — the 1.8.0 headline in RC1 as well — is
still the weakest thing in the system per trade. As in the RC1 study, the 15:30 conditional
exit (66 trades, +$14,208) is worth more than the whole net, the stop (169 trades, −$29,968,
13.6% "win") is where the money leaves, and the target (57 trades, +$21,141) is where it comes
back. Longs earn $8,432 on 172 trades against shorts' $2,589 on 170. By year: 2023 −$149 on 39
trades, 2024 +$7,363 on 156, 2025 +$3,806 on 147. Top 1% of trades 31% of net, top 5% 121%;
first half +$6,370 (+0.20 R), second half +$4,650 (+0.11 R).

**Matched control.** Same sessions, same side, same stop and target in points, same managed
stop, same 15:30 rule and 16:00 flatten, random quarter-hour entry, 1,000 draws: control median
+0.0612 R [−0.0076, +0.1212], the rule +0.1551, excess +0.0938, p 0.006. The RC1 excess was
+0.1013 at p 0.004. The entry rule still carries something the exit machine does not; the
alpha.2 changes carried none of it.

**Sizing modes**, alpha.2: FixedDollar $11,020 / PF 1.335 / DD −$2,870 / Sharpe 1.40;
ClosedEquityPercent $16,360 / 1.386 / −$3,820 / 1.42; ConfidenceScaledPercent $21,404 / 1.250 /
−$7,432 / 1.03. Sizing creates no edge; it moves the drawdown.

## 4. What to take from it

* Alpha.2 is a labelling and policy refactor over RC1 with two behavioural changes worth −$641
  on this sample, both inside the noise of 21 sessions. Nothing here argues for it over RC1 and
  nothing argues against it; the parent is the strategy.
* The three qualifications from the RC1 study stand unchanged and are the thing to act on: a
  17-trade tail carrying 121% of net, a 15:30 exit rule worth more than the strategy, and a
  2023 that is flat. A version 1.8.1 that spent its effort on the exit rather than the entry
  ordering would be testing the part of the system that has the money in it.
* The TradingView port is `pine/ftm/FTM_ORB_MNQ_v1_8_0_ALPHA2.pine`: the verified RC1 port
  with the two policy knobs as inputs ("Prior-session observation bars" 1, "H2 flip
  contract cap" 1), 56 lines changed, lint clean; at 2 and 0 it is the RC1 port. The
  Python simulator with the same two knobs is its order model.
* Still unverified: NT8 parity (the file's own header says so), the basis-point features on a
  synthetic-level series, and anything on MNQ's real tick data rather than NQ's path.
