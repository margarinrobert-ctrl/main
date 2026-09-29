# Six mathematical estimators as a meta layer on a Donchian + EMA trend primary, US30

`research/mathmodels/`. `US30_LONG_15m` only, resampled to 15/30/60m. Percent of entry price,
2.29-point round turn, both sides, one unit.

## What is new here

Everything on this branch so far has been a **pattern** — a channel, a crossover, a divergence — or a
feature pool built from those, and the standing verdict is `STUDY_FEATURES`: *features do not predict
here; the harness is the asset*. What had never been run is a set of **parameters of a stochastic
process**, where the reading is the implication of an estimated quantity rather than a fitted
threshold on a transform of price.

| estimator | what it estimates |
|---|---|
| **OU** | Ornstein–Uhlenbeck MLE: κ, half-life, equilibrium z-score |
| **DFA** | detrended fluctuation analysis: the Hurst exponent of the increments |
| **VR** | Lo–MacKinlay variance ratio VR(q) and its heteroskedasticity-robust z |
| **BNS** | Barndorff-Nielsen–Shephard bipower variation: the **jump** share of realised variance |
| **PE** | Bandt–Pompe permutation entropy |
| **KF** | Kalman local-level-plus-slope, filtered only, as a slope **t-statistic** |

## The positive controls found three bugs before any result

Each estimator is handed a simulated process with a known answer and must return it.

| test | truth | recovered |
|---|---|---|
| OU half-life | 20.0 / 60.0 | 20.32 / 52.18 (the known small-sample downward bias of the discrete AR(1) fit) |
| OU equilibrium z | sd 1.000 | 1.004 / 0.998 |
| DFA H, white noise | 0.500 | 0.4948 |
| DFA H, AR(1) φ=+0.5 | > white noise | 0.6488 |
| VR(4), martingale | 1.000 | 1.0059, rejecting at **6.3%** against a nominal 5% |
| VR(4), AR(1) φ=−0.3 | < 1 | 0.6201 |
| BNS jump share | 0.000 | 0.0004; **0.131** with jumps injected |
| permutation entropy | 1 noise / 0 ramp | 0.9936 / 0.0000 |
| Kalman slope | 0.0100 | 0.0100 |

Three things were wrong and the controls are the only reason they were found:

1. **The Lo–MacKinlay z was √n too small.** The robust denominator used `(Σd²/n)²·n` where the
   paper's is `(Σd²)²`, so θ was n times too large. At n = 1000 the statistic rejected on a
   martingale **0.000%** of the time. *A test that never fires looks like a quiet indicator, not a
   broken one* — nothing downstream would have flagged it.
2. **The BNS statistic divided by n twice** and floored the quarticity ratio at 1/n instead of 1,
   giving `bns.z` a mean of 35.8. Now 2.07.
3. **The Kalman leaked.** Its observation variance was `np.nanvar` over the *whole* series — a
   full-sample constant. The truncation audit read **8 of 8 probes failing**; with an expanding
   estimate it reads **0 of 80**.

## What the estimators say about US30 30m, before any strategy

| state | median | reading |
|---|---|---|
| `dfa.H` | 0.4957 | increments are a random walk to three decimals |
| `vr.ratio` | 0.9912 (z mean −0.085) | mildly **mean-reverting**, consistent with this branch's twelve independent routes to that conclusion |
| `bns.share` | 0.1103 | **11% of realised variance is jump**, not diffusion |
| `pe.h` | 0.9324 | near-maximal disorder in the ordinal patterns |
| `ou.halflife` | 78 bars | ≈ 39 hours where a mean-reverting fit exists at all |

## Gate 1 — the primary alone. FAIL

54 declared cells: entry 20/30/55 × EMA off/50/200 as a state × stop 2.0/2.5 ATR × 15/30/60m, exit
the opposite 20-bar channel or the stop, no target. 74.1% profitable. Marginals: **60m +0.0207**
(15m +0.0053, 30m −0.0002), **EMA200 +0.0163** against off +0.0046 — the EMA earns its place — and
entry 30 best.

Best cell **60m Donchian 30/20, EMA200 state, 2.0N**: research 666 trades, +0.0429 %/trade, PF 1.122.
Against a risk-matched random entry: **p 0.167**, and the two runners-up 0.227 / 0.263. Median hold
1,200 minutes, so it is a swing system.

