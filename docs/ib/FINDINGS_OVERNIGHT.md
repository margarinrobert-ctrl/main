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

## Status

The large-gap fade is **the best-supported candidate in this repository**: significant after FDR
across its own search grid, positive in both halves, and — uniquely — balanced across long and short
in both halves. It is still a 187-trade result concentrated in one year, sitting exactly on the
significance boundary, on one instrument.

Next: run it through the full protocol (walk-forward, PBO, deflated Sharpe), and test it on ES or CL,
where the auction mechanism should appear if it is real and will not if it is a 2025 NQ artefact.
