# V38 — 113,400 Donchian × ATR × LinReg-MA × MA configurations

**The answer to the brief, first.** The most profitable version by profit factor is

> **30-minute, Donchian 70 entry / 30 exit, 2.5 × ATR(14) stop, NO take profit, LRMA(50) with
> both readings (close > value AND slope > 0), and MA(250) with LRMA > MA.**
> Research: **PF 1.909**, +$73.03/trade, Sharpe +1.67, 131 trades.

And it is not worth trading, for reasons the grid states about itself before any holdout is opened:

| | |
| --- | --- |
| share of the 113,400 cells profitable on research | **92.5%** |
| research→locked profit-factor correlation | **−0.036** Pearson, **+0.002** Spearman |
| top-100 mean research PF → mean locked PF | **1.799 → 0.978** |
| that config on NQ's locked block | **PF 0.907**, −$13.09/trade |
| cells clearing a matched control on two fresh markets | **0 of 8** (p 0.077–0.382) |
| cells clearing a selectivity control | **0 of 8** (p 0.090–0.554) |

The top row is the maximum of ~105,000 profitable draws, and the ranking that produced it carries
no information about the next block.

## The grid

Long only, fixed a priori: NQ rose 89% over this sample and a search allowed to pick a side picks
long and calls drift an edge. Real MNQ costs ×1.44, a tick of slippage on stop exits only.

```
timeframe        15m, 30m                                    2
Donchian entry   15, 20, 30, 40, 55, 70, 90                  7
Donchian exit    10, 20, 30                                  3
ATR stop         1.0, 1.5, 2.0, 2.5, 3.0  × ATR(14)          5
take profit      none, 1.5R, 2R, 3R, 4R                      5
LRMA length      30, 50, 80        (the brief's 50 ± a rung) 3
LRMA reading     off | close>value | slope>0 | both           4
MA length        150, 200, 250     (the brief's 200 ± a rung) 3
MA reading       off | close>MA | LRMA>MA                     3
                                                    = 113,400
```

A trade's outcome depends only on its **signal bar** and its **geometry**, never on which indicator
fired, so the price is walked once per (timeframe, exit channel, stop, target) — 75 geometries a
timeframe — and every configuration is an array gather plus a position-lock loop. The whole sweep
runs in **115 seconds**.

## What each knob is actually worth (marginal average per axis)

| axis | best on research | its locked value | worst on research | its locked value |
| --- | --- | --- | --- | --- |
| Donchian entry | 90 → PF 1.272 | **1.035** | 15 → 1.129 | **1.093** |
| LRMA length | 80 → 1.229 | **1.041** | 30 → 1.162 | **1.097** |
| MA reading | LRMA>MA → 1.250 | **1.061** | off → 1.140 | **1.072** |
| ATR stop | 2.5 → 1.250 | **1.056** | 1.0 → 1.131 | **1.097** |

**Every axis inverts.** On all four, the setting research likes best is the one the holdout likes
least, and the ordering is exactly reversed. That is not four findings — it is one: research PF
rises with anything that makes the rule more selective and longer-horizon, and none of it survives.

**No take profit is 91% of the top 100 against a 20% population share** — the ninth independent
time on this branch. That one *does* replicate everywhere and is the only axis whose research
preference has ever held up.

## The three candidates, and the single locked read

Because the grid's own shape forbids trusting the top row, three candidates were carried, not one:

- **TOP** — best research PF.
- **CONSENSUS** — the modal setting of the top 100 on every axis. *It selected the identical cell*,
  which is itself informative: the top of this grid is a coherent region, not a lone spike.
- **ROBUST** — best mean research PF over its own ±1 neighbourhood on every ordered axis
  (30m, Donchian 70/30, 2.5N, no TP, LRMA **80** slope>0, MA 250 close>MA).

TOP's neighbourhood mean is 1.759 against its own 1.909, so **+0.150 of it is spike**.

| | NQ research | NQ **locked** |
| --- | --- | --- |
| TOP / CONSENSUS | PF 1.909, +$73.03, n 131 | **PF 0.907, −$13.09, n 68** |
| ROBUST | PF 1.876, +$72.97, n 134 | **PF 0.832, −$22.88, n 79** |

The shape is right — research better than holdout — and the level is a loss.

## Two markets that had no part in the search

Three feeds were restored this session and verified against the registry (US30_LONG's sha256
matches the studied copy exactly; the RTF unwraps to exactly its recorded 48,937 rows and span).
Their clocks were re-derived independently and all three peak at minute-of-day 570 = 09:30 New
York, with the ISO feed — whose offset is *stated* rather than derived — agreeing, which is the
positive control.

Frozen configurations, each market charged its **own** tick and point value:

