# Skill manual — directional alpha: the model picks the side, the Donchian break is the event

Companion to [`SKILL_DONCHIAN_BVAR_UQ.md`](SKILL_DONCHIAN_BVAR_UQ.md), which builds the same three
components the other way round: there the Donchian rule supplies the side and the model layer
supplies second moments; **here the BVAR and the network forecast the SIDE**, and the break is one
of three event populations the forecast can be evaluated on. Everything about model specification,
the BVAR's internals, the ensemble's internals, walk-forward hygiene and the live loop carries over
unchanged — read that document for those. This one is about the single problem a directional system
on this sample has, and what it takes to not be fooled by it.

Code: `research/dbu_dir.py`. Self-test: `python3 research/dbu_dir.py`.

**Status of the numbers.** Every number in §2 is a measurement of the code against *synthetic*
series with known ground truth — the bar file is git-ignored and absent here. Nothing is measured
on NQ. There is no backtest result in this document.

---

## 1. The problem, stated once

NQ rose 89% over this sample and 81% of bars sit in a daily uptrend. So on this data:

> "predicts direction" and "is long" are nearly the same statement.

A directional model fitted here will learn the drift, because the drift is the single largest and
most persistent signal in the series, and it will then report the index's own rise as its alpha.
Every honest directional result on this sample is a statement about what remains **after** that is
removed. Three structural defences, in the code rather than in the advice:

### 1.1 The prior shift

The classifier's log-odds has `logit(base_rate_train)` **subtracted** after calibration, per fold,
using that fold's *training* rows only. The BVAR's `p_up` is shifted by its own unconditional mean
on the **research block** only. Each source is shifted by its own prior, on its own scale — mixing
them is a real bug with a measured consequence (§2.3).

After the shift, `p = 0.5` means *"nothing beyond what being unconditionally long already gives
you"*. A model that has learned only the drift scores 0.5 everywhere and takes **no trades**.
`DirCfg.prior_shift = False` turns it off; that is a decision to measure drift, and it should be
made deliberately, once, to see the size of what you are removing.

### 1.2 The antisymmetric target

Both sides of every eligible bar are simulated with the same geometry, and the target is

```
y_dir = (R_long − R_short) / 2          antisymmetric under a price sign flip
lab   = 1[ R_long > R_short ]           "which side would have won"
```

Under a sign flip of the price series `y_dir` negates exactly. So a model fitted to it cannot
encode "long is good" anywhere except in a bias term — and the bias *is* the drift, estimated on
the training window, which is exactly what the prior shift removes. Costs are deliberately **not**
in these labels: the model is asked what the market does; the cost of acting on that is charged
once, later, where it belongs.

### 1.3 The mirror test

Negate the price series and re-run. The calls must flip. A drift-rider does not flip. This is the
cheapest genuine test of a directional claim that exists and it needs no holdout at all —
`selftest()` runs it on every commit and asserts >90% of all calls and >98% of confident calls
invert.

### 1.4 Side-neutral features

`dbu.features` multiplies several columns by `side` — correct when the side is given, fatal when
the side is the thing being predicted, because it hands the model its own answer.
`dbu_dir.dir_features` is signed instead: `break_up` and `break_dn` as separate columns, centred
channel position, centred close-in-bar, the BVAR's signed `mu` and `p_up − 0.5`. **The difference
between those two functions is the difference between the two systems.**

---

## 2. What the self-test measures, and why each case is there

`python3 research/dbu_dir.py` runs four cases on 12,000 synthetic bars each. All four matter, and
two of them are the ones a directional study usually skips.

| case | series | result | reading |
| --- | --- | --- | --- |
| **NULL** | no autocorrelation, no drift | AUC **0.502**, adjusted-edge t **−0.99** | the pipeline invents nothing |
| **POWER** | planted AR(1), φ = 0.35 | AUC **0.589**, adjusted edge **+0.92 ticks**, t **+8.51** | the pipeline *finds* an effect it was handed. A method that cannot detect a planted signal is not evidence of absence (`RESEARCH_PROTOCOL.md` Stage 0) |
| **DRIFT, shift off** | drift, no conditional structure | **97.3% long**, raw edge **+0.545 t**, drift term explains all of it, adjusted **−0.023 t** | this is what a naive directional system looks like on this sample: a large raw number that is entirely the index |
| **DRIFT, shift on** | same series | **55.5% long**, adjusted **−0.115 t** | the shift removes the tilt and the residual is noise |
| **MIRROR** | POWER series, negated | **97.6%** of calls flip, **100%** of confident calls | the signal is conditional, not a long bias |

