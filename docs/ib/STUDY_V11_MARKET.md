# The best market-order entry, and the first breakout on this branch to beat its own control

NQ 15-minute, 70,685 bars, 2022-12-26 → 2025-12-12. Research = first 65% of sessions; LOCKED read
once after parameters were fixed. 459 cells swept, on research only. Costs $1.44 a round turn.

## The configuration

**Donchian 55 breakout · ADX ≥ 25 · stop 2.5 × ATR(20) · 20-bar channel exit · ONE unit · NO take
profit · market order at the next open.**

| | n | PF | win | Sharpe | pts/trade | max DD | ret/DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| V9-PROP as shipped, research | 968 | 1.08 | 35.0% | 0.66 | +2.00 | 1,142 | 1.69 |
| V9-PROP as shipped, LOCKED | 477 | 1.17 | 35.8% | 1.23 | +6.17 | 2,580 | 1.14 |
| **V11, research** | 339 | **1.44** | 36.0% | **2.28** | **+12.19** | 703 | 5.88 |
| **V11, LOCKED** | 178 | **1.29** | 36.0% | **1.36** | **+11.61** | 2,044 | 1.01 |

Points per trade nearly double out of sample, on a third of the trades, and the shape decays
research → locked rather than improving.

## Both controls pass — which has not happened before on this branch

| gate | question | result |
| --- | --- | ---: |
| **matched control** | does the breakout beat a RANDOM BAR with identical stop, exits and trade count? | +12.19 vs +2.32, **p 0.007** |
| **selectivity control** | does ADX ≥ 25 beat a random filter of the same selectivity, drawn from the ungated breakout population? | +12.19 vs +4.89, **p 0.016** |

Every earlier version of this system failed the first gate at p 0.12–0.43, and this repository's
standing summary is that *four separate breakout triggers have failed against their own
random-entry controls*. **Two changes flip it: the ADX floor at 25 instead of 15, and removing the
take profit entirely.** Neither was chosen for that reason — both fell out of the marginal sweep.

## How the parameters were chosen

Marginal Sharpe averaged over every other setting, which is the robust way to read a grid — a
single top cell is the maximum of 459 draws, a marginal average is not:

| axis | marginal Sharpe |
| --- | --- |
| ADX | 0: +0.59 · 15: +0.74 · 20: +1.26 · **25: +1.78** |
| stop | 1.5N: +0.76 · 2.0N: +1.06 · **2.5N: +1.31** · 3.0N: +1.24 |
| take profit | **none: +1.37** · 1R: +0.92 · 1.5R: +1.00 · 2R: +1.04 · 3R: +1.14 |
| Donchian | 10: +1.16 · 20: +0.90 · 30: +1.10 · **55: +1.21** |

ADX and the stop were then extended past the edge of the grid, because both peaked at a boundary.
Beyond 25 the ADX effect stops being monotone (30: +1.76, 35: +2.27, 40: +1.81) and the
better-scoring cells thin out to n = 124–202 — the lottery shape — so **25 was kept**. The stop is
genuinely flat from 2.0N to 4.0N.

**No take profit beat every target tested.** That is the third time this branch has found the same
thing from a different direction, after `STUDY_INTRADAY_HEAT` (the target is never reached) and the
US30 target sweep (the surface rises monotonically with target distance).

**One unit beats two and three** on every measure that matters: Sharpe 2.28 / 2.04 / 1.95, drawdown
703 / 1,595 / 2,033. A trailing stop did not help at any multiple.

## Robustness

**Perturbation is a ridge.** Every axis, ±10–20%, moves profit factor by 0.05 or less:

| | −20% | −10% | base | +10% | +20% |
| --- | ---: | ---: | ---: | ---: | ---: |
| stop | 1.43 | 1.41 | **1.44** | 1.49 | 1.47 |
| ADX (22 / 28) | — | 1.45 | **1.44** | 1.40 | — |
| Donchian (45 / 65) | — | 1.43 | **1.44** | 1.44 | — |
| exit channel (15 / 25) | — | 1.39 | **1.44** | 1.45 | — |

- Bootstrap of the mean: 95% CI **[+2.46, +21.85]**, P(mean ≤ 0) = **0.0075**.
- 10% random trade omission: PF p5 1.28, median 1.38 — not carried by a handful of trades.
- Walk-forward, six folds, no refit: **5/6 positive**, median PF 1.61, worst 0.98.
- Monte Carlo, 20,000 shuffles: realised drawdown 2,044 against a median of **1,284** and a p95 of
  2,033. **The realised sequence was unlucky, not lucky** — the rarer and safer direction, and the
  opposite of what `STUDY_MEGA_144K` found. Size for the p99 of **2,459**.

## What to hold against it

- **Drawdown nearly triples out of sample** — 703 → 2,044 — so return-over-drawdown falls from 5.88
  to 1.01. Profit factor and Sharpe held; the drawdown did not.
- **One fold of six is flat** (PF 0.98, Sharpe −0.12) and it carries the entire maximum drawdown. A
  six-month dead patch is inside normal behaviour here.
- **Long only**, on a sample where NQ rose 89%. Not tested short.
- **459 cells were searched.** Both controls run on research and the locked block was read once,
  which is the discipline — but the multiplicity is real and the locked column is what to believe.

## The Pine

`pine/turtle/V11_MARKET_strategy.pine`, parity-checked by `research/v8opt/v11_parity.py`:
**98.8% of signals match, exit bar identical on 88.5%, per-trade correlation 0.9899–0.9997.** The
tightest port on this branch, because one unit and a market order remove both of the things that
broke the earlier ones — a ladder re-anchoring inside a bar, and a limit fill that has to be
ordered against the exits.
