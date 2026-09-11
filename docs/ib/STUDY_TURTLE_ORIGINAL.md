# The original Turtle system, reconstructed and frozen — in-sample and untouched out-of-sample

`research/turtle2/`. Nothing in this study is optimised. Every parameter is the published constant.

## What was built

The full mechanical system: Wilder 20-day N, System 1 (20-day entry / 10-day exit) with the skip
rule, System 2 (55-day / 20-day) as the always-taken failsafe, 2N stop, 0.5N pyramiding to 4 units
with all stops re-anchored to the most recent fill, whole-position exits, **long and short**.

Three things this reconstruction does that most do not:

**The skip rule is implemented from a shadow ledger, not from the trade list.** The rule says a
System 1 breakout is skipped if the *previous 20-day breakout* would have won — *whether or not it
was taken*. That cannot be read off realised trades, so `shadow_ledger()` simulates a parallel
non-overlapping single-unit ledger of every breakout. On US30 it skips **41.3%** of signals.

**Every fill is walked on the true intraday path.** All Turtle orders are stop orders, so entry,
adds, the 2N stop and the channel exit all trigger inside the day. `STUDY_ATME_LIVE.md` measured
what resolving that by rule instead of by sequence costs (PF 1.99 → 0.99). Residual same-bar
ambiguity is resolved stop-first and **counted**: 4.5% in-sample, 3.5% out-of-sample.

**The portfolio caps are enforced.** A first version omitted them, on the reasoning that the brief
specified only "4 units". The error is worth recording: without the 6-per-correlated-group and
12-per-direction caps the in-sample portfolio returned **299,376%** with a $75M average win on a
$1M account, because 5 markets × 2 systems × 4 units puts 40% of equity at risk and compounds it.
**The caps are the risk model, not a detail.**

## The portfolio, and its limitation

Gold, EURUSD, BTC, US30, US100 — four distinct bets, two of them correlated indices (0.758). The
original Turtles traded 20+ markets across rates, grains, energy, softs, meats. **Those asset
classes are absent here and a weak result is partly attributable to that.** NQ was dropped: ~750
daily bars against US100's 2,283 on the same underlying at 0.874 correlation.

Per-market 65/35 time split. Gold pre-2010 excluded with cause. Day boundary 17:00 New York on all
five. Intraday resolution is uneven and reported: US30 1m, gold 5m, US100/BTC 15m, EURUSD 30m.

## The result

Fixed-equity view (units sized off starting equity, so expectancy is comparable across blocks):

| | n | win | E[R] | PF | CAGR | maxDD | Sharpe | Sortino |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| S1, in-sample | 284 | 27.8% | +0.049 | 1.88 | 9.7% | 20.9% | 2.29 | 22.8 |
| S2, in-sample | 237 | 24.5% | **+0.492** | 3.13 | 14.0% | 15.7% | 2.10 | 55.4 |
| both, in-sample | 441 | 28.3% | **+0.294** | 2.41 | 13.4% | 27.6% | 1.64 | 28.5 |
| S1, **out-of-sample** | 195 | 25.1% | **−0.093** | 1.46 | 7.3% | 67.8% | 1.02 | 8.7 |
| S2, **out-of-sample** | 137 | 24.8% | +0.075 | 1.77 | 9.6% | 62.9% | 1.54 | 18.4 |
| **both, out-of-sample** | 285 | 26.7% | **+0.018** | **1.12** | 2.4% | **77.3%** | 0.41 | 1.90 |

Compounded (the real original): in-sample CAGR **28.9%** at a 41.7% drawdown; out-of-sample CAGR
**1.5%** at a **60.1%** drawdown.

**Profitable years: 18 of 21 in-sample, 3 of 12 out-of-sample.** Longest losing run 19 → **37**.

## Four things that decide the verdict

**1. The entire out-of-sample result is Bitcoin.**

| | n | E[R] | PF | CAGR | Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: |
| all 5 markets, OOS | 285 | +0.018 | 1.12 | 2.4% | 0.41 |
| **ex-BTC, OOS** | 231 | **−0.052** | **0.84** | **−3.1%** | **−0.67** |

Per market out-of-sample, only two are positive: gold +0.666 and BTC +0.316. EURUSD **−0.342**
(PF 0.45), US30 −0.210, US100 −0.161. A system carried by one asset's once-in-history run is not a
diversified trend-following edge.

**2. It is not a cost problem.** At **zero cost** the OOS block is +0.071 R / PF 1.43 — better, but
still a fraction of in-sample. It survives 1.5× and 2× costs and dies at 3× (−0.065). So execution
realism is not what breaks it; the edge decays on its own.

**3. The short side breaks out of sample.** Long +0.437 R, short **−0.403 R** — and in-sample the
short side was +0.098. On a sample where four of five markets rose, that is drift being harvested
long and paid back short.

**4. The concentration is extreme.** Top 1% of trades = 28% of gross profit, top 5% = **65%**,
top 10% = 83%. That is the honest signature of trend following rather than a defect — but combined
with a 77% drawdown and 3/12 profitable years it means the realised path is close to untradeable.

## Verdict

**The original Turtle mechanism does not show robust positive expectancy on this portfolio.** It is
strongly positive in-sample (+0.294 R, PF 2.41, 18/21 profitable years) and decays to roughly zero
out-of-sample (+0.018 R, PF 1.12, 3/12 profitable years), and what survives is one market. Ex-BTC
it is negative.

Two qualifications kept deliberately in front of that verdict. **The missing asset classes are a
real confound** — this is four bets, not twenty, and the diversification the system was designed
around is largely absent. And **System 2 is meaningfully better than System 1 on both blocks**
(+0.492 vs +0.049 in-sample; +0.075 vs −0.093 out-of-sample), which is consistent with the longer
channel being the more robust of the two and is worth carrying into any later comparison.

Nothing here was tuned, and nothing about these rules will be changed on the basis of the
out-of-sample block.
