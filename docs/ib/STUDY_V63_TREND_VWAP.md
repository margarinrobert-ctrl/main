# V63 — a trend-following design on a VWAP, a triple EMA cross and ATR

`research/v63/` — `v63feeds.py` (three feeds with a usable volume series), `v63core.py` (the design
and the exit tensor), `run_v63.py` (base rates, population, marginals, finalists — US100 research
only), `run_v63b.py` (frozen, read once on every block of three markets), `run_v63c.py` (drop-one,
costs, hold time, Monte Carlo), `run_v63d.py` (the two changes the drop-one pointed at),
`run_v63e.py` (the maximum hold, which binds), `v63_parity.py`. Output in `results/v63/`.
Ships `pine/v63/V63_TREND_VWAP_EMA_ATR_strategy.pine`.

---

## 1. The design, declared before anything ran

- **Trigger** — a triple EMA cross: the bar on which EMA(f) > EMA(m) > EMA(s) *becomes* true. A
  cross is an event and a stack is a state; the two are joined by one axis, `win`, the number of
  bars after the fresh stack in which an entry is still allowed. `win = 0` is the cross bar alone.
- **Trend** — the VWAP as a LEVEL, in five readings including a distance FLOOR and the "not
  extended" CEILING, because `STUDY_V40` and `STUDY_V51` both found a moving average is priced by
  its distance and that the ceiling form inverts. Two anchors (09:30 New York, the 18:00 roll) and
  — the component test that matters — **two weightings: volume, and none.**
- **ATR** — the stop, an optional chandelier trail, an optional target, an expansion gate.
- **Not swept, on evidence in hand**: no session window, no flatten (destructive on eleven prior
  measurements), one unit, market entry at the next open, long only.

**Searched on US100's research block only** (2016-11 → 2022-01), then frozen and read ONCE on
US100's later two blocks, the whole of US30 and the whole of NQ.

A note on the data: `mrl_bar.Feed` returns `v` as an array of ones, so a VWAP built on it would be
an unweighted average wearing a weighted name. The CFD exports carry `Volume` as literal zeros and
`TickVolume` as the real series, so **tick volume is used on US100 and US30 and is labelled a
proxy**; NQ carries true contract volume.

## 2. What the search block said

146,880 cells, 146,703 scorable, **87.4% profitable on research** — so the top row is the maximum of
about 128,000 positive draws. Marginals (annualised trade Sharpe / percent per trade):

```
tf     60: +0.68/+0.1226   15: +0.46/+0.0266   30: +0.41/+0.0459
win    30: +0.63   10: +0.56   3: +0.48   0: +0.40        <- the STATE, not the cross, is the signal
vwap   ceiling: +0.54   above: +0.53   rising: +0.53   OFF: +0.52   floor: +0.47
atrg   >=mean: +0.59   off: +0.59   >=1.1x: +0.37
tp     none: +0.82   4 ATR: +0.55   3 ATR: +0.40   2 ATR: +0.30     <- the 15th time
trail  2.5: +0.53   3.5: +0.52   none: +0.50   (but per-trade none +0.1085 against 2.5's +0.0360)
```

**The VWAP axis is nearly flat** — its best reading is +0.54 against +0.52 for off. And the
component test: over **69,003 matched pairs the volume-weighted anchor beats its unweighted twin in
55.7%, mean difference +0.0096 Sharpe.** The V in VWAP does essentially nothing here.

## 3. Frozen, and read once on three markets

Four finalists were declared. The best of them — 30m, EMA 13/34/89, `win` 30, price above a rising
anchored average, 1.5 ATR stop, 2.5 ATR chandelier trail, no target — was then taken apart on the
seven blocks that chose nothing:

| variant | blocks positive | n | %/trade | PF |
|---|---|---|---|---|
| the candidate | 6/7 | 2652 | +0.0406 | 1.24 |
| drop the VWAP filter | 6/7 | 3020 | +0.0320 | 1.18 |
| VWAP volume-weighted instead of flat | 6/7 | 2628 | +0.0399 | 1.23 |
| **drop the trail (fixed stop only)** | 6/7 | 1144 | **+0.1465** | **1.46** |
| add a 3 ATR target | 6/7 | 3249 | +0.0145 | 1.09 |
| enter on the cross bar only | 6/7 | 1512 | +0.0311 | 1.18 |
| **add the ATR expansion gate** | **7/7** | 1757 | +0.0601 | 1.34 |

