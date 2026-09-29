# US30 alone: four primaries, sixty timing cells, and the one thing that replicated

Asked to focus on US30 and keep working until an edge appeared. Six experiments, each with its
null in front, each decisive. No edge. What came out instead is the sharpest statement this branch
has of *why* US30 resists, and one structural fact that survived every block it was read on.

Blocks throughout: **A** = US30L 2016-10 .. 2022-12 (135,968 bars), **B** = US30L 2023-01 ..
2025-07 (57,974), **C** = `US30_ISO_15m` after US30L ends — 27,341 bars from a **different
provider** over a span no search here has touched.

## 1. Mean reversion, tested head-on, and dead before any barrier

Twelve independent routes on this branch have ended in mean reversion, and every US30 primary ever
tested here is a trend or breakout object. So the gap in the record was the primary those twelve
readings imply. Built mechanism-first: displacement `d = (close − close[n]) / ATR(14)`, side
**forced** to `−sign(d)` with no fitted direction, counterparty named as risk transfer (leveraged
intraday accounts being stopped out, hedgers who must re-hedge now), which predicts negative skew.

Forward return in ATR units, signed by the fade, Newey-West *t* at lag *h*:

| cell | h=1 | h=4 | h=16 | h=32 |
|---|---|---|---|---|
| unconditional drift | +0.0068 | +0.0255 | +0.0977 | +0.1819 |
| n=2 &#124;d&#124;≥2.5 fade | −0.0498 | −0.0988 | −0.0639 | +0.1149 |
| n=4 &#124;d&#124;≥2.5 fade | −0.0058 | −0.0578 | −0.1005 | −0.0583 |
| n=16 &#124;d&#124;≥1.5 fade | −0.0037 | −0.0181 | **−0.0884** (t −2.8) | −0.0920 |

**Every declared fade cell is negative.** And the mechanism's own conditioning variable contradicts
it: flow is proportional to |d|, so the reversal must grow with |d|, and the quintile gradient
**FALLS in 7 of 8 cells** (n=16/h=16: −0.0217, −0.0350, −0.0640, −0.0938, −0.1049). That is the
test that killed `STUDY_LEV_ETF_REBALANCE` in one run, reproduced.

## 2. The mirror is not drift — it is the 2023-25 regime

Displacement *continues*, monotonically in |d|. The obvious explanation is that US30 rose 144% and
a rule signed by `sign(d)` is long whenever d > 0, so each side was given **its own** drift
baseline. At h=16, n=16, |d| ≥ 1.5:

| block | drift | long excess | short excess |
|---|---|---|---|
| A research | +0.0977 | **+0.0769** | **+0.0775** |
| B holdout | +0.0265 | **−0.0654** | **−0.0730** |

Both sides beat drift on research, so it is *not* drift — and both invert on the holdout. The drift
itself collapses +0.0977 → +0.0265, which is `STUDY_TURTLE`'s instruction to print what the control
earned per block. Recorded as the second of two looks and **not adopted**; writing a momentum story
around a side flip is the failure the architecture exists to prevent.

## 3. The overnight premium is exposure, not timing

Zero fitted parameters — session boundaries are exchange facts, the side is long by construction.
It has the right shape everywhere: net **+0.0337 / +0.0092 / +0.0538 %** of price a session,
decaying across the research split and returning on the reserved forward feed, with research skew
**−1.08** exactly as the risk-transfer story predicts. 90.2% of the research block's whole move
arrived overnight. Then the null:

| block | overnight net | random same-length window | p | always-long |
|---|---|---|---|---|
| A research | +0.0337 | +0.0301 | 0.405 | Sharpe 0.51 (overnight 0.65) |
| B holdout | +0.0092 | +0.0302 | 0.782 | Sharpe 0.79 (overnight 0.27) |
| C forward | +0.0538 | +0.0443 | 0.383 | Sharpe 1.31 (overnight 1.66) |

**A random 15-hour window earns what the overnight leg earns, on all three blocks.** The clock
carries nothing; 8 of 10 years positive is what a rising market gives away. The mechanism's own
gradient (premium by prior realised vol) RISES on research and FALLS on the holdout.

## 4. Sixty timing cells with the exposure held fixed — fewer passes than chance

That null is the sharp instrument. So hold the exposure *exactly* fixed and ask only about the
timing: long at the next open, hold exactly L bars, exit at an open. No stop, no target, no barrier
tie-break, nothing to fit — the only thing a condition can change is **when**, and cost is identical
in both arms and cancels.

**The null is a circular shift of the condition's own mask within the block.** A condition selects
clustered bars, so a control drawn as independent random bars has too narrow a spread and passes
everything — the defect that made 17,121 of 27,786 tests "pass" in `research/edgelab`. Shifting the
mask circularly preserves its count and run-length structure **exactly** and destroys only its
alignment with price.

20 declared conditions in seven families — every family that has ever cleared anything on this
branch: volatility state, the clock, prior-session levels, distance from the MA200, participation
against a causal time-of-day baseline, displacement, momentum — × 3 holding lengths (4h / 16h / 64h).

> **1 of 60 cells clears p ≤ 0.05 against 3.0 expected by chance. 0 survive BH at q 0.10.**

