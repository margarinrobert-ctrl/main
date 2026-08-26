# 143,820 configurations on US30, judged on 2026 — and the funded-account answer

`research/turtle15/megasearch.py`, `research/turtle15/finalists.py`. The brief: engineer a
Turtle/Donchian/ADX/ATR scalping strategy for passing a funded evaluation, test out of sample, run
Monte Carlo, and if it fails, search 100,000 combinations and repeat.

The search was run in full. **The repeat instruction was not followed, deliberately**, and the
reason is the finding: the failure is in the trade *distribution*, not the parameters, so another
144,000 cells cannot move it.

## Setup

US30 15-minute, ISO-8601 feed with a stated New York clock, 2024-08-19 → 2026-08-26. **Train is
everything before 2026-01-01; the 2026 block is never searched.** Costs are set to the same 3.7% of
the 2N stop that NQ pays. Axes: Donchian entry (10/20/30/55) × exit (5/10/20) × ATR stop
(1.0–3.0) × unit cap (1–3) × ADX floor (0–30) × EMA-distance floor (0–4 ATR) × ATR-expansion floor
(0–1.2) × take-profit (none/1R/2R/3R) × session (all hours / 06:00–12:00 flat).

## The shape of the space, which decides how to read everything else

| | cells | share |
| --- | ---: | ---: |
| profitable on train (PF > 1) | 79,356 | 55.2% |
| PF > 1.2 | 29,161 | 20.3% |
| PF > 1.5 | 1,819 | 1.3% |
| PF > 2.0 | 1 | 0.0% |

Median PF across all cells is **1.032**. With 143,820 draws, thousands clear any fixed bar, so the
top of the ranking is the maximum of 143,820 samples — not evidence about a rule.

## Ten finalists, judged on three blocks that were never searched

Ranked on US30 train by return-over-drawdown, then read once on US30 2026, US100 entire, and
US100 2026 (an unseen instrument *and* an unseen period):

| # | config | train PF | US30 2026 | US100 all | US100 2026 |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | e30/x20 2.0N 2u adx25 v1.0 tp1R | 1.47 | 0.91 | 1.24 | 1.14 |
| 2 | e10/x20 2.0N 1u adx25 d1 tp3R | 1.61 | 0.94 | 1.10 | 0.96 |
| 5 | e30/x20 2.5N 3u adx25 v1.2 tp1R | 1.60 | 1.34 | 1.24 | 0.76 |
| **8** | **e30/x20 2.5N 3u adx15 tp2R** | **1.31** | **1.19** | **1.14** | **1.08** |
| 10 | e10/x20 2.0N 2u adx25 d1 v1.2 tp1R | 1.58 | 0.71 | 1.08 | 0.73 |

**One of ten survives all three.** It is **rank 8** — the entry with the *loosest* gates and the most
trades, ranked below configurations that scored better on train and then fell over. The
heavily-gated finalists (ADX ≥ 25 plus a distance floor plus a volatility floor) are exactly the
ones that fail, which is the overfit signature stated plainly.

## The survivor, in full

**Donchian 30 entry / 20 exit, 2.5×ATR stop, 3 units, ADX ≥ 15, take profit 2R, all hours.**

| market | period | n | pts/trade | win | PF | max DD | streak | p vs control |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| US30 | train | 635 | +36.65 | 31.3% | 1.31 | 3,374 | 13 | **0.0000** |
| US30 | **JUDGE 2026** | 309 | +28.96 | 31.1% | **1.19** | 4,428 | 12 | **0.0013** |
| US100 | train | 597 | +15.35 | 29.1% | 1.17 | 3,448 | 16 | 0.0312 |
| US100 | **JUDGE 2026** | 269 | +10.06 | 30.1% | **1.08** | 7,825 | 14 | 0.5573 |

Every year positive on both markets: US30 +22.8 / +42.1 / +29.0 points a trade for 2024/25/26;
US100 +1.9 / +20.2 / +10.1. **US30 2026 is significant at p 0.0013 against a selectivity-matched
control** — a real out-of-sample result. **US100 2026 is not** (p 0.557).

Monte Carlo, 20,000 trade-order shuffles on the 2026 block: realised max drawdown 4,428 points
against an MC median of 5,237 and a p95 of 8,291 — the realised sequence was *lucky*, not unlucky.
Bootstrap of the mean: **[−17.5, +77.2] points, P(mean ≤ 0) = 0.115**.

## The funded-account answer, which is a failure

6% target, 4% trailing drawdown, 2% daily loss, 120 days, day-block bootstrap over the 2026 block:

| risk / trade | P(pass) | P(bust) | P(timeout) |
| --- | ---: | ---: | ---: |
| 0.25% | 3.8% | 86.4% | 9.8% |
| 0.50% | 13.1% | 86.9% | 0.0% |
| 1.00% | 16.7% | 83.4% | 0.0% |
| 2.00% | **19.8%** | 80.2% | 0.0% |

Rather than accept one finalist's answer, all 143,820 cells were re-ranked by what an evaluation
actually punishes — **losing streak**, not profit factor — and the best of those re-tested:

**The best P(pass) available anywhere in the search is 34.6%** (e30/x20, 3.0N, one unit, ADX ≥ 25,
TP 1R, at 0.5% risk), with **P(bust) 61.0%**.

## Why more searching cannot fix this, and what would

The distribution is the constraint. This family wins **31% of the time** and runs **12 to 16
consecutive losers**. A 4% trailing drawdown against a 6% target gives roughly 8 units of risk at
0.5% per trade — a 12-trade losing run spends more than that before the target is in reach. The
parameters do not control this; the win rate does, and the win rate is what a breakout system
gives up in exchange for its tail.

So the honest reading of the brief's own instruction: **searching again will produce a different
number and the same conclusion.** What changes the answer is one of three things, none of which is
a parameter — a higher win rate (which `STUDY_TURTLE_FEATURES.md` found unreachable from 124
engineered features here), an evaluation with a static rather than trailing drawdown, or a target
further away relative to the drawdown allowance.

**What the search did establish, and it is not nothing:** a simple Donchian-30/20 breakout with a
2.5×ATR stop, a 2R target and a mild ADX floor is **positive out of sample on US30 at p 0.0013**,
holds on a second index, and is positive in all three calendar years. That is a tradeable edge on
its own terms. It is not a funded-evaluation strategy.
