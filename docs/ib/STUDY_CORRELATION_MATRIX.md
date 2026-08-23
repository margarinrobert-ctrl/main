# Correlation matrix, and what it exposed about nBos

A correlation matrix does not answer "is each leg profitable". It answers **"are these the same
trade wearing different clothes"** — two legs at rho 0.9 are one leg paying commission twice.

## The matrix — daily P&L, MNQ, Dec-2022..Dec-2025, 922 sessions

| | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 30m 2R target | 1.00 | 0.40 | 0.31 | 0.44 | 0.79 | **0.97** | 0.75 | 0.65 | 0.22 | 0.17 |
| 2 30m CHoCH exit | 0.40 | 1.00 | 0.32 | 0.49 | 0.32 | 0.39 | 0.11 | 0.48 | 0.22 | 0.21 |
| 3 30m 3R target | 0.31 | 0.32 | 1.00 | 0.24 | 0.26 | 0.30 | 0.17 | 0.28 | 0.49 | 0.16 |
| 4 30m 1R target | 0.44 | 0.49 | 0.24 | 1.00 | 0.33 | 0.42 | 0.18 | 0.47 | 0.12 | 0.27 |
| 5 30m 2R, nBos=1 | 0.79 | 0.32 | 0.26 | 0.33 | 1.00 | 0.78 | 0.61 | 0.51 | 0.21 | 0.23 |
| 6 30m 2R, no range filter | **0.97** | 0.39 | 0.30 | 0.42 | 0.78 | 1.00 | 0.73 | 0.64 | 0.22 | 0.20 |
| 7 30m 2R LONGS | 0.75 | 0.11 | 0.17 | 0.18 | 0.61 | 0.73 | 1.00 | **−0.00** | 0.12 | 0.08 |
| 8 30m 2R SHORTS | 0.65 | 0.48 | 0.28 | 0.47 | 0.51 | 0.64 | **−0.00** | 1.00 | 0.22 | 0.18 |
| 9 60m 2R target | 0.22 | 0.22 | 0.49 | 0.12 | 0.21 | 0.22 | 0.12 | 0.22 | 1.00 | 0.05 |
| 10 15m 2R target | 0.17 | 0.21 | 0.16 | 0.27 | 0.23 | 0.20 | 0.08 | 0.18 | 0.05 | 1.00 |

**PC1 explains 45% of variance. Effective number of bets: 5.54 out of 10 legs.**

### What the cells say

- **Longs and shorts correlate −0.00.** Exactly independent. This is the single best diversification
  in the whole book and it is free — it is already in the strategy. It also means the long-side
  advantage cannot be "hedged into" by weighting; the two sides are separate bets.
- **The range filter is nearly invisible at rho 0.97.** Removing it barely changes the *shape* of
  the P&L stream while costing $2,107 in level. A filter can matter for expectancy while being
  almost irrelevant to correlation — these measure different things, and reading one for the other
  is a mistake.
- **60m against 30m is 0.22, and 15m against everything is 0.05-0.27.** The timeframe legs are the
  genuine diversifiers. But 15m earns $4,004 over 340 trades — $12 a trade, below any realistic
  cost cushion. Independent and worthless is still worthless.
- **3R against 2R is only 0.31.** Different targets on the same signal produce substantially
  different streams, because the target determines *which* trades resolve and when.

## What the matrix exposed: nBos was never re-tested against the take-profit

Cell 5 showed `nBos=1` at **$18,067** against the spec's $11,679. The "enter on the second break"
rule was validated under the **CHoCH exit**, where a second break protected against whipsaw. With a
fixed 2R target that protection is redundant — the target already bounds the outcome — so waiting
costs trades without improving them. The two parameters were never tested *jointly*.

Re-tested across three nBos values and three targets:

| | research net | LOCKED net | LOCKED Sharpe |
| --- | --- | --- | --- |
| nBos 1, target 1.5R | $3,945 | $10,086 | **2.06** |
| **nBos 1, target 2.0R** | **$6,319** | **$11,748** | 1.94 |
| nBos 1, target 3.0R | $4,575 | $7,768 | 1.05 |
| nBos 2, target 1.5R | $609 | $7,273 | 1.73 |
| nBos 2, target 2.0R *(current spec)* | $2,747 | $8,932 | 1.70 |
| nBos 2, target 3.0R | $4,019 | $8,180 | 1.21 |
| nBos 3, target 2.0R | $3,869 | $4,168 | 0.99 |

`nBos=1` beats `nBos=2` at five of the six target levels, on both blocks.

### Validation, same battery the 2R target got

| test | nBos 1 | nBos 2 |
| --- | --- | --- |
| walk-forward stitched, 6 folds | **$16,313** | $11,481 |
| folds won | **5 of 6** | 1 of 6 |
| Monte Carlo median net | **$18,236** | $11,558 |
| Monte Carlo P(net < 0) | **0.2%** | 0.7% |
| **Monte Carlo maxDD median** | $2,888 | **$2,278** |
| **maxDD p95** | $5,166 | **$4,093** |
| paired same-session t | **+1.55** | — |

It wins on every return measure and loses on drawdown by about 26%.

### Why this is NOT being made the default

1. **t = +1.55 is not significant.** Better than the 2R target's +1.22, still short of any bar.
2. **It came from a nine-cell examination**, so a multiple-testing haircut applies — smaller than
   usual because the direction is consistent across targets rather than a single spike, but real.
3. **Drawdown rises 26%**, and this account's stated priority is a shallow drawdown.
4. It would be the **second** spec change in a row. Each one erodes the claim that this rule was not
   tuned, and that claim is most of what makes the out-of-sample result believable.

The honest position: `nBos=1` is *probably* better on return and *certainly* worse on drawdown, and
the difference is not established either way. The input exists; the evidence is now in its tooltip;
the default stays at the tested value.

Reproduce with `python research/corr_matrix.py`.
