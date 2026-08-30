# Skill manual — Donchian breakout x Bayesian VAR x deep uncertainty, on 1–15 minute bars

Asked for: a complete, implementable system combining classic Donchian channel breakouts on a
scalping horizon, a Bayesian VAR used as a multivariate filter and short-horizon forecast engine,
and a deep-learning uncertainty module that adapts size, geometry and holding time to real-time
epistemic and aleatoric uncertainty.

**Status of the numbers in this document.** The five modules described here are implemented,
committed and self-tested — against *synthetic* series with known ground truth, because the bar
file (`data/NQ_1m.csv`) is git-ignored and is not present in the environment this was written in.
Nothing here has been measured on NQ. Every performance statement is therefore either (a) a
property of the code, verified by a self-test named in the text, or (b) a prior result from
another study in this repository, cited. **There is no backtest result in this document, and you
should be suspicious of one that appears before §4's protocol has been run.**

**Directional variant.** This manual builds the system with the Donchian rule supplying the side
and the model layer supplying second moments. [`SKILL_DIRECTIONAL_ALPHA.md`](SKILL_DIRECTIONAL_ALPHA.md)
builds it the other way round — the BVAR and the network forecast the side — and covers the one
problem that variant has on this sample: NQ rose 89%, so "predicts direction" and "is long" are
nearly the same statement, and separating them takes machinery rather than care.

---

## 0. The prior you should start from

This repository has already measured most of the components of this idea separately, and the
results are not encouraging for the naive version:

| prior evidence | what it implies for this design |
| --- | --- |
| 134 causal features x 4 horizons x 2 timeframes = 1,072 IC tests; **one** survives FDR, worth 0.28 ticks against a 6.0-tick round turn (`STUDY_FEATURES.md`) | a network asked to predict direction here will not find one. Do not build the system around a directional head. |
| 5.7M-combination trend-pullback search: 127 rules beat a time-matched control **on research**, **0** survived the holdout, 6.4 expected by chance (`STUDY_TREND_PULLBACK_2.md`) | a breakout/trend family on this instrument and sample is exhausted by brute force. A new *search* will not fix it; new *information* or a new *cost regime* might. |
| the entry mechanic (a resting limit 0.75 x ATR(5) in your favour) makes $4.3–$37.7/trade with **no rule at all**, but destroys a good signal's edge (`STUDY_LIMIT_ENTRY.md`) | the execution layer is a larger lever than the signal layer, and it **substitutes** for a signal rather than complementing one. |
| 47 auction conditions x 9 strategies: 7/172 pass research, 0 survive holdout (`STUDY_AUCTION.md`) | adding a new indicator family to the same OHLCV has a poor track record here. |
| a 1-minute bar in the quiet session moves 16.6 ticks against a 3.8-tick round turn (`RESEARCH_PROTOCOL.md` §3b) | at 1m the cost is 23% of a bar. Prefer 5m or 15m; treat 1m as an execution timeframe, not a signal timeframe. |

So the honest framing of this system is **not** "Donchian plus AI finds an edge". It is:

> A Donchian break defines a *sparse, well-defined event population*. The BVAR prices the
> *conditional density* of the next h bars given the joint state of return, flow, volume and
> volatility. The network estimates the *second moment* of the outcome and its own *confidence* in
> that estimate. The first is a candidate generator, the second a veto, the third a **risk
> allocator**. The only claims made are about the second and third — variance is far more
> forecastable than direction, and it is monetisable through geometry and sizing without ever
> needing a directional edge to be significant.

If, after §4, the system has no positive net edge on the research block against a matched control,
the correct response is in `RESEARCH_PROTOCOL.md` §4: change the cost regime, change the session,
add information the price series does not contain — not widen the grid.

---

## 1. Strategy architecture

### 1.1 The five modules

| module | responsibility | self-test asserts |
| --- | --- | --- |
| `research/donchian.py` | the channel and the breakout trigger | bands match the naive definition; the current bar is excluded; truncating the future changes no past value |
| `research/bvar.py` | Minnesota-prior BVAR, per-bar predictive density | recovers a known VAR's coefficients to 0.034; analytic h-step predictive sd matches a 20,000-path Monte Carlo to 0.5%; the rolling driver is causal over 3,100 overlapping bars |
| `research/uq_net.py` | heteroscedastic deep ensemble + MC dropout | aleatoric sd tracks a synthetic noise level 0.48 vs 2.01 where the truth is 0.3 vs 2.0; epistemic sd rises 3.1x in a covariate-shifted region; ECE 0.037 out of sample; the purge gap is real |
| `research/dbu.py` | features, labels, gates, sizing, simulator, matched control | a 1R geometry on a driftless series resolves at its barriers 49.8/50.2 and loses exactly the cost line; the same series does **not** beat its matched control; doubling costs hurts; no trade overlaps or precedes its signal |
| `research/dbu_live.py` | the live/paper loop, latency budget and kill switches | nothing trades during warm-up; no second entry while in a position; the kill switch halts; 11 ms median per bar without the network |