**Gate 1 is not cleared.** The architecture's one declared exception applies: a primary with no
*unconditional* edge may still carry a *conditional* one, testable when the conditioning variables
were written down first. These six were — implemented and validated before any strategy was touched.
Everything below is therefore a conditional-edge claim carrying that caveat.

## Gate 2 — research passes, and the holdout does not confirm it

Ten states, two near-duplicates removed on the signal bars (`vr.ratio ≡ vr.z` at ρ 0.958,
`bns.share ≡ bns.z` at 0.959 — **eighth** pool-duplication catch here), leaving eight. Purged
embargoed CV, objective = the percent earned, every model beside a shuffled twin.

Ladder OOF IC: ridge +0.0490, rf +0.0710, **lgbm +0.0994**; twins −0.0321 / −0.0168 / +0.0129.
**Twin wins 0 of 3.**

| | n | %/trade | PF | total | p90 | control | p | P(mean≤0) |
|---|---|---|---|---|---|---|---|---|
| research base | 666 | +0.0429 | 1.122 | +28.59 | 1.449 | — | — | 0.174 |
| research kept 30% | 200 | **+0.2196** | **1.701** | +43.92 | 2.080 | 0.0438 | **0.003** | 0.005 |
| HOLDOUT base | 222 | +0.0212 | 1.065 | +4.70 | 1.190 | — | — | 0.370 |
| HOLDOUT kept | 91 | **+0.1028** | **1.334** | **+9.35** | 1.533 | 0.0258 | **0.158** | 0.188 |

Three things are the right shape and one is not. It **decays** across the split (research 0.2196 →
holdout 0.1028); **p90 of R rises** 1.190 → 1.533 so the tail survives, unlike `STUDY_V32`'s
win-rate mechanism; and it **doubles total return while keeping 41% of the trades** (4.70 → 9.35),
which almost no filter on this branch does. But it clears nothing: **p 0.158** against a random gate
of the same size, calibration drifts (kept 0.410 against the 0.30 it was set for), and the
**deflated Sharpe is 0.471 at 80 counted looks — per-trade Sharpe 0.0929 against an expected
best-of-noise of 0.0996, i.e. below the noise floor of its own search.**

## The drop-one picked the wrong subset, which is worth more than the result

On research, three states carry the model — `kf.t` (−0.0252 IC when removed), `vr.ratio` (−0.0246),
`dfa.H` (−0.0236) — and `ou.z`, `ou.kappa`, `pe.h` all **improve** it when dropped. That is a
coherent story: all three that carry are **persistence** estimators and the primary is a trend
follower, while the two mean-reversion states subtract. Tested directly:

| model | research | holdout |
|---|---|---|
| ridge on the 3 | +0.1737, PF 1.560, p 0.037 | +0.0174, PF 1.054, p 0.453, **IC −0.0122** |
| lgbm on the 3 | +0.0639, PF 1.208, p 0.345 | **−0.0345, PF 0.894**, p 0.762 |

**Both are worse out of sample than the eight-state model the ablation said to trim.** That inverts
`STUDY_V66`, where the ablation-selected subset beat the full set at t +17.08. Neither lean model is
calibrated either (kept 0.21 and 0.39 against 0.30). So the ablation is a research-block statistic
like any other, and using it to choose a feature set is one more selection to deflate for.

The ridge's `vr.ratio` coefficient is **+0.0165 against a univariate IC of −0.0242** — sign-flipped,
multicollinearity exploited conditionally, and the least stable part of any linear meta model.

## Verdict

**Nothing ships.** Gate 1 fails at p 0.167; the best Gate 2 cell reads p 0.158 out of sample with a
deflated Sharpe below its own noise floor; and the obvious lean variant is worse. What the study
does leave behind is a validated estimator library with positive controls and a clean truncation
audit, a diagnostic table of what US30 30m actually is as a process, and one methodological result —
a research drop-one can select a strictly worse feature set, so it is a hypothesis about which
features matter, not a decision procedure.

What would move it: more events. 91 holdout events cannot separate a +0.08 %/trade uplift from a
random gate, and the fix for that is not more estimators or more capacity — both were swept here.