**Removing the chandelier trail is worth 3.6× the per-trade result and more in total** (1144 ×
0.1465 = 168% against 2652 × 0.0406 = 108%). A trail is a take profit wearing a stop's name — the
same finding this branch has now made fifteen times about targets, reached from the exit side.

## 4. The final design, on every block of every market

**30-minute bars, long only. EMA 13 > 34 > 89 aligned for at most 30 bars; close above a rising
session VWAP; ATR(14) ≥ its own 50-bar mean. Enter at the next open. Stop 1.5 × ATR at the signal
bar. No trail, no target. Hard cap at 480 bars.**

| market | block | n | %/trade | total | PF | win | maxDD | random-filter p | random-entry p |
|---|---|---|---|---|---|---|---|---|---|
| US100 | research | 264 | +0.2200 | +58.1% | 1.67 | 14.0% | 15.7% | 0.924 | 0.282 |
| US100 | validation | 116 | +0.1596 | +18.5% | 1.31 | 10.3% | 12.2% | 0.123 | **0.018** |
| US100 | test | 91 | +0.3842 | +35.0% | 2.03 | 18.7% | 15.4% | **0.000** | **0.013** |
| US30 | research | 261 | +0.1799 | +47.0% | 1.69 | 16.5% | 10.1% | 0.726 | 0.250 |
| US30 | validation | 115 | +0.1352 | +15.6% | 1.42 | 10.4% | 9.8% | **0.000** | **0.010** |
| US30 | test | 85 | +0.1797 | +15.3% | 1.68 | 16.5% | 9.7% | **0.000** | 0.117 |
| NQ | research | 113 | +0.3585 | +40.5% | 2.28 | 16.8% | 5.2% | **0.045** | **0.018** |
| **NQ** | **locked** | **69** | **−0.0401** | −2.8% | **0.90** | 8.7% | 16.3% | 0.171 | 0.863 |

**Seven of eight blocks positive on three markets, and it clears a random entry with the identical
geometry on four of the seven blocks that had no part in the search.** That is a better spread than
anything else measured on this branch. It is not significance: US100 and US30 cover the same weeks,
so the blocks are not independent, and NQ's locked block loses.

Note the shape: US100's research block is the one that CHOSE the cell and it FAILS both controls
there (0.924 / 0.282) while the blocks that chose nothing pass. That is the opposite of the usual
selection premium and is worth watching rather than celebrating.

## 5. The four things a trader has to know

1. **It wins 9–19% of the time.** 86% of trades stop out for a small loss (mean −0.33 to −0.45%)
   and 14% run to the cap for a large gain (+2.97 to +4.42%). The capped trades supply **261–264%
   of net** and the top 5% of trades supply 140–153%. The longest run of consecutive losers in the
   pooled out-of-sample stream is **28**.
2. **It is not intraday and not a scalp.** Median hold 13–16 hours; the median WINNER holds **240
   hours — ten trading days** — and exits on the cap. It carries overnight and weekend gap risk.
   52–61 trades a year.
3. **The cap is load-bearing.** V61 and V62 measured a 480-bar cap inert because a channel exit
   always fired first; here there is no channel exit, so the cap IS the exit. Pooled over the
   blocks that chose nothing: 60 bars +0.0590 PF 1.24, 120 +0.1054, 240 +0.1427, 480 +0.1988,
   960 **+0.2484** PF 1.69 — monotone toward longer, 7/7 blocks positive at every rung but 480
   (6/7). An axis that binds must be swept, not inherited.
4. **Costs are not the binding constraint**: pooled +0.0470 at zero cost, +0.0406 at 1×, +0.0344 at
   2×, +0.0225 at 4×.

## 6. Parity

The script's own order model, written out in Python and diffed against the engine, agrees on the
trade count within one, gives **correlation 1.0000**, and reads +0.1% / +0.3% / −0.0% against the
engine on US100 / US30 / NQ. The single structural difference is that a time cap fills at the NEXT
bar's open — `strategy.close_all()` cannot sell the close of the bar that triggers it — and that is
worth about 0.2%.

## 7. Honest limits

- **It was selected on one market's research block** and the multiplicity is 146,703 cells for four
  finalists. The cross-market spread is the evidence, not the p-values.