### 1.2 Signal generation, exactly

At the **close of bar t** (never a forming bar — `CLAUDE.md` records that tick evaluation without
`barstate.isconfirmed` fired 5.1x as many signals, 80% on bars that never satisfied the rule):

**Stage 1 — the trigger (Donchian).**

```
upper_t = max(high[t-n .. t-1])          # the current bar is EXCLUDED. This is the trap.
lower_t = min(low [t-n .. t-1])
long  trigger:  close_t > upper_t + b*tick
short trigger:  close_t < lower_t - b*tick
```

with `n` in {10, 15, 20, 30, 40, 60} bars and buffer `b` in {0, 1, 2, 4} ticks. Two entry
mechanics, and they are *different strategies with different cost models*:

* `mode="close"` — read at the close, filled at the next open as a market order. This is what
  every engine in this repository simulates natively, and the only one whose fill assumption needs
  no defending.
* `mode="touch"` — a resting stop at `upper + b*tick`, filled at the level. Cheaper in slippage on
  a quiet break, catastrophically worse on a gap. If you simulate this as a next-open market order
  you silently award yourself the gap; `donchian.entry_level()` exists so the level is explicit.

**Stage 2 — the BVAR filter and veto.** The model (§2.1) supplies, at bar t, the predictive
density of the **cumulative return over bars t+1 … t+h**:

```
mu_t   = E[ sum_{j=1..h} r_{t+j} | state_t ]          in ticks
sd_t   = sqrt( aleatoric + parameter uncertainty )     in ticks
p_t    = P( sum_{j=1..h} r_{t+j} > 0 | state_t )
s_t    = ||one-step innovation||_Sigma^-1 / sqrt(k)    the model's own surprise at bar t
```

Gates, applied in this fixed order (the order is recorded in `parts` so you can see which gate is
doing the work, and drop the ones doing none):

```
side * mu_t / sd_t   >=  bvar_z        default 0.15   -- signal-to-noise, signed with the trade
side-adjusted p_t    >=  bvar_p        default 0.52   -- direction, priced against drift
s_t                  <=  surprise_max  default 3.0    -- veto when the VAR just broke
```

The third gate is the one a univariate filter cannot express: it fires when the observed bar is
far from *the joint distribution the model expected*, i.e. a structural break in progress. Trading
a breakout during one is a bet that the model you are filtering with is currently wrong.

**Stage 3 — the uncertainty layer.** The ensemble (§2.2) supplies per bar:

```
p_win        calibrated P(target before stop) for THIS geometry
sd_alea      the irreducible spread of the outcome, in R
sd_epi       ensemble disagreement about the mean outcome, in R
```

and these do three separate jobs:

1. **Veto** — skip when `sd_epi` is above its `epi_q` quantile (default 0.80). The threshold is
   fitted on the **research block only**; `dbu.signal()` refuses to compute it from the whole
   sample and says so loudly if the research block has too little coverage, because calibrating a
   threshold on the locked block is precisely the error `CLAUDE.md` says has already happened
   twice here.
2. **Geometry** — scale the stop (and hence the target, at fixed R) by
   `clip(sd_alea / median(sd_alea | research), 0.7, 1.6)`. Wider expected outcome distribution,
   wider barriers, so that the barrier-hit probabilities stay roughly constant instead of drifting
   with volatility. This is the mechanism by which the holding time adapts: a wider stop takes
   longer to hit, so the effective hold lengthens exactly when the outcome is more dispersed.
3. **Size** — §1.4.

**Stage 4 — the trade.** Entry at the next open (`mode="close"`), bracket = stop at
`stop_atr * ATR(14) * geometry_scale`, target at `tp_r` x that distance, hard time stop at
`max_hold` bars, session flatten at `flat_min` if set.

Nothing downstream of Stage 1 can create a trade. Every later stage can only remove trades or
shrink them. That is a deliberate structural property: it bounds the multiplicity of the search,
and it means the trade population is always a subset of a population you can compute a base rate
for.

### 1.3 How the deep module and the BVAR interact

They are **not** two forecasters averaged together. The relationship is hierarchical:

```
BVAR       ->  first moment and a PARAMETRIC second moment, from a linear Gaussian model
network    ->  a NON-parametric second moment CONDITIONAL ON THE BVAR'S OUTPUT being an input
```

