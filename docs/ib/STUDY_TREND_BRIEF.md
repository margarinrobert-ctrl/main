# Trend following on 200 EMA + ADX + EMA crossover + ATR + 50 EMA — a research report

Brief: build the most robust trend-following strategy possible around that framework, test whether
a 60%+ win rate is achievable without curve-fitting, and be honest if it is not.

**Short answer: 60% is achievable, and it is not coming from the trend-following stack.** It is a
property of the entry mechanic and the 1:1 geometry. The 200 EMA, ADX and EMA crossover, tested in
the roles assigned to them, add nothing that survives. Details below.

---

## 0. What this research can and cannot answer

| | |
| --- | --- |
| Instrument | **NQ/MNQ only.** One market. |
| Sample | 2022-12-26 → 2025-12-12, 1-minute bars |
| Timeframes | 5m, 15m, 60m, 240m, daily (resampled, exchange-local aligned) |
| **Cross-market (§7)** | **NOT ANSWERABLE HERE.** No SPY/QQQ/gold/FX/BTC data and no network access — the environment's proxy blocks external hosts. Any cross-market claim would be fabricated. |
| Regime | **One.** NQ roughly doubled over the sample. Every long-side result is scored against a matched control that already contains that drift. |

Three years of one instrument in one regime cannot establish a trend-following edge. It can
**falsify** one, and that is mostly what happened.

## A. Research summary

I could not fetch papers here (no network), so these are from knowledge, not retrieved, and should
be verified against the originals before being relied on:

* **Moskowitz, Ooi & Pedersen (2012), "Time Series Momentum", JFE.** ~58 liquid futures, 1965–2009.
  A security's own past 12-month excess return predicts its next-month return; the effect is
  strong across asset classes and partially reverses beyond ~12 months. This is the strongest
  academic support for trend following as a phenomenon — **at monthly horizons on diversified
  portfolios.**
* **Hurst, Ooi & Pedersen (2017), "A Century of Evidence on Trend-Following Investing", JPM.**
  ~110 years, positive in every decade. Again: diversified, multi-asset, slow.
* **Harvey, Liu & Zhu (2016), "…and the Cross-Section of Expected Returns", RFS.** With the number
  of strategies tested, a t-statistic near **3.0** is the appropriate hurdle for a new claim, not 2.
* **Sullivan, Timmermann & White (1999), JF.** Technical trading rules that looked significant
  (Brock/Lakonishok/LeBaron 1992) largely do not survive a data-snooping adjustment, and fail
  out-of-sample afterwards.
* **Bailey & López de Prado**, deflated Sharpe ratio and PBO; **White (2000)** Reality Check;
  **Hansen (2005)** SPA. All say the same thing: the number of configurations tried must enter the
  inference.
* **Zakamulin**, on moving-average rules: much of their apparent performance is regime and
  volatility-timing, and shrinks sharply once data snooping is accounted for.
* **Wilder (1978)** is the origin of ADX and ATR. Practitioner, not peer-reviewed.

**The gap that matters for this brief:** the academic evidence supports **slow, diversified,
multi-asset time-series momentum**. It does not support intraday single-instrument EMA-crossover
systems, which is what the framework here describes. Nothing in MOP or HOP implies a 9/21 crossover
on 60-minute NQ has an edge.

## B–C. Five variants, measured

60-minute bars, trend EMA 200, ADX>25, crossover 9/21, stop 2.0×ATR, MNQ itemised fees
($1.44 round turn) and bar-dependent slippage, **research block only** (first 65% of sessions).

| variant | side | R | entry | n | win% | expectancy | PF | Sharpe |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| A conservative continuation | long | 1:1 | market | 34 | 38.2 | −$51.47 | 0.61 | −0.70 |
| B slope-confirmed | long | 1:1 | market | 34 | 38.2 | −$51.47 | 0.61 | −0.70 |
| C pullback | long | 1:1 | market | 76 | 50.0 | +$0.11 | 1.00 | 0.00 |
| C pullback | long | 1:1 | LIMIT | 59 | 55.9 | +$34.70 | 1.51 | 0.76 |
| D breakout | long | 1:1 | LIMIT | 149 | **62.4** | +$44.46 | 1.67 | 1.46 |
| E adaptive | long | 1:1 | LIMIT | 281 | **61.9** | +$43.36 | 1.60 | 1.83 |
| E adaptive | long | 1:2 | LIMIT | 184 | 38.6 | +$23.60 | 1.20 | 0.55 |

**A and B produce identical trade lists.** The 200 EMA *slope* condition is redundant once price is
above the 200 EMA — it fires on the same bars. That is a finding about the framework: one of the
proposed conditions is not a condition.

**A and B are also dead**: 34 trades in three years, 38% win rate, profit factor 0.61. The EMA
crossover as an *entry trigger*, filtered by 200 EMA and ADX, is the weakest thing tested.

The short side is negative in essentially every variant, which is the sample's drift, not a
short-selling insight.

## D. The control that undoes the thesis

