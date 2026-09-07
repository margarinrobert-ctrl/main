# Three papers, one usable result

Three documents arrived with the instruction to reverse-engineer them into an intraday scalping
edge. Only one of them can do that, and not in the way the instruction implies. This document says
what each is, what it can produce here, and what came out of the one that applied.

| paper | what it is | can it yield an intraday futures edge? |
| --- | --- | --- |
| Viaggi, *A Standardized R-Multiple Framework* | trade-level **validation methodology** | **No — it validates edges, it does not create them.** But it applies directly to ours, and its central result explains a pattern this repo measured empirically. Implemented. |
| Bowles, Reed, Ringgenberg & Thornock, *Predicting Anomalies* | cross-sectional **equity** anomalies, quarterly accounting data | **No.** Wrong instrument, wrong horizon, wrong data. Detail below. |
| Cartea, Jaimungal & Ricci, *Trading Strategies within the Edges of No-Arbitrage* | optimal **market making** under stochastic control | **Not with our data.** Requires a limit order book and ≥2 structurally dependent assets. Detail below. |

## 1. The Viaggi framework, and the result it turns on

The model: each trade pays **+b** with probability p, or **−1** otherwise.

```
expectancy            e  = p·b − (1−p)
break-even win rate   p₀ = 1 / (b + 1)
null variance         Var(X) = b          ← verified exactly, symbolically and by simulation
```

That third line is the paper's real contribution. `E[X²] = p·b² + (1−p) = b(b+1)/(b+1) = b`. So the
variance of a zero-edge trade process **equals the reward multiple**.

The consequence is the opposite of retail intuition. Raising the reward-to-risk ratio lowers the win
rate you need — which feels like it makes the system easier — and raises the noise of the process by
exactly the same factor. Minimum trade record length is `N = z²·b / e²`:

| R:R | break-even win | null variance | trades to prove e = 0.10 | e = 0.20 | e = 0.30 |
| --- | --- | --- | --- | --- | --- |
| 1:1 | 50.0% | 1.00 | 271 | 68 | 31 |
| 1:2 | 33.3% | 2.00 | 542 | 136 | 61 |
| 1:3 | 25.0% | 3.00 | 812 | 203 | 91 |
| 1:4 | 20.0% | 4.00 | 1,083 | 271 | 121 |

**A 1:4 system needs four times the trades of a 1:1 system to prove the same edge.** Linear in the
reward multiple, quadratic in the reciprocal of the edge.

### This is the analytic explanation for something already measured here

`STUDY_MEGA_SEARCH.md` found, across 225,792 configurations, that **higher reward-to-risk was
monotonically worse in dollars while looking better in R** — median locked-holdout P&L fell from
−$945 at 1:0.75 to −$3,342 at 1:4. `STUDY_STOPS.md` found the same shape. At the time the mechanism
was described loosely as "R-multiples flatter". Viaggi gives the exact reason: **the search was
selecting on a statistic whose noise grows with b, so high-b configurations win the selection while
carrying proportionally less evidence.** Empirical finding and analytic result agree, and neither
was derived from the other.

## 2. Our own edge, put through it

`npx tsx scripts/quant-rmultiple.ts`, on the 1-minute NQ record.

| configuration | n | win% | implied b | cumulative R | critical R | z | p | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| published (retr 25 / stop 60 / 1:1) | 349 | 54.4% | 0.81 | 30.0 | 27.7 | 1.79 | 0.037 | passes |
| screenshot (retr 25 / stop 80 / 1:1) | 349 | 56.4% | 0.60 | 33.6 | 23.8 | 2.32 | 0.010 | passes |
| **v3 validated (retr 50 / stop 80 / 1:2)** | 167 | 55.7% | 1.23 | **54.2** | 23.6 | **3.78** | 0.000 | **passes** |
| v3, priced as best-of-1,536 | 167 | 55.7% | 1.23 | 54.2 | **72.0** | 3.78 | — | **fails** |
| v3, priced as best-of-225,792 | 167 | 55.7% | 1.23 | 54.2 | **89.1** | 3.78 | — | **fails** |

As a single pre-specified test the v3 geometry passes comfortably: z = 3.78, cumulative 54.2R
against a 23.6R bar.

**Priced as the survivor of a search, it fails.** Even at 1,536 candidates the bar rises to 72.0R,
above our 54.2R. At 225,792 it is 89.1R.

Which row is honest depends on a fact about history, not about statistics: the v3 geometry was
**not** read off the 225,792-cell sweep — it came from walk-forward folds that independently kept
picking a 50% retracement, and the big sweep came afterwards. But it was still chosen with knowledge
of search results. The defensible reading is that **the truth is between rows 3 and 4, and row 3
alone overstates the case.** This is the same conclusion `STUDY_SEARCH_CURVE.md` and
`STUDY_MEGA_SEARCH.md` reached by measurement; the framework now says it in the native unit.

## 3. Where the framework does not fit our data

