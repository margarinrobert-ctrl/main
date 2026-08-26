# The 15-minute Turtle: two of its three filters are inverted

`research/turtle15/`, `pine/turtle/TURTLE_LONG_15M_strategy.pine`. The brief was to improve the
existing Turtle on 15-minute NQ/ES/YM/GC without replacing it — preserve the architecture, analyse
the existing features first, engineer only from them, build a chop detector, and prove any change
survives walk-forward and perturbation.

**Only NQ was available.** ES, YM and GC have never been supplied to this environment, and the
XAUUSD and US30 feeds that once were have been wiped by container recycles. So **section 5 of the
brief — the cross-market matrix — was not run at all**, and there is no cross-market feature in the
shipped script. Everything below is one instrument.

## The baseline, which is where the problem starts

Raw Turtle on NQ 15m — 20/55 entries, 10/20 exits, 2N stop, 0.5N ladder, 4 units, skip-after-winner,
MNQ fees and slippage:

| block | n | pts/trade | win | PF | max DD | worst streak |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| research | 1,238 | −3.61 | 17.4% | **0.94** | 8,032 | 18 |
| holdout | 616 | −5.60 | 20.3% | **0.94** | 10,237 | 20 |

And the shipped preset's own gate, applied at 15m, is far worse than no gate at all:

| | n | pts/trade | PF | max DD | streak | vs selectivity control |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| T1 as shipped (ADX < 22 **and** dist < 3.964), research | 671 | **−15.83** | **0.73** | 11,565 | 34 | **p 0.9878** |

A random filter keeping the same proportion of breakouts beats it 99 times in 100. That is the
finding the rest of this study is about: the filters are not weak on 15 minutes, they are
**pointing the wrong way**.

## The ablation

31 features engineered strictly from the Turtle's own components — Donchian geometry, ATR(20),
ADX(14)/DI, EMA(100) — plus minute-of-day. Truncation audit: 248 checks, 0 mismatches. Each gate
tested against a **selectivity-matched control**: 4,000 random filters keeping the same number of
baseline trades. **21 of 112 gates cleared p < 0.05 against 5.6 expected by chance.**

The survivors cluster into three coherent families, and two of them are the shipped filters
reversed:

**ADX — ceiling becomes floor.**

| direction | threshold | n | pts/trade | PF | p |
| --- | --- | ---: | ---: | ---: | ---: |
| ceiling (shipped) | ≤ 18 | 515 | −19.37 | 0.65 | 0.983 |
| ceiling (shipped) | ≤ 22 | 778 | −13.98 | 0.76 | 0.981 |
| **floor** | ≥ 20 | 872 | +8.52 | 1.14 | **0.0003** |
| **floor** | ≥ 22 | 764 | +9.12 | 1.15 | **0.0027** |

**EMA100 distance — ceiling becomes floor, and the curve is monotone.**

| direction | threshold | n | pts/trade | PF | p |
| --- | --- | ---: | ---: | ---: | ---: |
| ceiling (shipped) | ≤ 3.196 | 929 | −11.82 | 0.81 | 0.981 |
| ceiling (shipped) | ≤ 3.964 | 1,041 | −7.92 | 0.87 | 0.938 |
| **floor** | ≥ 2 | 780 | +2.74 | 1.04 | 0.093 |
| **floor** | ≥ 3 | 606 | +11.84 | 1.20 | **0.0063** |
| **floor** | ≥ 4 | 459 | +17.91 | 1.31 | **0.0067** |

**ATR expansion — new, with no counterpart in the shipped rules.** `ATR(20) / mean(ATR(20), 200)`,
plateau PF 1.52–1.60 across floors of 1.05 to 1.15.

**Why "extended" reverses is worth stating plainly.** The Turtle's not-extended filter is a
mean-reversion assumption bolted onto a trend system: don't buy what has already run. On a daily
chart that is a real risk. On a 15-minute chart, distance from a 100-bar EMA measured in ATR is not
"overbought" — it is the *evidence that a directional move exists at all*, and it is the single
best separator in the whole feature set.

## The three gates are not the same gate

Pairwise |correlation| among ADX, EMA distance and ATR ratio is at most **0.23**, so they stack
rather than repeat:

