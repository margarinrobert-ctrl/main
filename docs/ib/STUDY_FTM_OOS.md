# FTM ORB 1.8.0-alpha.2: out-of-sample, robustness, forward-test design, Monte Carlo

1.05M one-minute NQ bars, 342 trades 2023-09-08 to 2025-10-31, MNQ, costs in. Split at 2025-01-01
(195 in-sample / 147 out-of-sample).

**CAVEAT THAT STAYS ATTACHED: this is a POST-HOC split of a sample this branch has already read
whole three times** (`STUDY_FTM_ORB_BACKTEST`, `STUDY_FTM_ANATOMY`, `STUDY_FTM_ALPHA2`). The
out-of-sample block is the least-contaminated slice available, not a clean holdout.

## 1. THE PUBLISHED p 0.004 IS AN IN-SAMPLE STATISTIC

`STUDY_TOP5` recorded the error and this reproduces it exactly, on both versions:

| version | block | n | rule R | control R | excess | p |
|---|---|---|---|---|---|---|
| RC1 | ALL | 342 | +0.1620 | +0.0611 | +0.1009 | **0.004** |
| RC1 | in-sample | 195 | +0.1942 | +0.0602 | +0.1339 | **0.005** |
| RC1 | OUT-OF-SAMPLE | 147 | +0.1194 | +0.0555 | +0.0639 | **0.151** |
| alpha.2 | ALL | 342 | +0.1551 | +0.0611 | +0.0939 | 0.009 |
| alpha.2 | in-sample | 195 | +0.1999 | +0.0602 | +0.1396 | **0.005** |
| alpha.2 | OUT-OF-SAMPLE | 147 | +0.0956 | +0.0555 | +0.0401 | **0.257** |

Note the control's own level: a random quarter-hour entry with identical management earns
**+0.056 R**, so this is not a case of clearing a null that loses money — the null is profitable,
and out of sample the rule adds +0.040 R to it and cannot be distinguished from it.

**THE ALPHA.2 POLICY CHANGE HELPS IN SAMPLE AND HURTS OUT OF SAMPLE**: +0.1999 against RC1's
+0.1942 in sample, +0.0956 against +0.1194 out of sample. That is the wrong shape for the change
itself, independent of the parent.

## 2. THE TWO ALPHA.2 KNOBS

**`h2_cap` HAS NO EFFECT ON R AT ALL.** Per-trade R is +0.1551 at every value of the cap, and
cap 0, 2 and 3 produce the IDENTICAL net ($11,462); only cap=1 differs, at $11,020. The cap never
changes which trade is taken or how it resolves — it only reduces SIZE on a handful of intraday
flips, and it is worth **-$441 and nothing else**. Two of its four settings are inert.

**`prior_bars` has no gradient and alpha.2 picked its worst rung.** Out-of-sample R by observation
bars: **1 → +0.0956**, 2 → +0.1194, 3 → +0.1041, 4 → +0.1307, 5 → +0.1208. Non-monotone, wandering,
and alpha.2's choice of 1 is the worst of five while RC1's 2 is middling and the best is 4, which
nobody chose. In-sample R is IDENTICAL (+0.1942) at 2, 3, 4 and 5 — the axis barely binds.

## 3. THE FOUR COMPATIBILITY GATES IMPROVE THE RESULT

| configuration | n | net | R_is | R_oos |
|---|---|---|---|---|
| source values (warm ON, lb 120, strict ON) | 342 | $11,021 | +0.1999 | +0.0956 |
| shipped defaults (warm OFF, lb 40, strict OFF) | 454 | $13,168 | +0.1498 | **+0.1222** |
| strict contiguity only | 454 | $14,946 | +0.1667 | **+0.1321** |
| lookback 120 only | 454 | $15,038 | +0.1785 | +0.1070 |

The deviations made for TradingView compatibility are not a compromise here — they raise both the
trade count and the out-of-sample per-trade result. The lookback axis is flat in R_oos across
20/40/60/90/120 (0.1197 / 0.1222 / 0.1144 / 0.1065 / 0.1070), confirming `STUDY_FTM_ANATOMY`'s
finding that the 120-session warm-up was never earning its constraint.

## 4. DROP-ONE: 8 OF 12 COMPONENTS IMPROVE THE OUT-OF-SAMPLE RESULT WHEN REMOVED

Baseline R_oos +0.0956.