The full stack with the network on a planted-signal series (`--demo --planted`, 24,000 bars):

```
SKILL  n 16,576  base 49.5%  acc 53.4%  auc 0.550  skill score +0.0056
EDGE   raw +1.169t  drift -0.005t  ADJUSTED +1.174t  t +4.63  long share 48%
trades 954  $-2,546  $-2.67/trade
  long   466 trades  $-2.52/trade   control $-3.13  p=0.000
  short  504 trades  $-2.84/trade   control $-3.21  p=0.000
```

**Read that last block carefully, because it is the whole lesson of this document.** The model has
genuine, strongly significant, two-sided directional skill on a series where a directional effect
was planted — AUC 0.550, adjusted edge +1.17 ticks at t = 4.63, and it beats a matched control on
*both sides* at p = 0.000. And it **still loses $2.67 a trade**, because 1.17 ticks of edge does not
pay a ~3-tick round turn.

That is not a bug in the demo. It is the arithmetic from `RESEARCH_PROTOCOL.md` §1 arriving on
schedule: **statistical skill and tradeable edge are different thresholds, and the gap between them
is the cost line.** Any directional research program on this instrument should expect to spend most
of its time in exactly that gap.

---

## 3. Architecture

```
event population        →  score                       →  side              →  trade
Donchian break (either      log-odds pool of the           |p−0.5| ≥ conf       both sides,
way) / every bar /          prior-shifted net and          else FLAT            no-overlap
failed break                the prior-shifted BVAR                              across the book
```

**Event populations** (`DirCfg.event`):

* `"break"` — a Donchian break in *either* direction. Note the model may take the **opposite** side
  of the break; that is the point of separating the event from the side.
* `"all"` — every eligible bar in the session window. Use this to measure the alpha itself, free of
  the event. If the alpha only works on breaks, that is a finding; if it works everywhere, the
  Donchian layer is decoration and should be dropped.
* `"fail"` — a break whose next bar closed back inside the channel. The classic failed breakout,
  and the one population where a directional model and a breakout rule disagree by construction.

**Score** (`blend`): log-odds pooling, not probability averaging. Averaging two models of the same
event pulls every disagreement toward 0.5 and destroys exactly the confident calls that sizing
depends on. Pooling in log-odds also makes the prior shift a subtraction rather than a
renormalisation. Default weight `w_bvar = 0.35`.

**Side** (`decide`): `|p − 0.5| ≥ conf`, default 0.03. Zero is a first-class outcome and is usually
the most common one. A bar with no forecast takes **no** side — explicitly, because the naive
version turns every NaN into a maximally-unconfident short, which is a silent short bias on exactly
the bars the model said nothing about.

**Sizing, exits, risk limits, live loop**: unchanged from the companion manual (§1.4, §5, §6 there).
The uncertainty machinery is *not* wasted in the directional system — `sd_epi` still shrinks the
Kelly fraction toward the base rate, and `min_conf_epi` optionally requires confidence to scale
with disagreement.

---

## 4. Scoring order — P&L is last, and it is not the evidence

Run these in order and stop at the first failure. Most directional studies run only the fourth,
which is why most directional studies are wrong.

1. **Directional skill.** Accuracy against the **label's own base rate** (not 50%), AUC, and a
   skill score `1 − logloss/logloss_base` against a constant-base-rate model. `always_long` is
   printed beside accuracy so the comparison cannot be dodged. If a directional model has no skill
   here, its P&L is a statement about drift and costs.
2. **Drift-adjusted edge.** `mean(side·fwd) − mean(side)·mean(fwd)` — the estimator from
   `RESEARCH_PROTOCOL.md` §2 — with a **Newey-West lag ≥ the horizon**, because overlapping h-bar
   windows induce MA(h−1) dependence and the automatic `4(n/100)^(2/9)` rule is far too short. All
   three numbers are reported together: raw, drift, adjusted. A raw edge with no adjusted edge is
   the index.
3. **Side balance.** Long and short counts and their separate per-trade P&L. A "directional" system
   that is 95% long has not been tested on the short side; it has been fitted to the sample's one
   regime. `CLAUDE.md` notes 81% of bars are in a daily uptrend and 7% in a downtrend, so the short
   side is close to untestable here — which is a reason to *report* the imbalance, not to hide it.