- **The pooled bootstrap (P(mean ≤ 0) = 0.0002) overstates**: US100 and US30 are the same weeks.
- **Two of the shipped choices were made after out-of-sample blocks were read** — dropping the trail
  and adding the ATR gate. Both are defensible (one restates a fifteen-times finding, the other was
  7/7) and both are post-hoc; the tooltips in the script say so.
- **The VWAP earns little.** Dropping it costs +0.0406 → +0.0320. It is a real but small component,
  and its volume weighting is worth nothing at all.
- **NQ's locked block loses**, and NQ is the market with the least history.
- Forward-test before sizing. With a 14% win rate and a 28-loss streak, the psychological and the
  statistical requirements are the same: you need many trades before the tail arrives.


## 8. Is the VWAP support, or a direction filter?

`research/v63/run_v63f.py`, `results/v63/stage_f.txt`. Asked directly, and it is a filter, not a
level: the shipped rule reads `close > VWAP and VWAP rising` once at the signal bar. It never places
an order at the VWAP, never waits for a touch and never requires a pullback. Two tests settle
whether it *could* be used as support.

**The five declared readings, at the shipped geometry, pooled over the seven blocks that chose
nothing** (this comparison is made AFTER those blocks were read, so it is descriptive):

| reading | blocks positive | n | %/trade | PF |
|---|---|---|---|---|
| off | 6/7 | 969 | +0.1603 | 1.47 |
| above | 6/7 | 868 | +0.1935 | 1.59 |
| **above and rising** (shipped) | 6/7 | 850 | +0.1988 | 1.60 |
| distance ≥ 0.5 ATR (the FLOOR) | 6/7 | 782 | **+0.2204** | **1.67** |
| 0 < distance ≤ 2.0 ATR (the CEILING) | **7/7** | 801 | +0.2076 | 1.65 |

Note the inversion against §2: on the search block, averaged over the whole grid, the FLOOR was the
worst reading (+0.47 Sharpe against +0.52 for off) and the ceiling the best. At the final geometry
on the blocks that chose nothing the floor is the best per trade. Same feature, two geometries,
opposite ranking — `STUDY_V52`'s finding that a filter is a property of a geometry, not of a market.

**The anatomy — the strategy's own trades split by distance from the VWAP at entry.** If the VWAP
were support, the nearest quartile would earn most:

| quartile | n | mean distance | %/trade | PF | win |
|---|---|---|---|---|---|
| Q1 nearest | 279 | 0.31 ATR | **+0.1325** | 1.41 | 12.5% |
| Q2 | 278 | 0.81 ATR | +0.2636 | 1.85 | 15.1% |
| Q3 | 278 | 1.42 ATR | +0.2538 | 1.77 | 15.5% |
| Q4 furthest | 279 | 2.80 ATR | +0.1660 | 1.46 | 14.3% |

**The nearest quartile is the worst**, the relationship is a hump rather than a gradient, and the
Spearman correlation between distance-at-entry and the trade's result is **−0.0495**. Buying near
the VWAP buys nothing. What the condition contributes is being on the right side of a rising
anchor — a state, not a location — and even that is worth only +0.0385 %/trade over having no VWAP
condition at all.


## 9. ATR as a regime filter — 86 declared readings, both directions

`research/v63/run_v63g.py`, `results/v63/stage_g.txt`, `results/v63/atr_regime.csv`. Every reading
replaces the shipped gate (not stacked on it), is scored against a random filter of the SAME
selectivity over the base's own signals with the position lock applied, and is read on all eight
blocks. The family was declared first: expansion against a rolling mean (32), the percentile of ATR
in its own trailing window (24), the same on ATR/price (24), and the slope (6).

**The direction is the finding, and it is consistent across all four families** on the seven blocks
that had no part in the search:

| family | direction | cells | mean edge | beats no-regime | clears its control |
|---|---|---|---|---|---|
| expansion | floor / rising | 112 | **+0.0471** | **71.4%** | 36.6% |
| expansion | ceiling / falling | 112 | −0.0431 | 35.7% | 14.3% |
| level | floor / rising | 84 | +0.0320 | 57.1% | 26.2% |
| level | ceiling / falling | 84 | −0.0542 | 34.5% | 15.5% |
| normalised | floor / rising | 84 | +0.0338 | 57.1% | 21.4% |
| normalised | ceiling / falling | 84 | −0.0539 | 35.7% | 16.7% |
| slope | rising | 21 | +0.0061 | 57.1% | 19.0% |
| slope | falling | 21 | −0.0275 | 47.6% | 19.0% |