Six of the twelve network features are BVAR outputs (`bvar_mu`, `bvar_z`, `bvar_sd`,
`bvar_epi_share`, `bvar_p`, `bvar_surprise`). So the network is a **meta-layer**: it learns where
the BVAR's own predictive density is trustworthy and where it is not, which is a much better-posed
learning problem than predicting returns, and one where a wrong answer costs you a skipped trade
rather than a bad trade.

The concrete decomposition, for an ensemble of M members evaluated with K MC-dropout passes:

```
mu_bar      = mean_{m,k} mu_{m,k}
aleatoric   = mean_{m,k} sigma^2_{m,k}      each model's own claim about irreducible spread
epistemic   = var_{m,k}  mu_{m,k}           disagreement between models fitted to the same data
```

(Kendall & Gal 2017; Lakshminarayanan et al. 2017.) Two cautions that matter more than the
architecture:

* the epistemic term is a **lower bound**, and it is only meaningful if members differ in
  initialisation *and* data order *and* bootstrap resample. All three are on in `uq_net.fit_ensemble`.
* on a walk-forward fold, epistemic uncertainty measures **distance from the training window**.
  That is exactly the regime-shift detector you want — and exactly why the model must be refitted
  on a schedule (§4.3), because otherwise the epistemic term grows monotonically and the veto
  eventually stops everything.

### 1.4 Position sizing, scaling and exits

`dbu.kelly_size`:

```
p        = base + (p_win - base) / (1 + sd_epi / sd_alea)      base = 1/(1+R)
f*       = (p (1+R) - 1) / R                                   Kelly on the barrier bet
f        = clip(f*, 0, 1) * kelly_frac                         kelly_frac default 0.25
q        = floor( f * equity / stop_dollars )
q        = min( q, floor(risk_per_trade / stop_dollars), max_contracts )
```

Four deliberate departures from textbook Kelly, in descending order of importance:

1. **The epistemic shrink.** `p` is pulled toward the geometry's driftless base rate in proportion
   to the ensemble's disagreement relative to the irreducible noise. An unfamiliar state cannot
   produce a large bet just because one member is confident. This is the single most important
   line in the module and the whole reason for the uncertainty machinery.
2. **`kelly_frac = 0.25`.** Kelly assumes `p` is known. It is estimated, and the variance of an
   estimated-p Kelly is enormous; a quarter is the usual compromise and is still aggressive.
3. **A hard per-trade risk cap** that wins over Kelly whenever they disagree, plus an integer
   contract cap. Futures do not size continuously, and on a small account the honest answer is
   1 contract nearly always. `CLAUDE.md`: **sizing creates no edge.** It manages ruin, and it is
   the mechanism by which uncertainty is *expressed*, not a source of return.
4. **Kelly may return zero,** and that is the system working. On the synthetic driftless demo,
   `p_win` sits near the base rate, `f*` is negative, and 298 of 300 gate-passing bars are sized
   to zero contracts. A sizing rule that always returns at least one contract is not a sizing rule.

**Scaling in** is deliberately *not* supported. On a 1R barrier geometry a scale-in changes the R
of the position, so the label the network was trained on no longer describes the trade. If you
want it, retrain the labels on the scaled geometry — do not bolt it on.

**Exits**, in priority order inside a bar: stop, target, session flatten, max hold. When one bar
contains **both** barriers the trade is booked as the **loss**, because the intrabar path is
unknown (`RESEARCH_PROTOCOL.md` Stage 0). The synthetic self-test shows this biases the barrier
win rate to 49.8% on a driftless series where the theory says 50% — a known, small, conservative
amount rather than an unknown one. `research/intrabar.py` can price the true 1-minute path if you
want the ambiguity resolved rather than assumed.

### 1.5 Costs, slippage and latency, up front

```
round turn = commission + 2 x spread + stop slippage
MNQ:  $1.20 + 2 x 1 tick ($0.50) + 1 tick on stops   ~ 2.4 ticks of commission alone
NQ:   $4.00 + 2 x 1 tick ($5.00) + 1 tick on stops   ~ 0.8 ticks of commission
```

`RESEARCH_PROTOCOL.md` §3b: **micros are the wrong lever for a marginal edge** — they cut dollar
risk 10x but commission only ~3x, so the per-tick hurdle roughly triples. They are the right tool
for sizing a small account and the wrong tool for making a marginal strategy viable.

Latency: the model side of the loop is ~11 ms measured without the network and ~15–20 ms with it
(`dbu_live.selftest`). That is not the binding constraint. Feed latency, broker round trip and
queue position are, and they total 100–300 ms on a retail stack. **Test the strategy's sensitivity
to a 300 ms delay offline before wiring anything up** — `research/live_timing.py` and
`docs/ib/LIVE_EXECUTION.md` already do this for the shipped strategies.

