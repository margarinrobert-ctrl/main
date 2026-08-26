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

## Cross-market: the gate transfers, and a units error nearly hid it

`research/turtle15/markets.py`. US30 15-minute (2016-10 → 2025-07, 193,942 bars) and XAUUSD
15-minute resampled from 5m (2004-06 → 2026-01, 494,235 bars) arrived after the study above was
finished. **Every constant stayed frozen** — ADX ≥ 20, EMA distance ≥ 3.0 ATR, ATR ratio ≥ 1.10,
three units, all chosen on NQ. Nothing was refitted, which is the point: a rule needing new
constants per market has not transferred, it has been fitted twice.

Note these two markets have no research/holdout distinction of their own here. The gate was fitted
on NQ, so **both of their blocks are out-of-sample** — they are two independent samples, not a
selection pair.

### The units error, found in my own first run

The first pass charged the NQ round turn — 1.72 points — in each market's own points, and gold came
back at PF 0.35 to 0.74: a decisive-looking failure. It was arithmetic.

| market | median close | median ATR(20) | 2N stop | 1.72 points as % of risk |
| --- | ---: | ---: | ---: | ---: |
| NQ | 20,227 | 23.24 | 46.49 | 3.7% |
| US30 | 31,023 | 31.21 | 62.42 | 2.8% |
| XAUUSD | 1,306 | **1.59** | **3.17** | **54.2%** |

**Gold was paying more than half its stop distance in fees on every trade.** A cost is not a number,
it is a *fraction of the risk being taken*, and the two only coincide inside one instrument. Re-run
with each market paying the same fraction of its own ATR that NQ pays:

| market | block | baseline PF | **improved PF** | improved pts/trade | selectivity p |
| --- | --- | ---: | ---: | ---: | ---: |
| US30 | first 65% | 0.98 | **1.07** | +5.75 | 0.303 |
| US30 | last 35% | 0.86 | **1.30** | +33.82 | **0.0097** |
| XAUUSD | first 65% | 0.90 | **0.94** | −0.26 | 0.371 |
| XAUUSD | last 35% | 1.04 | **1.18** | +1.32 | 0.148 |

Pooled in ATR-normalised units so two instruments can be added at all:

| | trades | 2N-units per trade |
| --- | ---: | ---: |
| baseline, both markets | 17,073 | **−0.0655** |
| improved, both markets | 2,889 | **+0.1469** |

**Both markets flip from negative to positive, and the shipped gate is worse than no gate on US30
too** (PF 0.97 research / 0.79 locked against a 1.00 / 0.87 baseline) — the inversion replicates on
8.7 years of data that had no part in finding it.

**What it does not establish.** Only US30 clears significance on its own, and only in one of its two
blocks. Gold is *improved* but lands either side of break-even (0.94 and 1.18) — consistent with
`STUDY_XAUUSD_SCALP.md` finding no robust edge there by any route. **ES was requested and has still
not been supplied**, so the four-market comparison the brief asked for remains three markets. And
the BTC file supplied alongside these is **daily bars over thirteen months** — it cannot inform
15-minute work at all.

**The durable lesson is the units one.** Every cost figure on this branch is quoted in points, and
points are not comparable across instruments. Before any cross-market cost comparison, express the
cost as a fraction of the stop distance. Had that check not been run, this study would have
concluded that the gate fails on gold — with a table to prove it.

## The cross-market matrix — run at last, and it does not survive

