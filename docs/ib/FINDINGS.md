# Initial Balance — what the study found

Full report: [`STUDY_IB.md`](STUDY_IB.md). Strategy code: `src/lib/quant/strategies/initialBalance.ts`.
TradingView port: `NQ_InitialBalance.pine`.

Three years of 5-minute NQ (Dec 2022 – Dec 2025, 751 RTH sessions), entries modelled as **real
resting limit orders** that only fill if price trades through them, costs of 1 tick spread + 1 tick
slippage per side + $4 commission.

## 1. The published geometry is regime-dependent, not edged

| period | trades | net edge | PF | HAC t |
| --- | --- | --- | --- | --- |
| whole sample | 533 | +7.1 ticks | 1.067 | 0.57 |
| Dec 2022 – Jan 2025 (research) | 366 | **−4.3 ticks** | 0.96 | −0.37 |
| Jan 2025 – Dec 2025 (holdout) | 167 | **+32.1 ticks** | 1.25 | 1.06 |

The whole-sample number is the average of a losing two years and a winning one. Neither half is
statistically significant on its own, and the split is the finding: **this strategy's result is
dominated by regime, not by its geometry.** A backtest run only on 2025 would look like a discovery.

## 2. Optimising it makes it strictly worse — and fools the plateau test

| | result |
| --- | --- |
| best of 1,200 parameter sets, in-sample | Sharpe 1.95, +71.9 ticks/trade, PF 1.78 |
| same procedure, walk-forward out-of-sample | Sharpe **−0.71**, −16.9 ticks/trade, PF 0.83 |
| walk-forward efficiency | −0.52 |
| folds profitable | 29% |
| probability of backtest overfitting | **0.567** (>0.5 = the procedure selects noise) |
| deflated Sharpe | 0.000 |

The in-sample optimum ranked the published geometry **#923 of 1,200** — and then lost money out of
sample while the published geometry made some.

**The important methodological result:** that in-sample optimum sat on a textbook **plateau** —
neighbour stability 0.90, 100% of adjacent parameter sets also profitable — and still failed
completely out of sample. A smooth parameter surface is a necessary condition, not a sufficient
one. Anyone using "the parameters aren't a spike" as their overfitting check is not protected.

What the search actually discovered was `sideMode=1` (longs only) in all twelve of its top
configurations. That is the NQ uptrend, not an edge in the setup — the same setting lost money over
the research half.

## 3. Monte Carlo on the walk-forward trades

20,000 paths, $50,000 account:

| | reshuffled order | resampled with replacement |
| --- | --- | --- |
| median max drawdown | 35.2% | 36.6% |
| 95th percentile drawdown | 47.5% | 70.6% |
| P(ending below start) | 100% | 80% |
| P(25% drawdown) | 97.8% | 76.9% |

## 4. Anomaly search — 20 slices, nothing survives

Every feature computable at the moment the IB window closes was tested for **lift** (this bucket's
mean R minus every other trade's), because a slice of a profitable strategy looks profitable
regardless. Weekday, overnight gap, where the first hour closed in its range, whether it took the
prior session's extreme, range versus the prior day, range percentile.

**Nothing survived Benjamini-Hochberg control.** The strongest result was that **wide first hours
are worse**: −0.33R lift, t = −2.18, raw p = 0.029, q = 0.588.

That one is worth keeping anyway, because it is the only result that had a reason to exist *before*
it was measured: a wide IB makes the 60% stop enormous while the 50% target scales identically, so
the same geometry risks far more for the same reward. A finding with a mechanism survives a failed
significance test better than a finding without one — it just cannot be called established.

## 5. The one change worth making

Replace the absolute points range filter with a **rolling percentile** one. A 100-point first hour
meant something very different in 2023 than in 2025, so a fixed threshold silently becomes a
different filter as volatility drifts.

| configuration | research half | holdout half |
| --- | --- | --- |
| published geometry | −4.3 ticks, PF 0.96 | +32.1 ticks, PF 1.25 |
| **+ skip widest 40% of IB days** | **+14.7 ticks, PF 1.19** | **+30.4 ticks, PF 1.29** |

Consistent direction in both halves, motivated before it was measured, and it turns the losing half
positive. It is still not significant (t = 1.16 and 1.20). It is an improvement, not a fix.

Two filters that look better and should be rejected: skipping the widest 20% (holdout t = 1.85 but
research t = 0.26) and longs-only (holdout t = 1.96 but research t = −0.61). Both are 2025 regime,
and both would have been selected by an optimiser looking only at the recent half.

## 6. Bottom line

The IB breakout-retracement on NQ is **not a demonstrated edge**. It is a plausible mechanism with
a positive tilt that is inside the noise band, whose measured profitability depends on which
two-year window you look at. The percentile filter improves it on defensible grounds. Nothing here
justifies risk capital, and the specific thing to watch in forward testing is not the equity curve
but **whether the 2023–24 loss regime returns**.

## What was built to reach this conclusion

- The backtest engine gained **resting limit orders** — an order that works for hours, fills only on
  a trade-through, and is cancelled at the session close. The IB entry is defined by a price that
  has to come to you; modelling it as a market order at the next open measures a different and much
  easier strategy. Covered by 10 tests including exact-geometry assertions.
- `ibFeatures.ts` computes per-session IB features and the lift-based conditional test with FDR
  control, so "which days are worth trading" is answered mechanically rather than by eye.
