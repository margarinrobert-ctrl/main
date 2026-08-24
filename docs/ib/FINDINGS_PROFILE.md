# Volume / Market Profile on NQ — the only candidate, and its limits

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

## 3b. Cross-timeframe check — and a material downgrade

The same strategy, same logic, rebuilt from **1-minute** bars. The first comparison was confounded
(`entryDelayBars: 3` is 15 minutes on 5-minute bars and 3 minutes on 1-minute bars), so the delay is
matched in wall-clock terms here:

| | trades | win | expectancy | PF | HAC t | per-trade R 95% CI |
| --- | --- | --- | --- | --- | --- | --- |
| **5-minute bars**, full sample | 423 | 50.4% | **0.143 R** | 1.260 | **3.00** | **[0.048, 0.234]** |
| **1-minute bars**, delay matched | 441 | 46.5% | **0.068 R** | 1.170 | 1.35 | **[−0.022, 0.160]** |
| 1-minute, 3-min delay | 456 | 45.2% | 0.029 R | 1.125 | 0.56 | [−0.074, 0.136] |
| 1-minute, 30-min delay | 426 | 47.7% | 0.074 R | 1.086 | 1.36 | [−0.036, 0.186] |

**The edge roughly halves on 1-minute bars and loses significance.** Every 1-minute variant has a
confidence interval containing zero, and every one has a weak research half (PF 0.94–1.04) carried by
the holdout.

The likely mechanism is not subtle and it does not favour the 5-minute number. **Finer bars resolve
stop hits more accurately.** On a 5-minute bar, a dip that touches the stop and recovers within the
bar is only caught if the bar's low reaches the level; on 1-minute bars far more of those dips are
correctly booked as stop-outs, at the right moment. The engine's pessimistic same-bar rule helps but
does not close the gap, because it only fires when a single bar contains *both* levels.

**So the 1-minute figure is the better estimate, not the worse one.** The honest restatement:
expectancy is around **0.07 R with a confidence interval containing zero**, not 0.143 R with an
interval excluding it. The direction survives on every timeframe and both halves; the significance
does not.

This is a downgrade of the headline in section 3, and it is stated here rather than buried because
the 5-minute number was reported first.

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

**The honest status: a directionally consistent effect that is not statistically established.** It
is the only thing in this repo positive in both halves on both sides, and on the timeframe that
measures stops most accurately its confidence interval contains zero. It is also concentrated in one
year and untested outside NQ.

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

## 5b. The constructs the first pass left untested

"Do not assume the common strategies are optimal" means testing the ones that make specific,
falsifiable claims — not just the popular ones. Two remained, both now built and tested on **both
timeframes**, with the entry delay matched in wall-clock terms:

### Naked (virgin) points of control

A prior session's POC that price has not traded through since. Auction theory calls it unfinished
business and argues it acts as a magnet. It is one of the few Market Profile ideas that names a
specific price rather than a zone, which is what makes it testable.

| variant | 5m full sample | 1m full sample |
| --- | --- | --- |
| trade toward nearest naked POC, 1:1 | R −0.006, PF 0.96, CI [−0.07, 0.06] | R 0.004, PF 0.98, CI [−0.06, 0.06] |
| same, 1.33:1 | R −0.020, PF 0.91 | R 0.012, PF 1.01 |
| same, 2:1 | R 0.020, PF 1.01 | R 0.006, PF 1.00 |
| **fresh naked POCs only (≤ 5 sessions)** | R 0.053, PF 1.09, t 1.26 | R 0.049, PF 1.12, t 1.29 |

**The magnet claim is not supported.** Around 730 trades per timeframe and every confidence interval
contains zero. Freshness helps in the expected direction — a POC left naked for a week is weaker
than one left naked yesterday — but the research half is roughly ten times the holdout half on 1m
(0.063 → 0.006), so even that is not carried out of sample.

### Low-volume nodes

Two incompatible stories are told about thin prices inside value: that price **rejects** from them
(the auction failed there before), and that price **accelerates** through them (nothing to slow it
down). Both are tested; they cannot both be right.

| variant | 5m full sample | 1m full sample |
| --- | --- | --- |
| LVN rejection → target the POC, 1:1 | R 0.008, PF 1.50, win 17% | R −0.075, PF 0.81, **1m holdout t = −1.97, CI [−0.36, −0.01]** |
| LVN acceleration, 1:1 | R −0.055, PF 0.87 | R −0.091, PF 0.81 |
| **LVN acceleration, 2:1** | R −0.166, PF 0.73, t −1.73 | **R −0.185, PF 0.71, t −2.24, CI [−0.35, −0.02]** |

**Neither story works, and the acceleration story is significantly wrong.** Trading breaks through
low-volume nodes loses on both timeframes, in both halves, at both reward-to-risk settings, and on
1-minute data the full-sample confidence interval excludes zero. This is the strongest *negative*
result in the whole repository, and like the other consistent negatives — pullback entries, the ORB
retracement, the 50-MA pullback — it is more reliable than any of the marginal positives, because it
replicates everywhere it is tested.

The rejection story is merely unsupported rather than significantly wrong, but it too degrades on
the finer timeframe.

### The complete Market Profile search

Seven distinct constructs, all with a 40-point minimum target and at least 1:1 reward-to-risk:

| construct | verdict |
| --- | --- |
| **fade to near value-area edge** | **the only positive; ~0.07 R on 1m, CI containing zero** |
| 80% rule traverse | positive in research, negative in holdout |
| POC rotation from an in-value open | highest raw hit rate (80%) but unusable at 40 points; fails holdout |
| acceptance / trend-day continuation | negative in both halves |
| naked POC magnet | flat; every CI contains zero |
| low-volume node rejection | negative, significantly so on 1m holdout |
| low-volume node acceleration | **significantly negative, CI excluding zero on 1m** |

## 6. Next steps that would actually settle it

1. **ES and CL.** The concentration in 2025 and the NQ-only sample are the two biggest weaknesses.
   The auction-theory mechanism is instrument-agnostic, so it should appear elsewhere. If it does
   not, this is a 2025 NQ artefact.
2. **Position sizing.** At the measured drawdown distribution, one NQ contract per $50k is too much.
   And size against the 1-minute expectancy of ~0.07 R, not the 5-minute 0.143 R.
3. **Tick-level profiles.** These profiles spread each bar's volume uniformly across its range,
   which is right on average and wrong in detail. A true tick profile would sharpen the POC and the
   value-area edges, and the edge is defined by exactly those levels.