| gate | n | keep | pts/trade | PF | max DD | p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ADX ≥ 22 | 764 | 62% | +9.12 | 1.15 | 3,876 | 0.0032 |
| EMA dist ≥ 3.0 | 606 | 49% | +11.84 | 1.20 | 3,744 | 0.0060 |
| ATR ratio ≥ 1.10 | 505 | 41% | +13.66 | 1.19 | 3,781 | 0.0080 |
| ADX + ATR | 350 | 28% | +26.50 | 1.38 | 2,568 | 0.0013 |
| dist + ATR | 249 | 20% | +35.97 | 1.52 | 1,914 | 0.0015 |
| **all three** | 209 | 17% | **+39.36** | **1.57** | **1,986** | 0.0018 |

## The chop detector is the three gates counted

The brief asked for a four-state regime classifier. Counting how many of the three conditions hold
produces one, and it grades **monotonically on research**:

| score | research PF | holdout PF |
| --- | ---: | ---: |
| 3/3 strong trend | **1.58** | 1.56 |
| 2/3 developing | 1.19 | 1.66 |
| 1/3 transition | 0.93 | 1.13 |
| 0/3 chop | **0.63** | 0.91 |

## Perturbation, and one honest refusal

ADX has a plateau from 18 to 22 (PF 1.50–1.57) and degrades above 25. ATR ratio has a plateau from
1.05 to 1.15. **EMA distance does not plateau — it rises monotonically to PF 2.06 at ≥ 4.5 ATR on
n=142.** That is a ridge running off the edge of the grid, which on this branch has meant buying a
smaller sample rather than finding an edge. **3.0 was chosen as the interior of the curve, not its
peak.** The same reasoning kept the ATR stop at the Turtle's 2N even though 2.5N and 3.0N scored
better: a wider stop buys hold time.

**Unit cap 4 → 3, on risk-adjusted grounds only.** Raw profit prefers 4 units; return over drawdown
prefers 3 (5.23 against 4.14 on research) — and **that ordering held out of sample** (1.68 against
1.46). Drawdown is what a funded evaluation measures.

**Skip-after-winner is inert at 15m**: PF 1.57 with it and 1.57 without, 209 trades against 211.
Kept because it is part of the specification, not because it earns anything.

## Walk-forward and the holdout

Five rolling windows within the research block, configuration frozen: **all five positive**, PF 1.19
to 2.40, where the baseline runs 0.83 to 1.13.

Multiplicity, stated before the reveal: about **173 research evaluations** — 112 ablation gates, ~34
threshold rungs, 7 combinations, 20 perturbation cells.

| | research | | | holdout | | |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| | n | pts/trade | PF | n | pts/trade | PF |
| raw Turtle | 1,238 | −3.61 | 0.94 | 616 | −5.60 | 0.94 |
| shipped preset | 671 | −15.83 | 0.73 | 345 | +0.86 | 1.01 |
| **improved** | 216 | +34.34 | **1.58** | 88 | +52.47 | **1.56** |

**Research 1.58 → holdout 1.56 is the right shape.** Max drawdown 8,032 → 1,417 points on research,
worst losing streak 18 → 16 (6 on the holdout). Every full year is positive: 2023 +28.03, 2024
+49.13, 2025 +45.47 points a trade — no single year carries it.

Stress: selectivity control on the holdout **p 0.0335**. Trade-order Monte Carlo, 20,000 shuffles —
realised drawdown 2,742 points against a median of 1,951 and a p95 of 3,108, so the realised
sequence was unlucky but unremarkable. Costs: PF 1.62 at zero, 1.56 as modelled, 1.50 at 2×, 1.44 at
3×, **1.34 at 5×**.

Prop-firm shape, holdout, one MNQ contract: net $9,235, max drawdown $5,483, return/DD 1.68, worst
day −$1,916, worst week −$1,839, worst month −$1,154, 6.8 trades a month, longest losing run 6, win
rate 36.4% at a 2.72:1 payoff.

## What is not established

**n = 88 on the holdout, and the interval is wide.** The selectivity control gives p 0.0335, but a
bootstrap of the mean gives **[−23.9, +140.7] points with P(mean ≤ 0) = 0.098**. The payoff is
fat-tailed by construction — 36% win rate at 2.72:1 — so the *direction* is supported and the
*magnitude* is not resolved. Anyone reading +52.47 as a forecast is reading the wrong number.

**On the holdout the 2-of-3 bucket earned more in total** than 3-of-3: n 308 at +47.66 (PF 1.66)
against n 88 at +52.47 (PF 1.56). `minScore` is exposed so this is visible, and it is left at 3,
because loosening it on the strength of the holdout would spend the only block reserved for
judging.

**No cross-market anything.** The correlation matrix, the ES/YM confirmation test, the equity/gold
regime work and the per-market comparison table all require data this environment does not have.
They are not negative results; they are unrun.