`research/turtle15/crossmkt.py`. Three markets on one New York index: NQ, US30 and XAUUSD 15-minute,
58,058 common bars, 2022-12 → 2025-07 (NQ's span is the binding constraint).

### A join error that announced itself

The first panel reported **corr(NQ, US30) = 0.031** for two US equity indices. That number is not a
weak relationship, it is a wrong one: `fastbars` stamps `ts` in **UTC** while `mod` is already
**New York**, and the two disagree by 5 hours in winter and 4 in summer. Every engine in this
repository reads `mod`, so all the strategy work was always correct — but the panel joined on `ts`
and compared NQ against US30 bars five hours away. A constant shift would have been wrong too, for
the same reason it was wrong on the BTC feed; only a real DST-aware conversion lands every bar.

Corrected, with the equity-open volatility peak landing at 09:00–10:00 New York in all three series:

| | NQ | US30 | XAU |
| --- | ---: | ---: | ---: |
| NQ | 1.000 | **0.683** | 0.077 |
| US30 | 0.683 | 1.000 | 0.084 |
| XAU | 0.077 | 0.084 | 1.000 |

And the brief's point about correlations not being constant holds: rolling 500-bar NQ–US30 runs from
**−0.18 to +0.94**, with a p10–p90 range of +0.25 to +0.82.

*I wrote the alignment warning into that module's docstring and then walked into it in the next
command. The implausible number is what caught it — which is the argument for having a prior about
what a correlation should be before reading one.*

### The hypothesis, tested exactly as the brief framed it

Does NQ breaking out **while US30 confirms** continue more often, and does NQ breaking out **alone**
fail more often? On research the answer is a coherent, monotone yes — 23 gates tested:

| gate on top of the improved NQ setup | n | pts/trade | PF | p |
| --- | ---: | ---: | ---: | ---: |
| US30 12-bar momentum ≥ 0.5 | 167 | +50.08 | 1.88 | **0.0075** |
| US30 12-bar momentum ≥ 0 | 184 | +43.28 | 1.75 | **0.0143** |
| US30 also breaking its own channel | 124 | +56.94 | 1.97 | 0.0367 |
| US30 above its own EMA100 | 179 | +42.98 | 1.71 | 0.0398 |
| **US30 12-bar momentum < 0 (divergence)** | 61 | **−9.79** | **0.86** | 0.9578 |

Every confirmation direction positive, every divergence direction negative, monotone across three
horizons. Correlation regime does nothing (p 0.31–0.73); gold momentum does nothing (best p 0.10).

### And it fails out of sample

| block | | n | pts/trade | PF | p |
| --- | --- | ---: | ---: | ---: | ---: |
| research | improved gate | 204 | +32.90 | 1.53 | — |
| research | + US30 momentum ≥ 0 | 184 | +43.28 | 1.75 | **0.0138** |
| **LOCKED** | improved gate | 55 | +35.74 | 1.34 | — |
| **LOCKED** | + US30 momentum ≥ 0 | 51 | **+25.17** | **1.22** | **0.8067** |
| **LOCKED** | divergence bucket | 11 | **+85.96** | 2.72 | 0.2973 |

**The sign inverts.** Out of sample the confirmation gate is *worse* than not using it, and the
divergence bucket — which lost money on research — is the best cell on the board at n=11. Pooled,
the cross-market gate lowers NQ's result from +0.8516 to +0.8465 2N-units per trade.

So section 5 of the brief has an answer and it is **negative**: on this data, cross-market
confirmation is an attractive, internally coherent research finding that does not replicate. It is
**not** shipped in the Pine. Note the shape — strong on research, absent on the holdout — is the
ordinary way a 23-gate search fails, and the coherence of the research pattern is exactly what makes
it persuasive enough to be worth stating as a negative.

## Per-market comparison, pooled and ATR-normalised

Points are not comparable across instruments, so results are expressed in **2N-units** — profit
divided by the trade's own initial risk.

| | trades | 2N-units/trade | win | PF | max DD (2N) | worst streak |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ baseline | 1,854 | −0.0918 | 18.3% | 0.94 | 234.0 | 20 |
| **NQ improved** | 304 | **+0.8516** | 32.2% | **1.57** | 59.0 | 16 |
| NQ improved + cross-market | 235 | +0.8465 | 31.5% | 1.56 | 57.5 | 14 |
| US30 baseline | 4,917 | −0.1134 | 18.8% | 0.93 | 733.2 | 42 |
| **US30 improved** | 766 | **+0.2922** | 28.1% | **1.19** | 108.2 | 14 |
| XAUUSD baseline | 12,156 | −0.0461 | 18.4% | 0.97 | 1,743.8 | 39 |
| **XAUUSD improved** | 2,123 | **+0.0944** | 25.7% | **1.05** | 329.5 | 24 |

All three markets go from negative to positive and every drawdown falls by a factor of three or
more. **The ordering is the honest part**: NQ is where the gate was fitted, so +0.8516 carries that
selection. US30's **+0.2922** and gold's **+0.0944** are the unfitted estimates, and they are three
to nine times smaller. Expect the unfitted number, not the fitted one.

## The session constraint, measured at 15m for the first time

Signals restricted to the window, position forced flat at its end:

| window (New York) | research PF | **LOCKED PF** |
| --- | ---: | ---: |
| no session | 1.58 | **1.56** |
| 09:30–16:00 | 1.49 | **0.90** |
| 06:00–16:00 | 1.44 | **0.86** |
| 09:30–12:00 | 1.16 | **0.71** |
| 06:00–12:00 | 1.04 | **0.64** |

**Every windowed variant is negative out of sample**, and the damage is monotone in window length —
the shorter the day, the worse it gets. That is the ninth independent time the intraday constraint
has removed a result on this branch, and the monotonicity names the mechanism: these trades are paid
by being allowed to run. A 12:00 flatten does not trim the system, it removes what pays for it.

This is a genuine conflict with the standing requirement to be flat by noon, and it is not
resolvable by tuning: there is no window here that both closes daily and keeps the edge.

## 07:00–11:00 New York, searched on Sharpe and drawdown

`research/turtle15/session_opt.py`. The request was the best Sharpe and the smallest drawdown for a
07:00–11:00 window on 15 minutes. 102 configurations searched inside it — unit cap, ATR stop
multiple, exit channel length, all three gate thresholds — ranked by **Sharpe** with drawdown
reported beside it, never by profit. That objective is also the safer one: the unit cap chosen on
return-over-drawdown was the one structural choice that held out of sample, while choices made on
raw profit ran off the edges of their grids.

| configuration (07:00–11:00, flat 11:00) | research PF / Sharpe | **holdout PF / Sharpe** |
| --- | ---: | ---: |
| no gate at all | 0.65 / −2.28 | 0.79 / −1.07 |
| shipped gate, 3 units, 2.0N | 1.03 / +0.06 | **0.44 / −1.00** |
| best by Sharpe: 1 unit, 1.5N, ADX ≥ 20, dist ≥ 4.0, vol ≥ 0.90 | 1.23 / **+0.57** | **0.85 / −0.39** |

**Nothing in that window survives.** The best research Sharpe of +0.57 becomes −0.39.

### It is the window, not the flatten

Same 07:00–11:00 entries, only the exit policy changed:

| exit policy | holdout PF |
| --- | ---: |
| flat at 11:00 (as asked) | 0.44 |
| flat at 16:00 | 0.53 |
| no flatten, Turtle exits only | 0.45 |
| no flatten, one unit | 0.41 |
| *same gate, entries at any hour* | ***1.56*** |

Removing the clock does not rescue it. The damage is in **which breakouts those hours contain**, not
in cutting them short — which is a different mechanism from the one found for the 06:00–12:00 window
on the unconstrained family, where holding was what paid.

### Where the edge actually is

Improved gate, three units, no flatten, by entry window, **both blocks shown**:

| window (New York) | research PF / Sharpe | holdout PF / Sharpe | holdout max DD |
| --- | ---: | ---: | ---: |
| all hours | 1.58 / 1.40 | 1.56 / 1.10 | 2,742 |
| **07:00–11:00** | 1.38 / 0.66 | **0.42 / −1.44** | 2,979 |
| 11:00–16:00 | 1.94 / 1.60 | 1.85 / 1.10 | 1,343 |
| 16:00–20:00 | 3.08 / 1.33 | 1.92 / 1.05 | **741** |
| **11:00–24:00** | 1.90 / **1.68** | 1.85 / **1.38** | 1,408 |

**11:00 onward delivers both things the request asked for** — a better holdout Sharpe than trading
every hour (1.38 against 1.10) and roughly half the drawdown (1,408 against 2,742). 07:00–11:00 is
the single worst window tested.

**The caveat is not optional.** That table was read on both blocks, so choosing 11:00–24:00 from it
is partly a choice made on the holdout, and nothing was held back to check it afterwards. The
07:00–11:00 result is the clean one precisely because that window came from the request rather than
from a search.

### Two structural findings the search produced

**The channel exit is inert inside a short window.** Exit lengths of 5, 10 and 20 bars give
bit-identical results — median hold is **2 bars** and **no trade reaches 15**. A 10-bar channel low
cannot bind before the clock does. Inside four hours this is not a Turtle system; it is an ATR stop
and a clock wearing Turtle clothing, the same shape `STUDY_INTRADAY_HEAT.md` found when a
take-profit stopped binding.

**One unit is the lowest-drawdown answer, by a wide margin** — 318 points against 1,267 for four
units on the same research trades, and four units scored the worst Sharpe of all 48 risk cells
(−1.74). If a short window is traded at all, it should be traded small.

`pine/turtle/TURTLE_15M_SESSION_strategy.pine` ships the window free and defaulted to 07:00–11:00 as
requested, with the measured table in its header and a HUD row that turns **red** for any window
starting before 11:00, so a window known to fail out of sample can never be invisible in a
screenshot.
