# EMA / SMA on NQ — does a moving average find an edge?

Full report: [`STUDY_MA.md`](STUDY_MA.md). Strategy: `src/lib/quant/strategies/movingAverage.ts`.

5-minute NQ, Dec 2022 – Dec 2025, 766 RTH sessions split 537 research / 229 holdout, costs of 1 tick
spread + 1 tick slippage per side + $4 commission (3.80 ticks per round turn).

## The short answer

**No edge, EMA and SMA are indistinguishable, and nothing beats simply being long the session.**

## 1. Why this was unlikely before a single backtest ran

A moving average is a lagging low-pass filter on price. It contains no information price does not
already contain — it is a transform of the same series. So an MA rule cannot *create* an edge; it
can only *express* serial dependence that already exists in returns.

The alpha-discovery stage measured that dependence directly on this exact data:

- lag-1 autocorrelation of 5-minute returns: **+0.0107** (t = 2.14)
- variance ratio at 10 bars: **0.928** (z = −2.81, mild mean reversion)

Those numbers bound what *any* moving-average rule can extract. A rho of 0.011 on a bar whose
typical move is ~36 ticks is a fraction of a tick of forecast, against a 3.80-tick round turn. The
backtests below are a confirmation of that arithmetic, not an independent test.

## 2. The drift benchmark that everything must beat

Buy the session open, sell the session close, every day, one contract:

| | per day | total | t |
| --- | --- | --- | --- |
| research | $102 | $54,902 | 0.81 |
| holdout | $183 | $41,874 | 0.65 |

Any trend rule that cannot beat this is not adding information, it is adding exposure — and paying
commission for the privilege.

## 3. Ten pre-specified variants

| # | variant | research | holdout |
| --- | --- | --- | --- |
| 1 | EMA 9/21 cross, 2R target | −8.6t, PF 0.91 | +4.1t, PF 1.03 |
| 2 | SMA 9/21 cross, 2R target | −3.5t, PF 0.96 | −7.6t, PF 0.94 |
| 3 | EMA 9/21 cross, hold to flip | −3.3t, PF 0.96 | −5.2t, PF 0.96 |
| 4 | SMA 9/21 cross, hold to flip | −1.8t, PF 0.98 | +1.9t, PF 1.02 |
| 5 | **EMA 50/200 cross, hold** | **+51.8t, PF 1.54, t=2.50** | **−41.0t, PF 0.76** |
| 6 | SMA 50/200 cross, hold | +8.8t, PF 1.09 | −15.5t, PF 0.88 |
| 7 | price vs EMA 20, hold | −5.1t, PF 0.91 | +2.3t, PF 1.03 |
| 8 | price vs SMA 20, hold | −0.1t, PF 1.00 | +9.2t, PF 1.12 |
| 9 | **pullback to EMA 50** | **−12.9t, PF 0.87, t=−2.24** | **−24.0t, PF 0.83** |
| 10 | **pullback to SMA 50** | **−17.6t, PF 0.82, t=−2.86** | **−15.6t, PF 0.88** |

The golden-cross variant (#5) is the session's cleanest single illustration: **t = 2.50 in research,
then −41 ticks per trade on the holdout.** Nothing about the rule changed.

## 4. EMA versus SMA, tested properly

84 matched pairs — every configuration run twice, identical in every parameter except `maType`, so
the strategy design cancels and only the averaging method differs.

Pooling all 84 pairs gives mean +3.30 ticks in EMA's favour, t = 2.381, **p = 0.017**. That number
is wrong, and the way it is wrong is instructive: the 84 pairs are not independent. They share bars,
and 42 of them are the same configurations re-run on the other half of the same series. Splitting
properly:

| | pairs | EMA better | mean | median | t | p |
| --- | --- | --- | --- | --- | --- | --- |
| research | 42 | 23 (55%) | +2.57t | +1.24t | 1.64 | 0.101 |
| holdout | 42 | 23 (55%) | +4.03t | +1.16t | 1.75 | 0.080 |

Neither half is significant. And the decisive test — does the *same configuration's* EMA advantage
in research carry into the holdout?

- **sign agreement: 20/42 = 48%** (a coin flip)
- **correlation of the advantage: −0.393** (negative — where EMA won in research it tended to lose in the holdout)

**Conclusion: the EMA-versus-SMA choice does not matter.** Any backtest showing one is better is
measuring noise, and will not replicate. Choose on latency, tradition or taste; do not choose on
backtest.

## 5. The full protocol agrees

| | result |
| --- | --- |
| best of 800 configurations, in-sample | Sharpe 1.70, +10.5 ticks/trade, 802 trades |
| parameter surface | **spike** — no surviving neighbours |
| same procedure, walk-forward | Sharpe **−0.65**, −5.7 ticks/trade, PF 0.917 |
| walk-forward efficiency | −0.49 |
| PBO | 0.413 |
| deflated Sharpe | 0.000 |

## 6. The one result worth keeping

**Buying pullbacks to the 50-period moving average is a reliable loser on NQ intraday.** It is
negative in *both* halves for *both* averaging methods (−12.9t / −24.0t for EMA, −17.6t / −15.6t for
SMA) and it is the only configuration in the study to reach significance in the research half with
the *same sign* out of sample (t = −2.24 and −2.86).

Consistent negatives are worth more than inconsistent positives, and this one has a mechanism: the
50 MA is one of the most-watched intraday levels, so resting orders cluster there and price is drawn
through it rather than turning at it. That makes it a good place to have a stop run against you and
a poor place to buy.

Same shape as the 15-minute ORB result, where the retracement entry also lost in both halves. Two
independent studies now say the same thing: **on NQ intraday, waiting for a pullback to a reference
level is systematically worse than acting on the move.**
