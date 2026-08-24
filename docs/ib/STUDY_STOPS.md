# Four stop rules, measured

Adding a stop-loss selection to the strategy meant deciding what the options should be and then
finding out which of them work, rather than shipping four settings with confident tooltips.

Four methods, chosen because they scale with different things — which is what makes them different
trades rather than one trade with a different number:

| method | scales with |
| --- | --- |
| percent of the IB range from the broken edge | the day's own auction |
| a multiple of ATR from the entry | recent volatility |
| a fixed number of points from the entry | nothing |
| the opposite edge of the initial balance | the day's own auction, maximally wide |

Everything else is held at the validated v3 geometry (IB 60, 50% retracement, fixed 1:2, both sides,
flatten 11:59) so the stop is the only moving part. 167 trades, 1-minute NQ, realistic fills.
Reproduce with `npx tsx scripts/quant-stop-modes.ts`.

## The table

`mcDD95` is the 95th-percentile drawdown over 5,000 Monte Carlo resamples — the number to size
against, since the realised one is a single lucky ordering.

| method | win | E | PF | t | DD | mcDD95 | research | holdout |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| % of range, 60% | 43.7% | +0.388 | 1.37 | 2.02 | 3.1% | 13.0% | +0.438 | +0.272 |
| % of range, 70% | 50.9% | +0.377 | 1.64 | 3.15 | 4.4% | 14.4% | +0.394 | **+0.338** |
| **% of range, 80% (default)** | 55.7% | +0.325 | 1.66 | **3.84** | 5.6% | 17.6% | +0.414 | +0.116 |
| % of range, 90% | 56.3% | +0.189 | 1.35 | 2.61 | 7.5% | 26.1% | +0.225 | +0.103 |
| % of range, 100% | 58.1% | +0.134 | 1.24 | 2.08 | 10.2% | 33.4% | +0.205 | −0.032 |
| ATR(14) × 1.5 | 49.7% | +0.363 | 1.34 | 3.13 | 4.7% | 20.2% | +0.415 | +0.241 |
| ATR(14) × 2 | 53.3% | +0.356 | 1.51 | 3.62 | 5.1% | 20.0% | +0.406 | +0.241 |
| ATR(30) × 1 | 47.3% | **+0.435** | 1.41 | 3.02 | 3.5% | 14.5% | **+0.506** | +0.269 |
| ATR(30) × 1.5 | 52.1% | +0.398 | 1.44 | 3.54 | 4.8% | 18.5% | +0.450 | +0.277 |
| ATR(30) × 2 | 53.9% | +0.338 | 1.51 | 3.54 | 5.4% | 20.4% | +0.414 | +0.161 |
| **fixed 20 points** | 52.1% | +0.381 | **1.82** | 3.52 | **2.4%** | **9.3%** | +0.399 | **+0.342** |
| fixed 30 points | 54.5% | +0.273 | 1.70 | 3.11 | 3.0% | 13.1% | +0.306 | +0.196 |
| fixed 40 points | 57.5% | +0.193 | 1.58 | 2.62 | 4.5% | 16.8% | +0.257 | +0.043 |
| fixed 80 points | 60.2% | +0.061 | 1.30 | 1.29 | 9.2% | 29.9% | +0.127 | −0.092 |
| opposite IB edge | 58.1% | +0.134 | 1.24 | 2.08 | 10.2% | 33.4% | +0.205 | −0.032 |

## 1. Win rate is the price, not the prize

Win rate climbs monotonically with stop width — 43.7% at a 60% stop to 58.1% at 100%, and 52.1% to
60.2% across the fixed-point ladder. Over the same span expectancy **falls** from 0.388 to 0.134, and
the Monte Carlo drawdown nearly triples.

A wider stop buys a higher win rate by converting small losses into large ones. Every row here is
the same setup; the only thing changing is how much you pay when you are wrong. **A strategy
advertised on its win rate is telling you about its stop, not its edge.**

