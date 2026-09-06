# STUDY: the V61 CVD rule with the session on — IS/OOS, 15m vs 30m, Optuna, Monte Carlo, portfolio

**The ask.** IS/OOS on the incumbent 30m preset as it is actually being run (07:00–11:00 New York,
flatten on), try it on 15-minute bars, use Optuna to raise profit factor and cut drawdown, and build
a portfolio.

**The short answer.** The 15-minute chart *is* better — but not with the flatten on, and not for the
reason it looks. The flatten is what costs; the window is close to free. Optuna raises research
profit factor to 2.5 and both optima **invert** out of sample, with a population transfer
correlation of **−0.43**. The portfolio is the one genuine improvement, and its case is not a higher
return.

**Code.** `research/v61sess/sess_core.py`, `run_iss_oss.py`, `run_optuna.py`, `run_mc_portfolio.py`,
`plot_sess.py`. Output `results/v61sess/`, panel `session_panel.png`.

## Two things to fix before reading any Strategy Tester number

**1. The script sets no commission and no slippage.** Its own header says so. Unless Properties was
changed, the +$8,540 on screen is a **zero-cost** result. Measured here, cost is **4.6% to 21.9% of
gross** depending on configuration — and it is worst exactly where the flatten is on, because a
truncated trade earns less against a fixed round turn.

**2. On a 15-minute chart the incumbent preset is a different strategy.** The order-flow settings
are declared in minutes and converted by the chart timeframe, so k3/w20 on 30m (90 / 600 minutes)
becomes **k6/w40** on 15m — same time reach. But the channels are in **bars**, so 20/20 on 15m is
**half** the time reach of 20/20 on 30m. And the CVD is coarser: 15 one-minute sub-bars a bar
against 30.

*(Totals below will not match the tester: this branch holds three years of 1-minute NQ, a chart
holds more. The shape transfers; the totals do not.)*

## 1 — IS/OOS, both timeframes, both configurations

MNQ at $2/point, 0.72 points cost and 0.25 slippage a side. Research = first 65% of sessions.

| tf | configuration | block | n | PF | $ | maxDD $ | ret/DD | %/trade |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 30m | as shipped (all hours) | research | 158 | **1.784** | 7,482 | 746 | 10.02 | +0.1193 |
| 30m | as shipped | locked | 87 | 1.611 | 5,417 | 3,127 | 1.73 | +0.1384 |
| 15m | as shipped (all hours) | research | 225 | 1.570 | 5,933 | 798 | 7.44 | +0.0697 |
| 15m | as shipped | locked | 125 | **1.869** | 5,741 | 697 | **8.23** | +0.1022 |
| 30m | **as you run it** (07–11 + flatten) | research | 76 | 1.323 | 1,270 | 536 | 2.37 | +0.0440 |
| 30m | as you run it | locked | 39 | 1.598 | 1,380 | 639 | 2.16 | +0.0720 |
| 15m | **as you run it** | research | 87 | **1.151** | 674 | 876 | 0.77 | +0.0171 |
| 15m | as you run it | locked | 45 | 1.859 | 1,656 | 388 | 4.26 | +0.0796 |

**Your configuration keeps about a fifth of the return.** And on 15m it reads PF 1.151 on the block
that is allowed to judge it and 1.859 on the one that is not — the wrong shape, which is why the
15-minute result should not be trusted on the strength of the locked block alone.

**15m as shipped is the best-behaved leg in the table**: locked PF 1.869, ret/DD 8.23, Sharpe 2.07,
and its drawdown is a fifth of 30m's on the same block.

## 2 — The flatten is the cost. The window is not.

Four arms so the two changes are not confounded:

| tf | arm | research PF | locked PF | research ret/DD | locked ret/DD |
| --- | --- | --- | --- | --- | --- |
| 30m | all hours, no flatten | 1.784 | 1.611 | 10.02 | 1.73 |
| 30m | **07:00–11:00, NO flatten** | 1.683 | **2.853** | 5.20 | **5.80** |
| 30m | all hours, flatten 11:00 | 1.348 | 1.170 | 2.98 | 0.43 |
| 30m | 07:00–11:00 + flatten | 1.323 | 1.598 | 2.37 | 2.16 |
| 15m | all hours, no flatten | 1.570 | 1.869 | 7.44 | 8.23 |
| 15m | 07:00–11:00, NO flatten | 1.679 | 1.830 | 4.33 | 3.03 |
| 15m | all hours, flatten 11:00 | 1.359 | 1.323 | 3.08 | 1.06 |
| 15m | 07:00–11:00 + flatten | 1.151 | 1.859 | 0.77 | 4.26 |

**Adding the flatten to an all-hours run costs 0.4–0.5 profit factor on every timeframe and both
blocks.** Adding the window alone costs little and on 30m locked it *helps*. Fourteenth confirmation
on this branch that a hard flatten truncates exactly the trades a channel exit exists to hold.

**The single largest change available: turn the flatten off and keep your window.** On 30m that is
locked PF 2.853 with ret/DD 5.80. Read it as the best of eight cells, not as a fresh result.

## 3 — Optuna: 2,400 trials, and the ranking runs backwards

Two objectives (profit factor, and return/drawdown), TPE, **research block only**, 40 trades/year
floor, session start/end/flatten all searchable.