| market | span | n | PF | $/trade | Sharpe | years positive |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| US30 | 2016–2025 | 551 | **1.324** | +$122.85 | +0.66 | 8 of 10 |
| US30 | pre-2023 only | 387 | **1.364** | +$123.69 | +0.75 | |
| US100 | 2016–2025 | 621 | **1.332** | +$25.88 | +0.68 | 7 of 10 |
| US100 | pre-2023 only | 416 | **1.386** | +$24.73 | +0.73 | |

(ROBUST shown; it beats TOP on every fresh cell, so the neighbourhood criterion earned its keep.)

This is the `STUDY_V12_DONCHIAN_3020` shape again — **fails on the market that chose it, holds on
the ones that chose nothing** — and the pre-2023 slices, which contain 2018, COVID and the 2022
bear that the NQ sample does not, are the *best* cells in the table.

## And then the control, which is the whole point

Every market here rose, the rule is long only, and a trailing-exit long system in a rising market
is a drift harvester. Two nulls, 400 draws each:

| cell | rule $/trade | matched control | p | selectivity control | p |
| --- | ---: | ---: | ---: | ---: | ---: |
| US30 all | +$122.85 | +$47.05 | 0.092 | +$77.47 | 0.182 |
| US30 pre-2023 | +$123.69 | +$35.22 | **0.080** | +$39.57 | 0.092 |
| US100 all | +$25.88 | +$11.40 | 0.112 | +$12.60 | 0.090 |
| US100 pre-2023 | +$24.73 | +$8.27 | **0.095** | +$11.80 | 0.110 |

**0 of 8 cells clear the matched control. 0 of 8 clear the selectivity control.**

The rule earns two to three times what a random entry with the same geometry earns, consistently,
in the right direction, on four independent cells — and never at p ≤ 0.05. And a **random filter
keeping the same number of breakout bars does as well as the LRMA/MA stack in every single cell**,
which is the specific verdict on the 50/200 machinery the brief asked about: the exit geometry
(2.5N stop, no target, 30-bar channel) is doing the work, and the moving averages are selecting a
subset no better than chance would.

## The vectorbt cross-check, and what it caught

The winner was re-simulated in **vectorbt 1.1.0** as an independently written engine, because
three engine bugs on this branch were found exactly this way and none was visible by reading code.

| | my engine | vectorbt | ratio |
| --- | ---: | ---: | ---: |
| US30 trades | 551 | 513 | 0.93 |
| US30 $/trade | **+$122.85** | **+$256.25** | **2.09×** |
| US100 $/trade | **+$25.88** | **+$67.37** | **2.60×** |

The **signal sets agree** — which is the transcription check, and it passes. The **P&L differs by
2.1–2.6×**, and the entire difference is one convention: when a stop and a channel exit fall inside
the same bar, my engine takes the stop (the pessimistic branch) and vectorbt resolves it its own
way. A second engine being twice as generous on identical signals is not a discovery about the
market; it is `STUDY_V10_LIMIT`'s lesson arriving through a different door. **Any figure from a
bar-level backtest whose stop and exit can fall inside one bar is a statement about the
convention, not about the edge.**

## Deflated Sharpe, as a curve

| assumed trials N | 1 | 10 | 100 | 1,000 | 10,000 | 113,400 |
| --- | --- | --- | --- | --- | --- | --- |
| DSR | 0.227 | 0.038 | 0.003 | 0.0003 | 0.0000 | 0.0000 |

The observed locked Sharpe is negative, so this fails at **N = 1** and the multiplicity is not even
the binding problem.

## What to keep

1. **The grid was 92.5% profitable and told you nothing.** Research→locked PF correlation −0.036.
   Fourth independent measurement on this branch (V30 surrogate 0.96→0.07, V31 +0.215, V33 negative
   in all four cells) that in-sample ranking carries no information here.
2. **Every axis inverts.** Longer Donchian, longer LRMA, wider stop, more filtering — all best on
   research, all worst on the holdout, in exactly reversed order.
3. **No take profit again**, ninth time, 91% of the top 100 against 20% of the population.
4. **A random filter of the same selectivity matches the LRMA(50)/MA(200) stack in 8 of 8 cells.**
   That is the direct answer to the brief's question about those two averages.
5. **Fails on its own market, holds on two that chose nothing** — and still does not beat a random
   entry with the same exits. The exit geometry is the asset; the indicators are not.
6. **A second engine on identical signals paid 2.1× more.** Read the convention before the P&L.

## Files

| file | what it does |
| --- | --- |
| `research/v38/v38grid.py` | the 113,400-cell grid, the cached exit tensor, the position lock |
| `research/v38/v38feeds.py` | the three restored feeds, their clocks re-derived, per-instrument ticks |
| `research/v38/run_v38.py` | the sweep: grid shape, marginals per axis, top-100 consensus |
| `research/v38/run_v38b.py` | three candidates, the single locked read, cross-market, DSR curve |
| `research/v38/run_v38c.py` | the matched and selectivity controls, and the per-year table |
| `research/v38/run_v38_vbt.py` | the winner in vectorbt, as an independent engine |
| `docs/ib/v38_*.txt` | raw output |