## 2. The opposite-edge stop is the 100% stop

Identical to three decimals: 58.1% / +0.134 / 1.24 / 2.08 / 10.2% / 33.4% / +0.205 / −0.032. It has
to be — at any retracement depth, the far edge of the range sits exactly 100% of the range from the
broken one. The two rows were computed by completely different code paths, so this doubles as a
correctness check on the implementation.

It is also the worst option in the table. "Stop beyond the other side of the range" sounds
conservative and is the most expensive thing you can do here.

## 3. The default stays at 80%, on purpose

Stop 80% has the best t-statistic in the study (3.84) and a **holdout half (0.116) that is a quarter
of its research half (0.414)**. Stop 70% (0.394 / 0.338), ATR(30) × 1.5 (0.450 / 0.277) and the
20-point stop (0.399 / 0.342) all hold together far better across the split.

That is an argument for changing the default, and I am not making it. This sweep is a search over
22 configurations that has now touched the holdout. Moving the default because a 22-way search
preferred something else is precisely the mistake documented in `STUDY_SEARCH_CURVE.md`, where a
pre-specified configuration earned 0.312 against a searched one's 0.278–0.343.

The options ship measured. The default stays where it was independently validated, and the numbers
are in the tooltip so the choice is informed rather than inherited.

## 4. The best-scoring option is the least defensible

The 20-point fixed stop wins on profit factor (1.82), realised drawdown (2.4%), Monte Carlo drawdown
(9.3%) and holdout consistency (0.342). On the table alone it is the standout.

It is also an **absolute point distance on an instrument whose range roughly doubled across this
sample.** That is the identical objection that got fixed-point IB range filters replaced with
rolling-percentile ones in v2 of this strategy: a fixed number silently becomes a different rule as
volatility drifts. A 20-point stop in 2023 and a 20-point stop in 2025 are not the same trade, and
the backtest cannot tell you which one it was fitting.

ATR is the method whose mechanism survives that objection: it widens when the market is wide and
tightens when it is quiet without being told what a point is worth. ATR(30) beat ATR(14) at every
multiple tested, which is the expected direction — a longer average is a less noisy estimate of the
same quantity, and none of the differences are large.

If you use the 20-point stop, re-check the number as volatility moves. It will not re-check itself.

## 5. Stop choice and entry depth are not independent

At the 25% retracement the ranking inverts:

| method (at retr 25) | n | win | E | t | P&L | research | holdout |
| --- | --- | --- | --- | --- | --- | --- | --- |
| % of range, 80% | 349 | 53.0% | +0.078 | 1.89 | $29,677 | +0.098 | +0.039 |
| ATR(14) × 1.5 | 349 | 39.5% | +0.068 | 0.93 | $8,407 | +0.021 | +0.157 |
| **fixed 40 points** | 349 | 49.6% | **+0.145** | **2.39** | **$40,252** | +0.104 | +0.222 |
| opposite edge | 349 | 54.2% | +0.040 | 1.25 | $16,752 | +0.058 | +0.009 |

The ATR stop goes from one of the strongest options at a 50% retracement to the weakest at 25%, and
the winning fixed distance moves from 20 points to 40. That makes sense — a shallower entry sits
closer to the broken edge, so the same absolute stop is a different fraction of the trade — but it
means **the pair has to be re-measured together whenever either changes.** The largest total P&L in
the whole study, $40,252, is in this table rather than the main one, because 349 trades at a smaller
edge beats 167 at a larger one.

## Caveats

- 167 trades per row in the main table. These differences are real but not precisely measured, and
  several rows are inside each other's confidence intervals.
- One instrument, three years, one regime, as everywhere else here.
- The ATR is computed on session-filtered bars, so it is an ATR of 09:30–11:59 bars rather than of
  the full day. That is the right choice for a session strategy and is not what TradingView's
  `ta.atr()` will compute on a chart showing extended hours — expect a modest difference.
