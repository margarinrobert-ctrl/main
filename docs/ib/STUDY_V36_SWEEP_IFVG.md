# V36 — liquidity sweep → reversal → IFVG: the concept does not have an edge

**Verdict: FAILED.** Tested as specified, on 1-minute NQ with real costs, one live order and a true
1-minute execution path. Scored in R, **1.4% of 5,400 declared configurations clear a profit factor
of 1 and all 24 marginal averages are negative.** Scored in dollars — which is the correct unit here
and the correction is explained below — **16.1% clear PF 1, the median is 0.904, and all 24 marginal
averages are still negative.** The best configuration has no parameter plateau, loses 84% of its
edge on validation, and its apparent quality is a measurement artifact. No pre-entry filter, regime
condition or time window rescues it. **Out-of-sample was never opened, because nothing earned the
right to be tested there.**

Two of the most consequential findings below are errors in my own measurement, caught before they
reached a conclusion. They are reported as prominently as the strategy result.

---

## 1. What was blocked

Only `NQ_1m.csv` is on disk. **ES, MES, RTY, YM and GC have never been on this branch, and MNQ is the
same underlying as NQ so it is not an independent test.** §12 multi-market validation is therefore
UNTESTED, not "passed on one market". Every module is market-agnostic and runs unchanged on a new
feed. Cross-market generalisation is the single most valuable thing that could be added.

## 2. Exact rules, as implemented

**Liquidity pools.** Confirmed swing highs/lows on 1H (k=3) and 4H (k=2); Asia, London and
previous-day extremes; the running RTH extreme. 4,596 high pools and 4,570 low pools.
- A pivot at bar *i* with *k* bars either side is **knowable at i+k**, never at *i*. Every pivot
  carries its confirmation bar.
- **Sessions are measured in minutes since the 18:00 roll, not wall-clock.** The first version froze
  on `mod >= freeze`, and because the trading day rolls at 18:00 that also caught the 18:00–23:59
  bars of the *same* trading day — **evening bars were handed London levels from a London session
  that happens the next morning.** Asia 0–540, London 540–930, RTH 930–1320.
- **Previous-day levels leaked more subtly**: they were assigned per trading day only if that day
  appeared in the RTH groupby, so a 02:00 bar got its levels because the day *later* had RTH bars.
  The value was causal; its existence was not. Re-keyed to the last trading day strictly before.
- A pool is live for **5 trading days** and is **consumed** once swept.
- Truncation audit after both fixes: **CLEAN**.

**Sweep — four definitions, all tested, none assumed.** `wick` (pierce ≥ 0.10 ATR and close back
inside), `close` (close beyond, reclaim within 15 bars), `pen_only` (pierce only), `displace` (wick
plus a displacement candle within 10 bars).

**IFVG chain.** FVG at bar *i*: bullish when `low[i] > high[i-2]`, zone `[high[i-2], low[i]]`;
bearish when `high[i] < low[i-2]`. Knowable at the close of bar *i*. **Invalidated** when a candle
*closes* through the zone; at that close it **inverts**. A long after sweeping lows therefore needs a
**bearish FVG closed through to the upside** — a bullish IFVG acting as support. Inversion must
follow the sweep within 12 entry-timeframe bars; median observed gap is 3–5 bars.

**Entry.** Limit at the proximal zone boundary, limit at the midpoint, or market at the next open.
60 minutes to fill. **An unfilled limit holds the position lock** — one live order, the `STUDY_V34`
correction, without which a backtest holds a book it cannot place.

**Stop / target / management.** ATR(14/20/30) × {0.5…1.5}; beyond the sweep extreme + 0.25 ATR;
or the wider of the two. Targets 0.75R–2.0R. Breakeven and chandelier trail implemented. Costs: the
real MNQ stack at ×1.44. Stop resolves before target inside a minute.

**Census:** ~2,050–2,340 setups per (definition, timeframe) cell over three years, ~700–790/year.
Ample to test.