The model assumes every trade pays exactly +b or −1. Ours do not — a session flat at 11:59 or a gap
through a level lands between the two. That matters, because the entire threshold is built on
`Var(X) = b`.

| configuration | implied b | null variance | observed variance | ratio | share of trades that are clean +b / −1 |
| --- | --- | --- | --- | --- | --- |
| published | 0.81 | 0.81 | 0.74 | 0.92 | 68% |
| screenshot | 0.60 | 0.60 | 0.47 | 0.79 | 30% |
| **v3 validated** | 1.23 | 1.23 | **1.75** | **1.42** | **34%** |

Only a third of the v3 record is a clean binary outcome, and its **real variance is 42% above what
the model assumes.** Since the threshold scales with `√Var`, the correct critical value is about
**19% higher** than the analytic one — 28.1R rather than 23.6R. The conclusion survives (54.2R still
clears it), but the general lesson does not depend on our luck:

> **Applying this framework to a record without checking the binary assumption understates the bar.
> Report the observed variance beside the model's, always.** `validateRRecord` returns both for
> exactly this reason.

## 4. What a zero-edge system does anyway

167 trades at b = 1.23, simulated 20,000 times with **no edge at all**:

| diagnostic | median | tail |
| --- | --- | --- |
| max drawdown | 15.5R | 30.9R (95th) |
| equity MAE | −9.3R | −27.1R (5th) |
| equity MFE | **+9.1R** | **+27.5R** (95th) |
| longest losing streak | 7 | 12 (95th) |

A system with no edge whatsoever gets **+9.1R up at some point half the time, and +27.5R one time in
twenty** — and suffers a 12-trade losing streak one time in twenty. Neither a good run nor an ugly
one is evidence of anything on its own. Our realised 54.2R does sit well outside that distribution,
which is the honest form of the claim.

## 5. Why the other two papers cannot produce an intraday edge

**Predicting Anomalies** is a cross-sectional equity asset-pricing paper. It forms long–short decile
portfolios over 28 accounting anomalies, rebalanced quarterly, and earns 2.80% annualized by
trading ~3 months ahead of a 10-K release using a martingale forecast of the anomaly signal. To run
it you need CRSP daily returns, Compustat Snapshot point-in-time accounting data, and thousands of
stocks. The horizon is quarters and the unit is a diversified portfolio. **There is no intraday
futures analogue** — NQ has no accounting statements, no cross-section, and no quarterly signal.

One idea does transfer conceptually, and it is worth stating because it matches this repo's own
results: the paper finds that the *predictable* component of anomaly returns has been arbitraged
away in recent years (the martingale model earned +198bp in 1990–2006 and **−19bp** in 2007–2023),
while returns concentrate in the **false negatives** — the cases the model got wrong, which earn
268bp. Edge lives in the part that is hard to anticipate, and the easy part gets competed out. That
is the same shape as our finding that the widest, most thorough search lands at the 13th percentile.
It is a reason for humility, not a strategy.

**Trading Strategies within the Edges of No-Arbitrage** is much closer to scalping — it is an
optimal market-making paper, solving for limit and market order placement when midprices follow a
reflected Brownian motion inside a no-arbitrage region set by bid–ask spreads. Its two regimes
(quote both sides when far from the bounds; fire market orders when the midprice vector hits an
edge) are genuinely intraday. But implementing it requires:

- a **limit order book** — bid, ask, depth, and queue position. We have 1-minute OHLCV bars, which
  cannot express whether a passive order would have filled, let alone where it sat in the queue.
- **≥2 structurally dependent assets**, since the no-arbitrage region is defined between them. We
  have one instrument.
- **inventory-aware execution** at sub-second frequency, where our engine's decide-on-close /
  fill-next-bar model is three orders of magnitude too slow.

The honest translation of this paper into our setting would be a two-instrument spread band — ES
against NQ, say — with entries at band violations. That is a real, testable idea. **It needs ES
data, which this repository does not have**, and it would be a stat-arb strategy rather than the
market-making one the paper actually solves.

## Bottom line

The instruction was to make an edge from these papers. The truthful outcome is:

1. **The Viaggi framework is now implemented** (`src/lib/quant/rmultiple.ts`, 22 tests) and applied.
   It does not create an edge; it raises the bar on the one we have, and it independently explains
   the reward-to-risk finding this repo reached by brute force.
2. **Our best configuration passes as a single test and fails once the search is priced in.** That
   is the third independent route to the same conclusion.
3. **The other two papers cannot be turned into an intraday futures edge with the data here.** One is
   the wrong asset class and horizon entirely; the other is the right frequency but needs an order
   book and a second instrument.

## Caveats

- The framework's thresholds assume i.i.d. trades. Ours cluster by session, so the effective sample
  is smaller than n and the real bar is higher still than the numbers above.
- `impliedB` is taken from the realised average win rather than the order ticket, which is the right
  choice for a record containing session flats — but it makes b an estimate, not a constant.
- One instrument, three years, one regime, as everywhere else here.
