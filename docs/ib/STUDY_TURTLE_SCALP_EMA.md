# EMA150 trend, 20/50 cross aligned with 200, and a pullback to EMA20, on the Turtle Scalp

`research/tscalp/`, `results/tscalp/`. The submitted `Turtle Scalp 07:00-11:00 NY` Pine (its study
is not on this branch) was transliterated with its own order model -- armed stop at the signal
close, re-anchor at the fill bar's close, pyramid to 4 units bracketed at the position's level,
2R target, no channel exit, 11:00 flatten filling at the next open, skip-S1-after-a-win -- and
reproduces the script's header on the same feed: **899 locked trades against its 898, PF 1.056
against 1.04**. Note the script sets **no commission and no slippage**; everything here pays this
branch's US30 standard (1.50 pts a side). Research = US30 15m before 2022; locked = 2022+.

## Verdict

**None of the three gates survives, and the one that looks best is the sharpest inversion on this
branch in a while.** The strategy as asked -- EMA150 trend, 20>50>200 alignment, wait for a
pullback to EMA20 and let the Donchian fire there or after -- reads:

| | n | R/trade | PF | Sharpe | random filter, same selectivity |
|---|---|---|---|---|---|
| shipped script, research | 1,145 | +0.1047 | 1.080 | 0.43 | — |
| **the ask**, research | 465 | +0.0307 | 1.162 | 0.76 | median +0.0896, **p 0.837** |
| shipped script, locked | 899 | +0.0176 | 1.056 | 0.36 | |
| **the ask**, locked | 371 | **−0.0329** | **0.949** | −0.34 | (test alone PF 0.831) |

It fails a same-selectivity random filter on research and is worse than the ungated script out
of sample. Cross-market it is worse than the script on US100's test block (0.844 vs 1.016) and on
NQ's locked block (0.923 vs 1.209).

## Base rates first

Each gate's pass rate on the Donchian signal bars inside the window, against all bars:

| gate | on signal bars | all bars | lift |
|---|---|---|---|
| EMA150 above | 85.8% | 59.0% | 1.46× |
| 20>50>200 state | 58.3% | 45.1% | 1.29× |
| fresh 20/50 cross ≤5 bars, >200 | 6.6% | 2.2% | 3.01× |
| pullback: low ≤ EMA20 within 3 / 5 / 10 | 45.8 / 62.4 / 79.4% | 69.5 / 75.6 / 84.9% | **0.66 / 0.83 / 0.94×** |

**The pullback gate has a lift below one.** A Donchian breakout bar is, by construction, away from
its EMA20, so requiring a recent touch removes the cleanest breakouts and keeps the ones that
stalled -- the same mechanism `STUDY_KAMA_ENTRY` measured from the other side ("the tap loses to
just taking the trade"). Measured: the pullback alone turns the script **negative** (−0.0388,
PF 0.981) and a random filter of the same selectivity beats it in **100% of draws**.

## Drop-one, research

| variant | n | R/trade | PF |
|---|---|---|---|
| the ask (all three) | 465 | +0.0307 | 1.162 |
| − EMA150 | 466 | +0.0376 | 1.170 |
| − cross | 733 | +0.0089 | 1.104 |
| **− pullback** | 670 | **+0.1898** | **1.241** |

EMA150 is redundant once the 20>50>200 state is on: the grid cells `off/state/off` and
`above/state/off` are **identical** (670 trades, same result), because 20>50>200 already implies
price is above every long average. The pullback is the component doing the damage.

## The candidate, and what happened to it

EMA150 + 20>50>200 state, no pullback, is the drop-one consensus, the marginal winner on two of
three axes, and clears its research control at **p 0.000** (+0.1898 against a random-filter median
of +0.0976). Its neighbourhood is a plateau -- six one-rung perturbations of the three EMA lengths
read PF 1.206–1.285, Sharpe 1.09–1.34. Every robustness test a reader would ask for passes on
research.

**US30 locked, read once** (chosen after ~40 research cells were seen, so descriptive):
**−0.1683 R, PF 0.848, Sharpe −1.12** on 489 trades; test block alone **PF 0.717, Sharpe −2.44**;
random-filter control **p 1.000**; bootstrap P(mean≤0) 0.911. On the held-back markets it is
worse than the shipped script where the script is positive (US100 test 0.919 vs 1.016, NQ locked
1.105 vs 1.209) and only better where both lose.

Fifth "perfect plateau" on this branch to fail out of sample (`STUDY_V60`, `V38`, `V41`, `V64`).
Coherence rejects artefacts of the search; it cannot see a regime.

## What the script's own switches say, on the candidate (research)

- **No take profit** +0.3392 vs +0.1898 with the 2R target — the eighteenth time no target has won here.
- **No flatten** +0.3813, PF 1.344, and positive on **every** held-back block (US100 1.359 / 1.276 /
  1.078, NQ 1.097 / 1.102) where the flattened version is not. But a Turtle that holds overnight is
  a different strategy, not a filtered scalp, and it was not read on US30 locked.
- **One unit** halves the drawdown (2,879 → 1,305) for PF 1.220 — the prop answer again.
- **2× cost** takes the candidate to PF 1.065 and the ask to 1.001: a 1.5-point side on a 2.5×ATR
  US30 stop is not small.

## Monte Carlo (research)

Ask: execution P(total>0) 1.000, price jitter with EMAs/channels/ATR recomputed 1.000, day-block
bootstrap **P(mean≤0) 0.163**, permutation p99 drawdown **3.4× realised** (realised at the 0th
percentile — a lucky path), top 5% of trades **305% of net**. The base script: bootstrap 0.198,
top 5% **545% of net**. Neither excludes zero; both live in the tail.

## What ships

The script with the three gates as **inputs, all default OFF**, each tooltip carrying the number
above. The ask is reproducible by turning them on. Nothing was changed on the basis of performance.
