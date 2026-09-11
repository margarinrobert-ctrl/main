# V33 — the full optimisation pipeline: Sharpe and profit factor, win rate ignored

**Brief.** Optimise for risk-adjusted performance and profit factor, not net profit and not win
rate. Grid → random → Bayesian, walk-forward, regime testing, Monte Carlo, cost stress, deflated
performance, and a final untouched out-of-sample read.

**Verdict.** One candidate survives everything except statistics. **US30 long: out-of-sample Sharpe
+1.13, profit factor 1.412, 124 trades, drawdown 10.5 R** — against an unoptimised baseline of +0.33
/ 1.118. It clears parameter perturbation, cost stress to 3×, and both post-selection walk-forward
folds. It then **fails the deflated Sharpe at 0.0016 — and it still fails at 0.8101 if you assume
only ONE trial was ever run.** The multiplicity correction is not what kills it. The underlying
statistic was never significant. **Overfitting risk: HIGH. Robustness score 54.9/100. Ship nothing.**

---

## 1. Inspection and parameter classification

Strategy: Donchian channel breakout, opposite-channel exit, ATR stop, one unit, market order at the
next bar's open, optional CHOP regime gate.

| class | parameter | optimised |
| --- | --- | --- |
| entry | `entry_n` Donchian lookback | yes |
| exit | `exit_n` opposite-channel lookback | yes |
| stop | `stop_mult` ATR multiple | yes |
| take profit | `tp_r` R multiple, 0 = none | yes |
| regime | `chop_max`, `adx_min` | yes |
| volatility | `vol_policy` (V22's adaptive stop) | yes |
| session | entry window, New York minutes | yes |
| indicator | `atr_len` | fixed at 14 after the coarse pass |
| timeframe | 15 / 30 / 60m | yes |
| direction | long / short | optimised separately |

**Not optimised, and why.** Position size — fixed one unit; sizing creates no edge here and a ladder
is what generates the drawdown. Cost model — a measured input, not a free parameter; sweeping it
would be fitting the broker, so it is *stressed* instead. Entry mechanic — a resting limit is a
different strategy and cannot be settled on bar data.

**Leakage audit, run before the first fit.** Channels exclude the current bar; every filter is read
at the signal bar and never at the entry bar; ATR ends at the signal bar; entry fills at the next
open; a stop resolves before a target inside one bar (the pessimistic tie-break); nothing is
centred, `filtfilt`-ed or smoothed backwards; no universe selection, so no survivorship; the engine
can only fill a market order at an open and barriers inside a bar's range, so no unrealistic fill is
reachable. **Degrees of freedom: ten axes, 51,840 configurations per side per market, 207,360 in
total — a number carried into the deflated Sharpe rather than mentioned once and dropped.**

## 2. Baseline (unmodified, 30m Donchian 30/20, 2.0N, no target, CHOP ≤ 40, long)

| block | n | net R | PF | Sharpe | Sortino | Max DD | ret/DD | Calmar | win |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| US30 train | 513 | +120.2 | 1.420 | +1.01 | +2.96 | 20.6 | 5.82 | 0.90 | 0.357 |
| US30 valid | 177 | −19.5 | **0.823** | **−0.66** | −1.52 | 26.9 | −0.72 | −0.34 | 0.299 |
| US30 **oos** | 205 | +14.6 | 1.118 | +0.33 | +1.13 | 24.7 | 0.59 | 0.28 | 0.351 |
| NQ train | 224 | — | 1.129 | +0.42 | +1.20 | 12.1 | 1.39 | 0.64 | 0.371 |
| NQ valid | 61 | — | 2.073 | +2.03 | +6.74 | 11.6 | 2.47 | 3.44 | 0.475 |
| NQ **oos** | 78 | −1.0 | **0.976** | **−0.10** | −0.20 | 10.8 | −0.09 | −0.12 | 0.423 |

The shipped configuration is negative on NQ's final 20% and negative on US30's validation block.
That is the thing being improved on.

## 3. Data and method

60% train / 20% validation / 20% out-of-sample, chronological, never shuffled. Train scores every
configuration; validation chooses among the survivors; **out-of-sample is opened by exactly one
function, once, after the candidate is frozen.**

*One caveat that no split can fix:* this branch has read NQ's final block many times across V16–V32.
The OOS here is unseen by *this optimiser*, not unseen by *this project*. US30's is cleaner and has
4× the history, which is why US30 leads the report.

Objective, as specified:
`0.35 × Sharpe + 0.30 × PF + 0.20 × Return/DD + 0.15 × Robustness`, all bounded-normalised, with
multiplicative penalties for a thin trade count, a poor return/drawdown and profit concentrated in
the top 1% of trades. **Robustness is inside the objective** — the share of the immediate parameter
neighbourhood that also earns PF > 1 and Sharpe > 0 — so a spike with a dead neighbourhood is scored
down before it can reach validation.

**Two defects in the first objective, found and fixed before any OOS read.** Normalising against
2.0 / 1.8 / 3.0 made the score **saturate at exactly 1.000 across hundreds of NQ configurations**,
destroying the ordering where it matters; widened to 3.0 / 2.5 / 5.0, after which zero cells
saturate. And an absolute trade floor of 60 admitted 60-minute configurations with 67 training
trades that produce **zero validation trades** — infeasible as candidates whatever they score;
replaced by a floor on trades per year. Both changes are structural (a saturated score cannot rank;
an infeasible configuration cannot be a candidate), not choices about which configuration wins.

## 4. What the grid looks like before its top row is read

| cell | scorable | PF > 1 on train | median PF | best PF |
| --- | --- | --- | --- | --- |
| US30 long | 30,003 | **62.1%** | 1.078 | 2.258 |
| US30 short | 51,840 | **2.2%** | 0.853 | 1.193 |
| NQ long | 27,024 | **72.5%** | 1.103 | 3.615 |
| NQ short | 51,840 | **16.0%** | 0.884 | 1.631 |

Longs are broadly profitable and shorts are broadly not — on a sample where both indices rose. The
best long PF of 3.615 is the maximum of 27,024 draws from a population that is 72.5% profitable.

**And the ranking does not transfer. Train → validation Sharpe rank correlation is NEGATIVE in all
four cells: −0.181, −0.330, −0.050, −0.375.** Knowing which configuration ranked best on train is
worse than useless for predicting validation. This reproduces V30's surrogate finding on a different
search method.

## 5. The optimised candidate

**US30 long — 60m, Donchian 40/20, adaptive stop 2.5N/1.5N by volatility percentile, 2R target,
CHOP ≤ 45, entries 09:30–16:00 New York.** Chosen as the **centre of the top-20 surviving region**,
not its top row.

| block | n | net R | PF | Sharpe | Sortino | Max DD | ret/DD | Calmar | win |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| train | 286 | +26.8 | 1.191 | +0.50 | +0.77 | 16.4 | 1.63 | 0.25 | 0.395 |
| valid | 103 | +6.9 | 1.136 | +0.38 | +0.64 | 6.8 | 1.00 | 0.47 | 0.388 |
| **oos** | **124** | **+23.9** | **1.412** | **+1.13** | +1.88 | **10.5** | 2.28 | 1.06 | 0.411 |

OOS bootstrap: R/trade +0.1928 [+0.0082, +0.3700], P(R ≤ 0) **0.043**. Against the baseline's OOS
+0.33 / 1.118, the optimiser roughly tripled Sharpe and halved drawdown.

## 6. Robustness

**Perturbation** (validation, whole ladder): stability **1.000** — every rung of every informative
axis keeps PF > 1 and Sharpe > 0. **Two of six axes are inert and are excluded**: `stop` does
nothing whenever `vol_policy` is on (the policy supplies its own two stops), and `adx_min` empties
the sample at 60 minutes. Counting a flat line as four passing rungs is how a stability score
reaches 1.000 without measuring anything.

**Regimes** (validation, signal bars split then re-simulated): 5 of 6 scorable regimes PF > 1. But
**LOW volatility percentile is negative — PF 0.777, Sharpe −0.55** — against HIGH vol at 1.492 /
+0.86. The candidate carries V22's adaptive stop, whose whole premise is that heat is larger in the
low-vol bucket, and this is where it loses. Bear regime has 22 trades, unscorable.

**Walk-forward**, 6 rolling folds: PF > 1 in 5 of 6, and in **both** post-selection folds (1.398 /
+1.05 and 1.297 / +0.83). Fold 4, 2021-03 → 2022-08, is negative in both passes — the bear market.

**Monte Carlo** (train+valid): bootstrap whole days with trades attached — R/trade +0.0865
[−0.0175, +0.1865], P(R ≤ 0) 0.083. Permutation of the realised order — drawdown realised 16.8 R,
MC p50 16.8, p95 27.0, **p99 31.4. Size for the p99.**

**Cost stress**: PF 1.136 → 1.120 → 1.105 → 1.075 → **1.019** at 1.0× / 1.25× / 1.5× / 2× / 3×;
Sharpe +0.38 → +0.06. Positive throughout but the margin is gone by 3×.

## 7. Deflated performance — the test it fails

Observed Sharpe on train+valid: **+0.471** over 2,138 days, 389 trades, skew +1.976, kurtosis 11.29.

| assumed independent trials | Sharpe the null produces | deflated probability |
| --- | --- | --- |
| **1** | +0.178 | **0.8101** |
| 20 | +0.653 | 0.2936 |
| 100 | +0.869 | 0.1168 |
| **576** (distinct price walks) | +1.063 | 0.0382 |
| **51,840** (raw configurations) | **+1.458** | **0.0016** |

At the raw configuration count the null's expected *maximum* Sharpe is +1.458 and we observed
+0.471 — the search would beat this result by chance. But the row that settles it is the first:
**even at N = 1, with no multiplicity at all, the probability is 0.81, well short of 0.95.** The
statistic is not significant before any correction is applied. Positive skew and fat tails make it
worse, and both are real properties of a trend follower's return distribution.

## 8. Overfitting assessment

| | |
| --- | --- |
| Generalization gap (OOS − mean of train and valid) | Sharpe **+0.690**, PF **+0.249** |
| Parameter sensitivity | low — full plateau on all four informative axes |
| Train → validation rank transfer | **negative in all four cells** |
| Configurations tested | **207,360** |
| Deflated Sharpe | 0.0016 (0.8101 even at N=1) |
| **Overall overfitting risk** | **HIGH** |

The gap is *positive*: the candidate is **better out of sample than in sample**. This branch treats
that as a defect, not a result — it has now been seen five times, and it means the OOS block simply
suited the rule. A candidate whose evidence is that it did unexpectedly well on the one block it was
not fitted to has no mechanism behind it.

## 9. Final ranking, by generalisation

| market | side | OOS Sharpe | OOS PF | OOS n | OOS DD | stability | walk-fwd | regime | cost | gap | DSR | **score** |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| US30 | LONG | **+1.13** | **1.412** | 124 | 10.5 | 1.00 | 0.83 | 0.83 | 1.00 | +0.69 | 0.002 | **54.9** |
| NQ | LONG | −0.21 | 0.937 | 47 | 5.3 | 0.84 | 0.67 | 0.50 | 0.67 | −1.44 | 0.097 | 26.8 |
| US30 | SHORT | −0.51 | 0.839 | 112 | 12.9 | 0.00 | 0.33 | 0.20 | 0.00 | −0.17 | 0.000 | 9.5 |
| NQ | SHORT | — | — | — | — | — | — | — | — | — | — | **0.0** — no candidate cleared validation |

Score weights: OOS Sharpe 20, OOS PF 15, walk-forward 15, parameter stability 15, regime 10, Monte
Carlo 10, cost 10, generalization gap 10, with a ×0.60 cap when the deflated Sharpe fails. **Net
profit is not in the score at all.**

## 10. Verdict

**Ship nothing.** The pipeline did what it was asked: it found a configuration that improves
out-of-sample Sharpe from +0.33 to +1.13 and profit factor from 1.118 to 1.412 while halving
drawdown, and it did so without ever fitting on the block it was measured on. Every robustness test
except one comes back clean.

The one it fails is the one that matters most, and it fails it twice over: **the result is not
statistically distinguishable from a lucky draw even under the most generous possible assumption
about how much searching was done**, and its in-sample performance is *worse* than its
out-of-sample, which is the signature of a block that suited a rule rather than a rule that captured
something.

What is worth keeping is the negative rank transfer — **train → validation Sharpe correlation of
−0.05 to −0.375 across 207,360 configurations**. Combined with V30's surrogate result (research
surface fitted at ρ 0.96, locked predicted at ρ 0.07) and V31's cross-family result (research →
locked R correlation +0.215), this branch has now measured the same thing three ways with three
methods: **on this data, in-sample ranking carries no information about out-of-sample ranking.**
That is the constraint any future optimisation has to work around, and no amount of search
sophistication addresses it.

Reproduce: `python3 research/v33/run_grid.py`, then `run_final.py`, then `dsr_sweep.py`.
Raw output: `docs/ib/v33_pipeline_output.txt`, `docs/ib/v33_dsr_sweep.txt`. Trials:
`research/v33/trials/`.