**Trade the expansion, not the calm** — and that INVERTS this branch's two prior ATR results.
`STUDY_V28`'s only survivor of 240 cells was `atr percentile 500 ≤ 0.2`, the bottom fifth; re-run
here it improves **3 of 7** blocks with a mean edge of **−0.0615** and clears its control once.
`STUDY_V39` found calm and contracting states inverting hardest of any family. Fourth measurement,
same conclusion: a volatility-state rule's sign is not stable, so run both directions or run neither.

**Three readings improve on every one of the seven blocks that chose nothing:**

| reading | keeps | mean edge | 7/7? | clears control | worst block |
|---|---|---|---|---|---|
| `atr / sma(250) ≥ 1.2` | 15.3% | **+0.0981** | yes | 3/7 | +0.0025 (US30 research) |
| `atr percentile(100) ≥ 0.6` | 28.9% | +0.0874 | yes | 4/7 | +0.0188 (NQ research) |
| `atr / sma(100) ≥ 1.0` | 33.7% | +0.0845 | yes | 4/7 | +0.0092 (NQ research) |
| `atr / sma(50) ≥ 1.0` (shipped) | 34.5% | +0.0693 | **no, 5/7** | 3/7 | −0.0248 (US30 research) |

Three of 86 against **0.67 expected** if each block were a coin flip — but the blocks are not
independent (US100 and US30 are the same weeks), so read that as modest, not decisive.

**The sma(100) rung is strictly better than the shipped sma(50) at the same selectivity** — 7/7
against 5/7, +0.0845 against +0.0693, clearing on 4 blocks against 3. It was picked after those
blocks were read, so it ships as an INPUT and not as the default; the script's tooltip carries both
sets of numbers.

**Two cautions that belong with the table.** First, **21.9% of 602 out-of-sample cells clear their
control at p ≤ 0.05 against a 5% chance rate, while only 49.3% beat the no-regime baseline —
exactly chance.** Those two are consistent because the floor and ceiling directions cancel: the
floor family beats the baseline 71.4% of the time and the ceiling family 35.7%. Read the direction
split, never the pooled share. Second, **every reading — including all three survivors — has a
NEGATIVE edge on US100 research, the block that chose the strategy.** The regime filter helps on
the seven blocks that chose nothing and subtracts on the one that chose. That is an unusual shape
and it is not an argument in its favour.

Note also that the ATR gate scored 7/7 in the stage-C drop-one and 5/7 here. Nothing changed but
the base: stage C measured it on the candidate that still had the chandelier trail. A filter is a
property of a geometry, not of a market (`STUDY_V52`), measured again.


## 10. A time window and a hard flatten, with the full battery

`research/v63/v63sess.py`, `run_v63h.py`, `run_v63i.py`; `results/v63/stage_h.txt`,
`stage_i.txt`, `session.csv`. Two mechanics, kept separate: an ENTRY WINDOW takes only signals
inside `[start, stop)` and then manages the trade normally; a HARD FLATTEN also closes any open
position at the stop time. "Flat by the stop" means flat at the stop minute's OPEN, because
`strategy.close_all()` cannot sell the close of the bar that triggers it — so the engine exits at
the open of the first bar at or after the cutoff, which is what the script does.

### IS / OOS — pooled over the seven blocks that chose nothing

| window | no flatten | blocks + | with a flatten | blocks + | clock exits |
|---|---|---|---|---|---|
| all hours | **+0.1988** | 6/7 | — | — | — |
| 09:30-12:00 | +0.1964 | **7/7** | −0.0060 | 3/7 | 64% |
| 03:00-12:00 | +0.1894 | 6/7 | −0.0132 | 2/7 | 57% |
| 08:00-12:00 | +0.1841 | 6/7 | −0.0165 | 2/7 | 60% |
| 09:30-11:00 | +0.1803 | 6/7 | +0.0119 | 5/7 | 63% |
| 09:30-16:00 | +0.1693 | 6/7 | +0.0350 | 6/7 | 60% |
| 07:00-11:00 | +0.1590 | 6/7 | −0.0072 | 4/7 | 55% |
| 13:00-16:00 | +0.1580 | 6/7 | +0.0356 | 6/7 | 72% |

