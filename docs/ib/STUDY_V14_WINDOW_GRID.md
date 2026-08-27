# 1,290,240 cells per side in 07:00–11:00: the long side is an overfit, the short side is an entry mechanic


> **CORRECTION (V15).** Every limit-entry figure in this study was produced by `eem.run`, whose
> fill model scans forward from each signal in turn and fills at *that* signal's level — so a limit
> priced eight bars ago outranks a nearer one priced since. That needs eight simultaneous resting
> orders and for the far one to fill first; a script has one live order. Re-measured with the
> implementable model the legs keep **24–47%** of their R, with every shared trade identical (exit
> bar 100%, correlation 1.0000). Read the numbers below as an upper bound, not as a result. See
> `docs/ib/STUDY_V15_BOOK.md` §2 and `research/v15/v15_parity.py`. Market-order results are
> unaffected.

Grid fixed before it ran, and its rules chosen with the user: **entries only inside 07:00–11:00 New
York with exits running free**; a configuration must hold on **US30 and US100 independently**;
**both sides ranked separately**; ranked on **return over max drawdown**, the one criterion on this
branch whose in-sample ordering has survived out of sample. Train is everything before 2026-01-01.
**2026 was read once, at the end.**

## The engine

1.29M backtests is not affordable one at a time, but **a trade's outcome depends only on its signal
bar and its geometry** — not on which indicator produced the signal. So the price walk is done once
per (signal bar, geometry) and every configuration afterwards is an array lookup plus a numba
position-lock walk over the signal bars only. **5.16M cells in 16 seconds.**

`research/v14/v14tensor.py`, verified against `eem.run` (itself verified against `mirror.run`)
across **16 geometries on both sides and both instruments — exact trade counts, net within 1 point
in every cell.** One discrepancy was chased rather than tolerated: the first version indexed the
exit channel one bar staler than the engine, worth 0.20 points a trade. It was caught because the
trade *count* matched exactly and the net did not.

Grid: MA fast (8) × MA slow (7) × MA mode (3: off / state / fresh-cross-within-8) × ADX floor (6) ×
Choppiness ceiling (4) × entry mechanic (4: market, or a resting limit at 0.25/0.50/0.75 × ATR(5))
× stop (5) × take profit (4) × exit channel (4) = **1,290,240 per side per instrument.**

## The number that frames everything else

| | profitable on US30 | on US100 | **on BOTH** |
| --- | ---: | ---: | ---: |
| long grid | 71.0% | 72.5% | **58.0%** |
| short grid | 47.2% | 85.8% | **44.2%** |

**The top of a 1.29M ranking is the maximum of roughly 750,000 profitable draws.** Row 1 of the long
ranking shows profit factor 2.79 / 3.10 — that is what such a maximum looks like, and it is not
evidence of anything. The robust reading is what the **top 1000 agree on**, never the best row.

## Read once on 2026

| | long | short |
| --- | ---: | ---: |
| top-1000 still profitable on **both** | **0.3%** | **73.3%** |
| top-1000 still PF > 1.2 on both | **0.0%** | 28.4% |
| median 2026 PF (worse instrument) | **0.52** | 1.12 |
| the train #1 config on 2026 | 2.79/3.10 → **0.47/1.82** | 1.79/1.61 → 1.43/1.05 |

**Inside this window the long side is an overfit and the short side is not.** A limit entry does not
rescue the long side either — US30 2026 goes 0.72 with a market order and 0.75 with the limit.

## What actually earns the short result: the entry mechanic

Same geometry, same window, **no indicator at all** — only the order type changes:

| | market order | resting limit 0.75 × ATR(5) |
| --- | ---: | ---: |
| US30 train | PF 0.77, −17.71 pts | **PF 1.44, +24.73** |
| US30 2026 | PF 1.05, +3.78 | **PF 1.43, +27.32** |
| US100 train | PF 1.16, +7.72 | **PF 1.42, +17.50** |
| US100 2026 | PF 0.92, −5.97 | **PF 1.14, +9.00** |

The indicators then add on top, consistently in all four cells: 1.44→1.46, 1.43→**1.82**,
1.42→1.58, 1.14→**1.46**. Both parts are real; **the mechanic is the larger one.**

Shorting a rally back *up* into a resting limit is selling strength — which is why a short book works
here when "shorts lose by existing" has been the standing result everywhere else on this branch.

### The shipped configuration

Donchian 30 down-breakout · EMA 13 < EMA 34 · ADX ≥ 22 · resting limit 0.75 × ATR(5) above, 8-bar
expiry · 2.5N stop · 2R target · 25-bar exit channel · one unit · entries 07:00–11:00, exits free.

| | n | PF | pts/trade | Sharpe | ret/DD |
| --- | ---: | ---: | ---: | ---: | ---: |
| US30 train *(chosen)* | 145 | 1.46 | +27.89 | 3.04 | 4.98 |
| **US30 2026 JUDGE** | 71 | **1.82** | +48.28 | **4.07** | 4.25 |
| US100 train *(chosen)* | 139 | 1.58 | +25.18 | 3.09 | 6.99 |
| **US100 2026 JUDGE** | 75 | **1.46** | +28.25 | **2.69** | 2.25 |

What the top 1000 short configurations agree on — the robust reading: **ADX ≥ 22 (80%)**, exit
channel 25 (69%), **limit entry (100%; 0.75N in 63%)**, stop 2.5N (58%), a target of 1.5–2R (79%).
And **MA mode "off" in 58%** — the moving average is the least important component of the four.

## The limitation to weigh most

**This rests on a limit entry that could not be settled at 1-minute resolution.**
`STUDY_V10_LIMIT.md` established that a limit-entry backtest run on the same bars that decide the
exits measures intrabar ordering, and that three such artifacts together were worth a **Sharpe of
11** on a rule-free test. The engine here carries all three fixes, and the standing rule is that
these questions are settled on `limit_entry.run_1m`, the true 1-minute path. **Only 15-minute bars
were supplied for US30 and US100, so that test could not be run.**

The best available proxy is a **through-fill** requirement — price must trade *beyond* the limit
before a fill counts, which removes precisely the trades a touch-fill backtest invents:

| through | US30 train | US30 2026 | US100 train | US100 2026 |
| --- | --- | --- | --- | --- |
| 0.00N | 1.46 / Sh 3.04 | 1.82 / 4.07 | 1.58 / 3.09 | 1.46 / 2.69 |
| 0.10N | 1.35 / 2.28 | 1.76 / 3.81 | 1.39 / 2.23 | 1.30 / 1.84 |
| 0.20N | 1.20 / 1.38 | 1.67 / 3.44 | 1.36 / 2.07 | 1.22 / 1.47 |

It degrades and stays positive in all four cells. **Reassuring, not conclusive.** One-minute US30 and
US100 data makes it answerable.

Shipped as `pine/turtle/V14_WINDOW_SHORT_strategy.pine`.