---

## 2. Model specifications

### 2.1 The BVAR

**Variables** (`bvar.PanelCfg`, five by default — the smallest set that says something a
univariate model cannot):

| variable | definition | why |
| --- | --- | --- |
| `ret` | close-to-close change, in ticks | the forecast target |
| `flow` | `(2(c-l)/(h-l) - 1) * volume`, scaled by its trailing median absolute value | a bar-level signed order-flow proxy. Replace with real signed volume the moment you have it (§6.2) |
| `volz` | `log(volume / trailing median volume)` | participation: is anyone there at all |
| `rvol` | `log(true range / trailing median)` | the scale variable, and the one that makes the SV standardisation partly redundant on purpose |
| `dpos` | Donchian channel position, centred | where price sits in the structure the rule trades |

All five are stationary by construction, which is why the prior's own-first-lag mean is `delta=0`
(white noise) rather than `1` (random walk). **Put a level variable in this panel and you must
change `delta`,** or the prior is fighting the data.

Natural extensions, in the order they are worth trying: ES or YM returns at the same stamp
(cross-instrument lead-lag is the classic short-horizon multivariate effect, and this repository's
`STUDY_CORR_MATRIX_2.md` has the machinery); VIX or a realised-vol-of-vol term; a cumulative
delta or book-imbalance series if you have one. Each new variable costs `k*p` coefficients per
equation, so add them one at a time and read the *predictive* likelihood, not the fit.

**Lag order** `p = 6` on 5-minute bars (30 minutes of history), `p = 4` on 15-minute. With `k=5`
and `p=6` that is 155 free coefficients — hopeless unrestricted, routine with shrinkage.

**Prior**: Minnesota, implemented as Bańbura–Giannone–Reichlin dummy observations, so the
posterior mean *is* OLS on the augmented data and no `k²p²` precision matrix is ever built.
Tightness `lam` default 0.2, lag decay `alpha = 2`. `lam -> 0` is a random walk (or white noise,
at `delta=0`); `lam -> inf` is unrestricted OLS. The self-test asserts the shrinkage direction is
real. The one thing this dummy form gives up is a separate cross-lag looseness `theta`; the
Litterman equation-by-equation variant supports it at the cost of conjugacy, and the difference
was not worth the closed form.

**Stochastic volatility**: handled by causal EWMA standardisation (`lam_sv = 0.97`) — model
`y_t / sigma_{t-1}`, rescale the forecast by `sigma_t`. This captures the first-order effect (the
conditional variance moves by an order of magnitude between 04:00 and 09:30) at essentially zero
cost and keeps the model conjugate, which is what keeps online updating closed form. A full SV
BVAR (Carriero–Clark–Marcellino) or a TVP-BVAR is a strictly better model and a much worse fit for
a hot path; if you want one, fit it offline and use it to *choose* the EWMA half-life.

**Estimation and the trick that makes it affordable per bar.** The cumulative return over `h`
bars is a **linear functional of the companion state**:

```
z_{t+j} = c_j + C^j z_t + sum_{i<j} C^i e_{t+j-i}
sum_{j=1..h} g'z_{t+j}  =  a'z_t + b  +  sum_m w_m' e_{t+m},   w_m = sum_{i=0..h-m} (C')^i g
```

so per posterior draw `s` you precompute one vector `a_s`, one scalar `b_s` and one exact variance
`v_s = sum_m w_m' Omega w_m`. The per-bar forecast for a whole refit block is then a single
matmul `Z @ A`. Predictive mean = mean over draws; **epistemic** = variance across draws of the
draw-wise means; **aleatoric** = mean across draws of `v_s`; `p_up` = mean of `Phi(mu_s/sd_s)` —
a Gaussian mixture, not a point estimate plugged into a normal CDF. `selftest()` checks the
analytic `sd` against a 20,000-path simulation (2.757 vs 2.745).

Posterior draws: 200 (S=200 puts the Monte-Carlo error on `p_up` around 0.5 pp, far below the
data noise). Refit every 250 bars over a trailing 4,000-bar window. **The posterior in force at
bar t was fitted on rows ending before the refit block containing t** — the strictest reasonable
choice, and the only one that survives the truncation test.

**Impulse responses** (`bvar.irf`) are a *design* tool, not a signal: they tell you how many bars
a flow shock's return response survives, which is how you should choose `h`. Choosing `h` by grid
search over P&L is how you get a number that does not replicate.

### 2.2 The deep uncertainty model

