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
