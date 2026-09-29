# AutoBNN on the Donchian 55/30 cell: a forecaster gate and a Bayesian meta-label

`research/inst/autobnn.py`, `research/inst/run_autobnn.py`, `results/inst/autobnn.txt`. Google's
AutoBNN (compositional Bayesian neural networks standing in for the Automatic Statistician's
Gaussian-process kernels; TensorFlow Probability, 2024) rebuilt in torch because the reference
package needs the full TensorFlow stack: leaf components for linear, periodic, RBF and Matern
structure, combined by sum, product and changepoint; an ELBO-scored structure search over a small
grammar; mean-field variational inference with a learned noise scale; a sampled posterior
predictive so every forecast carries a standard deviation. **Positive control** on a trend plus an
8-cycle sine with noise sd 0.10: it selects `linear+periodic` and forecasts the held-out tail at
RMSE 0.099 — the noise floor — with a mean predictive sd of 0.109. The machinery is sound.

Applied to the user's Edge Finder cell — NQ 15m, RTH entries, Donchian 55 entry / 30 exit,
1.5 ATR adaptive stop, no target, swing hold, MA200 floor ≥ 2 ATR, CHOP ≤ 40 — reproduced first:
research 192 trades PF 2.495 (%) / locked 105 trades PF 1.916.

## Verdict

**AutoBNN adds nothing to this cell.** As a forecaster it is negatively informed on the bars the
strategy fires on and every gate built from it is worse than a random filter; as a Bayesian
meta-labeler its out-of-fold information coefficient equals its shuffled twin's, and the one
pre-declared locked read was a no-op because the posterior means did not transfer across the
split. Nothing here changes the shipped cell, and a BNN is not expressible in Pine in any case.

## Arm A — the forecaster as an entry gate

At each of the 960 pre-lock signal bars, AutoBNN is fitted to the previous 200 bars of log close
(period 26 bars = one RTH session) and asked for the log close 26 bars ahead. Structure searched
once per sequential fold on its first window; that structure refitted at every signal bar. Gate:
keep the signal if Φ(μ/σ) ≥ q.

The chosen structures rotate across folds (`linear*periodic+rbf`, `rbf`, `sum-of-products`,
`changepoint`, `changepoint`, `rbf`) — a grammar with no stable answer. On the research signal
bars the forecast's IC against the realised 26-bar move is **−0.070** (Spearman −0.095) and its
mean P(up) is **0.242**: the smooth components read a breakout bar as an excursion to revert,
which is the same thing every momentum reading on this branch has said from the other side.

| gate | keeps | research | random filter, same selectivity | shuffled gate |
|---|---|---|---|---|
| base | 100% | 192 trades, PF 2.495 | — | — |
| P(up) ≥ 0.50 | 19% | 57, PF 1.296 | median 1.946, **p 0.935** | 2.431 |
| P(up) ≥ 0.55 | 18% | 53, PF 1.484 | 1.876, p 0.770 | 1.180 |
| P(up) ≥ 0.60 | 15% | 46, PF 1.034 | 1.931, **p 0.970** | 0.946 |
| P(up) ≥ 0.70 | 12% | 38, PF 0.912 | 1.816, p 0.950 | 2.868 |

Every rung is worse than the base and worse than a random filter of the same selectivity; the
shuffled gate matches or beats it. **Locked, pre-declared (q = 0.60): base PF 1.916 → gated 1.416
on 19 trades.**

## Arm B — the Bayesian meta-label

Eight causal features at the signal bar (MA200 distance, CHOP, volatility percentile, ATR/price,
log returns over 1/4/16/64 bars) → the trade's R, with a shuffled-label twin trained on the same
folds. Purged sequential folds: training trades' exits precede the test fold's first signal.
Structures chosen: `rbf`, `matern`, `rbf`, `matern`, `linear`.

**OOF IC +0.071 against the shuffled twin's +0.068.** Whatever the model learned, a random
labelling learned the same amount.

| rule | research kept | random subset, same size | shuffled twin |
|---|---|---|---|
| base (scored trades) | 160, PF 2.700 | — | — |
| keep top 70% by posterior mean | 112, PF 3.583 | median 2.750, **p 0.023** | PF 2.798 |
| keep top 50% | 80, PF 3.557 | 2.650, p 0.137 | 1.559 |
| keep top 30% | 48, PF 2.979 | 2.641, p 0.393 | 1.692 |
| keep "confident" (μ − σ > 0) | **2** | — | 25 |
| keep posterior mean > 0 | 58, PF 2.932 | 2.599, p 0.377 | 2.236 |

One rung of five clears its null (keep-70, p 0.023), with its twin a whisker behind; the
"confident" rule — the thing a Bayesian model is supposed to buy — keeps two trades, because the
posterior sd exceeds the posterior mean on nearly every trade: the model knows it does not know.

**Locked, pre-declared (fit on all research trades, keep top 50% by posterior mean at the research
cut): kept 105 of 105.** Every locked posterior mean sat above the research-block median, so the
threshold filtered nothing — the posterior means shifted between blocks (locked IC +0.088, no
better than research). A read that cannot select is a null read, and it is also the finding: the
model's outputs are not calibrated across the split, so no threshold chosen on research means the
same thing out of sample.

## What to carry

- A structure grammar that picks a different composition in every fold has found the noise, not
  the series. On the positive control it settles at once.
- The forecaster's negative IC on breakout bars is the twelfth route to the same mean-reversion
  reading on this branch: smooth priors want an excursion to come back, and a breakout is an
  excursion.
- Bayesian uncertainty was honest and useless — the "confident" set is empty because nothing is
  confidently predictable here, which is the correct answer delivered in an unhelpful form.
- The cell stands as measured. The model is not in the script and could not be.
