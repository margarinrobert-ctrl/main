# FTM opening-range breakout on MNQ — the backtest, and what carries it

**What was run.** `FTM_OPENING_RANGE_BREAKOUT_MNQ_v1_8_0_RC1`, its own rules, walked over
1,048,575 real one-minute index-futures bars from 2022-12-26 to 2025-12-11 with MNQ contract
specs — 0.25 tick, $2 a point, the source's $2.50 sizing reserve, one tick of slippage. Sizing,
the managed stop, the conditional 15:30 exit and the 16:00 flatten are the source's, not mine.
`research/ftm/ftm_sim.py`, reported by `research/ftm/ftm_backtest.py`.

**Three caveats travel with every number.** The price series is **NQ, not MNQ** — the same
underlying future at a different multiplier, so the path is right and the specs make the dollars
MNQ's. The **levels are synthetic**: `NQ_1m` is a back-adjusted continuous contract, so anything
in basis points is distorted — `orb_bps`, the 120-day quantile and five of the fourteen model
features — which biases branch selection in a direction this study cannot sign. And the first
**116 admitted signals could not trade at all**, because the rule requires 120 completed sessions
of opening-range history before it may order.

---

## 1. The headline

Shipped defaults: FixedDollar, $535 risk, cap 2 contracts, $50,000 start.

| | |
| --- | ---: |
| trades | **342** |
| net | **$11,661** (23.3% on $50,000) |
| profit factor | **1.351** |
| win rate | 47.4% |
| expectancy | **+$34.10** · +12.81 points · **+0.1620 R** |
| average win / loss | $277 / −$185 |
| max drawdown | **−$3,032**, return over drawdown **3.85** |
| longest losing run | 9 |
| Sharpe, daily, zero-filled over every weekday | **1.46** |
| bootstrap P(mean R ≤ 0) | **0.005** |

**And it beats its matched control.** Same sessions, same side, same stop and target in points,
the same managed stop, the same 15:30 rule and the same 16:00 flatten — entered at a **random**
quarter-hour close of the same session, 2,000 draws:

| | R per trade |
| --- | ---: |
| the rule | **+0.1620** |
| control median | +0.0607 |
| control 5th–95th | [−0.0043, +0.1267] |
| **excess** | **+0.1013** |
| **p (control ≥ rule)** | **0.004** |

That null already contains the drift, the session timing and the whole exit machine, so the
excess is the entry rule. On a branch where five separate breakout triggers have failed this
gate, that is worth stating plainly.

---

## 2. Three things qualify it, and they matter more than the headline

**The top 5% of trades are 117% of net.** Seventeen trades out of 342 carry more than the whole
result; the other 325 lose money in aggregate. The top 1% alone is 29%. This is the same shape
`STUDY_KAMA_ENTRY.md` recorded before that rule decayed, and it means the equity curve is a
handful of outcomes wearing a strategy.

**2023 is flat.** By calendar year: 2023 **−$214** on 39 trades, 2024 +$7,292 on 156, 2025
+$4,583 on 147. Only 2024 is strong. The two halves of the trade sequence are +0.1952 R then
+0.1288 R, so it decays across the sample rather than growing.

**The exits, not the entries, are where the money is.** Split by exit reason:

| exit | n | net | R |
| --- | ---: | ---: | ---: |
| stop | 168 | −$30,200 | −0.81 |
| target | 58 | +$21,388 | +1.82 |
| **conditional 15:30** | 67 | **+$14,687** | +0.89 |
| 16:00 flatten | 49 | +$5,786 | +0.52 |

The conditional 15:30 exit alone contributes **more than the entire net result**. Whatever this
system is, its most valuable single component is the rule that closes a trade at 15:30 when
`closeR` sits outside [0R, +1R).

---

## 3. The 1.8.0 headline feature is the weakest path in the system

Every trade is tagged with the branch that produced it:

| decision path | n | net | win | R |
| --- | ---: | ---: | ---: | ---: |
| parent, no entry condition | 211 | **+$9,675** | 48.8% | **+0.20** |
| **RC1 direct (first signal near VWAP)** | 62 | +$797 | 43.6% | **+0.10** |
| prior-session disagreement reverse | 16 | +$722 | 62.5% | +0.33 |
| intraday continuation reverse | 22 | +$613 | 40.9% | +0.05 |
| intraday continuation keep | 19 | +$257 | 47.4% | +0.13 |
| weak-signal delay | 7 | −$32 | 42.9% | +0.13 |
| **high-volatility touch vote** | 5 | **−$370** | 20.0% | **−0.36** |

> **THE PLAIN PATH IS THE STRATEGY.** 211 of 342 trades take no refinement branch at all and earn
> **+0.20 R**, twice the RC1 direct action's +0.10 and better than every refinement branch except
> a 16-trade one. The 1.8.0 release note describes the direct action as the frozen headline
> behaviour; on this sample it is a **dilution**, not an improvement.

The high-volatility touch vote is negative on 5 trades — too few to judge, but nothing supports
keeping it. The prior-session disagreement reverse is the best branch at +0.33 R on 16 trades,
which is also too few to act on.

---

## 4. The sizing modes

Identical signals and exits; only the contract count differs.

| mode | trades | net | PF | max DD | return/DD |
| --- | ---: | ---: | ---: | ---: | ---: |
| FixedDollar (shipped) | 342 | $11,661 | 1.351 | −$3,032 | **3.85** |
| ClosedEquityPercent | 342 | $16,932 | **1.395** | −$4,044 | **4.19** |
| ConfidenceScaledPercent | 342 | **$24,676** | 1.275 | −$7,800 | 3.16 |

ConfidenceScaledPercent makes the most dollars and is the worst risk-adjusted answer: it drops
the defensive one-contract cap in high-volatility and countertrend regimes, which is exactly where
the drawdown comes from. Its profit factor is the lowest of the three and its drawdown is 2.6× the
FixedDollar figure. **The defensive caps are the risk model**, the same conclusion the original
Turtle programme reached about its unit caps.

---

## 5. Control-flow census

Over 473 eligible sessions: 458 admitted signals, 82 geometry rejects, 31 touch vetoes, 3
prior-session overrides, 7 nearest-neighbour overrides, 79 RC1 direct decisions, 379 parent
decisions, 9 weak-signal delays, 6 high-volatility votes of which 5 flipped, 20 prior-session
reversals, 24 intraday keeps, 26 intraday reversals, 374 model labels recorded, 116 warm-up
skips, 13 fail-closed events, and 342 entries split 172 long / 170 short.

The direction model fires rarely: **7 nearest-neighbour overrides and 3 prior-session overrides
in 458 admitted signals.** Whatever the quarterly 15-NN contributes, it contributes it 1.5% of the
time — the machinery is far larger than its effect.

---

## 6. What would change the verdict

This is one instrument over three calendar years with an effective sample of about two and a half,
on synthetic levels, with 117% of the net in the top 5% of trades. It clears its matched control,
which most things here do not. What it has not had: a second instrument, a block that chose
nothing, an NT8 Analyzer reconciliation, or a real MNQ series with true levels so the
basis-point features are undistorted. The first and last are the cheapest and would be worth
more than any parameter change.