**Architecture** (`uq_net.HeteroMLP`): shared trunk of 2 x 64 GELU with dropout p=0.15, three
heads — `mu`, `log var` (clamped to ±8), and a barrier logit. Small on purpose: the input is 12
engineered features, most of which are already model outputs, and `STUDY_FEATURES.md` found this
instrument's 134 features are really 28 principal components. A wide network here is a way of
hiding a search, not of adding information.

Why an MLP and not a sequence model: the temporal structure is already in the BVAR state and the
channel features. If you want a sequence model, a small GRU over the last 32 bars of the panel is
the right shape — but train it in the same walk-forward harness and compare on *predictive NLL of
the barrier outcome*, not on P&L, or you have just moved the overfitting one level up.

**Objective**: `Gaussian NLL(mu, logvar; y) + lam_cls * BCE(logit; label)`, `lam_cls = 0.5`.

* `y` = the trade's outcome **in R**, from `dbu.labels` — i.e. from the same triple-barrier walk
  the strategy trades. Training on a raw h-bar forward return instead is the classic mistake: the
  barrier *order* is what pays, and a forward return does not know about it.
* `label` = 1 if the target was hit before the stop.

**Ensemble**: 5 members x 20 MC-dropout passes = 100 forward evaluations per row, batched. Each
member gets its own seed, its own shuffle and an 80% bootstrap resample.

**Calibration**: temperature scaling on the contiguous *tail* of each training window, never a
random split (overlapping labels leak). `uq_net.ece` reports expected calibration error; the
synthetic test lands at 0.037 out of sample. **Report ECE beside every `p_win` or do not quote the
`p_win`** — the sizing formula divides by it.

**Purging**: labels resolve over up to `max_hold` bars, so neighbouring rows share outcome. Folds
are purged by `max_hold` bars and embargoed by the same. Without it, validation loss is optimistic
and the calibration step calibrates on its own training set.

### 2.3 Feature pipeline (12 features, all read at the signal bar)

| feature | source |
| --- | --- |
| `donch_pos`, `donch_w_atr`, `donch_age`, `break_size` | channel geometry and how hard this break cleared it, in ATR units |
| `close_in_bar` | the one feature that survived FDR in `STUDY_FEATURES.md` |
| `atr_ratio` | ATR now vs 60 bars ago — the volatility *trend*, not its level |
| `bvar_mu`, `bvar_z`, `bvar_sd`, `bvar_p`, `bvar_epi_share`, `bvar_surprise` | the BVAR density |

Everything is either scale-free or divided by ATR, so nothing carries the 89% index rise as a
level. **No calendar features** — `CLAUDE.md`: weekday and month partition the sample and hand the
search a free lottery; removing them was worth $8,771 on the holdout. Minute-of-day is *not* a
feature either; it enters through the session window and through the matched control, which is
where it belongs.

The pipeline is realistic live because every feature is a function of closed bars only, and
`dbu_live.Runner` recomputes them from the same code path as the research layer. Feature parity
between research and live is not a nice-to-have; a separate live implementation is how this
repository produced its worst bugs (`STUDY_WHY_PINE_DIVERGED.md`).

---

## 3. The code

Five modules, each runnable standalone (`python3 research/<module>.py` runs its self-test):

```
research/donchian.py    channel, breakout triggers, indpool registration, leak check
research/bvar.py        panel, Minnesota prior, NIW posterior, h-step functionals, rolling driver
research/uq_net.py      heteroscedastic deep ensemble, MC dropout, temperature scaling, purged WF
research/dbu.py         features, labels, gates, sizing, simulator, base rate, matched control
research/dbu_live.py    the live loop, paper broker, latency budget, kill switches
```

The full research path is one call:

```python
import dbu
cfg = dbu.Cfg(don_n=20, buf_ticks=2, win=(570, 660), h=6, stop_atr=1.5, tp_r=1.0, max_hold=24)
res = dbu.pipeline(d, cfg, side=1)      # d = the bar dict from research/fastbars.py
```

which runs: BVAR rolling density -> features -> triple-barrier labels -> purged walk-forward
ensemble -> gates -> sizing -> simulation -> research/locked split -> matched control. Every stage
is out of sample by construction; there is no step in which the whole sample is fitted and scored.

`python3 research/dbu.py --demo` runs the whole thing on synthetic bars in about a minute — a
wiring test, not a result. On that driftless series it produces 1,163 triggers, 414 surviving the
BVAR gates, 300 surviving the epistemic veto, and **2** surviving the sizing rule, which is the
correct behaviour: Kelly declines a bet with no edge.

### Integrating with the existing harness