| | trials scorable | research PF>1 | locked PF>1 | **corr(research PF, locked PF)** |
| --- | --- | --- | --- | --- |
| PF objective | 998 | 99.7% | 58.2% | **−0.458** Pearson / −0.487 Spearman |
| ret/DD objective | 1,038 | 99.3% | 63.4% | **−0.417** / −0.475 |

**Top 1% by research PF: 2.44 research → 0.749 locked, against the whole population's 1.099.**
Selecting the best research cells was worse than picking at random from the population.

Both optima invert:

| finalist | research PF | research ret/DD | **locked PF** | locked total |
| --- | --- | --- | --- | --- |
| Optuna PF optimum (15m, 50/47, 3.6N) | 2.472 | 6.08 | **0.604** | **−6.25%** |
| Optuna ret/DD optimum (30m, 18/13, 1.5N) | 2.506 | **21.09** | **0.910** | **−2.12%** |
| incumbent 30m, unoptimised | 1.784 | 10.02 | 1.611 | +12.04% |
| incumbent 15m, unoptimised | 1.570 | 7.44 | **1.869** | +12.78% |

Ninth optimiser on this branch to lose to the author's constants. `STUDY_V64_OPTUNA` already ran
6,000 trials on this rule and none of six finalists beat the shipped presets; this reproduces it
with the session axis open, which is a bigger box and a worse result.

## 4 — Monte Carlo

**Edge (day-block bootstrap, 2,000 draws):**

| leg | research P(mean ≤ 0) | locked P(mean ≤ 0) |
| --- | --- | --- |
| 30m all hours | 0.006 | 0.065 |
| 30m 07–11 no flatten | 0.040 | 0.035 |
| **15m all hours** | **0.008** | **0.003** |
| 15m 07–11 + flatten (yours) | **0.314** | 0.047 |

**15m all hours is the only leg that excludes zero on both blocks.** Your configuration does not
exclude zero on research at all.

**Path (permutation, drawdown only):** p99 runs **1.2× to 3.5×** the realised drawdown on every leg.
30m all-hours locked sits at the **94th percentile** — that block's drawdown was unlucky, not
typical. Your 15m config's realised $388 sits at the 17th percentile with a p99 of $1,029.
**Size against the p99.**

**Execution:** P(total ≤ 0) = 0.000 on every leg with cost drawn 0.5×–2× and slippage 0–2×.

**Parameters (300 joint draws):** 100% of jittered neighbours are PF > 1 on every leg except yours
on research (86%). Your 15m config is the only one where **67% of neighbours beat the shipped
cell** — it is not sitting on a peak, it is sitting in a hole.

## 5 — Portfolio: the one real improvement, and its case is not return

Daily strategy returns in points, zero-filled on non-trading days:

| | 30m all hours | 30m 07–11 | 15m all hours | 15m yours |
| --- | --- | --- | --- | --- |
| 30m all hours | 1.00 | 0.69 | **0.36** | 0.21 |
| 15m all hours | 0.36 | 0.13 | 1.00 | 0.48 |

**0.36 between the two all-hours legs is genuinely low.** `STUDY_HYPO` found eight "different"
breakout hypotheses correlating 0.87–0.96, and `STUDY_TOP5` a two-market book at 0.90. This is not
that — the two timeframes fire at different moments.

| combination | block | $ | maxDD $ | ret/DD | Sharpe | PF |
| --- | --- | --- | --- | --- | --- | --- |
| 30m all hours | research | 7,482 | 746 | **10.02** | 1.40 | 1.865 |
| 30m all hours | locked | 5,417 | 2,393 | **2.26** | 1.29 | 1.706 |
| 15m all hours | research | 5,933 | 734 | 8.09 | 1.45 | 1.663 |
| 15m all hours | locked | 5,741 | 599 | **9.58** | 2.07 | 2.051 |
| **50/50 both all-hours legs** | research | 6,707 | **556** | **12.06** | **1.65** | 1.808 |
| **50/50 both all-hours legs** | locked | 5,579 | 921 | 6.06 | **2.00** | 1.924 |
| inverse-vol, all four legs | locked | 4,163 | 538 | 7.74 | 2.03 | **2.277** |

**The argument for the portfolio is regret, not return.** The best single leg on research (30m,
ret/DD 10.02) collapsed to **2.26** on locked; the best on locked (15m, 9.58) was second on
research. You cannot pick the winner in advance. The 50/50 was **first on research (12.06)** and
second on locked (6.06) — and it has the **lowest research drawdown of any arm** ($556 against $746
and $734) and the best research Sharpe. On a strict ret/DD test it loses to the best single leg out
of sample, and that is reported rather than hidden; on Sharpe and drawdown it wins or ties.

## What to change, in order

1. **Turn the flatten off.** Largest single improvement available, measured on both timeframes and
   both blocks. Keep the 07:00–11:00 window if you want fewer, cleaner trades — it is close to free.
2. **Set commission and slippage in Properties.** Everything on screen is currently gross.
3. **Run both timeframes at half size rather than choosing one.** 0.36 correlation, lower drawdown,
   and it removes the choice you cannot make in advance.
4. **Do not use the Optuna output.** Its research ranking is negatively correlated with the locked
   result across 2,400 trials, and both optima lose money out of sample.
5. **Size against the permutation p99, not the equity curve** — 1.2× to 3.5× the drawdown you see.

**Standing caveats:** one market (CVD needs 1-minute bars and NQ is the only feed here with them),
the CVD is a proxy, and the locked block has now been read repeatedly across the V61/V64 studies, so
its p-values are weaker than a first read.
