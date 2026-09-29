# PIN, estimated the Bayesian way — the estimator was the problem, and fixing it made the answer worse

Griffin, Oberoi & Oduro (2018, SSRN 3305086), *Estimating The Probability Of Informed Trading: A
Bayesian Approach*, applied to the same NQ 10-minute event stream as `STUDY_PIN.md`.

## Why this paper was worth running

`STUDY_PIN.md` estimated the EKOP/EHO mixture with Yan (2009)'s four-step moment estimator and got
PIN = 0.014 on NQ against the equity literature's 0.10–0.20, and read that as the mechanism being
absent on an index future. This paper says something different and directly on point:

1. **MLE-based PIN is biased**, and the bias is worst "in the case of liquid and frequently traded
   assets" — an index future is the extreme of that case. So a low PIN on NQ may be the estimator,
   not the market.
2. **Yan's step 1 has to go.** It labels event periods with an event study over the whole sample,
   which is two-sided; `pin_core` replaced it with "a period whose return exceeds `evK` trailing
   standard deviations", an ad hoc rule carrying a free parameter that had to be chosen. The Gibbs
   sampler infers `D_t` as a **latent variable** instead. That is a strict reduction in free
   parameters on the primary, which is what the mechanism-first architecture actually cares about.
3. **It licenses the intraday application.** The paper explicitly generalises to "the type of news
   is fixed over intervals at other frequencies, for example over a 15 minute interval", and claims
   reliable estimation from as few as 26 observations.

All three are reasons to expect the earlier verdict to change. It did change — in the sense that
PIN moved into the literature's band — and the reason it moved is the finding.

## The estimator, and its positive control

`research/pin/pin_bayes.py` implements their section 3.4: data augmentation on the informed part of
each count (`S^i | S_t ~ Bin(S_t, μ/(μ+λ_s))`), conjugate Beta/Gamma full conditionals (5a)–(5e),
and a multinomial resample of `D_t` from the log-sum-exp of their L1/L2/L3.

Checked against a **known answer drawn from the model itself** before being pointed at NQ:

| T | α (true 0.35) | δ (0.45) | μ (40) | λ_b (60) | λ_s (55) | PIN (0.1085) | 90% CI |
|---|---|---|---|---|---|---|---|
| 60 | 0.371 | 0.425 | 34.2 | 61.1 | 54.2 | 0.0987 | [0.0716, 0.1246] |
| 120 | 0.335 | 0.504 | 38.1 | 59.5 | 55.7 | 0.0996 | [0.0797, 0.1197] |
| 400 | 0.350 | 0.455 | 41.0 | 59.8 | 55.0 | 0.1112 | [0.0994, 0.1236] |

The credible interval covers the truth at every sample size, and the paper's claim that ~26–60
periods suffice is supported. Four chains from deliberately hostile starts (μ from 5 to 150, α from
0.1 to 0.9) give **Gelman-Rubin R-hat 0.9999–1.0024** on every parameter — the sampler converges and
nothing below is an artefact of a bad chain.

**One published conditional is wrong and is not reproduced.** Their equation (5b) reads
`δ ~ Be(ν + T1 + T2, T2 + τ)`. δ is P(bad | news), so its Beta counts bad against good and the first
shape must be `T1`, not `T1 + T2` — the `T1 + T2` is copied from the α line (5a) directly above,
where it is correct because α counts news against no-news. Demonstrated rather than asserted: on
simulated data with a true δ of 0.30, the corrected form returns **0.293** and the published form
returns **0.589**.

## What it does to NQ

Same bars, same volume-weighted B and S, same rolling 120-session window, same posterior decision
rule, same geometry and costs. **Only the estimator differs**, so anything that moves is the
estimator. 735 sessions fitted both ways:

| parameter | Yan | Bayes | corr |
|---|---|---|---|
| α | 0.2750 | 0.5742 | 0.477 |
| δ | 0.5156 | **0.9303** | −0.009 |
| μ | 18.56 | 94.58 | −0.108 |
| λ_b | 181.76 | 187.68 | 0.976 |
| λ_s | 177.95 | 129.71 | 0.112 |
| **PIN** | **0.0142** | **0.1554** | 0.051 |
| μ/(λ_b+λ_s) | 0.0519 | 0.3253 | −0.178 |

