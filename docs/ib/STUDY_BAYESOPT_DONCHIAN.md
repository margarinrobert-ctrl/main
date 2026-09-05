# Bayesian optimisation of the Donchian breakout family on NQ 15m

`research/inst/run_bayesopt.py`, `run_bayesopt_ctl.py`, `results/inst/bayesopt.txt`,
`bayesopt_trials.parquet`. Optuna over a continuous space the 504,000-cell grid could not reach —
entry 10–120, exit 5–80, stop 0.5–4.0 ATR, target off or 1–10 ATR, hold 8–960 bars (log), adaptive
stop, MA200 floor −1 to 4 ATR, CHOP 30–70, prior-session-high gate, RTH or all-hours entries —
searched on the **research block only**. Four studies: research total return, PF with ≥100
trades/yr, Sharpe (each 1,200 multivariate-TPE trials) and total return under a Gaussian-process
sampler (100 trials). Every trial's locked result was logged and never used as an objective. The
finalists were read once on locked (3,700 trials of multiplicity), then scored against a random
entry with their own geometry at their own rate.

Baseline, the user's cell (Donchian 55/30, 1.5 adaptive, no target, swing hold, MA floor 2, CHOP
40, RTH): research PF 2.495 / +19.5% / Sharpe 3.48; locked PF 1.932 / +8.1% / Sharpe 2.72.

## Verdict

**Optimising the profit factor or the Sharpe made the cell worse out of sample. Optimising total
return found a different, looser strategy that earns three times the money at a lower profit
factor — and, unlike most things found by search here, it clears a random-entry control on the
locked block.** So: no improvement on the metric the cell was chosen for; a real one on the metric
it was not.

| study | finalist | research | locked | random entry, locked (p PF / p total) |
|---|---|---|---|---|
| the cell | 55/30, 1.5 adaptive, no TP, MA 2, CHOP 40 | PF 2.50, +19.5%, Sh 3.48 | PF 1.93, +8.1%, Sh 2.72 | 1.02, +0.2% (**0.050 / 0.090**) |
| **PF ≥100/yr** | 56/25, **0.61** stop, no TP, MA 1.35, CHOP 43.6, PSH | PF 2.59, +22.7% | **PF 1.59, +5.0%** | 1.13, +1.4% (0.170 / 0.255) |
| **Sharpe** | 76/75, **3.92** stop, TP 1.5, MA **3.89**, CHOP **31.7**, PSH | PF 2.62, Sh **7.38** | **PF 0.72, −2.3%, Sh −2.22** on 41 | — |
| **total (TPE)** | **11**/47, 3.80 stop, TP 3.2, hold 103, no filters | PF 1.41, **+44.8%** | PF 1.36, **+27.3%**, Sh 1.87 on 331 | 1.07, +4.5% (**0.010 / 0.000**) |
| total (GP) | **10/80, 4.0** stop, **TP 10, hold 960**, no filters | PF 1.37, +36.8% | PF 1.58, +33.3% on 183 | 1.23, +10.6% (0.070 / 0.005); research p 0.270 |

**The box-edge check** (V64's tell): the PF finalist's stop sits at 0.61 of a [0.5, 4.0] box; the
Sharpe finalist has three parameters at edges; the GP finalist has **five** — entry at the
minimum, exit, stop, target and hold all at their maxima — which is the optimiser rediscovering
"be long as much as possible" in a sample that rose 89%, and its random-entry control agrees: a
coin flip with that geometry earns +20.6% research / +10.6% locked on its own, and the rule fails
its research PF control (p 0.270).

**fANOVA importance**: the stop carries **0.90** of the total-return objective, 0.78 of Sharpe,
0.56 of the GP objective; only the PF study is carried by CHOP (0.53 + 0.22). An optimiser told to
maximise money on this data mostly learns to widen the stop.

**Transfer across all trials**: Spearman between the research objective and the locked total is
+0.40 (total), +0.12 (PF), **−0.03 (Sharpe)**, +0.07 (GP). The Sharpe ranking carries no
information at all — its top 1% by research reads +1.9% locked against a population mean of
+4.0%. Top-10 neighbourhoods: total +42.2% → +22.0% (100% locked-positive); PF 2.56 → 1.89
(below the cell's 1.93); Sharpe 6.65 → 1.05 with 30% of the ten negative.

## The one real finding, stated carefully

The TPE-total finalist — RTH entries, an **11-bar** Donchian entry, 47-bar channel exit, 3.8 ATR
stop, 3.2 ATR target, ~1-day hold, **no filters** — is not the cell improved; it is a different
strategy in the same family: about 320 trades a year at PF 1.36–1.41, against the cell's 104 at
1.93–2.50. It earns **+27.3% locked against the cell's +8.1%**, its top-10 neighbourhood is
locked-positive ten times out of ten at a mean +22.0%, and a random entry running the identical
geometry at the same rate earns +4.5% on locked (p 0.000 on total, 0.010 on PF). Its entry length
sits one rung above the box minimum, so the box-edge caveat is partly on it too; and it trades the
cell's profit factor for count exactly as the 504k marginals said the family does. It clears the
bar the cell itself only reaches marginally (cell locked control p 0.050 / 0.090 — the first
control this cell has been given, and it is borderline).

## What to carry

- **Bayesian optimisation buys the objective you name, at the cost of the ones you don't.** PF and
  Sharpe optima decayed or inverted; the total-return optimum held because "more trades at a wide
  stop" is a property of the family, not of the parameters.
- The stop's 0.56–0.90 fANOVA share is the mechanism in one number.
- Five parameters at the box edge is a result about the box, not the market.
- Nothing here reaches PF 2 out of sample at any count; the cell's 1.93 remains the family's best
  locked profit factor at ≥100 trades/yr, and it sits on a p 0.05 control.