| configuration | n | win% | expectancy | PF | Sharpe | net |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **no rule at all — market entry** | 925 | 53.8 | $15.27 | 1.15 | 0.97 | $14,127 |
| **no rule at all — LIMIT entry** | 810 | **60.0** | **$38.79** | 1.47 | **2.58** | **$31,421** |
| just `close>ema200` — LIMIT | 564 | 59.4 | $35.63 | 1.48 | 2.19 | $20,094 |
| E adaptive (full stack) — LIMIT | 281 | 61.9 | $43.36 | 1.60 | 1.83 | $12,185 |
| D breakout — LIMIT | 149 | 62.4 | $44.46 | 1.67 | 1.46 | $6,625 |

**Taking every bar with the resting-limit entry produces a 60.0% win rate, a higher Sharpe (2.58)
and 2.6× the net profit of the best trend rule.** The complete 200 EMA + ADX + crossover +
distance + volatility stack buys **1.9 points of win rate** and costs 65% of the trades.

The 60% is the entry mechanic. It is not the trend stack.

## E. Parameter sensitivity — flat, for the wrong reason

| trend EMA | 100 | 150 | 180 | 200 | 220 | 250 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| win % | 61.3 | 61.2 | 61.7 | 61.9 | 61.9 | 62.2 |
| Sharpe | 1.71 | 1.76 | 1.84 | 1.83 | 1.82 | 1.81 |

| ADX threshold | **0 (none)** | 20 | 25 | 30 | 35 |
| --- | ---: | ---: | ---: | ---: | ---: |
| n | 446 | 368 | 281 | 205 | 150 |
| Sharpe | **2.23** | 1.79 | 1.83 | 1.58 | 1.29 |

Nothing collapses outside 200 — which normally indicates robustness. Here it indicates
**irrelevance**: the parameter does not matter because the filter does not matter. The ADX table is
blunter still: **removing ADX entirely gives the highest Sharpe.** As a filter it raises per-trade
expectancy slightly while destroying enough trades to lower risk-adjusted return.

Crossover pairs: 20/50 (Sharpe 2.13) > 12/26 (2.03) > 9/21 (1.83) > 5/13 (1.48). Also flat, also
without a spike — and still below the no-filter case.

## F. Stop research — the 50 EMA is not superior

No rule + LIMIT, 1:1, research block. **Two fill models, because they disagree:**

| stop | bar-level win% | bar-level PF | bar-level Sharpe | **true 1-min path win%** | **true path PF** |
| --- | ---: | ---: | ---: | ---: | ---: |
| ATR × 1.0 | 68.0 | 2.22 | **7.33** | **59.9** | **1.44** |
| ATR × 1.5 | 63.2 | 1.70 | 4.17 | 56.9 | 1.31 |
| ATR × 2.0 | 60.0 | 1.47 | 2.58 | 56.8 | 1.29 |
| ATR × 2.5 | 59.1 | 1.41 | 1.95 | 56.7 | 1.30 |
| ATR × 3.0 | 60.8 | 1.50 | 2.00 | 58.5 | 1.36 |
| 50 EMA distance | 58.8 | 1.53 | 2.10 | — | — |
| 50 EMA, floor 1.0×ATR | 62.4 | 1.53 | 2.15 | — | — |
| 20-bar swing low + ATR | 62.4 | 1.69 | 1.82 | — | — |

**The Sharpe of 7.33 is a fill-model artifact and was caught by resolving the exits on the actual
1-minute bars inside each 60-minute bar.** With a limit entry 0.75×ATR below the close and a stop
1.0×ATR below the fill, the target sits only ~0.25 ATR above the signal close — and a bar-level
model cannot tell whether price reached the limit and then the target, or the limit and then the
stop. It assumes the favourable order. The true path says the win rate is **59.9%, not 68%**, and
the profit factor **1.44, not 2.22**.

**Every bar-level number in this report should be read as ~3–8 points optimistic on win rate.**

On the honest path, ATR-based stops beat both 50-EMA variants, and the 50 EMA only becomes
competitive once an ATR floor is bolted onto it — at which point it is mostly an ATR stop.

## G. Timeframe

No rule + LIMIT, 1:1, research block, bar-level:

| tf | n | win% | expectancy | PF | Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: |
| 5m | 7,421 | 57.2 | $5.42 | 1.19 | 3.12 |
| 15m | 2,401 | 60.0 | $19.17 | 1.40 | **3.59** |
| 60m | 810 | 60.0 | $38.79 | 1.47 | 2.58 |
| 240m | 241 | 65.1 | $120.19 | 1.88 | 2.28 |
| daily | 45 | 77.8 | $531.88 | 3.35 | 1.84 |

Win rate rises with timeframe and sample size collapses with it. **The daily 77.8% is 45 trades and
means nothing.** Sharpe peaks at 15m. Note 5m expectancy of $5.42 against a ~$2.94 round turn —
that is the cost line eating most of the edge, exactly as the literature on intraday costs implies.

## H. The holdout — read once

Two candidates, pre-committed, 60m, 1:1, LIMIT entry:

