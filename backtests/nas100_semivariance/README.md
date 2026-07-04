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

## Deep dive: contrarian W=1 (`advanced_analysis.py`)

Advanced metrics, harder benchmarks and Monte Carlo for the best variant.
Outputs: `results/benchmarks.csv`, `results/advanced_metrics.csv`,
`results/monte_carlo.png`, `results/diagnostics.png`.

**Vs harder benchmarks (net of costs).** Simple mechanical baselines beat it
on risk-adjusted terms:

| | contrarian W=1 | buy & hold | 200d MA long/flat | vol-target 10% B&H |
|---|---|---|---|---|
| CAGR | 11.1% | 19.9% | 14.5% | 11.2% |
| Sharpe | 0.46 | 0.79 | **0.85** | **0.98** |
| Sortino | 0.68 | 1.03 | 0.91 | 1.25 |
| Calmar | 0.40 | 0.56 | 0.57 | 0.65 |
| max DD | −27.8% | −35.6% | −25.6% | **−17.2%** |
| longest DD | **1,079 days** | 535 | 389 | 404 |

Its one structural virtue: positive skew (+0.87) and a tail ratio > 1 — it's
long crash-rebound convexity, the opposite profile of the short-vol-flavored
baselines. But it spent 4.3 years in its longest drawdown and its profit
factor is only 1.09.

**Block-bootstrap Monte Carlo** (10,000 paths, 20-day blocks of its own net
returns): median CAGR 11%, but the 5th percentile path loses money over 9
years (CAGR −1.1%), P(overall loss) ≈ 7%, median max drawdown −35% with a 5%
chance of −55% or worse.

**Permutation test** (10,000 circular shifts of the position series over the
same prices — same exposure, same turnover, timing destroyed): realized
Sharpe 0.46 vs null mean −0.26, **p = 0.015**. So the *timing* is real
relative to a coin-flip long/short book — but that alpha is again
concentrated in the 2020 window (ex-COVID Sharpe 0.16, Sortino 0.24), and it
still doesn't survive comparison with trivial long-only baselines.

## Expected value & the long-only refinement

Per-side EV of contrarian W=1 (net of costs, 1,195 trades, avg hold 1.9 days):

| | EV/trade | win rate |
|---|---|---|
| long trades (after bad-vol days) | **+0.217%** | 69.5% |
| short trades (after good-vol days) | −0.058% | 52.7% |
| combined | +0.079% (~19 pts at NAS100 ≈ 24,600) | 61.1% |

All the edge is on the long side, so the best version is **long-only
contrarian W=1** (long the day after bad volatility dominates, flat
otherwise): CAGR 15.4%, Sharpe 0.81, max DD −25.9%, t-stat 2.44, ex-COVID
Sharpe 0.70, OOS Sharpe 0.56 — matches buy & hold risk-adjusted with ~48%
exposure. Caveat: this refinement was found by inspecting the same data
(selection bias), so treat the headline numbers as optimistic.

TradingView implementation: `../../SemivarianceContrarian.pine`
(Pine v6 strategy, run on a 30-minute NAS100 chart; long-only by default,
long/short modes and the W window as inputs).

## Martingale / split-size research (`martingale_analysis.py`)

Position-sizing schemes on top of long-only contrarian W=1, evaluated on the
historical path **and** on 10,000 bootstrapped 9-year trade sequences (sizing
is path-dependent, so the Monte Carlo re-runs each scheme's state machine per
path). Ruin = a 50% account drawdown at any point.

| scheme | hist. CAGR | hist. maxDD | MC median maxDD | **P(ruin)** |
|---|---|---|---|---|
| fixed 1x | 16.9% | −22.9% | −21.8% | 0.1% |
| martingale ×2, cap 4x | 36.5% | −21.4% | −40.1% | **24.5%** |
| martingale ×2, cap 8x | 41.1% | −21.4% | −48.3% | **46.5%** |
| anti-martingale ×2, cap 4x | 21.4% | −71.2% | −58.4% | **75.3%** |
| split-entry 1/3, full = 1x | 9.2% | **−11.0%** | −13.7% | **0.0%** |
| split-entry 1/3, full = 2x | 18.0% | −21.2% | −26.3% | 1.6% |

