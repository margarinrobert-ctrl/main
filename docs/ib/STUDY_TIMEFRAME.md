# Does the 1-hour chart beat the 30-minute one? 248,832 configurations

Four intervals — 15m, 30m, 60m, 120m — crossed with every structural and risk parameter the
BOS/CHoCH rule has. **248,832 configurations, 109,501 of them with enough trades to score.**
Chosen on the research block (first 65% of sessions), read once on the locked block. MNQ costs
throughout: $2/point, $1.00 commission per round turn, 1 tick spread + 1 tick slip each side,
1 extra tick on a stop fill.

The sweep kernel was validated before it was trusted: on the incumbent's own settings it returns
**141 trades, $11,679, PF 1.64, 44.0% win, locked block $8,932** — the published figures to the
dollar.

## 1. The honest comparison: pairs, not winners

A search that picks the best cell on each timeframe is comparing search widths, not timeframes.
So every non-timeframe parameter set was run on all four intervals and the pairs compared
directly. **10,032 parameter sets are tradeable on all four.**

| interval | mean locked $ | median locked $ | % locked positive | mean trades |
| --- | --- | --- | --- | --- |
| 15m | 952 | 1,269 | 61.3% | 709 |
| **30m** | **1,767** | **1,774** | **70.4%** | 376 |
| 60m | 342 | 123 | 51.4% | 205 |
| 120m | −1,005 | −1,139 | 38.4% | 105 |

| against 30m | mean difference | pairs won | paired t |
| --- | --- | --- | --- |
| 15m | −$815 | 45.4% | **−16.05** |
| 60m | −$1,425 | 35.0% | **−32.31** |
| 120m | −$2,772 | 27.2% | **−53.78** |

**In dollars, 30m wins and it is not close.** That is the answer to the question as asked.

## 2. But the 1-hour chart is better per trade, not worse

Dollars are trades × edge-per-trade, and the two move in opposite directions here. Separate them
with the barrier bound: for a price path with no drift, P(target before stop) = `1/(1+R)`, a
property of the geometry and not of the entry. **An entry that adds nothing scores exactly that.**
The excess is the only part of a win rate the entry earned.

| interval | target | bound | mean win % | mean excess |
| --- | --- | --- | --- | --- |
| 15m | 2.0R | 33.3% | 34.2% | +0.86 |
| 30m | 2.0R | 33.3% | 34.9% | +1.59 |
| **60m** | **2.0R** | **33.3%** | **35.2%** | **+1.89** |
| 120m | 2.0R | 33.3% | 33.4% | +0.06 |

Signal quality **rises** from 15m to 60m and then falls off a cliff at 120m. Throughput falls
faster than quality rises, so 30m wins on net — but 60m is not a degraded 30m, it is a rarer and
cleaner one. On the incumbent's own settings, transplanted with nothing refitted:

| | trades | win % | excess over bound | net $ | PF | maxDD |
| --- | --- | --- | --- | --- | --- | --- |
| 5m | 999 | 33.9 | +0.6 | 1,236 | 1.02 | 5,998 |
| 15m | 340 | 37.1 | +3.8 | 4,004 | 1.10 | 3,585 |
| **30m** | 141 | 44.0 | **+10.6** | **11,679** | 1.64 | 2,865 |
| **60m** | 45 | 55.6 | **+22.2** | 7,574 | **2.22** | **1,196** |
| 120m | 22 | 36.4 | +3.1 | −1,209 | 0.78 | 2,887 |

55.6% at a 2R target is a binomial z of **+3.16** against the 33.3% bound.

### It is a plateau, not a spike

The single most useful test on any good-looking number. A real setting has neighbours that score
near it; a mined one falls off in every direction. All twelve one-step perturbations of the 60m
leg keep a positive excess:

| moved | trades | win % | excess |
| --- | --- | --- | --- |
| nBos 1 | 96 | 42.7 | +9.4 |
| nBos 3 | 29 | 58.6 | +25.3 |
| stop 1.5×ATR | 46 | 50.0 | +16.7 |
| stop 2.5×ATR | 40 | 47.5 | +14.2 |
| swing k2 | 64 | 42.2 | +8.9 |
| swing k4 | 43 | 46.5 | +13.2 |
| EMA 100 | 43 | 53.5 | +20.2 |
| EMA 50 | 48 | 52.1 | +18.8 |
| range filter off | 45 | 55.6 | +22.2 |
| range filter ≥ 1.5 | 40 | 52.5 | +19.2 |