Best five: `clk.overnight` L16 p 0.050, `vol.pct250≤0.2` L16 p 0.051, `ma.|d200|≤0.5` L256 p 0.094,
`ma.d200≥+1.5` L16 p 0.103, `lvl.near prior close` L64 p 0.105. Worst: `vol.atr/sma100≥1.2` L16 at
p 0.990. This is the cleanest available statement of why eight Donchian breakouts, the Initial
Balance, the VWAP-EMA spec, the volume profile and three primaries in this study all failed the
same way — **on US30 at 15 minutes, timing is worth nothing once exposure is held fixed.**

## 5. The one condition with a prior, tested as a replication — and it inverts

The top cell, `ATR percentile over its own last 250 bars ≤ 0.2`, is the same variable
`STUDY_V28` found as one of only **two survivors of 240 declared ATR-regime cells on US30**,
clearing both blocks at p 0.003. Two constructions, two framings, one variable — so this was scored
as a pre-registered replication, not a discovery.

| rung, L=16 | A research | B holdout | C forward |
|---|---|---|---|
| pct250 ≤ 0.1 | +0.0193 excess, **p 0.021** | −0.0154, **p 0.888** | −0.0124, p 0.746 |
| pct250 ≤ 0.2 | +0.0128, p 0.051 | −0.0148, p 0.942 | −0.0018, p 0.568 |
| **mirror** pct250 ≥ 0.8 | −0.0055, p 0.743 | **+0.0247, p 0.005** | −0.0113, p 0.815 |

The research block says calm, the holdout says the opposite at p 0.005, the reserved forward block
says neither. **Seventh move of a volatility-state sign on this branch.** Run both directions or
run neither.

## 6. What replicated: the mechanism, on all three blocks

The same run reproduced `STUDY_V22`'s mechanism on US30 — monotone, every block, including the
different-provider forward feed. Median forward realised volatility over 16 bars divided by the
trailing ATR at the signal bar, by ATR-percentile bucket:

| block | Q1 (calmest) | Q2 | Q3 | Q4 | Q5 | Q1−Q5 |
|---|---|---|---|---|---|---|
| A research | **3.364** | 2.936 | 2.535 | 2.177 | 1.926 | +1.438 |
| B holdout | **3.746** | 3.034 | 2.757 | 1.966 | 1.867 | +1.879 |
| C forward | **2.930** | 2.726 | 2.670 | 2.061 | 1.728 | +1.202 |

ATR(14) is backward-looking and volatility mean-reverts, so when ATR sits low in its own
distribution the next four hours realise **3.0–3.7×** it and when it sits high only **1.7–1.9×**.
That is not a direction call and no amount of it will become one — it is a statement about how far
price travels relative to the stop you just placed.

## 7. And its actionable form does not transfer

Signal stripped out entirely so only the stop can move the answer: long the first RTH bar's open,
out at the last RTH bar's close or the stop, one trade a session, zero conditions.

| block | adaptive − fixed 2.0N | **naive inverse** − fixed 2.0N |
|---|---|---|
| A research | **+0.0136** | −0.0081 |
| B holdout | **−0.0192** | **+0.0095** |
| C forward | +0.0126 | +0.0069 |

The falsifier wins on the holdout: the **naive inverse is the best policy there** (PF 1.206, Sharpe
0.91 against adaptive's 1.031 / 0.14), and on the forward block both are positive so nothing
separates. The reason is visible in one number — the *calm share itself moves*, 47.9% → 23.3% →
22.0%, so a rule keyed to a fixed percentile cut is a different rule in each block. And there is
nothing under it to improve: the base is null on A and B and **negative at every stop on C**
(−0.0007 to −0.0290 %/session, PF 0.856–1.007).

## Verdict

No edge on US30, and the reason is now measured rather than asserted:

1. **Timing is worth nothing here with exposure held fixed** — 1 of 60 declared cells at p ≤ 0.05
   against 3.0 expected, zero surviving BH, across every family that has ever worked on this branch.
2. **Both directions of the displacement family are closed** — the fade negative in every cell with
   its own gradient inverted, the mirror beating drift on both sides and then inverting on both.
3. **The overnight premium, which has the best shape of anything measured here, is a random
   15-hour window** on all three blocks.
4. **The volatility-state sign moved for the seventh time**, and this time the mirror cleared the
   holdout at p 0.005 while failing the other two blocks.

What survived is a **sizing fact, not an edge**, and it survived a reserved forward block from a
different provider: forward vol over trailing ATR runs 3.0–3.7× in the calmest quintile against
1.7–1.9× in the busiest. Any US30 system placing an ATR stop is placing a stop whose real width
varies by roughly **2×** with the volatility percentile, and that is worth knowing whether or not
the percentile ever becomes a filter — but keying a stop policy to a fixed percentile cut does not
transfer, because the share of bars in the calm bucket halves between blocks.

What would move this: **1-minute US30 bars** (the finest feed here is 15m, which is why the CVD
family could never be tested properly on this market — `STUDY_V61_US30`), or a genuinely
independent conditioning series. Not more parameter search: the exposure-matched test above is the
strongest form of that question and it came back below chance.

`research/mr30/`, `run_g0.py` … `run_g6.py`.
