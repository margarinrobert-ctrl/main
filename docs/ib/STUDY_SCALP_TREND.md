# Trend-following intraday scalp on three instruments: chop filtering works, and it is not enough

*Brief: convert the multi-day Turtle to an intraday scalp, trend-following only, no mean reversion,
avoid range/chop markets, 07:00–12:00 New York. Run on US30, NQ and US100.*

**Result: the chop filter does exactly what it should — it turns a losing breakout into a
break-even one, monotonically and on a broad plateau — and the improvement is about +0.05 R per
trade, which is not enough to clear the cost floor out of sample on any instrument.** US30 fails
out of sample, NQ has the wrong shape, and US100 is the sole marginal survivor at
**P(edge ≤ 0) = 25.8%**.

`research/scalp/`.

---

## 1. A third instrument, and why it matters

US30 is the first genuinely separate market on this branch. Every prior study ended with the same
caveat: NQ and US100 track the **same** underlying index, and `STUDY_TREND_LONG.md` measured the
cost — 68% of signals fire on the identical bar, so one cannot replicate the other.

| 15-minute return correlation | US30/US100 | US30/NQ | **NQ/US100** |
| --- | ---: | ---: | ---: |
| whole sample | 0.758 | 0.679 | **0.874** |

**No lead-lag at any offset** — every cross-correlation peaks at k=0, so nothing is tradable
between them. Correlation is stable by session (pre-market, RTH, post) and varies 0.54–0.87 by
year, so it is a real structural difference and not a regime artifact.

US30 also arrives as **2,880,287 one-minute bars**, which removes the constraint that blocked
`STUDY_US100_EDGELAB.md`: at a scalping stop on 15-minute bars, 47% of trades touched both
barriers inside one candle and the outcome was decided by the tie-break rule.

**Clocks are derived per feed, never inherited.** `feeds.derive_offset` locates the 09:30 activity
step separately in winter and summer and refuses a constant shift if they disagree. US30 resolves
to New York + 7, consistent across seasons — the same answer as US100, but measured.

## 2. A real look-ahead the audit caught

The truncation test — recompute every feature on history ending at bar *i* and require an exact
match — **failed on US30**. Overnight aggregates were masked to NaN before 07:00, on the reasoning
that the session is incomplete until then. That is only half the condition: **from 18:00 the next
overnight has already begun**, so an evening bar was reading its own still-forming group's running
high, low and last close. The audit located it precisely, at bars stamped 18:30–23:15.

Fixed to the complete 07:00–18:00 window; all three instruments now pass. **No published result
changes** — every study on this branch uses these features inside 07:00–11:00, where the old mask
was already correct.

## 3. The window the brief asked for is the wrong one

A 20-bar breakout long, 1.0×ATR stop, 1:1, research block, by hour:

| hour NY | 07:00 | 08:00 | 09:00 | **10:00** | **11:00** | 12:00 | 13:00 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| US30 15m | −0.338 | −0.246 | −0.222 | **+0.036** | **+0.010** | −0.145 | −0.070 |
| US100 15m | −0.425 | −0.393 | −0.277 | **+0.027** | **+0.007** | −0.079 | −0.108 |
| NQ 5m | −0.322 | −0.275 | −0.182 | −0.051 | −0.047 | −0.036 | +0.022 |

**07:00–09:00 is the worst part of the day on all three instruments.** The briefed 07:00–12:00
window contains one good hour and three bad ones; 09:00–09:30 also carries a 6–10% intrabar
ambiguity spike from the pre-open. Both windows are reported throughout, and the briefed one is
worse everywhere.

## 4. The chop filter does what it is supposed to

`research/scalp/regime.py` supplies eleven trend-quality measures, all causal, **all oriented so
higher = more trending** (the Choppiness Index is negated, and its name says so). Gating a 20-bar
breakout on each, US30 5m, research block, trade-weighted expectancy:

| gate (09:30–12:00) | n | E[R] |
| --- | ---: | ---: |
| breakout-20, no filter | 5635 | −0.0078 |
| + efficiency ratio > p40 | 4111 | +0.0106 |
| + efficiency ratio > p55 | 3442 | +0.0165 |
| + ADX > p70 | 2273 | +0.0196 |
| + ADX > p85 | 1262 | **+0.0382** |

**The response is monotone in the strength of the trend requirement**, which is the signature of a
mechanism rather than a fitted threshold. In the briefed window it lifts the base from **−0.111 to
+0.002** — a +0.11 R rescue, and still only break-even.

**Stacking the gates makes it worse.** ADX and the efficiency ratio correlate **0.642** — they
measure the same thing — so combining them cuts the sample without adding information:

| | n | E[R] | p |
| --- | ---: | ---: | ---: |
| efficiency ratio > p55 alone | 3442 | +0.0165 | 0.050 |
| ADX > p70 alone | 2273 | +0.0196 | 0.075 |
| **both** | 1911 | **+0.0102** | 0.175 |
| both + uptrend (+DI > −DI) | 1896 | +0.0110 | 0.133 |

The direction filter contributes nothing (−0.0101 against a −0.0078 base). One chop filter is the
whole effect.

## 5. The statistic that had to be fixed first

Two measures disagree **in sign** on this data:

* `expR` — trade-weighted mean R. **The economics**: every signal is taken.
* `day_R` — mean of per-day means. The correct unit of *inference*, since intraday triggers
  cluster several to a session — but it weights a one-trade day equally with a twelve-trade day.