Range **+8.9 to +25.3**, never negative.

## 3. What the search picked, and why it was rejected

Best on the research block across all 248,832: **120m, k5, EMA50, nBos 1, 2.5×ATR, 3R, 24h, both
sides** — research $17,665, locked **$10,741**, nominally beating the incumbent's $8,932.

It is a spike:

| one step away | locked $ |
| --- | --- |
| **the winner** | **10,741** |
| nBos 2 | **−5,557** |
| timeframe 60m | 5,249 |
| timeframe 240m | 2,033 |
| stop 2.0×ATR | 3,323 |
| target 2.0R | 7,527 |
| EMA 200 | 2,642 |

Neighbour median $7,527, **85% of neighbours below it**, and a single click on nBos costs
$16,298. It also comes from the interval with the worst distribution of any (median locked
−$1,145, only 38.4% positive) and no measurable entry information (+0.06 excess at 2R). The
winner is a hole in the noise, not a setting.

**Walk-forward passed it: 0 negative forward folds of 6.** So did the incumbent. As in
`RESEARCH_PROTOCOL.md` §4c, walk-forward cannot separate these — the market rose through every
fold. Not adopted.

## 4. What was adopted: run both charts

The 60m leg is not a replacement, it is a second instance of the same spec — the "60m core"
preset already in the script, range filter off, nothing refitted. The two share only **23 of 163
trading days** and their daily P&L correlates **+0.25**.

| book | block | net $ | maxDD | net/DD | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 30m alone | full | 11,679 | 2,865 | 4.08 | 1.13 |
| 60m alone | full | 7,574 | 1,196 | 6.33 | 1.21 |
| **30m + 60m** | **full** | **19,253** | **1,912** | **10.07** | **1.43** |
| 30m alone | research | 2,747 | 2,710 | 1.01 | 0.65 |
| 60m alone | research | 3,672 | 1,196 | 3.07 | 1.05 |
| **30m + 60m** | **research** | **6,419** | **1,912** | **3.36** | **1.00** |
| 30m alone | LOCKED | 8,932 | 1,315 | 6.79 | 1.70 |
| 60m alone | LOCKED | 3,902 | 972 | 4.01 | 1.46 |
| **30m + 60m** | **LOCKED** | **12,834** | **1,713** | **7.49** | **2.00** |

More money and a **smaller worst drawdown** than 30m on its own, on both blocks. Return-over-
drawdown goes 4.08 → 10.07 on the full sample. A stationary block bootstrap of the combined
locked block, 10,000 paths: p5 $6,947, median $12,239, p95 $17,900.

## 5. What is not being claimed

- **45 trades in three years**, 14 of them in the locked block. The 60m leg's locked contribution
  is $3,902 at **t = +1.46** — it improves the book but does not clear a significance bar on its
  own, and it never will at that frequency.
- **The 60m edge is asymmetric.** Longs 24 trades, 75.0% win, +$7,614. Shorts 19 trades, 26.3%,
  −$1,180. Section 4c again: direction is doing work, on a sample where the index rose. The leg
  is kept two-sided precisely because the long-only version is what an overfit would look like.
- **The bootstrap's P(net<0) = 0.0% means very little.** Every resampled path is drawn from a
  rising market. It is reported for completeness, not as evidence.
- The marginal table is the quiet confirmation: averaging over everything else, the best value on
  each axis is EMA 200 ($321), target 1.0–2.0R, stop 1.5–2.0×ATR, nBos 2 ($36), 30m ($394) —
  every one of them the incumbent's existing setting. The spec was already at the marginal optimum
  on every axis. The only thing 248,832 configurations found was a second chart to run it on.

## Reproduce

```
python3 research/tf_sweep.py       # the 248,832-configuration sweep
python3 research/tf_analyse.py     # paired, selected, barrier bound, section 4c, marginals
python3 research/tf_followup.py    # incumbent per interval; plateau-vs-spike; walk-forward
python3 research/tf_60m.py         # the 60m plateau, the combination, the block split
```