## 3. Phase 1 — the declared baseline fails

| cell | R/trade | PF (dollars) | net $ |
| --- | --- | --- | --- |
| wick 5m | −0.186 | 0.875 | −4,027 |
| **wick 15m** | −0.078 | **1.055** | +1,670 |
| close 5m | −0.128 | 0.929 | −2,322 |
| close 15m | −0.042 | 0.944 | −1,898 |
| pen_only 5m | −0.237 | 0.844 | −4,673 |
| **pen_only 15m** | −0.088 | **1.050** | +1,450 |
| displace 5m | −0.176 | 0.838 | −5,149 |
| **displace 15m** | −0.135 | **1.037** | +1,100 |

**Diagnosis, not just a number.** Stopped trades average **−1.164 R** and targets pay **+1.360 R**
against a nominal −1.0/+1.5 — both gaps are cost, which runs 7–11% of risk. Break-even for this
geometry is **46.1%**; actual is **43.2%**. Median risk is **3.735 ATR** with a p90 of 84.8 points,
because anchoring the stop to the sweep extreme puts it a long way from entry. The trigger is not
what phase 1 measured; the geometry is.

## 4. THE MEASUREMENT ERROR THAT MATTERS: R is unsafe with a structural stop

The sweep-extreme stop can sit a few ticks from the entry. Measured: **minimum risk 0.015 points**,
1st percentile 0.687, **3.4% of trades risking under two points**.

| risk quintile | median risk | **R/trade** | **points/trade** |
| --- | --- | --- | --- |
| Q0 (smallest) | 6.65 pts | **+0.6741** | **−1.41** |
| Q1 | 17.76 | −0.1235 | −1.80 |
| Q2 | 30.07 | −0.1230 | −4.08 |
| Q3 | 49.18 | +0.1812 | +10.00 |
| Q4 | 86.94 | +0.1227 | +14.21 |

**The smallest-risk quintile reads +0.67 R while losing money.** `CLAUDE.md` records exactly this for
a channel stop — *"94% of the apparent contribution is the denominator"* — and I walked into it.
Every R-denominated figure in phases 2–3 was rescored in dollars.

**The two units disagree in sign, and that is a real sizing result, not a contradiction.** At one
contract with risk varying from 0.7 to 87 points, the large-risk winners dominate and three phase-1
cells turn positive. Sized to **constant risk** — which §13 asks for — the small-risk losers weigh
equally and the result is negative. A trader cannot have the dollar version without accepting 100×
risk dispersion per trade.

## 5. Phase 2 — 5,400 declared cells, read by marginal average

| | in R | in dollars |
| --- | --- | --- |
| share clearing PF 1 | **1.4%** | **16.1%** |
| median PF | 0.717 | 0.904 |
| best PF | 1.418 | 1.758 |
| **marginal averages negative** | **24 of 24** | **24 of 24** |

Best marginals in dollars: `close` sweep −1.65 $/trade, 15m −1.85, `mid` entry −1.57, `sweep` stop
−2.35, ATR 20 −2.44, k 0.5 −2.06, target 0.75R −1.95. **There is no axis with a positive region.**

*A flaw in my own grid:* the sweep-extreme stop ignores the multiplier, so its 1,800 cells are 360
distinct configurations. Effective size is **3,960**, and the "top 15" is the top 3.

## 6. Phase 3 — the maximum is a corner, not a region

`pen_only / 15m / edge / sweep`, the grid's best cell, sits in the **intersection of the two worst
marginals**.

**Neighbourhood:** within its own family only **33% of 15 cells** clear PF 1 and the family mean is
**−0.0067 R**. One-axis perturbation:

| vary | result |
| --- | --- |
| entry | edge **+0.292** → mid **−0.554** → close **−0.245** |
| timeframe | 15m +0.292 → 5m **−0.277** |
| sweep definition | pen_only +0.292, close +0.225, wick −0.010, displace **−0.160** |

