# NAS100 backtest — semivariance asymmetry (SSRN 2815151)

Backtest of the "good vs bad volatility" idea from Baruník, Kočenda & Vácha,
*Asymmetric volatility connectedness on forex markets* (SSRN 2815151), adapted
to a single asset (NAS100) on ~9 years of 30-minute data (Nov 2016 – Oct 2025,
2,278 trading days).

## What the paper actually provides

The paper is a **measurement** paper, not a trading-rule paper. It decomposes
daily realized variance (from intraday returns) into:

- **RS⁻** — negative semivariance: volatility from down moves ("bad volatility")
- **RS⁺** — positive semivariance: volatility from up moves ("good volatility")

and studies the asymmetry **SAM = RS⁺ − RS⁻** across markets. The tradeable
single-asset adaptation tested here: compute daily RS⁺/RS⁻ from 30-minute
returns, form the normalized asymmetry over a rolling window W, and trade the
next day close-to-close on its sign. Three interpretations × W ∈ {1, 5, 20}:

| variant | rule |
|---|---|
| momentum | long when good vol dominates, short when bad vol dominates |
| contrarian | the opposite (bad vol → rebound) |
| long/flat | long when good vol dominates, else flat |

No look-ahead (signal at close t, return t+1), costs 2 bps per side,
out-of-sample split at 2022-01-01.

## Results (net of costs)

| strategy | CAGR | Sharpe | max DD | t-stat | OOS Sharpe |
|---|---|---|---|---|---|
| momentum W=1 | −19.0% | −0.92 | −86% | −2.76 | −0.83 |
| **contrarian W=1** | **+11.1%** | **0.46** | −28% | 1.37 | 0.39 |
| long/flat W=1 | −1.5% | −0.10 | −33% | −0.30 | −0.29 |
| contrarian W=20 | +10.5% | 0.44 | −28% | 1.31 | 0.28 |
| buy & hold | **+19.9%** | **0.79** | −36% | 2.38 | 0.45 |

Full grid in `results/results.csv`, equity curves in
`results/equity_curves.png`.

## Verdict: not profitable

1. **The paper's direct reading (momentum) loses badly** — Sharpe −0.92, −85%
   total. On NAS100, days dominated by good volatility do *not* precede more
   gains.
2. **The contrarian reading makes money in absolute terms** (+11% CAGR,
   Sharpe 0.46) — consistent with the asymmetric-volatility phenomenon (panic
   days precede rebounds) — but it is **not statistically significant**
   (t ≈ 1.4) and **still underperforms buy & hold** (Sharpe 0.79, CAGR 19.9%)
   with 132 round trips a year.
3. **The contrarian edge is one event.** 92% of its cumulative return came
   from the Feb–Jun 2020 COVID rebound. Excluding that window: Sharpe 0.16,
   t-stat 0.48 — indistinguishable from zero. Yearly P&L: 2017 −4%, 2018 −6%,
   2021 +3%, 2022 −4%, 2023 −2%.

So on this data the semivariance-asymmetry signal, in any of the nine
variants, does not produce an edge over simply holding NAS100 — which is what
you'd expect: the paper measures how volatility propagates, it never claims
the sign of SAM predicts index returns.

## Reproduce

```bash
pip install pandas numpy matplotlib
python3 backtest.py
```