| | research | **locked** | vs matched control |
| --- | --- | --- | --- |
| no rule + LIMIT | $38.79/tr, 60.0% | **$33.86/tr, 56.0%**, net $14,930 | ctrl $26.35, **p = 0.112** |
| E adaptive + LIMIT | $43.36/tr, 61.9% | **$4.71/tr, 53.1%**, net $683 | ctrl $8.76, **p = 0.647** |

* **The trend stack collapses out of sample** — expectancy falls 89%, win rate 61.9% → 53.1%.
* **The bare entry mechanic decays gracefully** but **does not clear significance** against a
  matched random entry on the holdout (p = 0.112).

Both decay, which is the right shape. Neither validates.

## I. The 60% question, answered honestly

**Break-even win rates, computed at the median ATR this data actually produced:**

| R | before costs | 2.0×ATR stop, 60m | 2.0×ATR stop, 15m |
| --- | ---: | ---: | ---: |
| 1:1 | 50.0% | 50.9% | 52.0% |
| 1:1.5 | 40.0% | 40.7% | 41.6% |
| 1:2 | 33.3% | 33.9% | 34.7% |

The trade-off is arithmetic: **1:1 is the only R at which 60% is even meaningful as a target.** At
1:2 a 60% win rate would be an enormous edge (hurdle 33.9%) and is not remotely attainable — the
measured 1:2 win rates here are 27–43%. Asking for "60% and 1:2" is asking for a profit factor
near 3, which nothing in this data or the literature supports.

**Is 60% achievable without curve-fitting? Yes — 56–60% on the honest fill model, at 1:1, and it
comes from the entry mechanic.** It does not come from the trend framework, it does not survive the
holdout at conventional significance, and it has not been tested on a second market.

**Would I trade it? No, and not because the win rate is too low.** Because:

1. **The edge is short-horizon mean reversion at the execution layer, not trend following.** A
   limit only fills on an adverse excursion, and adverse excursions partially revert. That is the
   opposite of the thesis in the brief.
2. **It fails the holdout significance test** (p = 0.112 against a matched control).
3. **The fill model is the weakest link.** Queue position is not modelled; `through_ticks` tests
   whether price traded past the level, not whether *your* order was near the front when it did.
   This places a resting order on essentially every bar — thousands of cancels — and exchange
   messaging fees and adverse selection are not in the numbers.
4. **One instrument, one regime.**

## What actually failed, itemised

| framework component | verdict |
| --- | --- |
| 200 EMA as trend filter | Flat 100→250. No spike, no contribution. Best Sharpe without it. |
| 200 EMA slope | **Redundant** — produces an identical trade list to price>EMA200. |
| ADX as regime filter | **Negative contribution.** ADX=0 gives the highest Sharpe. |
| EMA crossover as trigger | **Worst component.** 34 trades, PF 0.61, 38% win. |
| ATR for stops/normalisation | **Works** — and beats the 50 EMA. |
| 50 EMA as stop | **Not superior.** Only competitive with an ATR floor added. |
| 1:1 vs 1:2 | 1:1 clears its hurdle; 1:2 has better per-trade dollars at some settings but worse Sharpe. |
| 60% win rate | Attainable at 1:1, from the entry mechanic, ~56–60% honestly modelled. |

## Position sizing (§12)

Sizing creates no edge — it is a monotone transform of the same trade sequence — but it determines
survival. With the honest 60m figures (expectancy $30.63/trade, ~$200 average loss, worst losing
streak 6–8):

| risk/trade | worst-streak equity hit | comment |
| --- | ---: | --- |
| 0.25% | ~2% | survivable; slow compounding |
| 0.5% | ~4% | reasonable for a 56% / 1:1 system |
| 1.0% | ~8% | a 12-loss streak is a 12% hole, and streaks that long are not rare at 56% |

Risk of ruin is not quoted as a number because it depends on assumptions (fixed fractional, no
correlation between consecutive trades) that this data does not establish.

## How look-ahead bias is avoided (§14)

* A signal is read at the **close of bar i** and filled at the **open of bar i+1**. The engine's
  fill index is `i+1` by construction.
* Every indicator is asserted causal by **truncating the series at 70% and re-checking every value
  before the cut** (`indpool.leak_check`). A centred window, a whole-sample normalisation or a
  shift in the wrong direction changes its own history and is caught.
* Daily values used intraday are read with `lookahead_off` **and** a one-bar offset.
* The engine is asserted against `test_suite.sim_core` **trade for trade on 4.6M trades**.
* A bar containing both stop and target books the **stop**, and where that mattered the exits were
  re-resolved on the true 1-minute path.
* No survivorship bias: a single continuous futures series, not a selected universe. (Which also
  means the study says nothing about equity-universe strategies.)

## Reproduce

```bash
python research/trend_lab.py          # break-even table
python -c "import sys;sys.path.insert(0,'research');from trend_lab import variant_scan;variant_scan(tf=60)"
python research/user_stack.py         # the per-indicator scan
```

Measured on MNQ, one contract, itemised fees, bar-dependent slippage. Research tooling for
education and analysis, not financial advice. Nothing here justifies risk capital.
