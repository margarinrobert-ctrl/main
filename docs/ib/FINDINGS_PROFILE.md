# Volume / Market Profile on NQ — the first thing that survived

Full report: [`STUDY_VALUEAREA.md`](STUDY_VALUEAREA.md). Code: `src/lib/quant/volumeProfile.ts`,
`src/lib/quant/strategies/valueArea.ts`.

5-minute NQ, Dec 2022 – Dec 2025, 764 sessions with a prior profile, split 536 research / 228
holdout. Realistic fills, 3.80-tick round turn. **Every variant enforces a minimum 40-point target
and a reward-to-risk of at least 1:1**, as specified.

## Why this regime is different

Every prior study here was a scalp, where the 3.80-tick round turn was 10–25% of the move being
captured and was the binding constraint. At a 40-point (160-tick) minimum target, cost is **2.4% of
the target**. The cost wall that killed the scalping work simply is not the obstacle here, and that
alone changes what is findable.

## 1. Base rates first, before any strategy

Measured, not assumed. Sessions classified by where they opened relative to the *prior* session's
value area:

| open location | share | touch prior POC | touch prior VAH | touch prior VAL | re-enter VA | traverse to far edge |
| --- | --- | --- | --- | --- | --- | --- |
| below value | 27% / 26% | 43% / 41% | 27% / 24% | **66% / 59%** | 66% / 59% | 27% / 24% |
| inside value | 37% / 34% | **80% / 74%** | 69% / 67% | 59% / 67% | — | — |
| above value | 36% / 40% | 41% / 52% | **65% / 64%** | 27% / 29% | 65% / 64% | 27% / 29% |

*(research / holdout)*

Three things fall out, and they are the reason the strategy below looks the way it does:

- **The highest raw hit rate is the POC rotation from an in-value open (80%/74%) — and it is
  unusable here.** The median distance from open to prior POC on those sessions is 28/35 points, so
  most of those setups cannot offer a 40-point target at all.
- **The highest *usable* rate is the return to the near value-area edge after opening outside value
  (65%/64% above, 66%/59% below).** Opens outside value gap, so the distance is large: 89%+ of them
  are 40 points or more away.
- **The "80% rule" traverse completes 41% of the time conditional on re-entry — in both halves.**
  Remarkably stable, and still only 41%.

Scale check: prior value-area width median 97/131 points, session range median 199/270 points. A
40-point target is roughly 20% of a session. The constraint is comfortably feasible.

## 2. Nine pre-specified variants

| variant | research | holdout |
| --- | --- | --- |
| **M0 fade to near VA edge, 1:1** | n=290, **win 52%**, PF 1.12, t=0.94 | n=133, **win 54%**, PF 1.23, t=1.03 |
| **M0 fade to near VA edge, 1.33:1** | n=290, win 50%, **PF 1.19**, t=1.37 | n=133, win 51%, **PF 1.36**, t=1.49 |
| **M0 fade to near VA edge, 2:1** | n=290, win 42%, PF 1.19, t=1.30 | n=133, win 42%, PF 1.34, t=1.45 |
| M0 fade, gap ≥ 40pt only | n=225, win 52%, PF 1.13 | n=109, win 53%, PF 1.19 |
| M1 80% rule traverse, 1:1 | n=146, win 55%, PF 1.19 | n=76, win 50%, **PF 0.93** |
| M1 80% rule traverse, 2:1 | n=146, win 40%, PF 1.07 | n=76, win 34%, **PF 0.78** |
| M2 POC rotation, 1:1 | n=191, win 50%, PF 1.09 | n=78, win 42%, **PF 0.77** |
| M3 acceptance continuation, 1:1 | n=317, win 48%, **PF 0.88** | n=145, win 43%, **PF 0.65** |
| M3 acceptance continuation, 2:1 | n=317, win 34%, **PF 0.84** | n=145, win 36%, **PF 0.81** |