PIN lands in the literature's 0.10–0.20 band, exactly as the paper predicts for a liquid asset, and
the informed-to-uninformed ratio rises six-fold, so the posterior can now actually move off its
prior — the constraint that made the count-based version untradeable in `STUDY_PIN.md`.

The two estimators agree only on λ_b (corr 0.976) and agree on **nothing else** — δ correlates
−0.009 and PIN 0.051 across the same 735 windows. That alone should stop anyone quoting a PIN
without naming the estimator.

## And δ = 0.93 is the tell

The fitted model says **93% of news events are bad news**, on a sample where the index rose 89%.
That cannot be an information reading. Three diagnostics say what it is instead.

**1. The data are not Poisson.** A Poisson has variance equal to its mean:

| construction | mean B | var/mean B | mean S | var/mean S |
|---|---|---|---|---|
| bar counts (EKOP's own unit) | 191.7 | 2.46 | 184.4 | 2.42 |
| volume-weighted | 190.2 | **14.65** | 188.0 | **18.89** |

The model's *only* way to explain a spread wider than a Poisson allows is to invent an informed
component, because μ is the sole parameter that adds variance without adding mean symmetrically.
Nothing in the estimator distinguishes "informed traders arrived" from "this series is more variable
than a Poisson". And note which way δ leans: S is the more overdispersed of the two series (18.89
against 14.65), so the model puts the big μ on the sell side. **δ = 0.93 is reporting which series
is noisier, not which way the news went.**

**2. The fitted model still cannot reproduce the spread.** Posterior predictive, 400 replications:

| construction | | observed | model | ratio |
|---|---|---|---|---|
| bar counts | sd(B) | 19.6 | 15.6 | 1.25 |
| | sd(S) | 20.6 | 24.7 | 0.84 |
| volume-weighted | sd(B) | 48.5 | 15.0 | **3.24** |
| | sd(S) | 60.1 | 43.6 | 1.38 |

With the informed component maxed out (μ 84.8, δ 0.979) the model produces sd(B) = 15.0 against an
observed 48.5. The informed component is being used entirely as a variance sponge **and still falls
three-fold short**.

**3. The placebo settles it.** Fit the same estimator to deliberately information-free data —
negative binomial, B and S drawn **independently**, no news process in it at all — with the same
mean and a sweep of dispersion:

| target var/mean | PIN | α | δ | μ | μ/(λ_b+λ_s) |
|---|---|---|---|---|---|
| 1.0 | 0.0162 | 0.805 | 0.377 | 7.2 | 0.0194 |
| 2.0 | 0.0368 | 0.575 | 0.347 | 24.3 | 0.0667 |
| 5.0 | 0.0731 | 0.581 | 0.391 | 47.4 | 0.1358 |
| 10.0 | 0.1066 | 0.632 | 0.383 | 63.7 | 0.1890 |
| 20.0 | 0.1487 | 0.603 | 0.392 | 92.0 | 0.2894 |

NQ's volume-weighted series run var/mean 14.65 and 18.89, which this table maps to a PIN of roughly
**0.11–0.15**. Measured: **0.1554**. **The PIN this paper's estimator returns on NQ is what it
returns on data with no information in it whatsoever, at the same dispersion.** PIN here is a
dispersion statistic wearing a probability's name.

That is not a criticism of the sampler, which is correct and converges cleanly. It is a statement
about the EHO **model**: the Poisson likelihood has no way to separate information from
overdispersion, and a better estimator of a misspecified model estimates the misspecification
better. Duarte & Young (2009) and Gan, Wei & Johnstone (2017) — both cited in the paper — make this
argument; the placebo is the version of it that needs no theory.

## Gate 1 — and the better estimator produces the worse strategy

Two primaries, scored on the **research block only**, before any feature exists, against a matched
random entry (same window, same rate, same side mix, same exits, sorted so the position lock rejects
the same way):

* **session** — B1's construction: parameters from 120 prior sessions of daily B/S, signal is the
  posterior given the flow accumulated so far today.
* **interval** — the paper's own generalisation: news type fixed over 10-minute periods, parameters
  from the previous five sessions' worth of periods, signal is the posterior for the current period
  from that period's own flow.