| removed | R_is | R_oos | net |
|---|---|---|---|
| **SIDE = always long** | +0.1065 | **+0.2564** | $13,032 |
| no profit target | +0.2356 | **+0.1326** | $13,654 |
| no admission geometry | +0.1395 | +0.1163 | $10,210 |
| no kNN direction model | +0.1902 | +0.1074 | $11,141 |
| no 15:30 conditional exit | +0.2022 | +0.1062 | $11,250 |
| no high-ORB regime | +0.1935 | +0.1051 | $11,047 |
| no prior-day override | +0.1999 | +0.1034 | $11,048 |
| *as shipped* | +0.1999 | +0.0956 | $11,021 |
| SIDE = coin flip | -0.0162 | +0.0708 | $3,201 |
| no touch veto | +0.2030 | +0.0759 | $10,939 |
| **no entry refinement** | +0.2105 | **-0.0105** | $8,601 |
| SIDE = always short | +0.1153 | -0.1583 | -$46 |

**ALWAYS-LONG WITH THE IDENTICAL MACHINE EARNS 2.7x THE RULE OUT OF SAMPLE** (+0.2564 against
+0.0956, PF 1.663 against 1.252) while being WORSE in sample (+0.1065 against +0.1999). The whole
direction apparatus — kNN, prior-day override, refinement branches — helps where it was developed
and hurts where it was not.

**The direction call is worth +0.025 R over a coin flip out of sample against +0.216 in sample.**
`STUDY_FTM_ANATOMY` measured the side worth +0.10 R over a coin flip on the whole sample; split, it
is almost all in-sample.

No take profit wins again — the **24th** independent time on this branch. Only the entry refinement
is unambiguously load-bearing out of sample, and it is the component `STUDY_FTM_ANATOMY` already
flagged as the fragile part.

## 5. MONTE CARLO

| block | $/trade | 95% CI | P(mean<=0) | realised DD | MC p50 | MC p99 | DD percentile |
|---|---|---|---|---|---|---|---|
| ALL | +32.22 | [+2.43, +62.19] | 0.018 | $2,870 | $2,907 | $5,545 | 0.477 |
| in-sample | +37.00 | [-1.41, +75.89] | 0.030 | $2,870 | $2,173 | $4,129 | **0.839** |
| OUT-OF-SAMPLE | +25.89 | **[-21.33, +74.74]** | **0.138** | $2,298 | $2,452 | $4,669 | 0.414 |

The out-of-sample block does not separate from zero. **MC p99 drawdown is $4,669 against a realised
$2,298 — 2.0x — and that is the sizing number.**

**COST IS NOT THE OBJECTION, AND R IS BLIND TO IT.** Slippage and cost varied 0x to 4x inside the
walk: net falls linearly $12,181 → $7,541 and the strategy stays profitable at 4x, while **R/trade
is IDENTICAL at every multiplier (+0.155)** — R here is a gross measure, so quote dollars whenever
cost is the question. Session dropout: out of sample, keeping a random 50% of sessions still
finishes profitable 85% of the time.

## 6. THE FORWARD TEST, AND WHY IT NEEDS A DIFFERENT MONITOR THAN S3

The rule fires **160 times a year**. Per-trade standard deviation out of sample is **$295**.

| forward trades | months | 95% CI half-width |
|---|---|---|
| 40 | 3.0 | ±$92 |
| 100 | 7.5 | ±$58 |
| 159 | 12.0 | ±$46 |
| 300 | 22.6 | ±$33 |

**500 trades — 3.1 years — to show the out-of-sample mean ($25.89) differs from zero at 95%.**
Simulated on whole sessions: under the OOS expectation 40 trades finishes profitable 71% of the
time and 159 trades 85%; under the in-sample expectation, 80% and 96%.

**AND THE S3 SHORTCUT DOES NOT WORK HERE.** S3's average win and average loss are near-identical,
so its edge IS the win rate and a proportion converges fast. FTM's payoff ratio is **1.38:1**
(avg win $270, avg loss -$196), break-even **42.1%**, actual **47.6%** — the edge is in the PAYOFF,
which converges slowly. A win-rate count decides nothing here.

**What to monitor instead is the EXIT MIX**, because it is what the P&L is made of. Out of sample
it must reproduce: **stop 50%, cond1530 20%, close1600 16%, target 14%**. And the shares of net:
the conditional 15:30 exit alone is **+206% of out-of-sample net**, targets +188%, and stops
**-368%**. A live mix far from that means the port is not doing what the research did — which is a
different failure from the edge being absent, and it is the one a short forward test can actually
catch.

## Verdict

Out of sample the strategy is profitable ($3,806 on one MNQ over 147 trades) and **nothing about it
separates from a null**: it fails its matched control (p 0.257), fails to clear zero (P 0.138), is
beaten 2.7x by always-long with its own exit machine, and 8 of its 12 components improve it when
removed. What it demonstrably owns is the **exit machine**, not the entry.

Do not size it on 40 trades — that window cannot separate the in-sample expectation from the
out-of-sample one from zero. Run it to verify the port against the exit-mix targets above, and
treat any sizing decision as needing 300+ trades.

`research/ftm/run_o1.py`, `run_o2.py`, `run_o3.py`, `results/ftm2/ftm2_battery.png`.
