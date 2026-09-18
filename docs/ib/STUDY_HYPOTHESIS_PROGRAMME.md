# Eight breakout hypotheses, four markets: one candidate, and it is not a scalp

*Brief: research continuously, reject and improve; intraday trend-following scalping, avoid chop,
Turtle-style breakout triggers; test independently across all four markets; rank by robustness
rather than net profit; build a portfolio if the parts are complementary.*

**Result: one candidate survives — H5 "break and retest", robustness 74/100, +0.0435 R/trade over
845 out-of-sample trades on the three indices, P(edge ≤ 0) = 4.2%.** It fails on gold, dies at 1.5×
the assumed costs, and its geometry (4×ATR stop, 3R target, four-hour hold) means **it is not a
scalp**. Everything else in the library is at or below zero out of sample.

Two findings matter more than the ranking: **the eight hypotheses are mostly one hypothesis**, and
**strategy returns across markets are nearly uncorrelated even though prices are not** — which is
where the only real portfolio opportunity lies.

`research/hypo/`.

---

## 1. The library, and why each entry exists

An unconditional Donchian breakout is already known here to be negative gross on gold and to fail
out of sample on the indices, while a chop *filter* bolted on afterwards is worth about +0.05 R.
So the library varies the **mechanism by which chop is avoided**, and the axis it tests is:

> a **filter** excludes bars after the fact; a **setup** requires a precondition as part of the
> trigger.

| | hypothesis | market rationale |
| --- | --- | --- |
| H1 | Donchian breakout | control — the classic Turtle trigger |
| H2 | **squeeze breakout** | a tight range has stored disagreement; its resolution carries |
| H3 | opening-range break | the opening auction prices overnight information; breaking it is agreement |
| H4 | prior-session high | a level everyone sees accumulates resting orders |
| H5 | **break and retest** | a level retested and held has already survived the false-break test |
| H6 | MTF-aligned break | an intraday break with the dominant trend is continuation, against it noise |
| H7 | participation break | a real break brings volume; a false one leaks on thin activity |
| H8 | NR expansion | the narrowest bar marks the pause before expansion |

H2, H5 and H8 are *setups* in the sense above; the rest are filters or plain triggers.

## 2. Gross first: is there any signal?

Zero-cost expectancy separates a signal problem from an execution problem. Research block,
09:00–13:00, target 2R:

| hypothesis | NQ | US100 | US30 | XAUUSD |
| --- | ---: | ---: | ---: | ---: |
| H1 Donchian (2×ATR) | +0.033 | +0.075 | +0.065 | −0.020 |
| **H5 break and retest (2×ATR)** | **+0.121** | **+0.092** | **+0.063** | **+0.006** |
| H6 MTF-aligned (3×ATR) | +0.038 | +0.080 | +0.058 | +0.002 |
| H3 opening range (2×ATR) | +0.173 | +0.025 | +0.046 | +0.004 |
| H2 squeeze (2×ATR) | −0.155 | +0.042 | +0.096 | −0.024 |

**H5 and H6 are positive on all four markets gross**; H5 reaches median PF 1.24 and Sharpe 1.38
across markets. So signal exists — the question is whether it clears the round turn.

## 3. Net, and the corner problem

Nothing is positive on all four markets net. The best cells are **3/4**, and every one of them sits
at the widest geometry tested — which is the cost-drag signature, so the grid was extended to
8×ATR before reading it:

| hypothesis | stop | target | hold | markets + | med E[R] | med PF | med Sharpe | worst DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| H6 MTF-aligned | 4×ATR | 3R | 48 | 3 | +0.0221 | 1.080 | 0.46 | 320 R |
| **H5 break and retest** | 4×ATR | 3R | 48 | 3 | +0.0207 | 1.092 | 0.49 | **25 R** |
| H7 participation | 4×ATR | 3R | 48 | 3 | +0.0175 | 1.065 | 0.39 | 454 R |

**XAUUSD is the dissenting market in every case** — for the reasons `STUDY_XAUUSD_SCALP.md`
measured: a cost floor roughly three times the indices' and no gross signal at a scalping stop.

**A 4×ATR stop held 48 bars is a four-hour trade with a stop near 60 US30 points. That is not a
scalp**, and the brief asked for one. The scalping constraint is what fails, not the trend
hypothesis — the same conclusion the gold study reached independently.

## 4. Ranked research table

Ranked by robustness, not profit. Robustness = 25 × markets-positive + 25 × parameter plateau +
30 × out-of-sample retention + 20 × cost-stress survival.