`donchian.register()` adds `donch_hi`, `donch_lo`, `donch_mid`, `donch_w`, `donch_pos`,
`donch_w_atr`, `donch_age_up/dn` to `indpool`, so the tuner's rule language works directly:

```python
import donchian, tuner
donchian.register()
tuner.sweep("close > donch_hi{n} and donch_w_atr{n} < 4", n=[10,20,40], tf=5,
            stop=[1.0,1.5,2.0], target=[0.75,1.0,1.5], control=2000)
```

That path gives you `tuner.py`'s cached exit tensor (0.4 us per geometry) and its 6 ms matched
control, which is the right way to explore the *geometry* grid. `dbu.py`'s own simulator exists
because the BVAR and network gates need per-bar arrays the tensor does not carry; it is asserted
against the same pessimism rules but **it is not the authority** — before shipping anything, check
a fixed rule trade-for-trade against `test_suite.sim_core`, the way `tuner_test.py` does.

---

## 4. Hyperparameters, robustness and the protocol

### 4.1 Defaults and ranges

| knob | default | range worth exploring | notes |
| --- | --- | --- | --- |
| timeframe | 5m | 5m, 15m | 1m only as an execution layer: cost is 23% of a quiet bar |
| `don_n` | 20 | 10–60 | a real edge decays smoothly across this. If it exists at 20 and dies at 15 and 30, it is noise (`STUDY_1R_MORE.md`) |
| `buf_ticks` | 2 | 0–4 | the cheapest false-breakout guard there is; test it before any model gate |
| `h` | 6 | 4–12 | **choose from the IRF, not from P&L** |
| `stop_atr` | 1.5 | 1.0–2.5 | |
| `tp_r` | 1.0 | 0.75–2.0 | changes the base rate; recompute it, never assume 1/(1+R) |
| `max_hold` | 24 | 8–48 | |
| `bvar_z` | 0.15 | 0.0–0.4 | |
| `bvar_p` | 0.52 | 0.50–0.58 | |
| `epi_q` | 0.80 | 0.6–0.95 | |
| `lam` (Minnesota) | 0.2 | 0.05–1.0 | tune on **predictive likelihood**, not on P&L |
| `p` (lags) | 6 | 2–12 | |
| ensemble members | 5 | 3–10 | 10 buys almost nothing |
| `kelly_frac` | 0.25 | 0.1–0.5 | above 0.5 is a decision about ruin, not about return |

**How to tune without mining.** Three rules, all of which this repository learned expensively:

1. **Tune the model on model metrics, the strategy on strategy metrics.** `lam`, `p`, the panel,
   the network width and the dropout rate are chosen on *out-of-sample predictive likelihood and
   ECE*. Only the trading knobs (`don_n`, geometry, gate thresholds) are ever chosen on P&L. This
   collapses the multiplicity of the search by orders of magnitude.
2. **Sweep the neighbourhood, gate on the SIZE of the excess, never its sign.** Over a monotone
   threshold grid a union *is its loosest member*, so "any of these thresholds passes" is not a
   result. Ranking by a *minimum* over a neighbourhood is the obvious over-correction and cost
   $18,970 the one time it was tried.
3. **Run the matched control as a research GATE, in front, on every configuration** — not as a
   final check on the survivor. `dbu.control()` is the same construction as `oner_anom.py`: random
   entries with the same side, geometry and minute-of-day distribution, which prices drift, costs,
   barrier width and session timing in one number.

### 4.2 Validation, in the order it must run

1. **Stage 0 null.** Run the whole pipeline over simulated driftless bars with costs off. Anything
   significantly profitable is a bug. `dbu._synth` + `dbu.selftest` is this in miniature and it is
   already wired: the driftless series does not beat its control (p = 0.37).
2. **Leak check.** `donchian.selftest` and `bvar.selftest` both assert by truncation that no past
   output changes when the future is removed. Add every new feature to that check. Then re-read
   `CLAUDE.md` on `ent_bar` vs `sig_bar`: a conditional split of *realised trades* is not a filter
   test — filter the **triggers** and re-simulate.
3. **Base rate.** `dbu.base_rate()` on the exact geometry, over eligible bars. A 54% win rate is
   worthless if the geometry's base is 54.2%.
4. **Matched control on the research block.** If the rule does not beat it here, stop. Do not look
   at the holdout.
5. **Purged walk-forward** with re-fitting inside each fold — the *only* honest estimate, because
   it includes the cost of having to choose parameters.
6. **PBO (CSCV)**, Deflated Sharpe, White's Reality Check / Hansen's SPA over the candidate set.
   `research/test_suite.py` has all of these; the gates are in `RESEARCH_PROTOCOL.md` §3.