**The two most commonly published Market Profile plays both fail.** The 80% rule is positive in
research and negative in the holdout. POC rotation is worse. And betting on *acceptance* — the trend
day — loses in both halves at both settings, which is a consistent negative worth as much as any
positive: on NQ, opening outside value and staying there is not something to bet on.

What works is the least glamorous version: **open outside value, fade back to the near edge.**

## 3. M0 in detail, full sample

Both halves agreed in direction, so pooling is an estimate rather than an independent confirmation:

| | 1:1 | **1.33:1** | 2:1 |
| --- | --- | --- | --- |
| trades | 423 | 423 | 423 |
| win rate | **52.7%** | 50.4% | 42.3% |
| expectancy | 0.075 R | **0.143 R** | 0.160 R |
| profit factor | 1.171 | **1.260** | 1.251 |
| per-trade R, 95% CI | [0.002, 0.148] | **[0.056, 0.235]** | [0.041, 0.289] |
| HAC t | 1.92 | **3.00** | 2.47 |
| P&L, 1 contract | $63,868 | **$86,936** | $73,193 |
| max drawdown | 15.6% | **12.6%** | 10.7% |
| Sharpe | 0.72 | **1.05** | 0.99 |
| 2022/23/24/25 | all positive | all positive | all positive |

**The bootstrap CI on per-trade R excludes zero at all three settings**, and — for the first time in
this repo — **the long and short sides are both positive in both halves** (research L 0.10 / S 0.15,
holdout L 0.22 / S 0.12 at 1.33:1). Every previous candidate that looked promising had one side
carrying everything and flipping across the split.

## 4. What still fails, and it matters

**Gates passed: 5 of 10.**

- **P&L is concentrated in 2025: $57,995 of $86,936, i.e. 67%.** That breaches the 60% concentration
  gate. Every year is positive, but the last one is most of it — and 2025 was a good year for
  everything tested in this repo.
- **Monte Carlo is sobering at one contract on $50k.** Resampling with replacement: median max
  drawdown 32.7%, 95th percentile 73.9%, **P(25% drawdown) = 72.3%**. The equity curve's own 12.6%
  drawdown is a single lucky path. This needs materially more capital per contract, or a micro.
- **The parameter search is still selecting noise: PBO 0.524, deflated Sharpe 0.031.** The
  walk-forward is positive (+29 ticks, PF 1.275, 71% of folds, efficiency 0.41) but only t=0.95 on
  92 trades.
- The pooled t=3.00 uses the holdout, so it is not independent evidence.

**The honest status: a credible candidate, not a validated edge.** It is the only thing in this
repo that is positive in both halves on both sides with a CI excluding zero, and it is also
concentrated in one year and has not been tested outside NQ.

## 5. A test-infrastructure defect this study exposed

An explicit look-ahead check on the profile strategy initially **failed** — 40 mismatches out of 134
truncation points. Investigation showed the strategy was fine and **the test was wrong**.

Several strategies here carry per-session state (one trade per day, which side has been used, how
long price has held inside a level). That state only exists if the signal closure has been called on
every prior bar, which is how the backtester calls it. The old contract test called the closure
*once at the cut point*, comparing two different internal states and reporting an artefact.

The test now **replays** the closure over every bar from 0 to the cut on both the full and truncated
series and compares every decision. That is both correct and considerably stricter. All strategies
pass it.

This is worth flagging beyond this study: the previous version was giving false assurance on
`initial-balance`, `opening-range` and `value-area` — the three stateful strategies, which are also
the three most look-ahead-prone.

## 6. Next steps that would actually settle it

1. **ES and CL.** The concentration in 2025 and the NQ-only sample are the two biggest weaknesses.
   The auction-theory mechanism is instrument-agnostic, so it should appear elsewhere. If it does
   not, this is a 2025 NQ artefact.
2. **Position sizing.** At the measured drawdown distribution, one NQ contract per $50k is too much.
3. **Tick-level profiles.** These profiles spread each bar's volume uniformly across its range,
   which is right on average and wrong in detail. A true tick profile would sharpen the POC and the
   value-area edges, and the edge is defined by exactly those levels.