The classic martingale is the textbook mirage: the realized 2016–2025 path
happened to contain no long losing streak (70% trade win rate), so doubling
after losses *looks* free — same drawdown, double the CAGR. Reshuffle the same
trades and a quarter (cap 4x) to half (cap 8x) of alternate histories halve
the account. Sizing cannot add expectancy; it only reshapes the outcome
distribution around the same edge.

The defensible "split size" version is **tranche averaging-down**: enter 1/3
of full size, add 1/3 at the start of each day the trade is underwater (max
3). At a 1x cap it halves the max drawdown (−11% vs −23%) for proportionally
lower return; at a 2x cap it matches fixed-1x returns with P(ruin) 1.6%.
Both are implemented in `SemivarianceContrarian.pine` ("Sizing mode" input);
the martingale mode is included for experimentation but capped and labeled
high-risk.

## Robustness study (`robustness_analysis.py`)

Four tests over the strategy's full parameter space — W ∈ 1..30 × three
signal modes = 90 sets, fixed 1x sizing. Outputs: `results/param_grid.csv`,
`clusters.csv`, `walk_forward.csv` + three charts.

**1. Parameter stability.** Long-only contrarian is profitable for *all 30*
W values (median Sharpe 0.76); L/S contrarian all 30 positive (median 0.44);
L/S momentum all 30 negative. The long-only curve is a plateau, not a spike:
W 4–13 all ≥ 0.83, peak at **W=8 (Sharpe 1.02, CAGR 20.5%, t 3.07, ex-COVID
Sharpe 0.90, OOS Sharpe 0.60)** with a spike score of only +0.21 vs its
neighbours. The signal direction is robust; the exact window barely matters.

**2. Monte Carlo per parameter set** (2,000 block-bootstrap paths each).
W=8 long-only: 5th-percentile Sharpe 0.55, P(Sharpe<0) = 0.05%, P(−50% DD)
≈ 0.1%. Every long-only set has P(Sharpe<0) < 1%. Every momentum set has
P(ruin) > 90%.

**3. Cluster analysis** (hierarchical, on the 90×90 daily-return correlation
matrix). Five clusters: one big robust family (all contrarian sets W≥2,
n=58, median Sharpe 0.62), a small W=1 cluster (W=1 behaves differently from
the rest — another reason to prefer W=8), and three momentum clusters that
are uniformly toxic. The recommended config sits inside the robust family.

**4. Walk-forward** (re-pick the best set every 126 days by trailing-756-day
Sharpe, trade it OOS; 13 refits, 1,522 OOS days). The re-selected portfolio
collapses: **OOS Sharpe 0.19 vs average in-sample Sharpe of the picks 1.18
(walk-forward efficiency 0.16)**, while *fixed* W=1 long-only scored 0.87 on
the same OOS days (buy & hold 0.73). Lesson: the edge survives holding a
plateau parameter; it does not survive chasing recent winners.

Net recommendation: **long-only contrarian, W=8, never re-optimized** —
the Pine strategy's defaults.

## Fixing the walk-forward (`walk_forward_optimization.py`)

Can a selection *process* pass walk-forward? Five processes on identical OOS
days (Oct 2019 – Oct 2025), ordered by how much per-fold fitting they do:

| process | OOS Sharpe | WF efficiency | OOS maxDD |
|---|---|---|---|
| A greedy best-of-90 (the failure) | 0.19 | 0.16 | −45.9% |
| **B plateau ensemble** (equal-weight long-only W=2..30, no fitting) | **0.79** | **0.94** | −24.9% |
| C smoothed selection (pick best W±2-averaged trailing Sharpe) | 0.70 | 0.72 | −26.3% |
| D top-5 ensemble | 0.43 | 0.35 | −30.6% |
| E fixed W=8 (full-sample pick, benchmark only) | 0.98 | 0.98 | −23.3% |
| buy & hold | 0.73 | — | −35.6% |

The pattern is monotone: the less a process fits per fold, the better it
walks forward. The **plateau ensemble passes cleanly** (efficiency 0.94,
beats buy & hold risk-adjusted with 11pts less drawdown) and has *nothing*
to overfit — it holds a graded position equal to the share of W∈2..30
windows whose SAM is negative. Smoothed selection also passes (0.72).
Averaging is what works; picking is what fails.

## Reproduce

```bash
pip install pandas numpy matplotlib scipy
python3 backtest.py            # 9-variant grid vs buy & hold
python3 advanced_analysis.py   # deep dive + Monte Carlo on contrarian W=1
```
