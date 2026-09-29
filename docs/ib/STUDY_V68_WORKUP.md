# The full workup on the best cell — it survives everything except its own search

`research/v68/`. Donchian 11/47, 3.8×ATR stop, 3.2×ATR target, 96-bar hold cap, RTH entries,
NQ 15m. Research 680 trades / locked 337. **The locked block was opened in
`STUDY_BAYESOPT_DONCHIAN`, so every locked figure here is a second read and descriptive.**

## Optuna — the population says more than the optimum

1,200 TPE trials over a continuous space, research block only, every trial's locked result computed
and **logged but never selected on**.

**98.2% of trials are research-profitable and 95.0% locked-profitable**, so the best cell is the
maximum of ~1,178 positive draws. `corr(research, locked)` reads **+0.34 Pearson**, which flatters —
`STUDY_V64_OPTUNA` recorded exactly this trap, that TPE concentrates in a narrow good region so the
correlation is computed over a restricted range with both ends positive. The finalist table is the
one that answers the question:

| | research | locked |
|---|---|---|
| top 1% by research | +0.1260 | **+0.0499** |
| top 100 by research | +0.1012 | +0.0631 |
| **whole population** | — | **+0.0717** |

**The top 1% of the research ranking transfers worse than the average trial.**

**fANOVA puts 64.3% of the objective on the take profit**, whose optimum lands at 11.21 of a
[0, 12] box — 93% of the range, effectively at the wall. `exN` 0.145, `stop` 0.087, `ent` 0.067,
`hold` 0.026, session 0.032 combined.

## The optimiser's dominant lever buys a ratio it cannot convert into money

The target tested directly, each setting against a matched random entry carrying **its own**
geometry (300 draws), locked block:

| tp | n | %/event | PF | control p | **total** |
|---|---|---|---|---|---|
| 1.5 | 458 | 0.0171 | 1.094 | 0.127 | 7.8 |
| 2.0 | 407 | 0.0436 | 1.217 | 0.027 | 17.7 |
| **3.2 (shipped)** | 337 | 0.0791 | 1.352 | **0.000** | **26.6** |
| 5.0 | 287 | 0.0992 | 1.405 | 0.010 | 28.5 |
| 8.0 | 250 | 0.1094 | 1.426 | 0.050 | 27.4 |
| none | 236 | 0.1134 | **1.444** | 0.063 | **26.8** |

PF rises monotonically toward no target and **total return does not move** — 26.6 with the target
against 26.8 without. No-target buys a higher ratio by trading 30% less, and on research the target
is ahead outright (41.9 vs 36.3). The control p-value also **degrades** as the target widens
(0.000 → 0.063) because the random entry improves alongside the rule: `STUDY_V56`'s finding reached
from the other side. **The shipped 3.2 stays**, and the optimiser's 64%-of-objective preference is
an artefact of optimising a total that a lower trade count can reach just as well.

## vectorbt — failed transcription, so no gap was read

**740 trades against the engine's 1,017, ratio 0.728.** Fourth failure of this check on this branch
(V46 gave 0.12–0.98, V53 gave 6 against 175). Two traps in 1.1.0 are why: `sl_stop` is a **fraction
of price** resolving against the bar **close** rather than the fill, and **`td_stop` does not exist**,
so the hold cap cannot be expressed at all. **No P&L gap is read in either direction.**

## Four Monte Carlos, and a perturbation that never happened

The first execution MC returned **p5 = p50 = p95 to the cent**. `sess_core.run` declares
`cost=COST, slip=SLIP`, and a Python default argument binds **once at definition time** — so
reassigning the module attribute before each draw did nothing and 300 "perturbed" runs were 300
identical runs. Fixed by forwarding explicitly; verified by moving the total 41.89 → 9.59 at 4×
cost. **A perturbation whose quantiles are all equal has not been run.**

| | research | locked |
|---|---|---|
| execution noise, P(total ≤ 0) | 0.000 | 0.000 |
| **day-block bootstrap, P(mean ≤ 0)** | **0.0010** | **0.0265** |
| bootstrap 95% CI | [+0.025, +0.099] | **[−0.0016, +0.173]** |
| permutation, DD percentile | 0.518 | 0.738 |
| **permutation p99 / realised** | **1.91×** | **1.57×** |
| price jitter, sign kept | 1.000 | 1.000 |

Execution is not the binding constraint — a 3.8 ATR stop is ~57 points against a 1.72-point round
turn, so doubling both cost and slippage leaves P(total ≤ 0) at zero. **The locked CI does not
cleanly exclude zero**, running from −0.0016 on 337 trades. Price jitter — every bar perturbed, the
bar repaired, and **the channels and ATR recomputed from the jittered bars** — keeps the sign in
100% of draws at 0.5, 1.0 and 2.0 ticks with the trade count moving 1,017 → 1,016. The p99 drawdown
is the sizing number, not the backtest figure.

## Walk-forward — the fixed constants win, and the random arm is why that means something

144 cells re-selected inside every quarterly fold, against the fixed cell and a **random cell** from
the same grid:

| arm | total | folds positive |
|---|---|---|
| **fixed** | **+38.86** | **8/8** |
| re-chosen each fold | +32.34 | 7/8 |
| random cell | +22.72 | 5/8 |

**Selecting from this family beats picking from it arbitrarily (32.3 vs 22.7); re-selecting every
fold does not beat never selecting (32.3 vs 38.9).** That is `STUDY_V64_WFO`'s distinction, and the
random arm is what makes it visible — without it, fold 2 (+3.65 vs +2.62) reads as evidence for
re-selection when a random cell earned +6.93 that quarter.

**What the optimiser agrees on is more informative than what it picks.** Stop **3.8 in 8 of 8
folds**; entry 11 in 6 of 8; exit channel wanders 47 → 65 → 25 → 65 → 47 → 65 → 65 → 65 and target
3.2 → 5.0 → none → 5.0 → none → 3.2 → 3.2 → 3.2. The axes it settles on are the shipped values; the
axes it doesn't settle on are the ones with no information in them.

## Deflation — this is where it fails

* **Deflated Sharpe 0.688 — FAIL.** Per-observation Sharpe **0.1319** against an expected
  best-of-noise of **0.1131**, over **1,224 counted looks** (effective N 367.9 at ρ̄ 0.7), with
  `var_trials` **0.001461 measured over the 1,200 trial Sharpes**.
* **White's reality check p = 0.068 — FAIL.** Best candidate mean 0.0745 against a null max p95 of
  0.0782 across 60 candidates × 478 observations.

The cell's own edge is barely above the noise floor of the search that examined it.

## Verdict

It passes everything that asks whether the *result* is fragile — execution, path, price noise,
parameter neighbourhood (100% profitable over 15 cells), and a walk-forward it wins 8/8. It fails
the two tests that ask whether the *search* produced it, and its locked confidence interval does
not exclude zero.

That is a coherent, unexciting picture: a real but small edge, roughly the size of what 1,224 looks
at this family would throw up by chance. Nothing here justifies raising size, and nothing here
justifies abandoning it either. **The single actionable number is the p99 drawdown at 1.9× the
realised one** — size against that, not against the backtest.

What would change the verdict is not more searching, which is what the DSR is objecting to. It is
more out-of-sample events: a second market, or forward trades.