That is the brief's own rejection criterion, met exactly.

**Validation, read once:** mean of the top five **+0.2510 → −0.0064**. The winner falls from PF 1.413
to 1.077, losing 84% of its edge; three of five go negative.

## 7. Phase 4 — no filter, regime or time window rescues it

**A second measurement error, caught and corrected.** The first pass reported **5 of 11 features
clearing p ≤ 0.05 against 0.6 expected**. That comparison was wrong: for each feature the search
examines four quartiles and reports the **best**, so the statistic is a max-of-four while the control
drew a single subset — 44 effective tests, not 11. Under a null that also takes its own best of four:

| feature | naive p | **corrected p** |
| --- | --- | --- |
| gap_bars | 0.025 | 0.084 |
| rvol | 0.015 | 0.064 |
| pen_atr | 0.023 | 0.087 |
| atr_z | 0.040 | 0.166 |
| zone_atr | 0.042 | 0.169 |

**0 of 11 survive.** On the marginal-best base, all 11 best-quartiles are *profitable on validation*
(mean +0.199 vs train +0.118) — but that applies to the failures too, so it is a favourable
validation block, not a filter effect. Wrong shape.

On the train-winner base the "significant" features are the denominator artifact made visible:
**all eleven best-quartiles read R between +4.05 and +4.39.** If a feature were selecting, they would
differ. They are identical because every one is capturing the same handful of collapsed-risk trades.
NY-pm shows PF 7.332 on that base — a number with no meaning.

**Gradient-boosted quality score**, purged folds, shuffled twin: control p 0.098–0.600, and **the
shuffled twin beats the real model at both the 25% and 10% keep rungs.**

**Time of day** (marginal base): NY lunch +$0.083, NY open +$0.053, NY 10–11:30 −$0.002, **NY pm
−$0.096**. **Liquidity source:** 60m +0.041, prevday +0.042, london +0.018, **asia −0.258**. None
clears the corrected control.

## 8. Failure regimes, stated

The concept fails hardest on **5-minute entries** (every marginal worse than 15m), on **market
entries** (−4.15 $/trade, the worst single marginal), on **ATR-only stops** (Sharpe −2.84), at
**wide targets** (2.0R, −3.45 $/trade), on **Asia-session liquidity** (−0.258 R), and in the **NY
afternoon**. It is least bad at 15m, with a limit entry at the zone midpoint, a structural stop and a
target under 1R — which is to say, least bad where it trades least like the concept describes.

## 9. What was not reached, and why

Breakeven, trailing, partial exits and internal-liquidity targets are implemented but were **not
optimised**, and out-of-sample was **never opened**. Exit management redistributes an edge; it does
not create one, and nothing survived phases 1–4 to justify spending the OOS block. Opening it now
would only convert a clean negative into a contaminated one.

## 10. Verdict

**The liquidity-sweep → IFVG reversal mechanism does not contain a robust statistical edge on NQ
under realistic costs.** It is not close: the median configuration loses, every marginal is negative
in both units, the best cell has no neighbourhood and dies on validation, and every apparent filter
effect dissolves under a correctly-matched null.

What the study is worth keeping for is two methodological results that generalise beyond this
concept: **R is not a safe unit when the stop is structural**, and **a best-of-N subgroup search must
be scored against a null that also takes its best of N.** Both produced convincing false positives
here — PF 7.332 and 5-of-11 significance — and both are cheap to guard against.

Reproduce: `research/v36/` — `levels.py`, `setup.py`, `engine.py`, then `count.py`, `run_base.py`,
`run_grid.py`, `run_valid.py`, `run_filter.py`, `quartile_fix.py`. Raw output in
`docs/ib/v36_census.txt`, `v36_grid_dollars.txt`, `v36_filters.txt`, `v36_quartile_correction.txt`.
