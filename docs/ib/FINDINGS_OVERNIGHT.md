# Overnight structure and gaps — the strongest result in this repo

Code: `src/lib/quant/overnight.ts`. NQ, full 23-hour CME series, 764 sessions, split 534 research /
230 holdout.

Every prior study filtered to the 09:30–16:00 cash session and discarded two thirds of the data —
including the part of the day where the gap is *formed*. The gap and the overnight range are the
only information about today that exists before the cash open, so this is where a day-level anomaly
would live.

## 1. Gap fill is real, monotone, and replicates

Does the cash session trade back through the prior cash close?

| bucket | research | holdout | median minutes to fill |
| --- | --- | --- | --- |
| all sessions | 59.6% | 60.0% | 17 |
| **\|gap\| < 0.25 prior range** | **78.6%** | **83.8%** | 5 |
| \|gap\| 0.25–0.6 | 53.4% | 44.3% | 50 |
| **\|gap\| ≥ 0.6** | **32.5%** | **39.3%** | 62 |
| overnight range narrow (bottom third) | 72.1% | 69.7% | 8 |
| overnight range wide (top third) | 47.2% | 53.1% | 39 |

Monotone in gap size and stable across the split. Small gaps fill about 80% of the time; large gaps
about a third.

## 2. And the fill rate points the WRONG WAY as a trade

Fade the gap at the cash open, target the prior close, stop at a multiple of the gap. FDR applied
across the whole 12-cell grid actually examined, not just the winner:

| cell | n | E(R) | t | raw p | **BH q** |
| --- | --- | --- | --- | --- | --- |
| **\|gap\| < 0.25 @ 2:1** | 302 | **−0.100** | −2.43 | 0.015 | **0.098 ✓** |
| **\|gap\| ≥ 0.6 @ 2:1** | 187 | **+0.220** | +2.28 | 0.022 | **0.098 ✓** |
| **\|gap\| ≥ 0.6 @ 1:1** | 187 | **+0.131** | +2.25 | 0.025 | **0.098 ✓** |
| \|gap\| < 0.25 @ 1:1 | 302 | −0.116 | −2.03 | 0.042 | 0.127 |
| all gaps @ 1:1 | 733 | −0.027 | −0.78 | 0.434 | 0.631 |
| \|gap\| 0.25–0.6 (all settings) | 244 | ≈ −0.03 | ≈ −0.6 | > 0.47 | > 0.63 |

**The 80%-fill bucket is significantly NEGATIVE. The 35%-fill bucket is significantly POSITIVE.**

The mechanism is the same trap the Market Profile 80% rule falls into, now measured directly: a high
*eventual-touch* rate is not a win rate. For a small gap the target is close, but so is the stop, and
price wanders through both — the fill often arrives *after* the stop was hit. For a large gap both
levels are far, there is room for the trade to work, and when it does the payoff is large.

Anyone selling "gaps fill 80% of the time, so fade them" has the sign backwards on this market.

## 3. The candidate: fade large gaps

Gaps ≥ 0.6 of the prior cash range, faded toward the prior close, stop at half the gap (2:1):

| | n | E(R) | t | p |
| --- | --- | --- | --- | --- |
| research | 126 | +0.157 | 1.34 | 0.18 |
| holdout | 61 | **+0.350** | 2.07 | 0.039 |
| **full** | **187** | **+0.220** | **2.28** | **0.022** |

**The long/short decomposition is what makes this different from every previous candidate:**

| | long (faded gap-down) | short (faded gap-up) |
| --- | --- | --- |
| research | +0.122 (n=58) | +0.186 (n=68) |
| holdout | +0.428 (n=33) | +0.259 (n=28) |
| full | +0.233 (n=91) | +0.207 (n=96) |

**Both sides positive in both halves, with near-equal contributions.** Every earlier candidate in
this repo — the 15-minute ORB, the value-area fade, the golden cross — had one side carrying the
result and flipping across the split, which is the signature of fitting the index trend. This one
does not have that.

Other properties: at most one trade per session (fires on 24.5% of days), Monte Carlo resampling
gives a median drawdown of 23.3% and P(losing overall) of 1.1%.

## 4. What is still wrong with it

- **74% of P&L falls in 2025**, and 2024 contributed almost nothing (+$2,066 at 2:1, −$11,774 at 1:1).
  The same concentration that weakens every result in this repo.