| build | thresh | n | pts | PF | win% | ctl med | excess | p |
|---|---|---|---|---|---|---|---|---|
| session | 0.50 | 1125 | −1.02 | 0.968 | 49.1% | +0.81 | −1.83 | 0.780 |
| session | 0.70 | 1078 | −0.48 | 0.985 | 49.7% | +0.77 | −1.26 | 0.700 |
| session | 0.85 | 1023 | −0.53 | 0.983 | 49.6% | +0.90 | −1.43 | 0.705 |
| session | 0.95 | 950 | −1.07 | 0.966 | 49.5% | +0.86 | −1.93 | 0.765 |
| interval | 0.50 | 1031 | −4.08 | 0.871 | 47.1% | −0.87 | −3.22 | 0.865 |
| interval | 0.70 | 965 | −3.12 | 0.901 | 47.4% | −1.14 | −1.99 | 0.760 |
| interval | 0.85 | 853 | −4.62 | 0.859 | 45.8% | −1.24 | −3.37 | 0.840 |
| interval | 0.95 | 738 | −2.08 | 0.936 | 46.6% | −1.45 | −0.64 | 0.595 |

**0 of 8 clear at p ≤ 0.05, the excess is negative in all 8, and every cell is unprofitable.** The
Yan version was weakly positive on research (PF 1.037–1.116); the Bayesian version is PF
0.859–0.985. Gate 1 fails, so no feature was written and **the locked block was not opened** —
`STUDY_PIN.md`'s locked reads stand as the only ones taken on this family.

Two things in that table are worth reading beyond the verdict.

**The threshold has stopped filtering.** Trade counts run 1,125 → 950 across the whole 0.50 → 0.95
range, where the Yan version went 722 → 119. Because μ/(λ_b+λ_s) rose to 0.33, the posterior
saturates: it is above 0.95 almost whenever it is above 0.50. A "probability" that is decisive on
17,834 of 28,164 bars at the 0.85 level is not discriminating between states, it is reporting the
sign of an imbalance with a confident number attached.

**The paper's own preferred construction is the worse of the two.** Fixing the news type over
10-minute intervals — its explicit proposal, and the one better matched to intraday trading — gives
PF 0.859–0.936 against the session build's 0.966–0.985, on a mean period count of 5.0. Shorter
periods mean smaller counts, and smaller counts mean the Poisson is a better description but carries
almost no information per observation. The frequency generalisation is sound in principle and does
not survive contact with a single liquid instrument.

## Trials

14 in `STUDY_PIN.md`; 8 Gate-1 cells here (2 constructions × 4 thresholds) plus 2 construction
choices and the estimator swap = **25 counted looks on this family**. Nothing survived to deflate.


## The lesson worth keeping

**A better estimator of a misspecified model measures the misspecification more precisely.** The
Bayesian fit is unambiguously the better estimator — it converges, it quantifies uncertainty, it
drops a free parameter, and it recovers the truth on data drawn from the model. Every one of those
improvements is real, and together they took PIN from 0.014 to a number that looks *more* credible
against the literature while being *less* connected to information.

**Run the estimator on information-free data with the same nuisance structure before believing the
number it returns on real data.** The dispersion placebo cost eight seconds and is the only test
here that produced a verdict on its own — the P&L took forty minutes and said the same thing.

And the direction of the change is the useful part. Every improvement the paper claims is real and
verified here: the sampler converges (R-hat 1.000), quantifies uncertainty, drops the `evK`
parameter, and recovers a known truth. It moved PIN from a number that looked wrong (0.014) to a
number that looks right (0.155) — and the strategy built on the second is worse than the strategy
built on the first, at every threshold, on both constructions. **A parameter estimate agreeing with
the literature is not evidence when the literature's estimate is of the same misspecified model.**

## What would reopen it

Not a better estimator — that has now been tried and it made things worse. What the model needs is
the input it was written for: **trade-and-quote data with the aggressor side**, so B and S are true
buyer- and seller-initiated trade counts rather than one-minute bars signed by their own direction.
Under Lee-Ready classification the counts are genuinely closer to Poisson (the bar-count proxy
already runs var/mean 2.4 against the volume-weighted 14.7–18.9), and the dispersion the informed
component is currently absorbing would shrink. The other route is the model's own home ground:
**single names around scheduled events**, where α is genuinely large and there is an insider to be
on the other side of. Neither is available on this branch.
