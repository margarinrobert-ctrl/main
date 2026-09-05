# Optuna under the scalping constraints: entries 07:00–11:00 New York, hold ≤ 4 hours

`research/inst/run_bayesopt_scalp.py`, `results/inst/bayesopt_scalp.txt`,
`bayesopt_scalp_trials.parquet`. The Donchian family on NQ with two constraints added to the
previous study's space — entries only between 07:00 and 11:00 New York, hold capped at four hours
(5 to 240 minutes, converted to bars) — and 5-minute bars added as a scalping timeframe. Three
multivariate-TPE studies of 1,200 trials (research total return, PF at ≥100 trades/yr, Sharpe),
research block only; finalists read once on locked and scored against a random entry inside the
same window at the same rate. Multiplicity: 3,600 trials.

## What the constraints cost before any optimisation

| | research | locked |
|---|---|---|
| the cell, unconstrained | 192 trades, PF 2.50, +19.5% | 104, PF 1.93, +8.1% |
| the cell, 07–11 entries + 4h cap | 171, **PF 1.42, +5.4%** | 95, PF 1.33, +3.0% |
| plain Donchian 20/10, 1.5N, 4h cap, 5m | 982, PF 0.90, −7.7% | 511, PF 0.98, −0.8% |
| plain Donchian 20/10, 1.5N, 4h cap, 15m | 545, PF 0.99, −0.7% | 266, PF 1.34, +11.9% |

The window and the cap take 72% of the cell's research return away, and the cell under them fails
a random-entry control on locked (p 0.285). The plain family in the window is break-even on
research on both bar sizes — 5-minute bars lose outright.

## The populations

| study | profitable, research | profitable, locked | corr(research total, locked total) | top decile → locked |
|---|---|---|---|---|
| total | 65.1% | **35.3%** | **−0.182** | −1.68% vs −1.19% |
| PF ≥100/yr | 60.3% | **35.2%** | **−0.065** | −0.24% vs −0.20% |
| Sharpe | 67.0% | 73.8% | +0.141 | +2.69% vs +1.83% |

Two of the three research rankings are **negatively** correlated with the locked result:
selecting on research in this window is worse than not selecting (transfer Spearman −0.240 and
−0.094). V30 measured the same shape on the Turtle in 07:00–11:00. The Sharpe study is the odd one
out because its trials cluster in the 15m / wide-stop / few-trades corner where the locked block's
up-move pays anything long.

## The finalists, read once

| study | settings | research | locked | random entry in the window, locked (p PF / p total) |
|---|---|---|---|---|
| cell (constrained) | 55/30, 1.5 adaptive, MA 2, CHOP 40 | 171, PF 1.42, +5.4% | 95, PF 1.33, +3.0% | 1.12, +1.1% (0.285 / 0.305) |
| **total** | 15m, **Donchian 7/8**, 3.19 stop, TP 2.3, hold 230 min, no filters | 763, PF 1.18, +16.2% | **387, PF 1.13, +6.9%, win 49%** | 0.95, −2.5% (**0.040 / 0.015**) |
| PF ≥100/yr | 15m, 88/48, 1.38 adaptive, MA **3.99**, PSH, hold 153 | 232, PF 1.53, +8.0% | **128, PF 0.84, −1.7%** | 1.01, +0.1% (0.760 / 0.740) |
| Sharpe | 15m, 52/45, 2.38, TP 3.8, CHOP **30.0**, hold 222 | 59, PF 2.21, Sh 6.49 | 37, PF 1.32, +1.8% | 1.10, +0.6% (0.320 / 0.345) |

Box-edge check: the total finalist's entry (7) and hold (230 of 240) sit at edges, the PF
finalist's MA floor (3.99 of 4.0) and the Sharpe finalist's CHOP (30.0 of 30) do too.
Top-10 neighbourhoods: total +14.4% → **−1.4%** (20% locked-positive); PF +7.4% → −0.6% (20%);
Sharpe +8.3% → +2.4% (100%, on ~50 trades each). fANOVA: the stop carries 0.70 / 0.29 / 0.64 of
the three objectives.

## Verdict

**The best settings the optimiser can find for 07:00–11:00 with a four-hour cap are a fast
7/8-bar Donchian on 15-minute bars with a wide 3.2 ATR stop, a 2.3 ATR target and no filters — and
what they deliver is a coin-flip strategy with a small, real edge**: locked PF 1.13 at a 49% win
rate over 387 trades, +6.9%, clearing a random entry in the same window at p 0.040 / 0.015 on both
blocks (the only finalist that does). Its own neighbourhood is 20% locked-positive, its entry length
is one rung off the box minimum, and its research-to-locked transfer across the whole study is
negative, so it is one draw that happened to hold, not a ridge. The PF-optimised settings invert
out of sample (1.53 → 0.84); the Sharpe-optimised ones survive on 37 trades and fail their control.

Against the unconstrained cell (locked PF 1.93, +8.1% on 104 trades, hold to the channel exit) the
constraints buy nothing: less profit factor, about the same money, four times the trades. This is
the fourteenth time on this branch that an intraday window plus a hold cap has cost most of a
trend rule's edge — and the first where a 5-minute bar size was searched alongside and chosen by
none of the three objectives.