7. **Cost sensitivity at 1.5x and 2x.** Spreads widen exactly when breakouts fire. This is the
   test most likely to kill the result and therefore the one to run early.
8. **The locked block, once.** First 65% of sessions is research; the rest is read at the end, and
   never again. `dbu.split()` is the single definition. **A rule that passes on the locked block
   while failing on research is a defect, not a result** — it has happened twice here.

### 4.3 Recalibration schedule

| component | refit | rationale |
| --- | --- | --- |
| BVAR posterior | every 250 bars (~1 session on 5m), trailing 4,000 bars | cheap (~30 ms), and the coefficients genuinely move |
| ensemble | every ~4,000 bars (2–3 weeks on 5m), expanding window | expensive; and a network refitted too often chases noise |
| `epi_q` threshold and `sd_alea` median | with each ensemble refit, on the research block only | they are properties of the *current* model, not of the market |
| temperature | with each ensemble refit, on the held-out tail | |

Track `sd_epi` in production. A slow rise means the live distribution is drifting from the
training window, and it will silently veto everything before it ever tells you the model is stale;
`LiveCfg.max_stale_bars` makes that failure explicit instead.

### 4.4 The three warnings

**Look-ahead** hides in four places here specifically: the Donchian band including the current bar
(handled, asserted); a feature read at the fill bar instead of the signal bar (the single most
expensive bug in this repository's history — it produced a p=0.0005 holdout result across 9 of 9
strategies, and it was pure leakage); a network fold whose purge is shorter than the label horizon;
and any threshold, quantile or normalisation fitted over the whole sample. `dbu.signal()` refuses
the last one by construction.

**Microstructure noise** at 1–5 minutes is a large fraction of the observed variance, and it
biases everything estimated from close-to-close returns toward mean reversion. The variance-ratio
table in Stage 2 of the protocol tells you at which horizons the series actually departs from a
random walk; trade at those horizons or accept that you are trading noise. The flow proxy used
here is a *bar-level* proxy and it is the weakest link in the panel — see §6.2.

**Non-stationarity**: this sample is one regime. NQ rose 89% and 81% of bars are in a daily
uptrend, so the short side is close to untestable and any search allowed to pick a side picks
long. Direction is not free on this data; fix it, or dictate it from the daily trend
(`research/daily_trend.py`), rather than letting the optimiser choose.

---

## 5. Risk and edge realism

**Risk limits** (`dbu.Cfg`, `dbu_live.LiveCfg`): `risk_per_trade` $100 at the stop as a hard cap
that overrides Kelly, `max_contracts` 3, `daily_loss_limit` $400 enforced in the backtest *and* in
the live loop, plus a consecutive-loss kill switch. The daily limit resets at the session
boundary; the model-staleness halt does not.

**Where an edge could actually come from, in descending order of plausibility:**

1. **The uncertainty-conditional geometry.** Volatility is forecastable; direction here is not.
   Scaling the stop with predicted aleatoric spread keeps barrier probabilities stable across
   regimes, which mechanically improves the *distribution* of outcomes even with zero directional
   edge. This is the least exciting and most likely source of value in the whole design.
2. **The execution layer.** `STUDY_LIMIT_ENTRY.md` measured a resting limit 0.75 x ATR(5) in your
   favour earning $4.3–$37.7/trade with no rule at all, on both blocks and both sides. It
   *substitutes* for a signal rather than complementing one, so it is not compatible with a
   momentum breakout — but it says clearly that the fill is worth more than the forecast here, and
   a Donchian *stop* entry is the most expensive fill there is. Measure `mode="touch"` against
   `mode="close"` before tuning anything else.
3. **The BVAR's multivariate veto.** The one thing a VAR gives you that no univariate filter can:
   "this break is happening into a flow shock whose impulse response dies in two bars". If any
   part of the model layer earns its keep, this is the part.
4. **The directional forecast.** Least plausible. 1,072 IC tests on this instrument found one
   surviving feature worth 0.28 ticks against a 6.0-tick round turn.

**How it fails, in descending order of likelihood:**

* **It never clears costs.** The most likely outcome by a wide margin, and the arithmetic is
  visible before any modelling: a 5-minute quiet bar is 36 ticks and the round turn is 3.8.
* **The gates are just "trade less".** Any restrictive filter improves per-trade P&L on a losing
  population by removing trades. That is what the matched control is for — a filter that beats
  *total dollars* but not a random filter of the same selectivity has found nothing. Use
  `research/dropone.py`.
* **The uncertainty veto is a volatility filter in disguise.** Highly likely, and testable: regress
  `sd_epi` on ATR and session time, and check whether the veto still selects anything once you
  match on those.