4. **Net P&L per side, against a matched control drawn within each side.** Not against zero: both
   arms pay the round turn, so at large *n* a fair coin with a spread reports a huge significant
   negative and the thing it is significant about is the commission (`RESEARCH_PROTOCOL.md` §4a).
5. **Research/locked split**, read once. `trade()` flags a configuration that looks better on the
   locked block than on research as the wrong shape — the holdout is where an edge decays, not
   where it appears.

Then the rest of the protocol: purged walk-forward, PBO, Deflated Sharpe, cost sensitivity at 1.5x
and 2x, and the ten gates in §3 of the protocol.

---

## 5. Hyperparameters

Only the directional ones are listed; the rest are in the companion manual §4.1.

| knob | default | range | notes |
| --- | --- | --- | --- |
| `event` | `break` | `break`, `all`, `fail` | run `all` at least once — it tells you whether the event matters |
| `conf` | 0.03 | 0.01–0.10 | the whole trade-count knob. Sweep it and read the *shape*: a real edge is monotone in confidence |
| `w_bvar` | 0.35 | 0.0–1.0 | 0.0 and 1.0 are the two ablations worth reporting: they say which model is carrying the result |
| `prior_shift` | True | — | off = you are measuring drift. Do it once, deliberately, to size what you removed |
| `demean_target` | True | — | removes the training-window mean of `y_dir` from the regression head |
| `allow_short` | True | — | off is a much weaker claim on this sample, and should be labelled as such |
| `hac_lag` | `max_hold` | ≥ horizon | never the automatic rule |

**Tuning discipline is stricter here than in the companion system**, because a directional search
has more freedom to find nothing convincingly: tune the *model* on out-of-sample log-loss and AUC,
and only `conf` and `event` on anything resembling P&L. A confidence threshold swept against
adjusted edge, on research only, with the matched control as a gate, is about the maximum honest
search this design supports.

---

## 6. Where a directional edge could actually come from

Ranked by plausibility on *this* data, and none of these is free:

1. **Cross-instrument lead-lag.** ES/NQ/YM at the same stamp is the classic short-horizon
   multivariate effect, and the BVAR is the natural model for it — it is what a VAR is *for*. This
   is the single highest-value extension, and it needs a second data file, which is also what
   `STUDY_TREND_PULLBACK_2.md` concluded independently ("what would move it: cross-asset files, a
   second instrument").
2. **Order-flow imbalance**, from real signed volume rather than the bar-shape proxy in the panel.
   Rules built from OHLC alone compete with everyone who has the same OHLC.
3. **Short-horizon mean reversion at h = 1–2 bars**, which `STUDY_LIMIT_ENTRY.md` already measured
   as real and worth 0.28 ticks as a signal — far below costs as an alpha, and worth a great deal
   as a *fill*. If the directional model's edge turns out to live at h = 1, the correct product is
   an execution algorithm, not a strategy.
4. **The failed-breakout population** (`event="fail"`). Under-searched here relative to the
   continuation population, and structurally the place where a directional model can disagree with
   the crowd trading the same channel.

**How it fails**, ranked by likelihood: it never clears costs despite real skill (see §2 — this is
the modal outcome); the skill is the drift and the prior shift was off or mis-specified; the short
side has 7% of the sample and the "two-sided" result is one side plus noise; the walk-forward
folds leak through the label horizon; or the whole thing is the 1-in-1,072 feature found again by a
different route.

---

## 7. What to do first

1. `python3 research/dbu_dir.py` — all four self-test cases must pass.
2. On real 5-minute bars: `event="all"`, `conf=0`, `use_net=False`. That is the BVAR alone, on
   every bar, and it produces the **skill** table in about a minute. If AUC is 0.50 and the
   adjusted-edge t is inside ±2 there, the directional program is finished before it started, and
   you have learned that for the price of one command.
3. If there is skill: add the network, check the skill table improves *out of sample*, then sweep
   `conf` on research with the matched control as a gate.
4. Compare `event="all"` against `event="break"` and `event="fail"`. Whichever wins tells you
   whether you have a directional alpha, a breakout system, or a reversal system.
5. Only then look at P&L, and expect §2's gap between skill and tradeability.
