# MA cross + Donchian 30/20 + regime: the long side validates on five blocks, the short side is one year

36 engineered features, 180 information-coefficient tests, 18 single-indicator rule tests, 22
combinations. Selection on the **research two-thirds of a nine-year US100 file** only; four
independent blocks read once at the end. Costs charged as **3.7% of the 2N stop on every market**.

**Feeds.** A new tab-separated, newest-first file arrived and was identified by measurement, not by
its name: against US100 at a −7h shift the median level gap is **11.1 points** and the return
correlation **0.9399**, against 21,780 points for US30 — it is US100 on a New York +7 clock, and it
runs **2016-11 → 2025-10**, nine years. The ISO US100 feed is a *different provider* (that 11.1-point
gap) whose 2026 tail post-dates the long file entirely, which makes it a genuine forward block.

| feed | bars | span |
| --- | ---: | --- |
| US100 long (research + locked) | 206,703 | 2016-11 → 2025-10 |
| US100 ISO (different provider) | 46,700 | 2024-08 → 2026-08 |
| US30 ISO | 48,937 | 2024-08 → 2026-08 |
| XAU | 494,235 | 2004-06 → 2026-01 |

## The information coefficient says a one-bar scalp is arithmetically dead

180 tests, Newey–West with h lags for the overlap, Benjamini–Hochberg over the whole family.
**22 survive BH. The largest |IC| anywhere is 0.0305. Not one reaches 0.05.**

The translation into points is the finding:

| horizon | sd of forward move | IC 0.03 is worth | vs 1.215 round turn |
| --- | ---: | ---: | --- |
| h=1 | 12.94 pts | 0.39 pts | **0.32× — cannot pay** |
| h=4 | 27.16 pts | 0.81 pts | **0.67× — cannot pay** |
| h=16 | 59.82 pts | 1.79 pts | 1.48× — pays |

**At the one-bar scalping horizon you need IC ≥ 0.10 to clear costs, and the best measured is
0.0305.** That is not a tuning problem; it is arithmetic, and it settles the timeframe question
before any rule is written.

Worse for a trend reading: **every price-versus-MA feature is mean-reverting at h=1** —
`close_pos` −0.0272, `ma12_100_px_vs_s` −0.0201, `ma13_48_px_vs_s` −0.0196 — and ~zero at h=16. The
one exception is `ma13_48_fresh` (a cross within 8 bars), positive at both horizons. A decile split
confirms the rest: `ma13_48_gap` runs D1 −0.80, **D5 +3.65**, D10 +1.95 — non-monotone, a hump, not
a signal. ADX deciles are flat (spread +0.43 against a 1.22 cost) and Choppiness deciles are flat
(−0.13).

## Every indicator alone fails, on both sides

Exits held constant across all 18 rows — 2.0N stop, 20-bar channel, one unit, no target — so the
rows are comparable. Each scored against same-size random draws from the *no-indicator* population
of the same geometry.

**Long population** n=8,821, PF 1.11, +1.26 pts/trade. **Short population** n=11,792, PF 0.92,
−0.69 pts/trade — US100 rose across the span, so shorts lose by existing.

| best of each family | long p | short p |
| --- | ---: | ---: |
| MA 13/48 (cross, state, fresh) | 0.355 | 0.841 |
| MA 12/100 (cross, state) | 0.742 | 0.440 |
| ADX ≥ 25 alone | **0.994** | 0.625 |
| Choppiness ≤ 50 alone | **0.990** | 0.646 |
| regime_trend alone | 0.895 | 0.537 |
| Donchian 30 alone | 0.676 | 0.350 |

**Not one of 18 clears p < 0.05.** ADX and Choppiness are the *worst* standalone triggers, which is
what they should be — they are regime readings, not directional ones.

## The combination is where it lives, and only long

Donchian 30 always the trigger; the MAs and the regime as filters. Each filter added improves it
monotonically, which a random filter does not do:

| long combination | n | PF | pts/trade | Sharpe | p |
| --- | ---: | ---: | ---: | ---: | ---: |
| Donchian 30 alone | 2,217 | 1.04 | +0.79 | 0.24 | 0.690 |
| + ADX ≥ 25 | 1,223 | 1.08 | +1.42 | 0.40 | 0.455 |
| + both MA pairs up | 1,036 | 1.18 | +3.03 | 0.89 | 0.121 |
| **+ regime_trend instead of bare ADX** | **911** | **1.24** | **+3.87** | **1.14** | **0.064** |
| *inverted* (both MAs **down**) | 677 | 0.87 | −3.09 | −0.73 | 0.988 |

The inverse scoring −3.09 at p 0.988 is the useful half of that table: the filter has the **right
sign**, which a lottery ticket does not.

### Read once, on four independent blocks

| block | n | PF | pts/trade | Sharpe | max DD | p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| US100 9yr research *(chosen here)* | 911 | 1.24 | +3.87 | 1.14 | 859 | 0.064 |
| US100 9yr LOCKED | 481 | **1.46** | +12.62 | 2.15 | 889 | **0.002** |
| US100 ISO (different provider) | 300 | 1.27 | +11.03 | 1.29 | 1,861 | 0.108 |
| US30 ISO | 334 | 1.26 | +13.88 | 1.18 | 2,317 | **0.044** |
| XAU 2004–2026 | 3,059 | 1.14 | +0.30 | 0.64 | 256 | **0.036** |

**Positive on all five, across three asset classes and twenty-two years.** Walk-forward over nine
one-year folds: **8/9 positive**, median PF 1.35, worst 0.88. Bootstrap **P(mean ≤ 0) = 0.0001**.
10% random trade omission leaves PF p5 at 1.28. Monte Carlo: realised drawdown 889 against a median
of 1,257 and p95 of 1,937 — the sequence was **lucky**, so size for 1,937.

One flag: **locked (1.46) scores better than research (1.24)**, the wrong shape. Five independent
positives is stronger evidence than one shape check, but it is recorded rather than buried.

## Perturbation: the brief's own numbers are the flattest part

| axis | values | PF |
| --- | --- | --- |
| stop | 1.5N / **2.0N** / 2.5N / 3.0N | 1.39 / **1.35** / 1.29 / 1.23 |
| Donchian entry | 25 / **30** / 35 | 1.34 / **1.35** / 1.35 |
| exit channel | 15 / **20** / 25 | 1.32 / **1.35** / 1.35 |
| MA pair 1 | 12/48 / **13/48** / 15/48 | 1.35 / **1.35** / 1.35 |
| MA pair 2 | 12/90 / **12/100** / 12/110 | 1.32 / **1.35** / 1.32 |

**The MA lengths barely matter.** 13/48 and 12/100 are not special — every neighbour lands within
0.03. What matters is that the two pairs *agree* and that the regime filter is on. This is
`STUDY_MA_LAG` again from a different direction: MA type is not a degree of freedom, and here
neither is MA length.

## The short side does not exist here

**As specified** — short a down-breakout when the MAs point down — it loses on every block and every
combination scores worse than a coin (p 0.65–0.96).

**Inverted** — short a down-breakout when the MAs point *up*, fading a flush in an uptrend — looked
significant on three equity blocks (p 0.003 / 0.030 / 0.026), and it is not real:

- walk-forward is **4/9 folds**, median PF 0.99, worst 0.65
- **one fold carries the whole thing**: 2021-10 → 2022-10, PF 2.19, +33.80 pts/trade — the 2022 bear market
- bootstrap **P(mean ≤ 0) = 0.099**, which does not clear 5%
- on XAU it scores **PF 0.77, p 1.000**

A rule whose edge is one bear market is a bet on the next one. The short leg ships **off**.

## Shipped

`pine/turtle/V13_MA_DONCHIAN_REGIME_strategy.pine`, parity-checked by `research/v13/v13_parity.py`
on three markets: **98.8–99.6% of signals match, profit factor within 0.02, per-trade correlation
0.9786–0.9888.**

The engine gained a short side for this study (`eem.run(side=…)`), verified against `mirror.run` at
identical trade counts on both sides — 1,737 long and 1,699 short — with only the documented
stop-cannot-rest-above-market cap differing.