* **The network is calibrated on a regime and the regime changes.** ECE degrades before P&L does,
  which is why it is monitored (§6.3).
* **Live/backtest divergence at the fill.** A Donchian stop entry in fast conditions is exactly
  where modelled slippage understates reality. Paper-trade with `PaperBroker`, which is built to
  be *at least as pessimistic* as the backtester on purpose.

**Monitoring live decay.** Log every decision, taken or not, with its inputs and the model version
hash (`Runner._emit` writes JSONL). Then track, weekly: realised vs predicted `p_win` (ECE);
`sd_epi` drift; the gate-attrition table (`parts`) against its research distribution; realised
slippage vs modelled, per exit reason; and per-trade P&L against a rolling matched control on the
live period. **The first four are leading indicators; P&L is a lagging one.** A strategy whose
gate-attrition profile has shifted is already broken, whatever this month's P&L says.

---

## 6. Extensions and practical notes

### 6.1 Making it faster

* The BVAR's per-bar cost is already one matmul. The refit is the only heavy step: keep `X'X` and
  `X'Y` as sufficient statistics and update them rank-1 per bar, subtracting the leaving rows for
  a rolling window — the posterior is then a Cholesky solve, not a re-accumulation.
* The panel rebuild dominates the live hot path (~10 of ~11 ms). Make it incremental if you need
  single-digit milliseconds — **and assert it bar-for-bar against the vectorised version**, the
  way `tuner_test.py` asserts the exit tensor against `sim_core`. Do not make it incremental and
  hope.
* Network inference: pre-batch the MC-dropout passes into one forward call of shape
  `(members*mc, features)`; export to TorchScript or ONNX; or replace MC dropout with a last-layer
  Laplace approximation, which gives a closed-form epistemic term at one forward pass. Deep
  ensembles remain the better-calibrated option — this is a latency trade, not a free lunch.
* The whole geometry grid belongs in `research/tuner.py`'s exit tensor, not in `dbu.walk`: 0.4 us
  per geometry against ~1.3 ms.

### 6.2 Order-book features

The flow proxy in the panel is the weakest variable in it. With an L2 feed the natural upgrades,
in order of expected value: signed volume from trade-side classification (not from bar shape);
top-of-book imbalance at the moment of the break; depth *within* the breakout level, which is the
direct measurement of the thing a Donchian break is supposed to be about (resting stops above the
high); queue-position-aware fill modelling for `mode="touch"`. Add them to the panel one at a
time, and read the predictive likelihood, not the backtest.

Two cautions: book data is not available in this repository's current dataset, and any book
feature must be stamped *at or before* the bar close it is read on — a snapshot taken at
"bar close" by a feed that batches is a look-ahead with extra steps.

### 6.3 Logging, alerting, dashboard

Log JSONL, one line per closed bar, whether or not a trade resulted: timestamp, bar index, gate
outcome and the reason it stopped, `mu`/`sd`/`p_up`/`surprise`, `p_win`/`sd_epi`/`sd_alea`, the
chosen size and geometry, model version hash, and the wall-clock ms. The no-trade lines are the
valuable ones — they are the only record of what the system *declined*, which is what you need to
diagnose a veto that has silently turned into a full stop.

Alert on: model staleness, a gate whose pass rate moves more than 3 sd from its research
distribution, ECE above ~0.10 on a rolling 200-trade window, realised slippage above modelled for
20 consecutive trades, and any kill-switch trip. A one-page dashboard needs only five panels:
cumulative P&L vs a rolling matched control, the gate-attrition funnel, calibration (reliability
curve + ECE), `sd_epi` over time with the veto threshold drawn on it, and realised-vs-modelled
slippage by exit reason.

---

## 7. What to do first (in order, one to three days each)

1. Run `python3 research/donchian.py`, `bvar.py`, `uq_net.py`, `dbu.py`, `dbu_live.py`. All five
   must print their self-test. This is Stage 0.
2. Point `dbu.pipeline` at real 5-minute bars via `fastbars.bars(5)`. Compute the **base rate**
   for your geometry, then the **matched control** for the bare Donchian trigger with no model
   gates. If the bare trigger is not within a plausible distance of its control, you have learned
   the most important thing in the study on day one, for free.
3. Sweep `don_n` and the geometry through `tuner.sweep` with `donchian.register()`, on **research
   only**, with the control as a gate. Look at the *shape* of the surface, not the maximum.
4. Only then add the BVAR gates, and measure what each one removes (`parts`) and what it adds
   against a *random filter of the same selectivity* (`research/dropone.py`).
5. Only then add the network, and judge it first on **predictive NLL and ECE**, not on P&L.
6. Read the locked block once, at the end, and write down the multiplicity first.

