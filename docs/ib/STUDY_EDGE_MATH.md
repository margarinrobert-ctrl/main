# Deriving the edge instead of searching for it

Every prior study in this repository looked for a **pattern** and mostly found noise. This one starts
from the arithmetic: decompose what an intraday P&L *can* be made of, prove which components are
identically zero, measure the rest, and see what is left standing.

**Result:** on NQ 2022–25, four of the six possible channels are dead — provably or measurably — and
the two that are alive are *variance* and *execution*, neither of which is a directional forecast.
The specification the math implies is the one configuration this project already validated, and the
math explains **why** it works: not a better prediction, a cheaper fill and a lower trade count.

Code: `research/edge_math.py`. Reproduce with `python3 research/edge_math.py`.

## 0. A note on "no martingale"

Two different things share the name. The **staking system** — doubling after a loss — appears nowhere
in this repository and is not used below. The **mathematical martingale** is price itself, and it is
the subject of §1: the staking system fails for exactly the reason every barrier rule fails, which is
that no arrangement of bet sizes or exit levels changes the expectation of a fair game. It reshapes
the distribution and leaves the mean alone.

## 1. The barrier theorem: why no stop/target arrangement can create an edge

Any rule that opens a position and closes it at one of two price barriers has

```
E[P&L] = P(up first)·(up distance) − P(down first)·(down distance) − cost
```

If price is a martingale, the optional stopping theorem gives `P(up first) = down/(up+down)` exactly,
and the first two terms cancel **for every choice of barriers**. There is nothing to optimise; the
cost term is the entire expectation.

That is a theorem, not a hypothesis — but it is worth checking that NQ obeys it, because a
sufficiently strong drift or serial structure would break it. Across 292,908 bars:

| up (pts) | down (pts) | predicted P(up) | observed | n resolved | gross edge (pts) |
| --- | --- | --- | --- | --- | --- |
| 10 | 10 | 0.5000 | 0.4923 | 289,675 | −0.154 |
| 20 | 20 | 0.5000 | 0.5036 | 280,898 | +0.146 |
| 40 | 40 | 0.5000 | 0.5084 | 245,504 | +0.673 |
| 75 | 45 | 0.3750 | 0.3490 | 203,963 | −3.121 |
| 45 | 75 | 0.6250 | 0.6572 | 209,543 | +3.868 |
| 30 | 10 | 0.2500 | 0.2479 | 283,832 | −0.085 |
| 10 | 30 | 0.7500 | 0.7593 | 284,424 | +0.370 |
| 60 | 20 | 0.2500 | 0.2318 | 255,189 | −1.453 |

**Mean |observed − predicted| = 0.0134.** The martingale prediction is right to about one
percentage point everywhere.

Mean gross edge across these geometries: **+0.031 points**, against a round-turn cost of **0.950
points**. The gross edge is **3% of the cost**.

This single table is the arithmetic behind the SMC study, the MaxAI study, both ORB studies and the
400,226-configuration trend search. They were all searching a space whose expectation is zero by
construction.

The two large entries are the asymmetric pairs, and they are drift, not skill: a 45-up/75-down
geometry is a long-biased bet with a wide stop, and it earned +3.868 points in a market that rose.
Its mirror lost 3.121. That is the next section's subject.

## 2. Where the drift actually is

| segment | days | total pts | pts/day | sd | t | Sharpe | dollars |
| --- | --- | --- | --- | --- | --- | --- | --- |
| intraday 09:30–16:00 | 764 | 5,509 | 7.211 | 193.05 | 1.03 | **0.59** | $110,185 |
| overnight 16:00–09:30 | 764 | 6,691 | 8.758 | 145.80 | 1.66 | **0.95** | $133,825 |
| the whole 24h | 764 | 12,201 | 15.969 | 236.73 | 1.86 | **1.07** | $244,010 |

**54.8% of NQ's move accrued while the market was closed**, and the overnight leg did it with *lower*
volatility (sd 145.80 vs 193.05) and a better Sharpe (0.95 vs 0.59). An intraday strategy is
competing for the worse half of the day's drift.

Neither leg is statistically significant on its own over 764 days (t = 1.03 and 1.66), so this is
suggestive rather than established — one instrument, one three-year sample, in a bull market. But the
direction of the result is the point: **the intraday session is where the volatility is and not
where the drift is.**

## 3. Is the intraday series a random walk?

Lo–MacKinlay variance ratios. `VR(q) = Var(q-bar return) / (q · Var(1-bar return))`; 1 is a random
walk, below 1 is mean reversion (a fade edge), above 1 is trending (a momentum edge).

| q (bars) | VR(q) | z (homoskedastic) | **z2 (robust)** | reading |
| --- | --- | --- | --- | --- |
| 2 | 0.9993 | −0.36 | −0.10 | random walk |
| 5 | 1.0114 | **2.80** | 0.71 | random walk |
| 15 | 1.0211 | **2.68** | 0.68 | random walk |
| 30 | 1.0235 | **2.06** | 0.54 | random walk |
| 60 | 1.0179 | 1.10 | 0.31 | random walk |
| 120 | 1.0505 | **2.17** | 0.69 | random walk |

Read the homoskedastic column and NQ trends significantly at 5, 15, 30 and 120 bars — z above 2 in
four places. Read the **heteroskedasticity-robust** column, which is the only one valid on a series
with this much volatility clustering, and every statistic collapses below 0.71.

**The apparent trending is volatility clustering, not predictability.** There is no serial structure
to trade at any horizon from 2 minutes to 2 hours.

*(An earlier draft of this table reported z2 = 0.00 at every horizon. That was a bug — a spurious
factor of N in the Lo–MacKinlay δ term inflated the variance estimate by ~292,000× — and it read as
a result. Fixed before anything was concluded from it.)*