The gated breakout has **positive trade-weighted expectancy and strongly negative day-weighted
expectancy**, because its profitable days are precisely the high-activity trending ones. That is
what a trend-following system is supposed to look like, and a per-day mean punishes it for it.
`fast.score_block_bootstrap` resolves this: it resamples whole **days with all their trades
attached**, so clustering is respected, and computes the trade-weighted mean of the resample. Both
statistics are reported everywhere; scoring on `day_R` alone would have rejected the entire
trend-following family for the wrong reason.

## 6. Out of sample, on three instruments

20-bar breakout, long, efficiency ratio > research p55, 2.0×ATR stop, 1.5R target, 20-bar max
hold, flat at window end. Thresholds are research-block percentiles, frozen before any other block
was read.

**09:30–12:00 (measured window):**

| inst | tf | research E[R] / p | validation | production | **out-of-sample E[R] / p** |
| --- | ---: | ---: | ---: | ---: | ---: |
| US30 | 5m | +0.0165 / 0.060 | −0.0212 | −0.0120 | **−0.0170 / 0.220** |
| US30 | 15m | +0.0636 / **0.003** | −0.0199 | −0.0554 | **−0.0360 / 0.657** |
| US100 | 15m | +0.0635 / **0.003** | −0.0143 | +0.0450 | **+0.0141 / 0.210** |
| NQ | 5m | −0.0234 | +0.0228 | — | +0.0228 / 0.280 |

**07:00–12:00 (briefed window):** worse on every instrument. US30 5m goes −0.0574 research →
−0.0992 out of sample; US30 15m +0.0450 → −0.0680; US100 +0.0105 → −0.0278.

Three of four configurations reach p ≤ 0.06 on research and **not one holds out of sample**. NQ
is negative on research and positive out of sample, which is the wrong shape.

## 7. Walk-forward, Monte Carlo, robustness

Six equal folds, thresholds fixed, so the later folds are honest:

| fold | 1 | 2 | 3 | 4 | 5 | 6 | positive |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| US30 15m | +0.087 | +0.041 | +0.081 | −0.023 | −0.005 | −0.043 | **3/6** |
| US30 5m | +0.019 | −0.014 | +0.052 | −0.020 | −0.026 | +0.003 | **3/6** |
| **US100 15m** | +0.051 | +0.029 | +0.087 | +0.029 | −0.013 | **+0.074** | **5/6** |

US30's last three folds (2021–2025) are all negative — a clean decay. US100 is positive in five of
six including the most recent.

**Monte Carlo**, US100 15m out-of-sample (1,269 trades; day-block bootstrap for the edge,
permutation for the path):

| total | median DD | 95th DD | mean R p05 | p50 | p95 | **P(edge ≤ 0)** |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| +17.9 R | 23.9 R | 37.2 R | −0.0214 | +0.0144 | +0.0502 | **25.8%** |

**Robustness** — research-block expectancy across the geometry neighbourhood is a **broad
plateau**, positive in 18 of 20 cells and rising smoothly with both stop width and target. That is
a ridge, not a spike. But the maximum sits at the grid edge (stop 2.5–3.0×ATR, target 2R), which is
the cost-drag effect again — and at a 3×ATR stop held 20 bars this is no longer a scalp.

## 8. Verdict

| claim | status |
| --- | --- |
| Chop/range filtering improves a trend-following breakout | **SUPPORTED** — monotone in gate strength, +0.11 R rescue in the briefed window, broad robustness plateau |
| ADX and efficiency ratio are separate filters | **REJECTED** — correlate 0.642; stacking them halves the sample and the edge |
| A directional filter (+DI > −DI) adds value | **REJECTED** — contributes nothing |
| The 07:00–12:00 window is the right one | **REJECTED** — 07:00–09:00 is the worst part of the day on all three instruments |
| The filtered breakout is a tradable intraday edge | **REJECTED on US30 and NQ; INSUFFICIENT EVIDENCE on US100** — P(edge ≤ 0) = 25.8% |

**The honest summary**: the user's hypothesis about chop was right, and it is measurable. Excluding
range-bound tape turns a −0.111 R breakout into a break-even one, smoothly and robustly. The
problem is the size of the prize: a chop filter is worth roughly +0.05 R per trade, and at an
intraday scalping geometry the round-turn cost is worth more than that. The filter closes the gap;
it does not open one.

**What would move it**, in order:

1. **Use the 1-minute US30 data as the entry timeframe rather than only as a validation path.**
   Everything above is 5- and 15-minute. The one thing not yet tested is whether a finer entry
   grid finds the same breakout earlier, before the cost floor eats the move.
2. **Widen the geometry and stop calling it a scalp.** The robustness surface rises monotonically
   to the grid edge; a 3×ATR stop with a 2R target is where this structure actually pays, and that
   is a swing trade.
3. **Accept the instrument answer.** US100 is the only one of three where this survives at all,
   and it survives at p 0.21.

## Files

| | |
| --- | --- |
| `research/edgelab/feeds.py` | three-instrument loader, per-feed clock derivation, quality audit |
| `research/scalp/xmarket.py` | correlation, lead-lag, stability by year and session |
| `research/scalp/regime.py` | eleven causal chop/trend measures, all oriented higher = trending |
| `research/scalp/core.py` | the intraday conversion: window gate, barrier exits, session flatten |
| `research/scalp/discover.py` | geometry, entry-family and gate search |
| `research/scalp/strategy.py` | the frozen trend-following rule |
| `research/scalp/validate.py` | walk-forward, Monte Carlo, robustness, both statistics |
| `research/edgelab/fast.py` | `score_block_bootstrap` — day-block resample of the trade-weighted mean |

Measured on US30 CFD (1m/5m source), US100 CFD (15m) and NQ futures, one unit per trade, costs as
stated in `scalp/core.COSTS` and assumed rather than measured. Research tooling for education and
analysis, not financial advice.