| strategy | markets | OOS E[R] | OOS+ | trades | PF | Sharpe | Sortino | worst DD | plateau | **robust** | status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| **H5 break and retest** | 4 | **+0.0431** | **3/4** | 1484 | 1.18 | 0.96 | 1.97 | 31 R | 64% | **74.0** | **CANDIDATE** |
| H6 MTF-aligned break | 4 | −0.0074 | 2/4 | 13317 | 0.99 | −0.09 | −0.24 | 281 R | 66% | 35.2 | rejected |
| H7 participation break | 4 | +0.0006 | 2/4 | 17754 | 1.01 | 0.04 | 0.05 | 353 R | 65% | 35.0 | rejected |
| H4 prior-session high | 4 | −0.0122 | 1/4 | 4645 | 0.94 | −0.33 | −0.48 | 60 R | 66% | 31.2 | rejected |
| H1 Donchian breakout | 4 | −0.0008 | 2/4 | 20039 | 1.01 | 0.02 | 0.02 | 449 R | 58% | 31.0 | rejected |
| H3 opening-range break | 4 | +0.0406 | 3/4 | 7873 | 1.12 | 0.73 | 1.26 | 351 R | **23%** | 30.6 | **overfit risk** |
| H8 NR expansion | 4 | −0.0063 | 1/4 | 4727 | 0.97 | −0.19 | −0.30 | 133 R | 25% | 14.6 | rejected |
| **H2 squeeze breakout** | 4 | **−0.1346** | 1/4 | 1473 | 0.64 | −2.50 | −4.14 | 64 R | **1%** | **8.6** | **rejected** |

### Diagnosing the failures rather than discarding them

**H2 (squeeze) was the hypothesis I expected most from, and it ranks last.** The reasoning was
sound — require compression so chop is excluded structurally rather than filtered — and the data
rejects it flatly: a **1.2% parameter plateau** means essentially every neighbouring geometry is
negative, which is the definition of a non-mechanism. The diagnosis: compression on 5-minute bars
selects *low-ATR* bars, and a low-ATR bar is where the fixed round turn is largest relative to the
stop. The setup selects precisely the conditions where costs are worst.

**H3 (opening range) has the best raw OOS numbers of the rejected set and a 23% plateau.** It is
positive out of sample on 3/4 markets and *negative on research* for US100 and US30 — the wrong
shape. Combined with the narrow plateau, this is flagged **overfit risk** rather than promoted.

**H6/H7/H1 are the same trade.** See §5.

## 5. The eight hypotheses are mostly one hypothesis

Correlation of daily strategy returns, US30, research block:

| | H1 | H2 | H3 | H4 | H5 | H6 | H7 | H8 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| H1 | 1.00 | 0.39 | 0.57 | 0.36 | 0.66 | **0.91** | **0.96** | 0.71 |
| H6 | 0.91 | 0.31 | 0.49 | 0.35 | 0.61 | 1.00 | **0.87** | 0.63 |
| H7 | 0.96 | 0.26 | 0.59 | 0.37 | 0.62 | 0.87 | 1.00 | 0.65 |

**H1, H6 and H7 correlate 0.87–0.96 — they are one trade wearing three hats.** Adding an MTF
filter or a volume filter to a Donchian breakout does not produce a new strategy; it produces the
same strategy with fewer trades. Only **H2 (0.14–0.39)** and **H4 (0.17–0.37)** are genuinely
distinct, and both are rejected on their own merits.