## 4. Direction is not forecastable; magnitude is

Two regressions on identical bars and identical features (trailing volatility, trailing return, time
of day, time of day squared), forecasting the next 30 minutes:

```
forecasting the SIGN:   R^2 = 0.00058
forecasting the SIZE:   R^2 = 0.23024

volatility persistence, corr(|r_t|, |r_t+1|):   +0.1842
return persistence,     corr(r_t,   r_t+1):     -0.0054
```

**A 400:1 ratio.** Volatility is strongly forecastable; direction is not forecastable at all. This is
the central fact of the market and it is why every model in `STUDY_MODEL_LAYER.md` reached AUC 0.52
and no dollars.

## 5. Execution is the largest single term

| | cost per round turn | in points |
| --- | --- | --- |
| **taking** — cross the spread, ~1 tick slippage/side, $4 commission | $19.00 | 0.950 |
| **posting** — a resting limit filled at your price, commission only | $4.00 | 0.200 |
| difference | **$15.00** | 0.750 |

**$15 is 79% of the cost line, and it is larger than the gross edge of every geometry in §1.**

This is not a statistical claim, it is arithmetic, and it is the one lever that is fully under your
control. It also explains the project's most-repeated empirical finding from the other direction: a
**0% retracement — i.e. taking the break — was the single worst setting on a 225,792-cell grid**, and
pullback entries beat breakout entries on four independent arrivals. Those are the same fact.

**But execution alone does not rescue a random-entry rule.** The gross edge is 0.031 points and even
a commission-only fill costs 0.200 — you would need **6.5× more edge than exists**. Cheap execution
decides whether a real edge survives contact with the market; it does not create one.

## 6. Monetising the one live statistical channel

Volatility is the only forecastable quantity, and it cannot be traded directionally without options.
It can be used for **sizing**. Position size ∝ 1/σ̂, causal, capped at 3×, changing size only:

| leg | raw Sharpe | vol-sized | Δ | raw maxDD | sized maxDD |
| --- | --- | --- | --- | --- | --- |
| IB_retr | 1.44 | 1.44 | −0.00 | 5.6% | 5.9% |
| ORB5 | 0.35 | **0.54** | +0.19 | 32.4% | 25.9% |
| CMF_barrier | 0.78 | **0.88** | +0.10 | 30.6% | 36.1% |
| IB_breakout | 0.34 | **0.42** | +0.09 | 18.8% | 13.7% |
| equal-weight book | −0.55 | −0.44 | +0.11 | — | — |

Real and modest: **+0.09 to +0.19 Sharpe** where a strategy's P&L volatility actually varies, and
nothing for IB_retr, whose daily volatility is already stable. It improves a book; it does not create
one, and it never turns a negative Sharpe positive.

## 7. The specification the arithmetic implies

Scoring the six channels:

| channel | verdict | evidence |
| --- | --- | --- |
| barrier geometry | **dead** | observed P(up) matches the martingale to 0.013 |
| serial structure | **dead** | robust variance-ratio z below 0.71 at every horizon |
| direction forecast | **dead** | R² = 0.00058 on the sign of the next 30 minutes |
| variance forecast | **alive** | R² = 0.230 on size; +0.1–0.2 Sharpe as a sizing rule |
| execution | **alive** | $15/round turn, 79% of the cost line |
| drift | **partly** | 15.97 pts/day at t = 1.86, but 54.8% accrues overnight |

So a mathematically defensible intraday specification must:

1. **Not forecast direction.** R² of 0.0006 says the information is not in the price series.
2. **Post, never take.** The execution term is larger than any measurable edge.
3. **Trade rarely.** Each round turn costs 0.200–0.950 points against a gross edge of 0.031. Trade
   frequency is the dominant destroyer of expectancy, ahead of every parameter choice.
4. **Derive geometry from a session event**, not from a continuously-armed condition — a rule armed
   on every bar is a machine for finding coincidences (`STUDY_TREND_PULLBACK.md` §10).
5. **Use forecastable volatility for size, never for direction.**

That is a description of the configuration this project already validated:

> **Initial-balance retracement.** Build the IB 09:30–10:30. On a *close* beyond either edge, **rest a
> limit** at a 50% retracement. Stop at 80% of the range. Fixed 1:2 target. Both sides. Flat at 11:59.
> One trade per session.
>
> n = 167 (**0.22 trades/day**), mean **+0.3248R**, bootstrap 95% CI **[+0.1614, +0.4895]**,
> P(mean ≤ 0) = 0.0000, PBO 0.17–0.24, **Sharpe 1.44, max drawdown 5.6%**.

It satisfies every requirement above, and its Sharpe of 1.44 at a 5.6% drawdown beats 24-hour
buy-and-hold's 1.07 at 39.2%. **The math did not find a new edge — it explained the one that was
already there.** That edge is not a superior forecast; it is a passive fill, 0.22 trades a day, and
geometry anchored to an event rather than to a rolling indicator.

## 8. What this says about looking further

The productive directions are the ones the arithmetic leaves open, and none of them is another
parameter search:

1. **Information not in the price series** — order flow, book imbalance, trade-size distribution.
   §4's R² of 0.0006 is a statement about OHLCV, and every OHLCV-only rule competes with everyone
   else who has the same OHLCV.
2. **A cheaper cost regime**, which §5 prices exactly: $15/round turn is available to anyone willing
   to be filled passively and to wait.
3. **The overnight session**, where 54.8% of the drift accrued at a better Sharpe than the intraday
   session — a different study, not this one.
4. **Instruments where the same geometry can be tested out of sample.** Every result here is one
   instrument in one bull market.

## 9. Reproduce

```bash
python3 research/edge_math.py     # all six sections
python3 research/validate.py      # re-verifies the IB configuration quoted in S7
```