**The flatten costs −0.1710 %/trade averaged over the seven windows — 86% of the edge — and four of
the seven flattened windows are outright negative.** The mechanism is not subtle: this rule's median
WINNER holds 240 hours and exits on the 480-bar cap, so a daily flatten truncates every winner it
has. Twelfth confirmation of the intraday-constraint finding on this branch, and the most extreme
instance of it.

**No entry window beats all hours.** The one row worth knowing is 09:30-12:00 without a flatten:
+0.1964 against +0.1988 on **half the trades** and positive on 7 of 7 blocks against 6 of 7. Same
edge, more consistent, less exposure — a reasonable preference, not an improvement.

### Monte Carlo — day-block bootstrap for the edge, permutation for the path

| variant | n | %/trade | P(mean ≤ 0) | 95% CI | realised DD | MC p99 | percentile |
|---|---|---|---|---|---|---|---|
| shipped, all hours | 850 | +0.1988 | **0.0000** | [+0.0865, +0.3191] | 16.48% | 34.60% | 0.32 |
| 09:30-12:00, no flatten | 437 | +0.1964 | 0.0015 | [+0.0619, +0.3450] | 8.40% | 22.78% | 0.06 |
| 09:30-16:00 + flatten | 1132 | +0.0350 | 0.0027 | [+0.0093, +0.0610] | 5.62% | 15.13% | 0.06 |
| 13:00-16:00 + flatten | 856 | +0.0356 | 0.0063 | [+0.0071, +0.0657] | 4.28% | 13.24% | 0.02 |

All four exclude zero — the flattened ones at a fifth of the magnitude. **The flatten's real
attraction is the drawdown, 16.5% down to 4.3–5.6% — and the permutation says most of that comfort
is luck**: those realised drawdowns sit at the 2nd to 6th percentile of their own distributions with
a p99 of 13–15%. The pooled interval is optimistic throughout: US100 and US30 are the same weeks.

### Robustness

Every variant holds at 4× the modelled cost (shipped +0.1811, flattened +0.0167 to +0.0173). The
stop ladder is flat for the windowed variants (+0.1913 to +0.1964 across 1.5–3.0 N) and prefers
2.5 N for the shipped one (+0.2728), which is the same post-hoc preference §4 already recorded.

### Walk-forward optimisation

The window, the flatten and the stop re-chosen inside every training fold from **60 declared
cells**, then applied to the fold it had never seen — eight folds, expanding and rolling training
windows, three markets.

| market | mode | re-chosen | folds + | fixed constants | folds + | WFE |
|---|---|---|---|---|---|---|
| US100 | expanding | +0.3486 | 6/6 | +0.2523 | 6/6 | 1.38 |
| US100 | rolling 2 | +0.3233 | 6/6 | +0.2523 | 6/6 | 1.28 |
| US30 | expanding | +0.0966 | 3/6 | +0.1366 | 5/6 | **0.71** |
| US30 | rolling 2 | +0.0818 | 4/6 | +0.1366 | 5/6 | **0.60** |
| NQ | expanding | +0.1839 | 3/6 | +0.1936 | 5/6 | 0.95 |
| NQ | rolling 2 | +0.1953 | 4/6 | +0.1936 | 5/6 | 1.01 |

**Mean walk-forward efficiency 0.99 — re-optimising bought nothing**, and it cost consistency: the
fixed constants are positive on 5–6 of 6 folds on all three markets while the re-chosen cells manage
3–6. Fifth time on this branch that a re-optimiser has lost to the author's constants
(`STUDY_IBS_SESSION`, `STUDY_APM_VWAP`, `STUDY_TRENDDAY_EMA`, `STUDY_V60`).

**And the strongest single line in the study: the optimiser was free to take the flatten in 36 fold
decisions and took it in 0 of 36.** What it did choose was 09:30-16:00 and 13:00-16:00 windows with
wider stops on US100 and NQ, and all hours on US30 — no consensus across markets, which is what a
parameter with no information looks like.

Both mechanics ship in the script as inputs, **default off**, with these numbers in their tooltips.