This is the third time this branch has found its own condition pool to be largely duplicated
(`STUDY_RULE_ANATOMY.md`, `STUDY_SCALP_TREND.md`'s ADX/efficiency-ratio correlation of 0.642). **A
hypothesis count is not a diversification count.**

## 6. Portfolio: the diversification is across markets, not across hypotheses

Daily strategy-return correlation for one hypothesis across markets:

| | US30 | US100 | NQ | XAUUSD |
| --- | ---: | ---: | ---: | ---: |
| US30 | 1.00 | 0.29 | −0.00 | −0.01 |
| US100 | 0.29 | 1.00 | −0.00 | 0.00 |

**Strategy returns are nearly uncorrelated across markets even though the underlying prices
correlate 0.68–0.87.** The trades fire at different moments, so the decorrelation is real. That is
the one genuine portfolio opportunity in this study.

It does not, however, produce much:

| portfolio (research, daily R) | mean/day | Sharpe | max DD | Calmar |
| --- | ---: | ---: | ---: | ---: |
| H6 on US100 alone | +0.031 | 0.37 | 38 R | 0.21 |
| H6 on all four equal weight | +0.001 | **0.01** | 63 R | 0.00 |
| **H6 on the three indices** | +0.038 | **0.38** | 67 R | 0.14 |
| H6 on US30 alone | +0.050 | 0.23 | 178 R | 0.07 |
| US30, all eight hypotheses equal weight | +0.016 | 0.11 | 98 R | 0.04 |

Combining the three indices gives **Sharpe 0.38 against 0.37 for the best single market** — the
near-zero correlation raises return and volatility together and leaves the ratio flat. Including
gold destroys it (0.38 → 0.01). And **combining hypotheses makes things worse** (0.30 → 0.11),
because the correlated winners are diluted by the genuinely-distinct losers.

## 7. The candidate, adversarially tested

**H5 break and retest** — enter when a level that broke within the last 6 bars is retested to
within 0.25 ATR and holds. Stop 4×ATR, target 3R, max hold 48 bars, 09:00–13:00 New York.

Monte Carlo on out-of-sample trades (permutation for the path, bootstrap with a 0.02R execution
perturbation for the edge):

| | n | E[R] | median DD | 95th DD | mean p05 | **P(edge ≤ 0)** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| US30 | 476 | +0.0263 | 13.6 R | 21.4 R | −0.0318 | 22.9% |
| US100 | 225 | +0.0695 | 5.1 R | 8.2 R | +0.0031 | 4.2% |
| NQ | 144 | +0.0598 | 6.1 R | 9.7 R | −0.0407 | 16.1% |
| XAUUSD | 639 | −0.0208 | 24.7 R | 34.3 R | −0.0644 | **78.2%** |
| pooled, four markets | 1484 | +0.0158 | 22.0 R | 33.9 R | −0.0141 | 19.3% |
| **three indices only** | **845** | **+0.0435** | 13.3 R | 21.2 R | +0.0023 | **4.2%** |

**Cost stress** — the edge lives inside the assumption's error bar:

| × assumed cost | 0.5× | 1× | **1.5×** | 2× |
| --- | ---: | ---: | ---: | ---: |
| H5 median E[R] | +0.0382 | +0.0207 | **+0.0032** | −0.0143 |
| H6 median E[R] | +0.0411 | +0.0221 | +0.0022 | −0.0176 |

**At 1.5× the assumed spread every candidate is at zero, and at 2× all are negative.** Since
bid/ask is unavailable in all four feeds, the spread is assumed rather than measured — so the
result is not distinguishable from zero on execution grounds alone.

## 8. Verdict

| claim | status |
| --- | --- |
| A breakout carries gross signal on the indices | **SUPPORTED** — H5 and H6 positive on all four markets at zero cost |
| That signal survives realistic costs on all four markets | **REJECTED** — best is 3/4, gold always dissents |
| Compression (squeeze) avoids chop structurally | **REJECTED** — 1.2% plateau; it selects the low-ATR bars where costs are worst |
| The eight hypotheses are eight strategies | **REJECTED** — H1/H6/H7 correlate 0.87–0.96 |
| Multi-market portfolios diversify | **PARTLY** — returns are near-uncorrelated but Sharpe barely moves (0.37 → 0.38) |
| Multi-hypothesis portfolios diversify | **REJECTED** — 0.30 → 0.11 |
| **H5 is a tradable intraday scalping edge** | **NO — it is a CANDIDATE, and it is not a scalp** |

H5's status is **CANDIDATE**, not validated, for four stated reasons: 845 out-of-sample trades
across three markets; P(edge ≤ 0) = 4.2% selected from roughly 1,280 hypothesis × geometry × market
cells, which multiplicity alone makes unremarkable; zero expectancy at 1.5× assumed costs; and a
geometry that is a four-hour hold rather than a scalp.

**What to research next**, in order:

1. **Stop asking for a scalp.** Every positive cell in this study and the two before it sits at
   wide stops and hour-plus holds. The consistent, four-times-replicated finding is that the
   intraday *scalping* constraint is what fails — the cost floor is simply larger than the
   available edge at scalping distances.
2. **Measure the spread.** Three studies now end at the same place: the answer is inside the cost
   assumption. Bid/ask data would settle H5 in one run.
3. **Diversify across markets, not across indicators.** The correlation tables say adding a fifth
   filter to a breakout adds nothing, while adding a fifth *market* adds a genuinely independent
   return stream. That is where the next unit of work should go.

## Files

| | |
| --- | --- |
| `research/hypo/hypotheses.py` | the eight hypotheses, each with its market rationale |
| `research/hypo/metrics.py` | PF, expectancy, Sharpe, Sortino, Calmar, drawdown, concentration, robustness score |
| `research/hypo/engine.py` | hypothesis × market × geometry sweep on the research block |
| `research/hypo/validate.py` | out-of-sample, plateau, cost stress, Monte Carlo, market correlation |

Measured on US30 (5m), US100 (15m), NQ (5m) and XAUUSD (5m), 09:00–13:00 New York, one unit per
trade. Costs assumed, not measured — bid/ask is unavailable in every feed. Research tooling for
education and analysis, not financial advice.