- **n = 187.** Above the 100-trade minimum, not comfortably.
- **q = 0.098 is exactly at the boundary.** It survives FDR at 0.10 and would not at 0.05.
- One instrument, one three-year period.
- The 0.6 threshold was chosen from these buckets. The buckets were pre-specified as three, and the
  FDR above prices the whole grid, but it is still a threshold selected on this data.

## 5. Overnight range predicts cash range

| | correlation | t |
| --- | --- | --- |
| research | 0.465 | 12.1 |
| holdout | 0.520 | 9.2 |

Median 140-point overnight range precedes a 200-point cash range; 204 precedes 270. This replicates
the volume→range result from the volume study through an independent measure, and like it, it is a
**sizing and stop-distance input, not a direction call**.

## 6. Nothing directional survived

Ten directional conditions (fade/follow the gap, overnight close position, overnight range
conditioning), drift-removed and FDR-corrected: **every q = 0.859**, and the research/holdout signs
flip on almost all of them — "overnight strong close → follow" is +6.5 points/day in research and
−21.2 in the holdout. A clean null, and a useful check that the machinery is not simply generating
positives.

## 7. The full protocol — and it is largely unfavourable

Run through the standard gates on 1-minute bars with the full 23-hour series retained:

| | result |
| --- | --- |
| walk-forward OOS | 116 trades, +18.4 ticks, PF 1.106, Sharpe 0.35, **t = 0.53** |
| walk-forward efficiency | **−0.16** |
| folds profitable | 44% |
| **PBO** | **0.968** |
| deflated Sharpe | 0.315 |
| **gates passed** | **3 / 10** |

**PBO of 0.968 is the worst number in this repository.** It says that when the procedure picks a
best configuration in-sample, that configuration lands in the bottom half out-of-sample almost every
time. The parameter space around this strategy is noise-dominated and must not be searched.

The holdout table shows the same thing from the other side:

| configuration | trades | win | E(R) | PF | t |
| --- | --- | --- | --- | --- | --- |
| **pre-specified (0.6 threshold, 2:1)** | 60 | 55% | **0.483** | **2.119** | **2.71** |
| in-sample optimum | 44 | 48% | 0.154 | 1.672 | 1.45 |
| walk-forward modal | 75 | 52% | 0.063 | 1.493 | 1.51 |

**The pre-specified rule beats both optimised versions by a wide margin.** That is the same pattern
as every other study here, in its most extreme form: the economically motivated single threshold
carries the result and searching around it destroys it.

## 8. Robustness to entry timing — the one probe it passes cleanly

The original measurement entered at the cash open, which nobody can actually fill. Re-run at
increasing delays (1-minute bars):

| delay | full-sample E(R) | t | long | short |
| --- | --- | --- | --- | --- |
| 1 min | +0.207 | 1.89 | +0.172 | +0.239 |
| 2 min | +0.146 | 1.36 | +0.111 | +0.180 |
| 5 min | +0.139 | 1.62 | +0.141 | +0.136 |
| 10 min | +0.123 | 1.31 | +0.086 | +0.158 |
| 15 min | +0.191 | 2.29 | +0.219 | +0.165 |
| 30 min | +0.202 | 2.34 | +0.280 | +0.129 |

Positive at every delay across a thirty-fold range, with both sides positive throughout. **The
result is not an artefact of filling at the opening print**, which was the obvious objection.

But the split tells the rest: the research half is positive and insignificant at *every* delay
(E between +0.023 and +0.130, t between 0.19 and 1.16), while the holdout is strong at every delay
(E +0.240 to +0.483, t 1.86 to 3.50). The effect is carried by the recent period at every setting.

## Status


The large-gap fade is **the best-supported candidate in this repository and still not a validated
edge.** In its favour: it survives FDR across its own search grid at q = 0.098, it is positive in
both halves, it is uniquely balanced across long and short in both halves, and it is robust to entry
timing across a thirty-fold range of delays.

Against it, and decisively: it **passes 3 of 10 gates**, its walk-forward t is 0.53 with negative
efficiency, and its **PBO is 0.968** — the worst in this repo. The parameter space is noise. The only
version that works is the single pre-specified threshold, its research half is insignificant at every
setting tested, and roughly three quarters of the P&L falls in 2025.

The defensible reading is that there is a real mechanism here — large overnight gaps are priced in
thin liquidity and the cash session drags them back — that shows up consistently in sign and is too
small, too recent and too sample-limited to call established.

Next: run it through the full protocol (walk-forward, PBO, deflated Sharpe), and test it on ES or CL,
where the auction mechanism should appear if it is real and will not if it is a 2025 NQ artefact.
